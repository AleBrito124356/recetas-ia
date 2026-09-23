"""
Modo demo: grabar y reproducir respuestas del modelo ("record & replay").

¿Para qué sirve?
----------------
1. Para ver las 15 recetas funcionando nada más clonar el repositorio, sin
   crear cuenta, sin clave y sin internet: `python recetas.py demo`.
2. Para aprender la forma estándar de PROBAR aplicaciones con modelos de
   lenguaje sin gastar créditos: se graba una vez la respuesta real y las
   pruebas la reproducen siempre igual.

Cómo funciona
-------------
Cada receta, en modo demo, habla con `ClienteDemo` en vez de con la API. Este
cliente tiene la misma "forma" que el de la librería `openai`
(`.chat.completions.create(...)` y `.embeddings.create(...)`), así que las
recetas no se enteran del cambio.

- Chat: la respuesta se busca en los "casetes" de `datos/demo/*.json` usando
  como clave un hash (SHA-256) de los mensajes enviados. Si los mensajes
  cambian (otro prompt, otros datos), no hay respuesta grabada y se avisa con
  un error claro: el modo demo NUNCA inventa contenido.
- Embeddings: se calculan en local con un vectorizador de n-gramas de
  caracteres (sin red y determinista). No es semántico como un modelo real,
  pero basta para que la búsqueda de la receta 08 funcione de verdad.

Cada respuesta grabada lleva un campo `origen` honesto: "redactada a mano"
(las que vienen con el repo para los datos de ejemplo) o
"grabada de <modelo> el <fecha>" (las que grabas tú con NIM_GRABAR=1).

Variables de entorno
--------------------
  NIM_DEMO=1       usar ClienteDemo (lo activa también la opción --demo).
  NIM_GRABAR=1     usar el modelo real y guardar sus respuestas en el casete.
  NIM_DEMO_DIR     carpeta de casetes (por defecto datos/demo/).
  NIM_CASETE       nombre del casete donde grabar (por defecto, el del script).
"""

import hashlib
import json
import math
import os
import re
import sys
import unicodedata
import zlib
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from .nim import RAIZ, ErrorNIM

DIMENSION = 1024  # con menos, los choques del hash meten ruido en la búsqueda
# Identificador de los vectores locales: la caché de la receta 08 lo usa para no
# mezclar nunca estos vectores con los de un modelo real.
ID_VECTORES = f"demo|ngramas-hash-v1|{DIMENSION}"


class SinGrabacion(ErrorNIM):
    """El modo demo no tiene respuesta grabada para esta petición."""


# --------------------------------------------------------------------------- #
# Casetes                                                                      #
# --------------------------------------------------------------------------- #


def carpeta_casetes():
    """Carpeta con los casetes: NIM_DEMO_DIR o datos/demo/."""
    return Path(os.getenv("NIM_DEMO_DIR", "").strip() or RAIZ / "datos" / "demo")


def nombre_casete():
    """Casete donde grabar: NIM_CASETE o el nombre del script (05_extraer_facturas)."""
    nombre = os.getenv("NIM_CASETE", "").strip()
    if not nombre:
        nombre = Path(sys.argv[0] or "").stem
    return re.sub(r"[^A-Za-z0-9_.-]", "_", nombre) or "varios"


