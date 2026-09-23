"""
Pruebas de integración del cliente contra un servidor stub en 127.0.0.1.

Se ejecuta la receta 13 de verdad (proceso aparte, librería `openai` real) y
el stub responde 401, 429, 404... Nada sale de la máquina.
"""

import datetime
import json

from conftest import correr, puerto_cerrado, ruta_receta

RECETA_13 = ruta_receta(13)
PUNTOS = ["--puntos", "reunion el viernes; traer laptop"]


def _entorno(servidor, **extra):
    base = {"NIM_BASE_URL": servidor.url, "NIM_REINTENTOS": "0", "NIM_TIMEOUT": "10"}
    base.update(extra)
    return base


def test_endpoint_local_sin_clave_funciona(servidor_stub):
    servidor = servidor_stub((200, "Asunto: Reunion\n\nHola equipo."))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor))
    assert resultado.returncode == 0, resultado.stderr
    assert "Asunto: Reunion" in resultado.stdout
    # NIM_BASE_URL se respeta y la receta mandó un chat normal.
    assert servidor.chats()[0]["cuerpo"]["messages"][-1]["role"] == "user"


def test_nim_api_key_viaja_como_bearer(servidor_stub):
    servidor = servidor_stub((200, "Asunto: x"))
    entorno = _entorno(servidor, NIM_API_KEY="clave-de-prueba", NVIDIA_API_KEY="nvapi-otra")
    assert correr([RECETA_13] + PUNTOS, entorno).returncode == 0
    assert servidor.chats()[0]["auth"] == "Bearer clave-de-prueba"


def test_nim_model_elige_el_modelo(servidor_stub):
    servidor = servidor_stub((200, "Asunto: x"))
    correr([RECETA_13] + PUNTOS, _entorno(servidor, NIM_MODEL="mi-modelo-local"))
    assert servidor.chats()[0]["cuerpo"]["model"] == "mi-modelo-local"


def test_regresion_401_da_mensaje_en_espanol_sin_traza(servidor_stub):
    servidor = servidor_stub((401, "Invalid API key"))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor))
    assert resultado.returncode == 1
    assert "rechazo tu clave" in resultado.stderr
    assert "Traceback" not in resultado.stdout + resultado.stderr


def test_401_con_nim_debug_muestra_la_traza(servidor_stub):
    servidor = servidor_stub((401, "Invalid API key"))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor, NIM_DEBUG="1"))
    assert resultado.returncode == 1
    assert "Traceback" in resultado.stderr


def test_regresion_429_se_reintenta_y_luego_funciona(servidor_stub):
    servidor = servidor_stub((429, "rate limit"), (429, "rate limit"), (200, "Asunto: por fin"))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor, NIM_REINTENTOS="2"))
    assert resultado.returncode == 0, resultado.stderr
    assert "Asunto: por fin" in resultado.stdout
    assert len(servidor.chats()) == 3
    # Los reintentos ya no son silenciosos.
    assert "reintento 1 de 2" in resultado.stderr and "reintento 2 de 2" in resultado.stderr


def test_429_persistente_explica_el_limite(servidor_stub):
    servidor = servidor_stub((429, "rate limit"))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor))
    assert resultado.returncode == 1
    assert "limite de peticiones" in resultado.stderr
    assert "Traceback" not in resultado.stderr
    assert len(servidor.chats()) == 1  # NIM_REINTENTOS=0


def test_404_apunta_a_nim_model(servidor_stub):
    servidor = servidor_stub((404, "model not found"))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor))
    assert resultado.returncode == 1
    assert "no encuentra el modelo" in resultado.stderr and "NIM_MODEL" in resultado.stderr


def test_400_explica_entrada_demasiado_larga(servidor_stub):
    servidor = servidor_stub((400, "maximum context length exceeded"))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor))
    assert "demasiado largo" in resultado.stderr
    assert "maximum context length exceeded" in resultado.stderr


