"""Recetas de texto y audio: 03, 07, 12 y 14."""

import json
import sys
from types import SimpleNamespace

import pytest

from comun import nim

# --------------------------------------------------------------------------- #
# 03 / 14 - Audio (faster-whisper sustituido por un módulo falso)              #
# --------------------------------------------------------------------------- #


class _WhisperFalso:
    """Imita faster_whisper.WhisperModel sin descargar ningún modelo."""

    creados = []

    def __init__(self, tamano, device=None, compute_type=None):
        self.tamano = tamano
        _WhisperFalso.creados.append(self)

    def transcribe(self, ruta, language=None, beam_size=None):
        segmentos = [
            SimpleNamespace(start=0.0, end=2.5, text=" Hola a todos."),
            SimpleNamespace(start=2.5, end=6.0, text=" Movemos el lanzamiento al 22 de marzo."),
        ]
        info = SimpleNamespace(language=language or "es", language_probability=0.98)
        return iter(segmentos), info  # como el real: un generador perezoso


@pytest.fixture
def whisper_falso(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=_WhisperFalso))
    audio = tmp_path / "reunion.mp3"
    audio.write_bytes(b"ID3 audio de mentira")
    return audio


def test_03_transcribir_con_whisper_falso(receta, whisper_falso, capsys):
    texto, segmentos = receta(3).transcribir(whisper_falso, "tiny")
    assert texto == "Hola a todos. Movemos el lanzamiento al 22 de marzo."
    assert len(segmentos) == 2 and _WhisperFalso.creados[-1].tamano == "tiny"
    assert "probabilidad 98%" in capsys.readouterr().out


def test_03_main_con_tiempos_y_salida(receta, whisper_falso, tmp_path, monkeypatch, capsys):
    salida = tmp_path / "transcripcion.txt"
    monkeypatch.setattr(sys, "argv", ["03", str(whisper_falso), "--con-tiempos", "--salida", str(salida)])
    receta(3).main()
    assert "[00:02 - 00:06] Movemos el lanzamiento al 22 de marzo." in capsys.readouterr().out
    assert salida.read_text(encoding="utf-8").startswith("Hola a todos.")


