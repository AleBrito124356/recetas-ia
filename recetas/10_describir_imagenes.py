"""
Receta 10 - Describir imágenes (visión)
=======================================

Qué automatiza
--------------
Mira una imagen y genera dos cosas útiles:
  1. Un ALT-TEXT corto: la descripción para accesibilidad (lectores de pantalla)
     y SEO. Debe ser concreto y breve.
  2. Una DESCRIPCION DE PRODUCTO: un párrafo vendedor para una ficha de tienda,
     un catálogo o un marketplace.

Usa el modelo de visión meta/llama-3.2-90b-vision-instruct a través de NIM. La
imagen se envía codificada dentro de la propia petición (ver comun/nim.py).

Uso
---
  python recetas/10_describir_imagenes.py foto_producto.jpg
  python recetas/10_describir_imagenes.py zapatilla.png --contexto "zapatilla deportiva para correr"
  python recetas/10_describir_imagenes.py          (usa datos/producto_ejemplo.png)
  python recetas/10_describir_imagenes.py --demo   (sin clave: respuestas pregrabadas)

Formatos: jpg, png y webp. Las imágenes muy grandes gastan más tokens: si
puedes, redúcelas a unos 1000 px de lado antes de enviarlas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


def generar_alt_text(ruta_imagen):
    """ALT-TEXT: una sola frase, factual, sin florituras."""
    prompt = (
        "Describe esta imagen en UNA sola frase corta en espanol, para usar como "
        "texto alternativo (alt-text) de accesibilidad. Se factual y concreto: "
        "que se ve, no interpretaciones. Sin empezar con 'una imagen de'."
    )
    return nim.vision(prompt, ruta_imagen, max_tokens=120)


def generar_descripcion_producto(ruta_imagen, contexto):
    """DESCRIPCION comercial: un párrafo atractivo para una ficha de producto."""
    extra = f" El producto es: {contexto}." if contexto else ""
    prompt = (
        "Escribe una descripcion de producto en espanol para una tienda online, "
        "basandote en lo que ves en la imagen." + extra + " Un parrafo (3-4 frases), "
        "atractivo pero honesto, resaltando materiales, color, estilo y posible uso. "
        "No inventes caracteristicas que no puedas ver."
    )
    return nim.vision(prompt, ruta_imagen, max_tokens=300)


def main():
    parser = nim.nuevo_parser("Describe una imagen con IA de vision.")
    parser.add_argument(
        "imagen",
        nargs="?",
        default=str(nim.ruta_datos("producto_ejemplo.png")),
        help="Ruta a la imagen: jpg, png o webp (por defecto datos/producto_ejemplo.png).",
    )
    parser.add_argument(
        "--contexto", default="", help="Pista opcional sobre que es el producto."
    )
    args = parser.parse_args()

    ruta = Path(args.imagen)
    if not ruta.exists():
        print(f"No encuentro la imagen: {ruta}")
        print("Pasa la ruta de una imagen tuya, por ejemplo: foto.jpg")
        sys.exit(1)

    print("Analizando la imagen...\n")

    print("ALT-TEXT (accesibilidad / SEO)")
    print("-" * 60)
    print(generar_alt_text(ruta))

    print("\nDESCRIPCION DE PRODUCTO")
    print("-" * 60)
    print(generar_descripcion_producto(ruta, args.contexto))


if __name__ == "__main__":
    nim.ejecutar(main)