def test_conexion_rechazada_da_mensaje_en_espanol():
    url = f"http://127.0.0.1:{puerto_cerrado()}/v1"
    resultado = correr([RECETA_13] + PUNTOS, {"NIM_BASE_URL": url, "NIM_REINTENTOS": "0"})
    assert resultado.returncode == 1
    assert "No pude conectar" in resultado.stderr
    assert "Traceback" not in resultado.stderr


def test_timeout_da_mensaje_en_espanol(servidor_stub):
    servidor = servidor_stub((200, "tarde", 4))
    resultado = correr([RECETA_13] + PUNTOS, _entorno(servidor, NIM_TIMEOUT="1"))
    assert resultado.returncode == 1
    assert "tardo mas de 1 s" in resultado.stderr


def test_sin_clave_con_nvidia_no_hace_ninguna_peticion():
    resultado = correr([RECETA_13] + PUNTOS)
    assert resultado.returncode == 1
    assert "Falta tu clave de NVIDIA NIM" in resultado.stdout
    assert "--demo" in resultado.stdout


def test_embeddings_con_otro_proveedor_no_mandan_input_type(servidor_stub, tmp_path):
    servidor = servidor_stub((200, "El plan Pro cuesta 12 USD al mes."))
    resultado = correr(
        [ruta_receta(8), "--pregunta", "Cuanto cuesta el plan Pro?", "--cache", tmp_path],
        _entorno(servidor),
    )
    assert resultado.returncode == 0, resultado.stderr
    embeddings = [p for p in servidor.peticiones if p["ruta"].endswith("/embeddings")]
    assert embeddings and all("input_type" not in p["cuerpo"] for p in embeddings)


def test_grabar_y_reproducir_da_la_misma_salida(servidor_stub, tmp_path):
    """NIM_GRABAR=1 guarda la respuesta real; NIM_DEMO=1 la reproduce idéntica."""
    servidor = servidor_stub((200, "Asunto: Viernes\n\nHola, la reunion pasa al viernes."))
    casetes = tmp_path / "casetes"
    grabando = correr(
        [RECETA_13] + PUNTOS,
        _entorno(servidor, NIM_GRABAR="1", NIM_DEMO_DIR=str(casetes), NIM_MODEL="stub-model"),
    )
    assert grabando.returncode == 0, grabando.stderr
    casete = json.loads((casetes / "13_email_profesional.json").read_text(encoding="utf-8"))
    entrada = casete["entradas"][0]
    assert entrada["origen"] == f"grabada de stub-model el {datetime.date.today().isoformat()}"
    assert entrada["respuesta"].startswith("Asunto: Viernes")

    reproduciendo = correr([RECETA_13] + PUNTOS, {"NIM_DEMO": "1", "NIM_DEMO_DIR": str(casetes)})
    assert reproduciendo.returncode == 0, reproduciendo.stderr
    assert reproduciendo.stdout == grabando.stdout
    assert len(servidor.chats()) == 1  # la reproducción no tocó el servidor


def test_grabar_rag_usa_los_mismos_fragmentos_que_la_demo(servidor_stub, tmp_path):
    """Al grabar la 08, la recuperación es la de la demo: la grabación se reproduce."""
    servidor = servidor_stub((200, "El plan Pro cuesta 12 USD al mes (02_precios.md)."))
    casetes = tmp_path / "casetes"
    argumentos = [ruta_receta(8), "--pregunta", "Cuanto cuesta el plan Pro?", "--sin-cache"]
    grabando = correr(argumentos, _entorno(servidor, NIM_GRABAR="1", NIM_DEMO_DIR=str(casetes)))
    assert grabando.returncode == 0, grabando.stderr
    assert not [p for p in servidor.peticiones if p["ruta"].endswith("/embeddings")]
    reproduciendo = correr(argumentos, {"NIM_DEMO": "1", "NIM_DEMO_DIR": str(casetes)})
    assert reproduciendo.returncode == 0, reproduciendo.stderr
    assert reproduciendo.stdout == grabando.stdout
