"""Pruebas de `comun/formatos.py` y del modo demo (`comun/demo.py`)."""

import json
import math

import pytest

from comun import demo, nim
from comun.formatos import normalizar_texto, parsear_monto, parsear_numero, parsear_porcentaje

# --------------------------------------------------------------------------- #
# Números al estilo LATAM                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "texto, valor",
    [
        ("-84,50", -84.5),
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("$ -12.30", -12.3),
        ("-$12.30", -12.3),
        ("(45.00)", -45.0),
        ("84.50-", -84.5),
        ("B/. 1.500,00", 1500.0),
        ("USD 19.99", 19.99),
        ("1 234,56", 1234.56),
        ("2100.00", 2100.0),
        ("-1.234", -1234.0),
        ("0.500", 0.5),
        ("12,500", 12500.0),
        ("1.234.567,89", 1234567.89),
        ("", 0.0),
        (19.99, 19.99),
    ],
)
def test_parsear_monto(texto, valor):
    assert parsear_monto(texto) == pytest.approx(valor)


@pytest.mark.parametrize("texto", ["abc", "1,23,456", "--", "$"])
def test_parsear_monto_invalido(texto):
    with pytest.raises(ValueError):
        parsear_monto(texto)


def test_parsear_numero_y_porcentaje():
    assert parsear_numero(None) is None and parsear_numero("x") is None
    assert parsear_numero("19.99") == 19.99
    assert parsear_porcentaje("60%") == 60.0 and parsear_porcentaje("60,5 %") == 60.5


def test_normalizar_texto():
    assert normalizar_texto("  Acción   FINAL ") == "accion final"


# --------------------------------------------------------------------------- #
# Vectorizador local                                                           #
# --------------------------------------------------------------------------- #


def test_vectorizar_es_determinista_y_normalizado():
    a = demo.vectorizar("Cuanto cuesta el plan Pro?")
    assert a == demo.vectorizar("Cuanto cuesta el plan Pro?")
    assert len(a) == demo.DIMENSION
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)


def test_vectorizar_acerca_textos_parecidos():
    def coseno(x, y):
        return sum(i * j for i, j in zip(demo.vectorizar(x), demo.vectorizar(y)))

    pregunta = "precio del plan pro"
    assert coseno(pregunta, "Plan Pro: 12 USD al mes, precios") > coseno(
        pregunta, "Integracion con Zapier y webhooks"
    )


def test_vectorizar_ignora_tildes():
    assert demo.vectorizar("Facturación rápida") == demo.vectorizar("facturacion rapida")


# --------------------------------------------------------------------------- #
# Casetes: clave, reproducción y grabación                                     #
# --------------------------------------------------------------------------- #


def test_clave_estable_e_independiente_del_salto_de_linea():
    mensajes = [{"role": "user", "content": "hola\nmundo"}]
    windows = [{"role": "user", "content": "hola\r\nmundo"}]
    assert demo.clave_mensajes(mensajes) == demo.clave_mensajes(windows)
    assert demo.clave_mensajes(mensajes) != demo.clave_mensajes([{"role": "user", "content": "hola"}])


def test_aplicar_stop():
    assert demo.aplicar_stop("a\nObservacion: 9\nb", ["Observacion:"]) == "a\n"
    assert demo.aplicar_stop("sin parada", ["X:"]) == "sin parada"


def test_cliente_demo_reproduce_y_nunca_inventa(tmp_path):
    mensajes = [{"role": "user", "content": "hola"}]
    demo.guardar_entrada(
        "prueba",
        {"clave": demo.clave_mensajes(mensajes), "origen": "redactada a mano", "respuesta": "grabada"},
        tmp_path,
    )
    cliente = demo.ClienteDemo(tmp_path)
    respuesta = cliente.chat.completions.create(model="x", messages=mensajes)
    assert respuesta.choices[0].message.content == "grabada"
    with pytest.raises(demo.SinGrabacion) as error:
        cliente.chat.completions.create(model="x", messages=[{"role": "user", "content": "otra"}])
    assert "no hay respuesta grabada" in str(error.value)


def test_grabador_guarda_y_reemplaza_por_clave(tmp_path, cliente_falso):
    real = cliente_falso("primera", "segunda")
    grabador = demo.ClienteGrabador(real, carpeta=tmp_path, casete="receta_x")
    mensajes = [{"role": "user", "content": "hola"}]
    grabador.chat.completions.create(model="modelo-real", messages=mensajes)
    grabador.chat.completions.create(model="modelo-real", messages=mensajes)
    datos = json.loads((tmp_path / "receta_x.json").read_text(encoding="utf-8"))
    assert len(datos["entradas"]) == 1  # misma clave: se reemplaza, no se duplica
    assert datos["entradas"][0]["respuesta"] == "segunda"
    assert datos["entradas"][0]["origen"].startswith("grabada de modelo-real el ")


def test_casetes_del_repo_son_honestos_y_validos():
    casetes = sorted(nim.ruta_datos("demo").glob("*.json"))
    assert len(casetes) == 14  # todas las recetas que llaman al modelo (la 03 no)
    for archivo in casetes:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        assert datos["entradas"], archivo.name
        for entrada in datos["entradas"]:
            assert entrada["origen"] == "redactada a mano" or entrada["origen"].startswith("grabada de ")
            assert len(entrada["clave"]) == 32 and entrada["respuesta"].strip()


def test_modo_demo_por_variable_usa_el_cliente_demo(monkeypatch):
    monkeypatch.setenv("NIM_DEMO", "1")
    assert isinstance(nim.cliente(), demo.ClienteDemo)
    assert nim.id_embeddings() == demo.ID_VECTORES