def test_03_sin_faster_whisper_explica_como_instalarlo(receta, monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import -> ImportError
    with pytest.raises(SystemExit):
        receta(3).transcribir(tmp_path / "x.mp3")
    assert "pip install faster-whisper" in capsys.readouterr().out


def test_03_demo_estima_tiempos_desde_la_transcripcion(receta):
    texto, segmentos = receta(3).transcripcion_demo()
    assert texto.startswith("Ana: Buenos dias")
    assert segmentos[0].start == 0 and all(a.end == b.start for a, b in zip(segmentos, segmentos[1:]))


def test_03_formato_tiempo(receta):
    assert receta(3).formato_tiempo(125.9) == "02:05"


def test_14_con_audio_transcribe_y_resume(receta, whisper_falso, cliente_falso, monkeypatch, tmp_path, capsys):
    minuta = {
        "titulo": "Lanzamiento",
        "resumen": "Se mueve la fecha.",
        "decisiones": ["Lanzar el 22 de marzo"],
        "tareas": [{"tarea": "Avisar a clientes", "responsable": "Lucia", "fecha": None}, "Llamar al proveedor"],
        "pendientes": "Precio del plan Premium",
    }
    falso = cliente_falso("```json\n" + json.dumps(minuta) + "\n```")
    salida = tmp_path / "minuta.json"
    monkeypatch.setattr(sys, "argv", ["14", "--audio", str(whisper_falso), "--salida", str(salida)])
    receta(14).main()
    impreso = capsys.readouterr().out
    assert "Movemos el lanzamiento" in falso.llamadas[0]["messages"][-1]["content"]
    assert "[responsable: Lucia | fecha: Sin fecha]" in impreso
    assert "- Llamar al proveedor  [responsable: Sin asignar" in impreso
    assert "- Precio del plan Premium" in impreso
    assert json.loads(salida.read_text(encoding="utf-8"))["titulo"] == "Lanzamiento"


# --------------------------------------------------------------------------- #
# 07 - Subtítulos                                                              #
# --------------------------------------------------------------------------- #

SRT = (
    "1\n00:00:01,000 --> 00:00:04,200\nHola y bienvenidos.\n\n"
    "2\n00:00:04,500 --> 00:00:08,000\nHoy vamos a aprender\nen tareas del dia a dia.\n\n"
    "3\n00:00:08,300 --> 00:00:12,100\nSuscribete.\n"
)


@pytest.mark.parametrize("salto, bom", [("\n", False), ("\r\n", False), ("\r\n", True)])
def test_07_ida_y_vuelta_identica(receta, tmp_path, salto, bom):
    r07 = receta(7)
    original = ("\ufeff" if bom else "") + SRT.replace("\n", salto)
    entrada = tmp_path / "entrada.srt"
    entrada.write_bytes(original.encode("utf-8"))
    bloques, salto_detectado, con_bom = r07.leer_srt(entrada)
    assert (salto_detectado, con_bom) == (salto, bom)
    salida = tmp_path / "salida.srt"
    r07.escribir_srt(salida, bloques, [lineas for _, _, lineas in bloques], salto_detectado, con_bom)
    assert salida.read_bytes() == entrada.read_bytes()


def test_07_archivo_de_ejemplo_ida_y_vuelta(receta, tmp_path):
    r07 = receta(7)
    original = nim.ruta_datos("subtitulos_ejemplo.srt")
    bloques, salto, bom = r07.leer_srt(original)
    copia = tmp_path / "copia.srt"
    r07.escribir_srt(copia, bloques, [l for _, _, l in bloques], salto, bom)
    assert copia.read_bytes() == original.read_bytes()


def test_regresion_07_si_faltan_fragmentos_no_se_desalinean(receta, cliente_falso, capsys):
    # Antes devolvía ['Hello', 'Today', 'Hola']: el hueco se llenaba con el PRIMER texto.
    cliente_falso("Hello\n<<<>>>\nToday")
    assert receta(7).traducir_lote(["Hola", "Hoy", "Suscribete"], "ingles") == ["Hello", "Today", "Suscribete"]
    assert "esperaba 3 fragmentos y recibi 2" in capsys.readouterr().out


def test_07_si_sobran_fragmentos_se_recortan(receta, cliente_falso):
    cliente_falso("A<<<>>>B<<<>>>C")
    assert receta(7).traducir_lote(["uno", "dos"], "ingles") == ["A", "B"]


def test_07_reconstruir_conserva_numero_de_lineas(receta):
    r07 = receta(7)
    bloques = r07.parsear_srt(SRT)
    traducidos = ["Hello and welcome.", "Today we are going to learn in everyday tasks.", "Subscribe."]
    resultado = r07.reconstruir_srt(bloques, traducidos)
    bloque2 = resultado.split("\n\n")[1].split("\n")
    assert bloque2[:2] == ["2", "00:00:04,500 --> 00:00:08,000"] and len(bloque2) == 4


@pytest.mark.parametrize("n", [1, 2, 3])
def test_07_reenvolver(receta, n):
    lineas = receta(7).reenvolver("uno dos tres cuatro cinco seis siete ocho", n)
    assert len(lineas) == n
    assert " ".join(lineas) == "uno dos tres cuatro cinco seis siete ocho"


def test_07_parsear_srt_tolera_espacios_y_bloques_rotos(receta):
    sucio = "\n\n1\n00:00:01,000 --> 00:00:02,000\nHola   \n\n\n\nbasura sin tiempos\n\n2\n00:00:03,000 --> 00:00:04,000\nAdios\n"
    bloques = receta(7).parsear_srt(sucio)
    assert [(b[0], b[2]) for b in bloques] == [("1", ["Hola"]), ("2", ["Adios"])]


# --------------------------------------------------------------------------- #
# 12 - Diff de correcciones                                                    #
# --------------------------------------------------------------------------- #


def test_12_diff_marca_quitados_y_agregados(receta):
    diff = receta(12).mostrar_diff("ola como estas amigo", "Hola, ¿cómo estás, amigo?")
    assert diff == "[- ola como estas amigo] [+ Hola, ¿cómo estás, amigo?]"


def test_12_diff_conserva_lo_que_no_cambia(receta):
    diff = receta(12).mostrar_diff("les escrivo para contarles", "les escribo para contarles")
    assert diff == "les [- escrivo] [+ escribo] para contarles"


def test_12_diff_sin_cambios(receta):
    assert receta(12).mostrar_diff("todo bien", "todo bien") == "todo bien"
