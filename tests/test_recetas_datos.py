"""Recetas que trabajan con datos estructurados: 02, 05, 09 y 11."""

import random

import pytest

from comun import nim

# --------------------------------------------------------------------------- #
# 02 - Clasificar gastos                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "fecha, mes",
    [
        ("2026-01-03", "2026-01"),
        ("03/01/2026", "2026-01"),
        ("3/1/2026", "2026-01"),
        ("03-01-2026", "2026-01"),
        ("03.01.2026", "2026-01"),
        ("ayer", "sin-fecha"),
        ("2026-13-01", "sin-fecha"),
    ],
)
def test_02_mes_de(receta, fecha, mes):
    assert receta(2).mes_de(fecha) == mes


def test_regresion_02_csv_latam_con_punto_y_coma_y_coma_decimal(receta, tmp_path):
    # Antes: float('-84,50') -> ValueError y la receta moría.
    r02 = receta(2)
    csv = tmp_path / "banco.csv"
    csv.write_text(
        "\ufeffFecha;Concepto;Importe\n"
        "03/01/2026;Supermercado Rey;-84,50\n"
        "05/01/2026;Nomina;1.234,56\n"
        "07/01/2026;Cine;(12,00)\n",
        encoding="utf-8",
    )
    filas = r02.preparar_montos(r02.leer_movimientos(csv))
    assert [f["monto"] for f in filas] == [-84.5, 1234.56, -12.0]
    assert filas[0]["descripcion"] == "Supermercado Rey" and filas[0]["fecha"] == "03/01/2026"


def test_02_fila_con_monto_ilegible_se_descarta_con_aviso(receta, capsys):
    filas = receta(2).preparar_montos(
        [{"fecha": "2026-01-01", "descripcion": "a", "monto": "-10"},
         {"fecha": "2026-01-02", "descripcion": "b", "monto": "diez"}]
    )
    assert len(filas) == 1
    assert "fila 3 descartada" in capsys.readouterr().out


def test_02_clasificar_normaliza_categorias_y_acepta_lista(receta, cliente_falso):
    r02 = receta(2)
    cliente_falso('{"0": "alimentación", "1": "Inventada"}', '["Transporte", "Ingresos"]')
    assert r02.clasificar_lote(["super", "rara"]) == ["Alimentacion", "Otros"]
    assert r02.clasificar_lote(["uber", "nomina"]) == ["Transporte", "Ingresos"]


def test_02_clasificar_por_lotes(receta, cliente_falso):
    falso = cliente_falso('{"0": "Otros", "1": "Otros"}', '{"0": "Otros"}')
    assert receta(2).clasificar(["a", "b", "c"], lote=2) == ["Otros"] * 3
    assert len(falso.llamadas) == 2


def test_02_totales_por_mes_no_dependen_de_la_clasificacion(receta):
    r02 = receta(2)
    movimientos = r02.preparar_montos(r02.leer_movimientos(nim.ruta_datos("movimientos.csv")))
    for categorias in (["Otros"] * len(movimientos), r02.CATEGORIAS * 4):
        resumen = r02.resumir(movimientos, categorias[: len(movimientos)])
        assert round(sum(resumen["2026-01"].values()), 2) == 1530.56
        assert round(sum(resumen["2026-02"].values()), 2) == 1458.76


# --------------------------------------------------------------------------- #
# 05 - Validar facturas                                                        #
# --------------------------------------------------------------------------- #

FACTURA_OK = {
    "emisor": {"nombre": "DISTRIBUIDORA CENTRAL, S.A.", "ruc_nit": "155612345-2-2021 DV 33"},
    "documento": {"fecha": "2026-02-12"},
    "items": [
        {"descripcion": "Saco", "cantidad": 4, "precio_unitario": 18.5, "importe": 74.0},
        {"descripcion": "Vasos", "cantidad": 2, "precio_unitario": 9.75, "importe": 19.5},
        {"descripcion": "Jarabe", "cantidad": 6, "precio_unitario": 6.25, "importe": 37.5},
        {"descripcion": "Molino", "cantidad": 1, "precio_unitario": 145.0, "importe": 145.0},
    ],
    "subtotal": 276.0,
    "impuesto": {"nombre": "ITBMS", "tasa": 0.07, "monto": 19.32},
    "total": 295.32,
}