def _sin_retornos(valor):
    """Normaliza saltos de línea (\\r\\n -> \\n) para que el hash no dependa del SO."""
    if isinstance(valor, str):
        return valor.replace("\r\n", "\n")
    if isinstance(valor, list):
        return [_sin_retornos(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _sin_retornos(v) for k, v in valor.items()}
    return valor


def clave_mensajes(mensajes):
    """
    Huella estable de una conversación: SHA-256 del JSON canónico de los
    mensajes. Los mismos mensajes dan siempre la misma clave, en cualquier
    máquina; un solo carácter distinto da otra clave.
    """
    canonico = json.dumps(
        _sin_retornos(mensajes), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:32]


def _resumen_peticion(mensajes):
    """Primeras palabras del último mensaje del usuario, para leer el casete."""
    for mensaje in reversed(mensajes or []):
        if mensaje.get("role") != "user":
            continue
        contenido = mensaje.get("content")
        if isinstance(contenido, list):  # visión: [{"type": "text"...}, imagen]
            contenido = " ".join(
                p.get("text", "") for p in contenido if isinstance(p, dict)
            ) + " [+ imagen]"
        texto = " ".join(str(contenido).split())
        return texto[:160] + ("..." if len(texto) > 160 else "")
    return ""


def cargar_casetes(carpeta=None):
    """Lee todos los casetes de la carpeta y devuelve {clave: entrada}."""
    carpeta = Path(carpeta) if carpeta else carpeta_casetes()
    entradas = {}
    if carpeta.is_dir():
        for archivo in sorted(carpeta.glob("*.json")):
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            for entrada in datos.get("entradas", []):
                entradas[entrada["clave"]] = dict(entrada, casete=archivo.stem)
    return entradas


def guardar_entrada(nombre, entrada, carpeta=None):
    """Añade (o reemplaza, si la clave ya existe) una respuesta en un casete."""
    carpeta = Path(carpeta) if carpeta else carpeta_casetes()
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{nombre}.json"
    if ruta.exists():
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    else:
        datos = {
            "receta": nombre,
            "nota": "Respuestas para el modo demo (NIM_DEMO=1). La clave es el "
            "SHA-256 de los mensajes enviados; 'origen' dice de donde sale cada respuesta.",
            "entradas": [],
        }
    otras = [e for e in datos["entradas"] if e.get("clave") != entrada["clave"]]
    datos["entradas"] = otras + [entrada]
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return ruta


def aplicar_stop(texto, stop):
    """Corta el texto en la primera secuencia de parada, como haría la API."""
    if not stop:
        return texto
    secuencias = [stop] if isinstance(stop, str) else list(stop)
    cortes = [texto.find(s) for s in secuencias if s and s in texto]
    return texto[: min(cortes)] if cortes else texto


def _respuesta_chat(contenido, motivo="stop"):
    """Objeto con la misma forma que la respuesta de la librería openai."""
    mensaje = SimpleNamespace(role="assistant", content=contenido)
    return SimpleNamespace(choices=[SimpleNamespace(index=0, message=mensaje, finish_reason=motivo)])


# --------------------------------------------------------------------------- #
# Embeddings locales                                                           #
# --------------------------------------------------------------------------- #

_PALABRA = re.compile(r"[a-z0-9]+")
# Palabras muy frecuentes que no aportan tema (incluye interrogativos: en una
# pregunta como "Cuanto cuesta..." lo importante es lo que viene después).
_VACIAS = set(
    "a al algo como con cual cuales cuando cuanto cuanta cuantos cuantas de del "
    "donde e el ella en es esta este esto hay la las le lo los mas me mi o para "
    "pero por que quien se si sin sobre su sus te tu un una uno y ya yo".split()
)


def _normalizar(texto):
    """Minúsculas y sin tildes: 'Cuánto' y 'cuanto' deben parecerse."""
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def vectorizar(texto, dimension=DIMENSION):
    """
    Convierte un texto en un vector de `dimension` números, sin red.

    Técnica: "hashing trick" sobre palabras y n-gramas de caracteres (trozos de
    3 y 4 letras). Cada rasgo se asigna a una posición del vector con un hash
    estable (crc32) y suma allí su peso. Textos que comparten palabras o raíces
    ("precio", "precios") comparten posiciones y quedan cerca. El vector se
    normaliza a longitud 1, como los de un modelo de embeddings real.
    """
    palabras = [p for p in _PALABRA.findall(_normalizar(texto)) if p not in _VACIAS]
    rasgos = Counter()
    for palabra in palabras:
        rasgos["p:" + palabra] += 2  # la palabra completa pesa más que sus trozos
        envuelta = f" {palabra} "
        for n in (3, 4):
            for i in range(len(envuelta) - n + 1):
                rasgos[f"{n}:{envuelta[i:i + n]}"] += 1

    vector = [0.0] * dimension
    for rasgo, cuenta in rasgos.items():
        h = zlib.crc32(rasgo.encode("utf-8"))
        signo = 1.0 if (h >> 31) & 1 else -1.0
        vector[h % dimension] += signo * (1.0 + math.log(cuenta))

    norma = math.sqrt(sum(x * x for x in vector))
    return [x / norma for x in vector] if norma else vector


def embeddings_locales(textos):
    """Respuesta con la forma de `embeddings.create` usando `vectorizar`."""
    textos = [textos] if isinstance(textos, str) else list(textos or [])
    datos = [SimpleNamespace(index=i, embedding=vectorizar(t)) for i, t in enumerate(textos)]
    return SimpleNamespace(data=datos, model=ID_VECTORES)


# --------------------------------------------------------------------------- #
# Clientes                                                                     #
# --------------------------------------------------------------------------- #


class ClienteDemo:
    """Imita al cliente de `openai` reproduciendo respuestas grabadas."""

    def __init__(self, carpeta=None):
        self.carpeta = Path(carpeta) if carpeta else carpeta_casetes()
        self.entradas = cargar_casetes(self.carpeta)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.embeddings = SimpleNamespace(create=self._embeddings)
        self._avisados = set()

    def _chat(self, model=None, messages=None, stop=None, **_):
        clave = clave_mensajes(messages)
        entrada = self.entradas.get(clave)
        if entrada is None:
            raise SinGrabacion(
                "Modo demo: no hay respuesta grabada para esta entrada.\n"
                f"(peticion: \"{_resumen_peticion(messages)[:90]}\")\n\n"
                f"El modo demo solo reproduce los ejemplos grabados en {self.carpeta}\n"
                "con los datos y argumentos por defecto de cada receta. Para usar\n"
                "tus propios datos quita --demo / NIM_DEMO y usa una clave real.\n"
                "Para grabar respuestas nuevas: NIM_GRABAR=1 con una clave real."
            )
        origen = entrada.get("origen", "desconocido")
        if origen not in self._avisados:
            self._avisados.add(origen)
            print(
                f"[modo demo] respuesta pregrabada (origen: {origen}); no es el modelo en vivo.",
                file=sys.stderr,
            )
        return _respuesta_chat(aplicar_stop(entrada["respuesta"], stop))

    def _embeddings(self, model=None, input=None, **_):
        return embeddings_locales(input)


class ClienteGrabador:
    """
    Envuelve al cliente real y guarda cada respuesta de chat en un casete.

    Los embeddings se calculan con el mismo vectorizador local de la demo: así
    la receta 08 recupera exactamente los mismos fragmentos al grabar y al
    reproducir, y la respuesta grabada vuelve a encontrarse por su clave.
    """

    def __init__(self, real, carpeta=None, casete=None):
        self.real = real
        self.carpeta = Path(carpeta) if carpeta else carpeta_casetes()
        self.casete = casete or nombre_casete()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.embeddings = SimpleNamespace(create=lambda model=None, input=None, **_: embeddings_locales(input))

    def _chat(self, **parametros):
        respuesta = self.real.chat.completions.create(**parametros)
        opciones = getattr(respuesta, "choices", None) or []
        contenido = getattr(opciones[0].message, "content", None) if opciones else None
        if contenido:
            modelo = getattr(respuesta, "model", None) or parametros.get("model")
            ruta = guardar_entrada(
                self.casete,
                {
                    "clave": clave_mensajes(parametros.get("messages")),
                    "origen": f"grabada de {modelo} el {date.today().isoformat()}",
                    "peticion": _resumen_peticion(parametros.get("messages")),
                    "respuesta": contenido,
                },
                self.carpeta,
            )
            print(f"[grabando] respuesta guardada en {ruta}", file=sys.stderr)
        return respuesta
