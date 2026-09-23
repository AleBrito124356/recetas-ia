"""
Receta 12 - Revisar y corregir un texto (con diff)
==================================================

Qué automatiza
--------------
Corrige ortografía, gramática y estilo de un texto SIN cambiar tu voz ni el
significado. Y lo más importante: te muestra un "diff" (qué cambió exactamente)
para que tú decidas, en vez de aceptar cambios a ciegas.

El diff se calcula con `difflib`, de la librería estándar de Python: comparamos
el texto original con el corregido palabra por palabra.

Uso
---
  python recetas/12_revisar_texto.py --texto "ola como estas, kiero saver si bienes mañana"
  python recetas/12_revisar_texto.py --archivo borrador.txt --salida corregido.txt
  python recetas/12_revisar_texto.py        (usa datos/borrador_ejemplo.txt)
  python recetas/12_revisar_texto.py --demo (sin clave: respuesta pregrabada)
"""

import sys
import difflib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


def corregir(texto):
    """Devuelve el texto corregido manteniendo el tono del original."""
    sistema = (
        "Eres un corrector de estilo en espanol. Corriges ortografia, gramatica "
        "y puntuacion, y mejoras la claridad, PERO conservas la voz y el registro "
        "del autor: no lo vuelvas mas formal ni mas largo. Devuelve UNICAMENTE el "
        "texto corregido, sin comentarios ni explicaciones."
    )
    return nim.chat(prompt=texto, sistema=sistema, temperatura=0.2, max_tokens=1500)


def mostrar_diff(original, corregido):
    """
    Imprime las diferencias palabra a palabra.

    Marcamos con [- ...] lo que se quita y con [+ ...] lo que se añade. Es un
    formato de texto plano que se lee bien en cualquier terminal.
    """
    palabras_o = original.split()
    palabras_c = corregido.split()
    diff = difflib.ndiff(palabras_o, palabras_c)

    partes = []
    quitados, agregados = [], []

    def volcar():
        # Agrupamos supresiones y adiciones seguidas para que el diff se lea mejor.
        if quitados:
            partes.append(f"[- {' '.join(quitados)}]")
            quitados.clear()
        if agregados:
            partes.append(f"[+ {' '.join(agregados)}]")
            agregados.clear()

    for token in diff:
        codigo, palabra = token[:2], token[2:]
        if codigo == "  ":
            volcar()
            partes.append(palabra)
        elif codigo == "- ":
            quitados.append(palabra)
        elif codigo == "+ ":
            agregados.append(palabra)
    volcar()
    return " ".join(partes)


def main():
    parser = nim.nuevo_parser("Corrige un texto y muestra los cambios.")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--texto", help="Texto a corregir, entre comillas.")
    grupo.add_argument(
        "--archivo",
        help="Archivo de texto a corregir (por defecto datos/borrador_ejemplo.txt).",
    )
    parser.add_argument("--salida", help="Archivo donde guardar el texto corregido.")
    args = parser.parse_args()

    if args.texto is None:
        ruta = Path(args.archivo or nim.ruta_datos("borrador_ejemplo.txt"))
        if not ruta.exists():
            print(f"No encuentro el archivo: {ruta}")
            sys.exit(1)
        original = ruta.read_text(encoding="utf-8").strip()
    else:
        original = args.texto.strip()
    if not original:
        print("No hay texto que revisar.")
        sys.exit(1)

    print("Revisando el texto...\n")
    corregido = corregir(original)

    print("CAMBIOS PROPUESTOS")
    print("-" * 60)
    print(mostrar_diff(original, corregido))

    print("\nTEXTO CORREGIDO")
    print("-" * 60)
    print(corregido)

    if args.salida:
        Path(args.salida).write_text(corregido, encoding="utf-8")
        print(f"\nTexto corregido guardado en: {args.salida}")


if __name__ == "__main__":
    nim.ejecutar(main)
