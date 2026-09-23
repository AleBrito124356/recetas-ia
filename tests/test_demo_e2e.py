"""
Las 15 recetas de principio a fin en modo demo: proceso aparte, sin clave,
sin internet, con sus datos de ejemplo. Es exactamente lo que ve alguien que
acaba de clonar el repositorio y ejecuta `python recetas.py demo`.
"""

import json
import re

import pytest

from comun import nim
from conftest import RAIZ, correr, ruta_receta

DEMO = {"NIM_DEMO": "1"}


def demo(numero, *argumentos):
    resultado = correr([ruta_receta(numero)] + list(argumentos), DEMO)
    assert "Traceback" not in resultado.stderr, resultado.stderr
    return resultado


def test_01_resume_el_pdf_de_ejemplo():
    r = demo(1)
    assert r.returncode == 0, r.stderr
    assert "2 paginas" in r.stdout and "RESUMEN EJECUTIVO:" in r.stdout
    assert r.stdout.count("\n- ") == 6
    assert "origen: redactada a mano" in r.stderr  # nunca se presenta como modelo real


def test_02_totales_reales_del_csv(tmp_path):
    salida = tmp_path / "clasificados.json"
    r = demo(2, "--salida", salida)
    assert r.returncode == 0, r.stderr
    neto = next(l for l in r.stdout.splitlines() if l.startswith("TOTAL NETO"))
    assert neto.split()[-2:] == ["1,530.56", "1,458.76"]
    detalle = json.loads(salida.read_text(encoding="utf-8"))
    assert len(detalle) == 29 and all(d["categoria"] for d in detalle)


def test_03_demo_sin_audio_ni_faster_whisper():
    r = correr([ruta_receta(3), "--demo", "--con-tiempos"])
    assert r.returncode == 0, r.stderr
    assert "[00:00 - 00:10] Ana: Buenos dias" in r.stdout and "ESTIMADOS" in r.stdout


def test_03_sin_audio_ni_demo_explica_que_falta():
    r = correr([ruta_receta(3)])
    assert r.returncode == 2 and "--demo" in r.stderr


def test_04_un_borrador_por_resena(tmp_path):
    salida = tmp_path / "borradores.txt"
    r = demo(4, "--salida", salida)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("BORRADOR DE RESPUESTA:") == 6
    assert salida.read_text(encoding="utf-8").count("RESENA ") == 6


def test_05_json_y_validacion(tmp_path):
    salida = tmp_path / "factura.json"
    r = demo(5, "--salida", salida, "--estricto")
    assert r.returncode == 0, r.stderr
    assert "Validacion: todo cuadra" in r.stdout
    assert json.loads(salida.read_text(encoding="utf-8"))["total"] == 295.32


def test_06_tres_redes():
    r = demo(6)
    assert r.returncode == 0, r.stderr
    for titulo in ("LINKEDIN", "HILO DE X / TWITTER", "CAPTION DE INSTAGRAM"):
        assert titulo in r.stdout


def test_07_srt_traducido_con_los_mismos_tiempos(tmp_path):
    salida = tmp_path / "en.srt"
    r = demo(7, "--salida", salida)
    assert r.returncode == 0, r.stderr
    patron = re.compile(r"\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}")
    original = nim.ruta_datos("subtitulos_ejemplo.srt").read_text(encoding="utf-8")
    traducido = salida.read_text(encoding="utf-8")
    assert patron.findall(traducido) == patron.findall(original)
    assert "Hello and welcome to this quick tutorial." in traducido
    # Los subtítulos de dos líneas siguen teniendo dos líneas.
    lineas_por_bloque = lambda t: [len(b.strip().splitlines()) for b in t.strip().split("\n\n")]
    assert lineas_por_bloque(traducido) == lineas_por_bloque(original)


def test_08_rag_con_cache(tmp_path):
    argumentos = ("--pregunta", "Cuanto cuesta el plan Pro?", "--cache", tmp_path)
    primera = demo(8, *argumentos)
    assert primera.returncode == 0, primera.stderr
    assert "12 USD al mes" in primera.stdout
    assert re.search(r"Fuentes: 02_precios\.md \(0\.\d\d\)", primera.stdout)
    assert "(0 desde la cache, 22 nuevos)" in primera.stdout
    segunda = demo(8, *argumentos)
    assert "(22 desde la cache, 0 nuevos)" in segunda.stdout


def test_08_pregunta_sin_grabar_no_inventa(tmp_path):
    r = demo(8, "--pregunta", "Tiene app movil?", "--cache", tmp_path)
    assert r.returncode == 1
    assert "no hay respuesta grabada" in r.stderr


def test_09_informe_y_cita_verificada():
    r = demo(9)
    assert r.returncode == 0, r.stderr
    porcentajes = [int(p) for p in re.findall(r"^\s+\w+\s+(\d+)%", r.stdout, re.MULTILINE)]
    assert sum(porcentajes) == 100
    assert r.stdout.count("(!) Esta cita no aparece") == 1  # la única cita parafraseada


