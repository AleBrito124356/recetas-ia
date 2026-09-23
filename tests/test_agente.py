"""Receta 15 - agente ReAct: parser, defensa contra observaciones inventadas y calculadora."""

import time

import pytest

# --------------------------------------------------------------------------- #
# Parser                                                                       #
# --------------------------------------------------------------------------- #


def test_regresion_15_etiquetas_con_tilde(receta):
    # Antes: {'Pensamiento': 'x', 'Entrada': '145*32'} (sin Accion).
    campos = receta(15).parsear_respuesta("Pensamiento: x\nAcción: calcular\nEntrada: 145*32")
    assert campos == {"Pensamiento": "x", "Accion": "calcular", "Entrada": "145*32"}


def test_regresion_15_respuesta_final_de_varias_lineas(receta):
    # Antes: se quedaba solo con 'Son 4640.'.
    campos = receta(15).parsear_respuesta("Respuesta final: Son 4640.\nAdemas, tiene 4 cifras.")
    assert campos["Respuesta final"] == "Son 4640.\nAdemas, tiene 4 cifras."


def test_15_etiquetas_en_mayusculas_y_con_markdown(receta):
    campos = receta(15).parsear_respuesta("**ACCIÓN:** `calcular`\n**Entrada**: 2+2")
    assert campos["Entrada"] == "2+2"
    assert receta(15)._nombre_herramienta(campos["Accion"]) == "calcular"


def test_15_todo_tras_una_observacion_inventada_se_descarta(receta):
    r15 = receta(15)
    salida = "Pensamiento: calculo\nAccion: calcular\nEntrada: 145 * 32\nObservación: 9999\nRespuesta final: 9999"
    assert "Respuesta final" not in r15.parsear_respuesta(salida)
    assert r15.recortar_en_observacion(salida).endswith("Entrada: 145 * 32")


@pytest.mark.parametrize("texto", ["calcular", "`calcular`", "Calcular()", " 'calcular' ", "CALCULAR"])
def test_15_nombre_de_herramienta_normalizado(receta, texto):
    assert receta(15)._nombre_herramienta(texto) == "calcular"


# --------------------------------------------------------------------------- #
# Bucle del agente                                                             #
# --------------------------------------------------------------------------- #


def test_regresion_15_no_se_cree_una_observacion_inventada(receta, cliente_falso, capsys):
    # Antes devolvía '145 * 32 = 9999' sin haber ejecutado la herramienta.
    falso = cliente_falso(
        "Pensamiento: calculo\nAccion: calcular\nEntrada: 145 * 32\nObservacion: 9999\n"
        "Respuesta final: 145 * 32 = 9999",
        "Pensamiento: ya tengo el dato\nRespuesta final: 145 * 32 = 4640",
    )
    respuesta = receta(15).ejecutar_agente("Cuanto es 145 * 32?")
    assert respuesta == "145 * 32 = 4640"
    salida = capsys.readouterr().out
    assert "Accion: calcular('145 * 32') -> 4640" in salida
    # La observación que ve el modelo es la real, y su historial no guarda la inventada.
    segunda = falso.llamadas[1]["messages"]
    assert segunda[-1] == {"role": "user", "content": "Observacion: 4640"}
    assert "9999" not in segunda[-2]["content"]


def test_15_pide_parar_antes_de_la_observacion(receta, cliente_falso):
    falso = cliente_falso("Respuesta final: hola")
    receta(15).ejecutar_agente("di hola")
    assert "Observacion:" in falso.llamadas[0]["stop"]


def test_15_accion_con_tilde_ejecuta_la_herramienta(receta, cliente_falso):
    cliente_falso(
        "Pensamiento: cuento\nAcción: contar_letras\nEntrada: hola",
        "Respuesta final: tiene 4",
    )
    assert receta(15).ejecutar_agente("cuantas letras tiene hola?") == "tiene 4"


def test_15_herramienta_desconocida_y_formato_invalido(receta, cliente_falso):
    falso = cliente_falso(
        "Accion: buscar_en_google\nEntrada: algo",
        "No se que hacer",
        "Respuesta final: listo",
    )
    assert receta(15).ejecutar_agente("?") == "listo"
    assert "no existe" in falso.llamadas[1]["messages"][-1]["content"]
    assert "Error de formato" in falso.llamadas[2]["messages"][-1]["content"]


def test_15_limite_de_pasos(receta, cliente_falso):
    cliente_falso(*["Accion: fecha_actual\nEntrada: hoy"] * 3)
    assert "limite de pasos" in receta(15).ejecutar_agente("?", max_pasos=3)


# --------------------------------------------------------------------------- #
# Calculadora                                                                  #
# --------------------------------------------------------------------------- #


def test_regresion_15_potencias_gigantes_no_cuelgan(receta):
    # Antes: '9**9**9' dejaba al agente colgado (matado por timeout a los 20 s).
    inicio = time.perf_counter()
    resultado = receta(15).herramienta_calcular("9**9**9")
    assert time.perf_counter() - inicio < 1
    assert resultado.startswith("Error:")


@pytest.mark.parametrize(
    "expresion, esperado",
    [
        ("145 * 32", "4640"),
        ("145 x 32", "4640"),
        ("145 × 32 =", "4640"),
        ("`2 + 2 * 3`", "8"),
        ("10 / 4", "2.5"),
        ("10 / 3", "3.333333333"),
        ("2 ^ 10", "1024"),
        ("7 // 2", "3"),
        ("-(3 - 5) % 3", "2"),
        ("2 ** -2", "0.25"),
    ],
)
def test_15_calcular(receta, expresion, esperado):
    assert receta(15).herramienta_calcular(expresion) == esperado


@pytest.mark.parametrize(
    "expresion, pista",
    [
        ("1 / 0", "division entre cero"),
        ("10 ** 100", "cifras"),
        ("(10 ** 60) * (10 ** 60)", "cifras"),
        ("0.5 ** -400", "cifras"),
        ("(-8) ** 0.5", "numero real"),
        ("3,5 * 2", "punto para los decimales"),
        ("__import__('os').system('echo hola')", "solo se permiten"),
        ("1 + " * 100 + "1", "caracteres"),
        ("2 +", "invalida"),
    ],
)
def test_15_calcular_rechaza_lo_peligroso_o_invalido(receta, expresion, pista):
    resultado = receta(15).herramienta_calcular(expresion)
    assert resultado.startswith("Error:") and pista in resultado


def test_15_contar_letras(receta):
    assert "4 caracteres" in receta(15).herramienta_contar_letras("'4640'")


def test_15_dias_fin_de_mes(receta):
    assert receta(15).herramienta_dias_fin_mes(None).startswith("Faltan ")
