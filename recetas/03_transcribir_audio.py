"""
Receta 03 - Transcribir audio (local y gratis)
==============================================

Qué automatiza
--------------
Convierte un archivo de audio (una reunión grabada, una nota de voz, un
podcast) en texto. Reconoce español muy bien.

Por qué esta receta NO usa NVIDIA NIM
-------------------------------------
La transcripción corre 100% en tu máquina con `faster-whisper`, una versión
optimizada del modelo Whisper de OpenAI. Ventajas: es gratis, funciona sin
internet y tu audio nunca sale de tu computadora (importante si es sensible).
Si tienes GPU NVIDIA se acelera muchísimo; si no, corre en CPU (más lento).

Instalación
-----------
  pip install faster-whisper

La primera vez descarga el modelo (unos cientos de MB). Tamaños disponibles,
de más rápido/menos preciso a más lento/más preciso:
  tiny, base, small, medium, large-v3
Para español, "small" o "medium" dan un equilibrio muy bueno.

Modo demo
---------
Con --demo no se transcribe nada: se muestra la transcripción de ejemplo
(datos/transcripcion_reunion.txt) en los mismos formatos que daría la receta,
para ver la salida sin instalar faster-whisper ni tener un audio. Con
--con-tiempos, las marcas de tiempo de la demo son ESTIMADAS (no hay audio).

Uso
---
  python recetas/03_transcribir_audio.py reunion.mp3
  python recetas/03_transcribir_audio.py nota.wav --modelo medium --salida nota.txt
  python recetas/03_transcribir_audio.py --demo --con-tiempos
"""

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

PALABRAS_POR_SEGUNDO = 2.5  # ritmo típico al hablar, para estimar tiempos en la demo


def transcribir(ruta_audio, tam_modelo="small", idioma="es"):
    """
    Transcribe el audio y devuelve (texto_completo, lista_de_segmentos).

    Cada segmento trae su marca de tiempo (inicio, fin) y su texto, útil si
    después quieres generar subtítulos o saltar a un momento concreto.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(
            "Falta 'faster-whisper'. Instalalo con:\n\n"
            "  pip install faster-whisper\n\n"
            "Es una descarga aparte porque incluye el motor de transcripcion.\n"
            "Para ver la salida sin instalarlo: anade --demo."
        )
        sys.exit(1)

    # compute_type="int8" usa poca memoria y va bien en CPU. Si tienes GPU
    # puedes cambiar device a "cuda" para acelerar mucho.
    print(f"Cargando modelo '{tam_modelo}' (la primera vez se descarga)...")
    modelo = WhisperModel(tam_modelo, device="cpu", compute_type="int8")

    print("Transcribiendo... (puede tardar segun la duracion del audio)")
    # `segments` es un generador perezoso: la transcripción ocurre a medida que
    # lo recorremos, por eso lo convertimos a lista para poder reutilizarlo.
    segmentos, info = modelo.transcribe(str(ruta_audio), language=idioma, beam_size=5)
    segmentos = list(segmentos)

    print(f"Idioma detectado: {info.language} (probabilidad {info.language_probability:.0%})")
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    return texto, segmentos


def transcripcion_demo(ruta_texto=None):
    """
    Devuelve (texto, segmentos) a partir de una transcripción ya escrita.

    Cada línea no vacía es un segmento. Los tiempos se ESTIMAN a partir del
    número de palabras (2,5 palabras por segundo): sirven para ver el formato,
    no son tiempos reales de ningún audio.
    """
    ruta = Path(ruta_texto) if ruta_texto else nim.ruta_datos("transcripcion_reunion.txt")
    lineas = [l.strip() for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    segmentos, inicio = [], 0.0
    for linea in lineas:
        duracion = max(1.0, len(linea.split()) / PALABRAS_POR_SEGUNDO)
        segmentos.append(SimpleNamespace(start=inicio, end=inicio + duracion, text=linea))
        inicio += duracion
    return " ".join(lineas), segmentos


def formato_tiempo(segundos):
    """Convierte segundos a formato mm:ss para mostrar los segmentos."""
    minutos = int(segundos // 60)
    segs = int(segundos % 60)
    return f"{minutos:02d}:{segs:02d}"


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio a texto en local.")
    parser.add_argument("audio", nargs="?", help="Ruta al archivo de audio (mp3, wav, m4a, etc.).")
    parser.add_argument(
        "--modelo",
        default="small",
        help="Tamano del modelo: tiny, base, small, medium, large-v3.",
    )
    parser.add_argument("--idioma", default="es", help="Idioma del audio (por defecto es).")
    parser.add_argument("--salida", help="Archivo donde guardar la transcripcion (.txt).")
    parser.add_argument(
        "--con-tiempos",
        action="store_true",
        help="Muestra cada segmento con su marca de tiempo.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Sin audio ni faster-whisper: muestra la transcripcion de ejemplo "
        "(datos/transcripcion_reunion.txt) con tiempos estimados.",
    )
    args = parser.parse_args()

    if args.demo or nim.modo_demo():
        print("[modo demo] No se transcribe audio: se muestra datos/transcripcion_reunion.txt.")
        if args.con_tiempos:
            print("[modo demo] Los tiempos son ESTIMADOS a 2,5 palabras por segundo.")
        texto, segmentos = transcripcion_demo()
    else:
        if not args.audio:
            parser.error("falta la ruta del audio (o usa --demo para ver un ejemplo)")
        ruta = Path(args.audio)
        if not ruta.exists():
            print(f"No encuentro el audio: {ruta}")
            sys.exit(1)
        texto, segmentos = transcribir(ruta, args.modelo, args.idioma)

    print("\n" + "=" * 60)
    if args.con_tiempos:
        for s in segmentos:
            print(f"[{formato_tiempo(s.start)} - {formato_tiempo(s.end)}] {s.text.strip()}")
    else:
        print(texto)
    print("=" * 60)

    if args.salida:
        Path(args.salida).write_text(texto, encoding="utf-8")
        print(f"\nTranscripcion guardada en: {args.salida}")


if __name__ == "__main__":
    nim.ejecutar(main)
