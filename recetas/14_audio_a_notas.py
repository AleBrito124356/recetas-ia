"""
Receta 14 - De audio (o transcripción) a minuta de reunión
==========================================================

Qué automatiza
--------------
Toma la transcripción de una reunión y la convierte en una minuta accionable:
decisiones tomadas, tareas con su responsable y fecha, y temas pendientes. Deja
de tomar apuntes: graba, transcribe y deja que la IA ordene el caos.

Dos formas de usarla:
  - Con un archivo de TEXTO ya transcrito (por defecto usa el ejemplo incluido).
  - Con un archivo de AUDIO: lo transcribe primero con faster-whisper (local,
    gratis) reutilizando la lógica de la receta 03, y luego genera la minuta.
    En modo --demo no se transcribe el audio: se usa la transcripción de
    ejemplo, para ver el flujo completo sin instalar faster-whisper.

Uso
---
  python recetas/14_audio_a_notas.py
  python recetas/14_audio_a_notas.py --texto datos/transcripcion_reunion.txt
  python recetas/14_audio_a_notas.py --audio reunion.mp3
  python recetas/14_audio_a_notas.py --demo --salida minuta.json
"""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


def _cargar_receta03():
    """
    Cargamos el módulo de la receta 03 por ruta porque empieza por un número
    ('03_...') y no se puede importar con un import normal.
    """
    ruta_receta = Path(__file__).resolve().parent / "03_transcribir_audio.py"
    spec = importlib.util.spec_from_file_location("receta03", ruta_receta)
    receta03 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receta03)
    return receta03


def transcribir_audio(ruta_audio):
    """Reutiliza la receta 03 para transcribir el audio en local."""
    texto, _ = _cargar_receta03().transcribir(ruta_audio, tam_modelo="small", idioma="es")
    return texto


def generar_minuta(transcripcion):
    """Pide al modelo una minuta estructurada en JSON."""
    sistema = (
        "Eres un asistente que resume reuniones. A partir de una transcripcion "
        "produces una minuta accionable. Devuelves SOLO JSON valido en espanol."
    )
    prompt = (
        "Genera la minuta de esta reunion con esta estructura JSON:\n"
        "{\n"
        '  "titulo": "titulo breve de la reunion",\n'
        '  "resumen": "2-3 frases",\n'
        '  "decisiones": ["decision 1", "decision 2"],\n'
        '  "tareas": [{"tarea": "que hay que hacer", "responsable": "nombre o Sin asignar", '
        '"fecha": "fecha mencionada o Sin fecha"}],\n'
        '  "pendientes": ["tema que quedo abierto"]\n'
        "}\n\n"
        "Asigna responsables solo si se mencionan en la transcripcion; si no, usa "
        '"Sin asignar".\n\n'
        f"TRANSCRIPCION:\n{transcripcion}"
    )
    respuesta = nim.chat(prompt=prompt, sistema=sistema, temperatura=0.2, max_tokens=1500)
    return nim.extraer_json(respuesta, esperado=dict)


def _lista(valor):
    """El modelo a veces devuelve un texto suelto donde pedimos una lista."""
    if isinstance(valor, list):
        return [v for v in valor if v not in (None, "")]
    return [valor] if valor not in (None, "") else []


def imprimir_minuta(minuta):
    """Formatea la minuta para leerla o pegarla en un correo."""
    print("=" * 60)
    print(str(minuta.get("titulo") or "Minuta de reunion").upper())
    print("=" * 60)
    print(f"\n{minuta.get('resumen') or ''}\n")

    print("DECISIONES")
    for decision in _lista(minuta.get("decisiones")) or ["(ninguna)"]:
        print(f"  - {decision}")

    print("\nTAREAS")
    tareas = _lista(minuta.get("tareas"))
    if not tareas:
        print("  (ninguna)")
    for tarea in tareas:
        if not isinstance(tarea, dict):
            tarea = {"tarea": str(tarea)}
        print(
            f"  - {tarea.get('tarea')}  "
            f"[responsable: {tarea.get('responsable') or 'Sin asignar'} | "
            f"fecha: {tarea.get('fecha') or 'Sin fecha'}]"
        )

    print("\nPENDIENTES")
    for pendiente in _lista(minuta.get("pendientes")) or ["(ninguno)"]:
        print(f"  - {pendiente}")
    print("=" * 60)


def main():
    parser = nim.nuevo_parser("Convierte una reunion en minuta accionable.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--texto", help="Archivo de texto con la transcripcion.")
    grupo.add_argument("--audio", help="Archivo de audio a transcribir antes de resumir.")
    parser.add_argument("--salida", help="Archivo .json donde guardar la minuta.")
    args = parser.parse_args()

    if args.audio and not nim.modo_demo():
        ruta = Path(args.audio)
        if not ruta.exists():
            print(f"No encuentro el audio: {ruta}")
            sys.exit(1)
        print("Transcribiendo audio (local con faster-whisper)...")
        transcripcion = transcribir_audio(ruta)
    else:
        if args.audio:
            print("[modo demo] No se transcribe el audio: se usa datos/transcripcion_reunion.txt.")
        ruta = Path(args.texto) if args.texto else nim.ruta_datos("transcripcion_reunion.txt")
        if not ruta.exists():
            print(f"No encuentro la transcripcion: {ruta}")
            sys.exit(1)
        transcripcion = ruta.read_text(encoding="utf-8")

    if not transcripcion.strip():
        print("La transcripcion esta vacia: no hay nada que resumir.")
        sys.exit(1)

    print("Generando minuta...\n")
    minuta = generar_minuta(transcripcion)
    imprimir_minuta(minuta)

    if args.salida:
        Path(args.salida).write_text(
            json.dumps(minuta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nMinuta guardada en: {args.salida}")


if __name__ == "__main__":
    nim.ejecutar(main)