def test_05_factura_de_ejemplo_valida(receta):
    texto = nim.ruta_datos("factura_ejemplo.txt").read_text(encoding="utf-8")
    assert receta(5).validar(FACTURA_OK, texto) == []


def test_regresion_05_impuesto_null_no_rompe(receta):
    # Antes: AttributeError: 'NoneType' object has no attribute 'get'.
    avisos = receta(5).validar({"items": [{"importe": 10}], "subtotal": 10, "impuesto": None, "total": 10})
    assert not any("no coincide" in a or "no cuadra" in a for a in avisos)


def test_regresion_05_detecta_linea_e_impuesto_imposibles(receta):
    # Antes: validar() devolvía [] para esta factura.
    avisos = receta(5).validar(
        {
            "items": [{"cantidad": 4, "precio_unitario": 18.5, "importe": 99.0}],
            "subtotal": 99.0,
            "impuesto": {"tasa": 0.07, "monto": 50.0},
            "total": 149.0,
        }
    )
    assert any("4 x 18.50 = 74.00" in a for a in avisos)
    assert any("7.00% de 99.00 = 6.93" in a for a in avisos)


def test_05_campos_obligatorios_fecha_y_textos(receta):
    r05 = receta(5)
    datos = dict(FACTURA_OK, documento={"fecha": "12/02/2026"}, total="295,32")
    avisos = r05.validar(datos)
    assert any("AAAA-MM-DD" in a for a in avisos)
    assert not any("total" in a and "no coincide" in a for a in avisos)  # "295,32" se entiende
    assert "Falta el campo obligatorio 'emisor.nombre'." in r05.validar({"items": []})
    assert any("2026-02-30" in a for a in r05.validar(dict(FACTURA_OK, documento={"fecha": "2026-02-30"})))


def test_05_tasa_en_porcentaje_y_cifras_inventadas(receta):
    r05 = receta(5)
    texto = nim.ruta_datos("factura_ejemplo.txt").read_text(encoding="utf-8")
    assert r05.validar(dict(FACTURA_OK, impuesto={"tasa": 7, "monto": 19.32}), texto) == []
    inventada = dict(FACTURA_OK, subtotal=300.0, total=321.0, impuesto={"tasa": 0.07, "monto": 21.0})
    avisos = r05.validar(inventada, texto)
    assert any("no aparece en el texto" in a for a in avisos)


@pytest.mark.parametrize("basura", [None, [], "texto", {"items": "no es lista", "subtotal": "abc"}])
def test_05_validar_nunca_lanza(receta, basura):
    assert isinstance(receta(5).validar(basura), list)


# --------------------------------------------------------------------------- #
# 09 - Encuesta                                                                #
# --------------------------------------------------------------------------- #


def test_regresion_09_porcentajes_como_texto(receta, capsys):
    # Antes: TypeError: unsupported operand type(s) for /: 'str' and 'int'.
    analisis = {
        "sentimiento_general": {"positivo": "60%", "neutral": "25", "negativo": 15},
        "temas": [],
        "resumen_ejecutivo": "x",
    }
    receta(9).imprimir_informe(analisis, 18)
    salida = capsys.readouterr().out
    assert "Positivo   60%" in salida and "Negativo   15%" in salida


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ({"positivo": 0.5, "neutral": 0.25, "negativo": 0.25}, {"positivo": 50, "neutral": 25, "negativo": 25}),
        ({"Positivo": "33.3%", "Neutral": "33.3%", "Negativo": "33.3%"}, {"positivo": 34, "neutral": 33, "negativo": 33}),
        ({"positivo": 60, "neutral": 30}, {"positivo": 67, "neutral": 33, "negativo": 0}),
        (None, {"positivo": 0, "neutral": 0, "negativo": 0}),
    ],
)
def test_09_normalizar_sentimiento_suma_100(receta, entrada, esperado):
    assert receta(9).normalizar_sentimiento(entrada) == esperado


def test_09_lee_respuestas_con_comas_sin_comillas(receta):
    respuestas = receta(9).leer_respuestas(nim.ruta_datos("encuesta.csv"), "respuesta")
    assert len(respuestas) == 18
    assert respuestas[14] == "Perfecta para freelancers como yo. Simple, directa y hace justo lo que promete."


