"""
Receta 04 - Responder reseñas de clientes
=========================================

Qué automatiza
--------------
Genera borradores de respuesta para reseñas de Google, redes o cualquier
plataforma. Adapta el tono, agradece lo positivo y responde con profesionalismo
lo negativo sin sonar a robot.

IMPORTANTE: esta receta produce BORRADORES. Nunca publica nada automáticamente.
Tú revisas, editas si hace falta y publicas a mano. Responder reseñas es
reputación de marca: la última palabra siempre es humana.

Uso
---
  python recetas/04_responder_resenas.py
  python recetas/04_responder_resenas.py --tono cercano --negocio "Cafe Aroma"
  python recetas/04_responder_resenas.py --archivo datos/resenas.txt --salida borradores.txt
  python recetas/04_responder_resenas.py --demo      (sin clave: respuestas pregrabadas)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

# Descripción de cada tono. Editar estos textos cambia por completo la voz de
# las respuestas sin tocar la lógica: es el "panel de control" de la receta.
TONOS = {
    "profesional": "cordial y profesional, trato de usted, correcto y sobrio",
    "cercano": "cálido y cercano, trato de tú, amable y humano sin exagerar",
    "formal": "muy formal y protocolario, ideal para servicios corporativos o legales",
}


def separar_resenas(texto):
    """
    Separa el archivo en reseñas individuales.

    Convención del archivo de ejemplo: cada reseña va separada de la siguiente
    por una línea con tres guiones (---). Es simple y fácil de editar a mano.
    """
    bloques = [b.strip() for b in texto.split("---")]
    return [b for b in bloques if b]


def responder(resena, negocio, descripcion_tono):
    """Genera un borrador de respuesta para una reseña concreta."""
    sistema = (
        f"Eres quien gestiona la reputacion de '{negocio}'. Redactas respuestas "
        f"a resenas con un tono {descripcion_tono}. Reglas: agradece siempre, "
        "personaliza segun lo que dice el cliente, si hay una queja reconocela y "
        "ofrece una solucion o un canal de contacto, nunca discutas ni te pongas "
        "a la defensiva, y se breve (2 a 4 frases). Responde en espanol."
    )
    prompt = f"Redacta la respuesta a esta resena:\n\n\"{resena}\""
    return nim.chat(prompt=prompt, sistema=sistema, temperatura=0.6, max_tokens=300)


def main():
    parser = nim.nuevo_parser("Genera borradores de respuesta a resenas.")
    parser.add_argument(
        "--archivo",
        default=str(nim.ruta_datos("resenas.txt")),
        help="Archivo con las resenas separadas por '---' (por defecto el de ejemplo).",
    )
    parser.add_argument("--negocio", default="tu negocio", help="Nombre del negocio.")
    parser.add_argument(
        "--tono",
        choices=list(TONOS.keys()),
        default="profesional",
        help="Tono de las respuestas.",
    )
    parser.add_argument("--salida", help="Archivo donde guardar los borradores.")
    args = parser.parse_args()

    ruta = Path(args.archivo)
    if not ruta.exists():
        print(f"No encuentro el archivo de resenas: {ruta}")
        sys.exit(1)

    resenas = separar_resenas(ruta.read_text(encoding="utf-8"))
    print(f"{len(resenas)} resenas encontradas. Tono: {args.tono}.\n")

    lineas_salida = []
    for i, resena in enumerate(resenas, start=1):
        respuesta = responder(resena, args.negocio, TONOS[args.tono])
        bloque = (
            f"RESENA {i}\n"
            f"{resena}\n\n"
            f"BORRADOR DE RESPUESTA:\n{respuesta}\n"
            f"{'-' * 60}"
        )
        print(bloque + "\n")
        lineas_salida.append(bloque)

    print(">> Recuerda: son BORRADORES. Revisa y edita antes de publicar.")

    if args.salida:
        Path(args.salida).write_text("\n".join(lineas_salida), encoding="utf-8")
        print(f">> Borradores guardados en: {args.salida}")


if __name__ == "__main__":
    nim.ejecutar(main)
