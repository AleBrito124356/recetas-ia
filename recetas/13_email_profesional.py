"""
Receta 13 - Redactar un correo profesional
==========================================

Qué automatiza
--------------
Convierte tus notas sueltas (puntos rápidos, ideas en desorden) en un correo
bien escrito. Eliges idioma (español o inglés) y tono (formal o cercano).
Perfecto para ese email que te da pereza redactar bien.

Uso
---
  python recetas/13_email_profesional.py --puntos "reunion movida al viernes; traer laptop; confirmar asistencia"
  python recetas/13_email_profesional.py --archivo notas.txt --idioma en --tono formal
  python recetas/13_email_profesional.py        (usa datos/notas_correo.txt)
  python recetas/13_email_profesional.py --demo (sin clave: respuesta pregrabada)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

# Combinamos idioma y tono en instrucciones concretas para el modelo.
IDIOMAS = {
    "es": "espanol",
    "en": "ingles",
}
TONOS = {
    "formal": "formal y profesional, trato de usted (o 'you' formal en ingles)",
    "cercano": "cordial y cercano, cercano pero correcto, sin sonar rigido",
}


def redactar(puntos, idioma, tono):
    """Genera asunto + cuerpo del correo a partir de los puntos."""
    sistema = (
        f"Eres un asistente que redacta correos electronicos en {IDIOMAS[idioma]}. "
        f"Tono: {TONOS[tono]}. Estructura el correo con un saludo, un cuerpo claro "
        "y una despedida. Se conciso: nadie quiere leer un correo largo. Empieza la "
        "respuesta con una linea 'Asunto:' y luego el cuerpo."
    )
    prompt = (
        "Convierte estos puntos en un correo bien redactado. Puedes reordenarlos "
        f"para que fluya mejor:\n\n{puntos}"
    )
    return nim.chat(prompt=prompt, sistema=sistema, temperatura=0.5, max_tokens=700)


def main():
    parser = nim.nuevo_parser("Redacta un correo profesional desde notas.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--puntos", help="Puntos del correo separados por ';' o saltos de linea.")
    grupo.add_argument(
        "--archivo",
        help="Archivo de texto con los puntos (por defecto datos/notas_correo.txt).",
    )
    parser.add_argument("--idioma", choices=list(IDIOMAS.keys()), default="es", help="Idioma.")
    parser.add_argument("--tono", choices=list(TONOS.keys()), default="cercano", help="Tono.")
    parser.add_argument("--salida", help="Archivo donde guardar el correo.")
    args = parser.parse_args()

    if args.puntos is None:
        ruta = Path(args.archivo or nim.ruta_datos("notas_correo.txt"))
        if not ruta.exists():
            print(f"No encuentro el archivo: {ruta}")
            sys.exit(1)
        puntos = ruta.read_text(encoding="utf-8").strip()
    else:
        puntos = args.puntos.strip()
    if not puntos:
        print("No hay puntos para redactar el correo.")
        sys.exit(1)

    print(f"Redactando correo ({IDIOMAS[args.idioma]}, tono {args.tono})...\n")
    correo = redactar(puntos, args.idioma, args.tono)

    print("=" * 60)
    print(correo)
    print("=" * 60)

    if args.salida:
        Path(args.salida).write_text(correo, encoding="utf-8")
        print(f"\nCorreo guardado en: {args.salida}")


if __name__ == "__main__":
    nim.ejecutar(main)
