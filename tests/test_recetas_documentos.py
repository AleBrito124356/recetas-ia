"""Recetas que trocean documentos: 01 (resumir PDF) y 08 (RAG)."""

import numpy as np
import pytest

from comun import nim

# --------------------------------------------------------------------------- #
# 01 - Resumir PDF                                                             #
# --------------------------------------------------------------------------- #


def test_regresion_01_trocear_respeta_el_limite_con_parrafos_gigantes(receta):
    # Antes: 67.500 caracteres sin líneas en blanco -> 1 trozo de 67.500.
    texto = "linea de un informe muy largo sin parrafos\n" * 1500
    trozos = receta(1).trocear(texto, tam_max=9000)
    assert len(trozos) > 1
    assert max(len(t) for t in trozos) <= 9000
    assert "".join(t.replace("\n", "") for t in trozos) == texto.replace("\n", "")


@pytest.mark.parametrize(
    "texto",
    [
        "palabra " * 5000,                       # una sola línea enorme
        "x" * 25000,                              # una "palabra" enorme (URL, hash)
        "Frase corta. " * 3000,                   # muchas frases
        ("parrafo normal. " * 20 + "\n\n") * 80,  # párrafos que se pueden juntar
    ],
    ids=["linea-enorme", "palabra-enorme", "muchas-frases", "parrafos"],
)
def test_01_ningun_trozo_supera_el_limite(receta, texto):
    trozos = receta(1).trocear(texto, tam_max=2000)
    assert trozos and max(len(t) for t in trozos) <= 2000


def test_01_texto_corto_es_un_solo_trozo(receta):
    assert receta(1).trocear("Hola.\n\nAdios.") == ["Hola.\n\nAdios."]


def test_01_condensar_hace_map_reduce_por_rondas(receta, cliente_falso):
    r01 = receta(1)
    texto = ("Una frase con datos del informe. " * 30 + "\n\n") * 40  # ~40.000 caracteres
    # Resúmenes largos: juntos no caben en un trozo y obligan a otra ronda.
    resumen = "Resumen de la parte con datos. " * 50
    falso = cliente_falso(*([resumen] * 100))
    contenido = r01.condensar(texto, tam_max=4000)
    assert len(contenido) <= 4000
    llamadas = len(falso.llamadas)
    assert llamadas > len(r01.trocear(texto, 4000))  # hubo más de una ronda
    for llamada in falso.llamadas:
        assert len(llamada["messages"][-1]["content"]) <= 4000 + 200  # trozo + instrucción


def test_01_extrae_el_pdf_de_ejemplo(receta):
    texto, paginas = receta(1).extraer_texto_pdf(nim.ruta_datos("informe_ejemplo.pdf"))
    assert paginas == 2
    assert "Café Aroma" in texto and "48.600 USD" in texto
    assert "  " not in texto  # espacios normalizados


def test_01_pdf_sin_texto(receta, tmp_path, capsys, monkeypatch):
    from pypdf import PdfWriter

    vacio = tmp_path / "escaneo.pdf"
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    with open(vacio, "wb") as f:
        escritor.write(f)
    monkeypatch.setattr("sys.argv", ["01", str(vacio)])
    with pytest.raises(SystemExit):
        receta(1).main()
    assert "escaneo" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 08 - RAG                                                                     #
# --------------------------------------------------------------------------- #

PRECIOS = nim.ruta_datos("docs", "02_precios.md").read_text(encoding="utf-8")


def test_regresion_08_no_corta_listas_por_la_mitad(receta):
    # Antes: el primer trozo acababa en '... del plan Pro.\n- Usuarios' (a medio ítem).
    lineas_originales = {l.strip() for l in PRECIOS.splitlines() if l.strip()}
    for trozo in receta(8).trocear_texto(PRECIOS):
        cabecera, _, cuerpo = trozo.partition("\n")
        assert cabecera.startswith("Facturia — Planes y precios")
        for linea in cuerpo.splitlines():
            assert not linea.strip() or linea.strip() in lineas_originales


def test_08_cada_seccion_sabe_de_que_plan_habla(receta):
    trozos = receta(8).trocear_texto(PRECIOS)
    pro = [t for t in trozos if "Hasta 3 usuarios" in t]
    assert pro and pro[0].startswith("Facturia — Planes y precios > Plan Pro — 12 USD/mes")


def test_08_respeta_tam_y_aplica_solape(receta):
    texto = "# Doc\n\n" + "\n\n".join(f"Parrafo numero {i}. " + "texto " * 20 for i in range(30))
    trozos = receta(8).trocear_texto(texto, tam=400, solape=150)
    assert len(trozos) > 3 and max(len(t) for t in trozos) <= 400
    # El último párrafo de un trozo reaparece al principio del siguiente.
    for anterior, siguiente in zip(trozos, trozos[1:]):
        ultimo = anterior.split("\n\n")[-1]
        if len(ultimo) <= 150:
            assert siguiente.split("\n", 1)[1].startswith(ultimo)


def test_08_ignora_almohadillas_dentro_de_codigo(receta):
    texto = "# Guia\n\n```bash\n# esto es un comentario\nls\n```\n\nFin."
    secciones = receta(8).secciones_markdown(texto)
    assert [titulo for titulo, _ in secciones] == ["Guia"]


def test_08_recuperar_con_vectores_hechos_a_mano(receta):
    fragmentos = [{"fuente": "a.md", "texto": "a"}, {"fuente": "b.md", "texto": "b"}, {"fuente": "c.md", "texto": "c"}]
    matriz = np.array([[1, 0, 0], [0, 1, 0], [0.6, 0.8, 0]], dtype=np.float32)
    resultado = receta(8).recuperar("?", fragmentos, matriz, k=2, vector_pregunta=[0, 2, 0])
    assert [f["fuente"] for f, _ in resultado] == ["b.md", "c.md"]
    assert resultado[0][1] == pytest.approx(1.0) and resultado[1][1] == pytest.approx(0.8)


def test_regresion_08_la_segunda_vez_no_se_vuelven_a_pagar_embeddings(receta, cliente_falso, tmp_path):
    r08 = receta(8)
    falso = cliente_falso()
    carpeta = nim.ruta_datos("docs")
    fragmentos, _ = r08.construir_indice(carpeta, r08.CacheEmbeddings(tmp_path, "modelo-x"))
    assert sum(len(c["textos"]) for c in falso.embeddings_de("passage")) == len(fragmentos)

    antes = len(falso.embeddings_de("passage"))
    r08.construir_indice(carpeta, r08.CacheEmbeddings(tmp_path, "modelo-x"))
    assert len(falso.embeddings_de("passage")) == antes  # 0 llamadas nuevas

    r08.construir_indice(carpeta, r08.CacheEmbeddings(tmp_path, "otro-modelo"))
    assert len(falso.embeddings_de("passage")) > antes  # otro modelo: no se mezclan vectores


def test_08_con_vectores_locales_encuentra_el_plan_pro(receta, monkeypatch):
    monkeypatch.setenv("NIM_DEMO", "1")
    r08 = receta(8)
    fragmentos, matriz = r08.construir_indice(nim.ruta_datos("docs"))
    mejor, _ = r08.recuperar("Cuanto cuesta el plan Pro?", fragmentos, matriz, k=1)[0]
    assert mejor["fuente"] == "02_precios.md" and "Plan Pro" in mejor["texto"]