def test_09_cita_textual(receta):
    r09 = receta(9)
    respuestas = ["La app es rápida, pero le falta modo oscuro."]
    assert r09.cita_textual('"la app es rapida, pero le falta modo oscuro"', respuestas)
    assert not r09.cita_textual("La app es lenta", respuestas)


# --------------------------------------------------------------------------- #
# 11 - Datos sintéticos                                                        #
# --------------------------------------------------------------------------- #


def test_regresion_11_clientes_tras_una_frase_son_una_lista(receta, cliente_falso):
    # Antes: extraer_json devolvía el primer objeto y random.choice(dict) fallaba.
    cliente_falso('Claro, aqui tienes:\n[{"id": 1, "nombre": "Ana Perez", "email": "a@x.com"}]')
    clientes = receta(11).generar_clientes(1)
    assert isinstance(clientes, list) and clientes[0]["nombre"] == "Ana Perez"


def test_regresion_11_precio_como_texto_no_rompe_los_pedidos(receta):
    # Antes: TypeError: type str doesn't define __round__ method.
    pedidos = receta(11).generar_pedidos(
        1, [{"id": 1, "nombre": "Ana"}], [{"id": 1, "nombre": "Cafe", "precio": "19.99"}], 1
    )
    assert pedidos[0]["items"][0]["importe"] == round(19.99 * pedidos[0]["items"][0]["cantidad"], 2)


def test_11_normalizar_registros(receta, capsys):
    productos = receta(11).normalizar_registros(
        {"productos": [
            {"id": 1, "nombre": "A", "precio": "$ 1.234,50"},
            {"id": 1, "nombre": "B", "precio": 5},
            {"nombre": "", "precio": 3},
            {"id": 3, "nombre": "C", "precio": "gratis"},
            "no soy un objeto",
        ]},
        "productos",
    )
    assert [(p["id"], p["nombre"], p["precio"]) for p in productos] == [(1, "A", 1234.5), (2, "B", 5.0)]
    assert "se descartaron 3 productos" in capsys.readouterr().out


def test_11_sin_registros_validos_da_error_claro(receta):
    with pytest.raises(nim.ErrorNIM):
        receta(11).normalizar_registros([{"sin": "nombre"}], "clientes")


def _datos_11():
    clientes = [{"id": i, "nombre": f"Cliente {i}"} for i in range(1, 6)]
    productos = [{"id": i, "nombre": f"P{i}", "precio": round(1.1 * i, 2)} for i in range(1, 9)]
    return clientes, productos


def test_11_invariantes_de_los_pedidos(receta):
    clientes, productos = _datos_11()
    pedidos = receta(11).generar_pedidos(200, clientes, productos, 4, random.Random(1))
    ids_clientes = {c["id"] for c in clientes}
    precios = {p["id"]: p["precio"] for p in productos}
    for pedido in pedidos:
        assert pedido["cliente_id"] in ids_clientes
        assert 1 <= len(pedido["items"]) <= 4
        assert len({l["producto_id"] for l in pedido["items"]}) == len(pedido["items"])
        for linea in pedido["items"]:
            assert linea["importe"] == round(precios[linea["producto_id"]] * linea["cantidad"], 2)
        assert pedido["total"] == round(sum(l["importe"] for l in pedido["items"]), 2)


def test_11_semilla_hace_los_pedidos_reproducibles(receta):
    clientes, productos = _datos_11()
    r11 = receta(11)
    a = r11.generar_pedidos(30, clientes, productos, 3, random.Random(42))
    b = r11.generar_pedidos(30, clientes, productos, 3, random.Random(42))
    c = r11.generar_pedidos(30, clientes, productos, 3, random.Random(43))
    assert a == b and a != c


def test_11_exporta_csv_con_ids(receta, tmp_path):
    clientes, productos = _datos_11()
    r11 = receta(11)
    pedidos = r11.generar_pedidos(3, clientes, productos, 2, random.Random(0))
    r11.exportar_csv(tmp_path, clientes, productos, pedidos)
    cabecera = (tmp_path / "pedidos.csv").read_text(encoding="utf-8").splitlines()[0]
    assert cabecera == "pedido_id,cliente_id,cliente,producto_id,producto,cantidad,importe"
