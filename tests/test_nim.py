"""Pruebas del cliente compartido `comun/nim.py` (en el mismo proceso)."""

import argparse

import pytest

from comun import nim

# --------------------------------------------------------------------------- #
# extraer_json                                                                 #
# --------------------------------------------------------------------------- #


def test_extraer_json_objeto_directo():
    assert nim.extraer_json('{"a": 1}') == {"a": 1}


def test_extraer_json_con_valla_de_codigo():
    assert nim.extraer_json('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}


def test_extraer_json_valla_despues_de_una_frase():
    texto = 'Claro, aqui esta:\n```json\n{"total": 3}\n```\nAvisame si necesitas algo.'
    assert nim.extraer_json(texto) == {"total": 3}


def test_regresion_extraer_json_lista_de_un_elemento_tras_una_frase():
    # Antes devolvía el objeto interior {'id': 1, ...} en vez de la lista.
    resultado = nim.extraer_json('Aqui tienes:\n[{"id": 1, "nombre": "Ana"}]')
    assert resultado == [{"id": 1, "nombre": "Ana"}]


def test_extraer_json_objeto_tras_una_frase_y_con_texto_despues():
    texto = 'Resultado: {"clave": {"anidado": [1, {"x": 2}]}} y eso es todo.'
    assert nim.extraer_json(texto) == {"clave": {"anidado": [1, {"x": 2}]}}


def test_extraer_json_no_se_confunde_con_corchetes_de_la_prosa():
    texto = 'Nota [1]: el objeto es {"a": 1, "b": 2, "c": 3}'
    assert nim.extraer_json(texto) == {"a": 1, "b": 2, "c": 3}


def test_extraer_json_esperado_lista_desenvuelve_objeto():
    texto = '{"clientes": [{"id": 1}, {"id": 2}]}'
    assert nim.extraer_json(texto, esperado=list) == [{"id": 1}, {"id": 2}]


def test_extraer_json_esperado_objeto_con_lista_falla():
    with pytest.raises(nim.RespuestaInvalida):
        nim.extraer_json("[1, 2, 3]", esperado=dict)


@pytest.mark.parametrize("texto", ["", "no hay json aqui", "{roto: sin comillas", None])
def test_extraer_json_invalido_lanza_value_error(texto):
    with pytest.raises(ValueError):
        nim.extraer_json(texto)


# --------------------------------------------------------------------------- #
# chat / vision / embeddings                                                   #
# --------------------------------------------------------------------------- #


def test_regresion_chat_con_content_none_da_error_claro(cliente_falso):
    # Antes: AttributeError: 'NoneType' object has no attribute 'strip'.
    cliente_falso(None)
    with pytest.raises(nim.RespuestaVacia) as error:
        nim.chat("hola")
    assert "vacia" in str(error.value)


def test_chat_arma_los_mensajes_y_pasa_stop(cliente_falso):
    falso = cliente_falso("  respuesta  ")
    assert nim.chat("pregunta", sistema="reglas", stop=["Observacion:"]) == "respuesta"
    llamada = falso.llamadas[0]
    assert llamada["messages"] == [
        {"role": "system", "content": "reglas"},
        {"role": "user", "content": "pregunta"},
    ]
    assert llamada["stop"] == ["Observacion:"]
    assert llamada["model"] == nim.MODELO_CHAT


def test_chat_sin_stop_no_envia_el_parametro(cliente_falso):
    falso = cliente_falso("ok")
    nim.chat("hola")
    assert "stop" not in falso.llamadas[0]


def test_vision_envia_la_imagen_como_data_url(cliente_falso):
    falso = cliente_falso("una taza roja")
    assert nim.vision("describe", nim.ruta_datos("producto_ejemplo.png")) == "una taza roja"
    contenido = falso.llamadas[0]["messages"][0]["content"]
    assert contenido[1]["image_url"]["url"].startswith("data:image/png;base64,iVBOR")


def test_vision_con_imagen_inexistente():
    with pytest.raises(FileNotFoundError):
        nim.vision("describe", "no_existe.png")


def test_embeddings_por_lotes_y_con_parametros_de_nvidia(cliente_falso):
    falso = cliente_falso()
    vectores = nim.embeddings([f"texto {i}" for i in range(70)], input_type="query")
    assert len(vectores) == 70
    assert [len(c["textos"]) for c in falso.llamadas_embeddings] == [32, 32, 6]
    assert all(c["input_type"] == "query" for c in falso.llamadas_embeddings)


def test_embeddings_en_otro_proveedor_no_envia_parametros_de_nvidia(cliente_falso, monkeypatch):
    monkeypatch.setenv("NIM_BASE_URL", "https://api.openai.com/v1")
    falso = cliente_falso()
    nim.embeddings("hola")
    assert "extra_body" not in falso.llamadas_embeddings[0]


# --------------------------------------------------------------------------- #
# Configuración                                                                #
# --------------------------------------------------------------------------- #


def test_base_url_por_defecto_y_por_variable(monkeypatch):
    assert nim.base_url() == nim.BASE_URL_NVIDIA
    monkeypatch.setenv("NIM_BASE_URL", "http://localhost:11434/v1")
    assert nim.base_url() == "http://localhost:11434/v1"


@pytest.mark.parametrize(
    "url, local",
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:8000/v1", True),
        ("https://integrate.api.nvidia.com/v1", False),
        ("https://api.groq.com/openai/v1", False),
    ],
)
def test_es_local(url, local):
    assert nim.es_local(url) is local


