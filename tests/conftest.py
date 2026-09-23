"""
Utilidades compartidas por las pruebas.

Todo corre SIN internet y SIN clave:
  - `cliente_falso` sustituye al cliente de la API por uno que devuelve las
    respuestas que le indiques y apunta cada llamada (para contarlas).
  - `servidor_stub` levanta un servidor HTTP compatible con OpenAI en
    127.0.0.1 (puerto aleatorio) que responde lo que le pidas: 200, 401,
    429... Así se prueban los errores reales de la librería `openai`.
  - `correr` ejecuta una receta como lo haría una persona, en un proceso
    aparte, con un entorno limpio (sin claves ni variables NIM_*).
"""

import copy
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Antes de importar comun.nim: nada de .env del usuario ni variables heredadas.
os.environ["NIM_IGNORAR_DOTENV"] = "1"
_VARIABLES = (
    "NIM_DEMO", "NIM_GRABAR", "NIM_BASE_URL", "NIM_API_KEY", "NVIDIA_API_KEY",
    "NIM_DEMO_DIR", "NIM_CASETE", "NIM_DEBUG", "NIM_REINTENTOS", "NIM_TIMEOUT",
    "NIM_MODEL", "NIM_VISION_MODEL", "NIM_EMBED_MODEL", "OPENAI_API_KEY",
)
for _variable in _VARIABLES:
    os.environ.pop(_variable, None)

from comun import demo, nim  # noqa: E402

_MODULOS = {}


def cargar_receta(numero):
    """Importa recetas/NN_*.py como módulo (sus nombres empiezan por número)."""
    numero = str(numero).zfill(2)
    if numero not in _MODULOS:
        ruta = next((RAIZ / "recetas").glob(f"{numero}_*.py"))
        spec = importlib.util.spec_from_file_location(f"receta{numero}", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _MODULOS[numero] = modulo
    return _MODULOS[numero]


@pytest.fixture
def receta():
    return cargar_receta


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Cada prueba empieza sin modo demo, sin claves y sin cliente creado."""
    for variable in _VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(nim, "_cliente", None)
    yield


# --------------------------------------------------------------------------- #
# Cliente falso (en el mismo proceso)                                          #
# --------------------------------------------------------------------------- #


class FakeCliente:
    """
    Imita al cliente de `openai`. Cada respuesta puede ser un texto, None
    (simula content=None) o una función que recibe los mensajes.
    """

    def __init__(self, respuestas=()):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.llamadas_embeddings = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.embeddings = SimpleNamespace(create=self._embeddings)

    def _chat(self, **parametros):
        # Copia: el agente sigue añadiendo mensajes a la misma lista después.
        parametros = copy.deepcopy(parametros)
        self.llamadas.append(parametros)
        if not self.respuestas:
            raise AssertionError("El cliente falso se quedo sin respuestas")
        respuesta = self.respuestas.pop(0)
        if callable(respuesta):
            respuesta = respuesta(parametros["messages"])
        return demo._respuesta_chat(respuesta)

    def _embeddings(self, model=None, input=None, **parametros):
        textos = [input] if isinstance(input, str) else list(input)
        tipo = (parametros.get("extra_body") or {}).get("input_type")
        self.llamadas_embeddings.append({"textos": textos, "input_type": tipo, **parametros})
        return demo.embeddings_locales(textos)

    def embeddings_de(self, tipo):
        return [c for c in self.llamadas_embeddings if c["input_type"] == tipo]


@pytest.fixture
def cliente_falso(monkeypatch):
    def instalar(*respuestas):
        falso = FakeCliente(respuestas)
        monkeypatch.setattr(nim, "_cliente", falso)
        return falso

    return instalar


# --------------------------------------------------------------------------- #
# Servidor stub compatible con OpenAI (en 127.0.0.1)                           #
# --------------------------------------------------------------------------- #


def _cuerpo_chat(texto):
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": "stub-model",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": texto}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _cuerpo_embeddings(textos):
    return {
        "object": "list",
        "model": "stub-embed",
        "data": [
            {"object": "embedding", "index": i, "embedding": demo.vectorizar(t, 64)}
            for i, t in enumerate(textos)
        ],
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


class ServidorStub:
    """
    Servidor HTTP mínimo. `guion` es una lista de respuestas que se consumen en
    orden (la última se repite): (codigo, texto) o (codigo, texto, segundos de
    espera). Para /embeddings siempre responde 200 con vectores locales.
    """

    def __init__(self, guion):
        self.guion = list(guion)
        self.peticiones = []
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self):
                largo = int(self.headers.get("Content-Length", 0))
                cuerpo = json.loads(self.rfile.read(largo) or b"{}")
                servidor.peticiones.append(
                    {"ruta": self.path, "cuerpo": cuerpo, "auth": self.headers.get("Authorization")}
                )
                if self.path.endswith("/embeddings"):
                    textos = cuerpo.get("input")
                    textos = [textos] if isinstance(textos, str) else textos
                    return self._responder(200, _cuerpo_embeddings(textos))
                paso = servidor.guion.pop(0) if len(servidor.guion) > 1 else servidor.guion[0]
                codigo, texto = paso[0], paso[1]
                if len(paso) > 2:
                    time.sleep(paso[2])
                if codigo == 200:
                    return self._responder(200, _cuerpo_chat(texto))
                return self._responder(codigo, {"error": {"message": texto, "type": "stub"}})

            def _responder(self, codigo, datos):
                crudo = json.dumps(datos).encode("utf-8")
                try:
                    self.send_response(codigo)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(crudo)))
                    if codigo == 429:
                        self.send_header("retry-after-ms", "20")
                    self.end_headers()
                    self.wfile.write(crudo)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # el cliente se fue (p. ej. por timeout): no es un error del stub

            def log_message(self, *args):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.http.daemon_threads = True
        puerto = self.http.server_address[1]
        assert puerto not in (8765, 9876)
        self.url = f"http://127.0.0.1:{puerto}/v1"
        self.hilo = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.hilo.start()

    def chats(self):
        return [p for p in self.peticiones if p["ruta"].endswith("/chat/completions")]

    def cerrar(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def servidor_stub():
    creados = []

    def crear(*guion):
        servidor = ServidorStub(guion or [(200, "ok")])
        creados.append(servidor)
        return servidor

    yield crear
    for servidor in creados:
        servidor.cerrar()


def puerto_cerrado():
    """Un puerto de 127.0.0.1 donde no escucha nadie (conexión rechazada)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------------------------- #
# Ejecutar recetas como procesos                                               #
# --------------------------------------------------------------------------- #


def correr(argumentos, entorno=None, timeout=90):
    """Ejecuta `python <argumentos>` desde la raíz con un entorno limpio."""
    limpio = {
        k: v for k, v in os.environ.items() if k not in _VARIABLES and not k.startswith("NIM_")
    }
    limpio.update(
        NIM_IGNORAR_DOTENV="1",
        PYTHONIOENCODING="utf-8",
        NO_PROXY="127.0.0.1,localhost",
        no_proxy="127.0.0.1,localhost",
    )
    limpio.update(entorno or {})
    return subprocess.run(
        [sys.executable] + [str(a) for a in argumentos],
        cwd=RAIZ,
        env=limpio,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def ruta_receta(numero):
    return next((RAIZ / "recetas").glob(f"{str(numero).zfill(2)}_*.py"))