def test_10_describe_la_imagen_de_ejemplo():
    r = demo(10)
    assert r.returncode == 0, r.stderr
    assert "ALT-TEXT" in r.stdout and "Taza de cerámica roja" in r.stdout


def test_11_datos_sinteticos_reproducibles(tmp_path):
    carpetas = [tmp_path / "a", tmp_path / "b"]
    for carpeta in carpetas:
        r = demo(11, "--salida", carpeta, "--pedidos", "12", "--semilla", "7")
        assert r.returncode == 0, r.stderr
    a, b = [(c / "pedidos.json").read_text(encoding="utf-8") for c in carpetas]
    assert a == b
    clientes = json.loads((carpetas[0] / "clientes.json").read_text(encoding="utf-8"))
    productos = json.loads((carpetas[0] / "productos.json").read_text(encoding="utf-8"))
    pedidos = json.loads(a)
    assert len(clientes) == 10 and len(productos) == 8 and len(pedidos) == 12
    assert all(isinstance(p["precio"], float) for p in productos)  # "12.50" se convirtió
    ids = {p["id"] for p in productos}
    for pedido in pedidos:
        assert pedido["cliente_id"] in {c["id"] for c in clientes}
        assert all(l["producto_id"] in ids for l in pedido["items"])
        assert pedido["total"] == round(sum(l["importe"] for l in pedido["items"]), 2)


def test_11_exporta_csv(tmp_path):
    r = demo(11, "--salida", tmp_path, "--formato", "csv", "--semilla", "1")
    assert r.returncode == 0, r.stderr
    assert {p.name for p in tmp_path.iterdir()} == {"clientes.csv", "productos.csv", "pedidos.csv"}


def test_12_diff_del_borrador():
    r = demo(12)
    assert r.returncode == 0, r.stderr
    assert "[- escrivo] [+ escribo]" in r.stdout


def test_13_correo():
    r = demo(13)
    assert r.returncode == 0, r.stderr
    assert "Asunto: Reunión con el proveedor de café" in r.stdout


def test_13_entrada_distinta_no_tiene_respuesta_grabada():
    r = demo(13, "--puntos", "algo que nunca se grabo")
    assert r.returncode == 1 and "no hay respuesta grabada" in r.stderr


def test_14_minuta(tmp_path):
    salida = tmp_path / "minuta.json"
    r = demo(14, "--salida", salida)
    assert r.returncode == 0, r.stderr
    assert "[responsable: Lucia | fecha: 18 de marzo]" in r.stdout
    assert len(json.loads(salida.read_text(encoding="utf-8"))["tareas"]) == 5


def test_14_audio_en_demo_usa_la_transcripcion(tmp_path):
    r = demo(14, "--audio", tmp_path / "no_hace_falta.mp3")
    assert r.returncode == 0, r.stderr
    assert "No se transcribe el audio" in r.stdout


def test_15_agente_usa_herramientas_reales():
    r = demo(15)
    assert r.returncode == 0, r.stderr
    assert "Accion: calcular('145 * 32') -> 4640" in r.stdout
    assert "Accion: contar_letras('4640') -> El texto '4640' tiene 4" in r.stdout
    assert "145 * 32 = 4640" in r.stdout.split("=" * 60)[-2]


# --------------------------------------------------------------------------- #
# Lanzador recetas.py                                                          #
# --------------------------------------------------------------------------- #


def test_lanzador_lista_las_15_recetas():
    r = correr([RAIZ / "recetas.py"])
    assert r.returncode == 0
    numeros = re.findall(r"^  (\d\d)  ", r.stdout, re.MULTILINE)
    assert numeros == [f"{i:02d}" for i in range(1, 16)]


def test_lanzador_ejecuta_una_receta_con_sus_argumentos():
    r = correr([RAIZ / "recetas.py", "5", "--demo"])
    assert r.returncode == 0, r.stderr
    assert "Validacion: todo cuadra" in r.stdout


def test_lanzador_receta_inexistente():
    r = correr([RAIZ / "recetas.py", "99"])
    assert r.returncode == 2 and "No existe la receta" in r.stdout


def test_recorrido_demo_completo(tmp_path):
    r = correr([RAIZ / "recetas.py", "demo", "--salida", tmp_path], timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert "15 de 15 recetas OK" in r.stdout
    assert (tmp_path / "subtitulos_en.srt").exists() and (tmp_path / "minuta.json").exists()


@pytest.mark.parametrize("numero", range(1, 16))
def test_todas_las_recetas_tienen_ayuda(numero):
    r = correr([ruta_receta(numero), "--help"])
    assert r.returncode == 0 and "--demo" in r.stdout
