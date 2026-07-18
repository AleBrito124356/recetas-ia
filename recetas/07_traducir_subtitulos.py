"""
Receta 07 - Traducir subtítulos .srt
====================================

Qué automatiza
--------------
Traduce un archivo de subtítulos .srt a otro idioma conservando EXACTAMENTE las
marcas de tiempo y la numeración. Solo cambia el texto; los tiempos quedan
intactos para que el subtítulo siga sincronizado con el video.

Truco de eficiencia: en lugar de traducir línea por línea, mandamos varios
subtítulos juntos con un separador especial y los volvemos a partir. Menos
llamadas = más rápido y menos créditos.

Uso
---
  python recetas/07_traducir_subtitulos.py datos/subtitulos_ejemplo.srt
  python recetas/07_traducir_subtitulos.py video.srt --idioma "ingles" --salida video_en.srt
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

# Separador improbable de aparecer en un subtítulo. Lo usamos para unir varios
# textos en una sola petición y luego volver a separarlos sin ambigüedad.
SEPARADOR = "\n<<<>>>\n"


def parsear_srt(contenido):
    """
    Convierte el texto de un .srt en una lista de bloques.

    Cada bloque de un .srt tiene: un número, una línea de tiempos
    (00:00:01,000 --> 00:00:04,000) y una o más líneas de texto. Los bloques se
    separan por una línea en blanco. Devolvemos [(indice, tiempos, texto), ...].
    """
    bloques = []
    for bruto in contenido.strip().split("\n\n"):
        lineas = bruto.strip().splitlines()
        if len(lineas) >= 2 and "-->" in lineas[1]:
            indice = lineas[0].strip()
            tiempos = lineas[1].strip()
            texto = " ".join(l.strip() for l in lineas[2:])
            bloques.append((indice, tiempos, texto))
    return bloques


def traducir_lote(textos, idioma_destino):
    """Traduce una lista de textos en una sola llamada, manteniendo el orden."""
    unido = SEPARADOR.join(textos)
    sistema = (
        f"Eres un traductor profesional de subtitulos al {idioma_destino}. "
        "Traduces de forma natural y concisa (los subtitulos deben leerse rapido). "
        f"Respetas el separador '{SEPARADOR.strip()}' entre fragmentos y devuelves "
        "EXACTAMENTE el mismo numero de fragmentos en el mismo orden, sin numerarlos."
    )
    prompt = (
        f"Traduce cada fragmento al {idioma_destino}. Manten el separador tal cual "
        f"entre fragmentos:\n\n{unido}"
    )
    respuesta = nim.chat(prompt=prompt, sistema=sistema, temperatura=0.3, max_tokens=3000)
    partes = [p.strip() for p in respuesta.split(SEPARADOR.strip())]

    # Red de seguridad: si el modelo devolvió otra cantidad de fragmentos,
    # rellenamos con el original para no desalinear los tiempos.
    if len(partes) != len(textos):
        print(
            f"  aviso: esperaba {len(textos)} fragmentos y recibi {len(partes)}. "
            "Se completa con el texto original donde falte."
        )
        partes = (partes + textos)[: len(textos)]
    return partes


def reconstruir_srt(bloques, textos_traducidos):
    """Vuelve a armar el .srt con los tiempos originales y el texto traducido."""
    piezas = []
    for (indice, tiempos, _), texto in zip(bloques, textos_traducidos):
        piezas.append(f"{indice}\n{tiempos}\n{texto}")
    return "\n\n".join(piezas) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Traduce un archivo .srt de subtitulos.")
    parser.add_argument("srt", help="Ruta al archivo .srt de entrada.")
    parser.add_argument(
        "--idioma", default="ingles", help="Idioma de destino (por defecto ingles)."
    )
    parser.add_argument("--salida", help="Ruta del .srt traducido (por defecto agrega sufijo).")
    parser.add_argument(
        "--lote", type=int, default=20, help="Cuantos subtitulos traducir por llamada."
    )
    args = parser.parse_args()

    ruta = Path(args.srt)
    if not ruta.exists():
        print(f"No encuentro el archivo: {ruta}")
        sys.exit(1)

    bloques = parsear_srt(ruta.read_text(encoding="utf-8"))
    if not bloques:
        print("No se encontraron subtitulos validos en el archivo.")
        sys.exit(1)

    print(f"{len(bloques)} subtitulos. Traduciendo al {args.idioma} en lotes de {args.lote}...")

    textos = [b[2] for b in bloques]
    traducidos = []
    for inicio in range(0, len(textos), args.lote):
        lote = textos[inicio : inicio + args.lote]
        print(f"  lote {inicio // args.lote + 1}")
        traducidos.extend(traducir_lote(lote, args.idioma))

    resultado = reconstruir_srt(bloques, traducidos)

    salida = Path(args.salida) if args.salida else ruta.with_name(ruta.stem + "_traducido.srt")
    salida.write_text(resultado, encoding="utf-8")
    print(f"\nListo. Subtitulos traducidos en: {salida}")


if __name__ == "__main__":
    main()