def test_clave_nim_api_key_tiene_prioridad(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-de-nvidia")
    monkeypatch.setenv("NIM_API_KEY", "clave-generica")
    assert nim._obtener_clave() == "clave-generica"


def test_endpoint_local_no_necesita_clave(monkeypatch):
    monkeypatch.setenv("NIM_BASE_URL", "http://localhost:11434/v1")
    assert nim._obtener_clave() == "sin-clave-local"


def test_sin_clave_explica_como_conseguirla_y_menciona_la_demo(monkeypatch, capsys):
    with pytest.raises(SystemExit) as salida:
        nim._obtener_clave()
    assert salida.value.code == 1
    texto = capsys.readouterr().out
    assert "build.nvidia.com" in texto and "--demo" in texto


def test_clave_de_ejemplo_se_detecta(monkeypatch, capsys):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-XXXXXXXXXXXXXXXXXXXXXXXX")
    with pytest.raises(SystemExit):
        nim._obtener_clave()
    assert "clave de ejemplo" in capsys.readouterr().out


def test_otro_proveedor_sin_clave_pide_nim_api_key(monkeypatch, capsys):
    monkeypatch.setenv("NIM_BASE_URL", "https://api.groq.com/openai/v1")
    with pytest.raises(SystemExit):
        nim._obtener_clave()
    assert "NIM_API_KEY" in capsys.readouterr().out


def test_reintentos_y_timeout_desde_el_entorno(monkeypatch, capsys):
    assert (nim.reintentos(), nim.timeout()) == (2, 120)
    monkeypatch.setenv("NIM_REINTENTOS", "5")
    monkeypatch.setenv("NIM_TIMEOUT", "0")
    assert (nim.reintentos(), nim.timeout()) == (5, 1)
    monkeypatch.setenv("NIM_REINTENTOS", "muchos")
    assert nim.reintentos() == 2
    assert "no es un numero" in capsys.readouterr().err


def test_opcion_demo_del_parser_activa_el_modo_demo(monkeypatch):
    monkeypatch.setenv("NIM_DEMO", "0")  # para que monkeypatch lo restaure al terminar
    assert not nim.modo_demo()
    parser = nim.nuevo_parser("prueba")
    parser.add_argument("--x", default=1)
    args = parser.parse_args(["--demo"])
    assert nim.modo_demo()
    assert not hasattr(args, "demo")
    assert isinstance(parser, argparse.ArgumentParser)


# --------------------------------------------------------------------------- #
# Errores en español                                                           #
# --------------------------------------------------------------------------- #


def _error_http(clase, codigo, mensaje="detalle del servidor"):
    import httpx2

    peticion = httpx2.Request("POST", "http://127.0.0.1/v1/chat/completions")
    respuesta = httpx2.Response(codigo, request=peticion)
    return clase(mensaje, response=respuesta, body={"error": {"message": mensaje}})


@pytest.mark.parametrize(
    "nombre, codigo, pista",
    [
        ("AuthenticationError", 401, "rechazo tu clave"),
        ("PermissionDeniedError", 403, "permiso"),
        ("NotFoundError", 404, "no encuentra el modelo"),
        ("RateLimitError", 429, "limite de peticiones"),
        ("BadRequestError", 400, "demasiado largo"),
        ("InternalServerError", 503, "Suele ser temporal"),
    ],
)
def test_describir_error_http(nombre, codigo, pista):
    openai = pytest.importorskip("openai")
    pytest.importorskip("httpx2")
    texto = nim.describir_error(_error_http(getattr(openai, nombre), codigo))
    assert pista in texto
    assert "detalle del servidor" in texto


def test_describir_error_conexion_y_timeout():
    openai = pytest.importorskip("openai")
    httpx2 = pytest.importorskip("httpx2")
    peticion = httpx2.Request("POST", "http://127.0.0.1/v1")
    assert "No pude conectar" in nim.describir_error(openai.APIConnectionError(request=peticion))
    assert "tardo mas de" in nim.describir_error(openai.APITimeoutError(request=peticion))


def test_describir_error_json_invalido_y_desconocido():
    assert "JSON esperado" in nim.describir_error(nim.RespuestaInvalida("x"))
    assert "NIM_DEBUG=1" in nim.describir_error(KeyError("rara"))


def test_ejecutar_convierte_la_excepcion_en_mensaje_y_codigo_1(capsys):
    def main():
        raise nim.RespuestaVacia("El modelo devolvio una respuesta vacia.")

    with pytest.raises(SystemExit) as salida:
        nim.ejecutar(main)
    assert salida.value.code == 1
    assert "respuesta vacia" in capsys.readouterr().err


def test_ejecutar_con_nim_debug_deja_ver_la_excepcion(monkeypatch):
    monkeypatch.setenv("NIM_DEBUG", "1")

    def main():
        raise KeyError("depurame")

    with pytest.raises(KeyError):
        nim.ejecutar(main)
