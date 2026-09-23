"""
Receta 07 - Traducir subtítulos .srt
====================================

Qué automatiza
--------------
Traduce un archivo de subtítulos .srt a otro idioma conservando EXACTAMENTE las
marcas de tiempo y la numeración. Solo cambia el texto; los tiempos quedan
intactos para que el subtítulo siga sincronizado con el video. También se
respeta el formato del archivo: si un subtítulo ocupaba dos líneas, la
traducción también ocupa dos; los saltos de línea (\\r\\n de Windows o \\n) y
el BOM de UTF-8 se conservan tal cual.

Truco de eficiencia: en lugar de traducir línea por línea, mandamos varios
subtítulos juntos con un separador especial y los volvemos a partir. Menos
llamadas = más rápido y menos créditos.

Uso
---
  python recetas/07_traducir_subtitulos.py              (usa datos/subtitulos_ejemplo.srt)
  python recetas/07_traducir_subtitulos.py video.srt --idioma "ingles" --salida video_en.srt
  python recetas/07_traducir_subtitulos.py --demo
"""

import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

# Separador improbable de aparecer en un subtítulo. Lo usamos para unir varios
# textos en una sola petición y luego volver a separarlos sin ambigüedad.
SEPARADOR = "\n<<<>>>\n"
BOM = "\ufeff"  # marca de orden de bytes que algunos editores ponen al inicio


def parsear_srt(contenido):
    """
    Convierte el texto de un .srt en una lista de bloques.

    Cada bloque de un .srt tiene: un número, una línea de tiempos
    (00:00:01,000 --> 00:00:04,000) y una o más líneas de texto. Los bloques se
    separan por una línea en blanco. Devolvemos [(indice, tiempos, lineas), ...]
    donde `lineas` es la lista de líneas de texto del subtítulo.
    """
    contenido = contenido.lstrip(BOM).replace("\r\n", "\n").replace("\r", "\n")
    bloques, actual = [], []
    for linea in contenido.split("\n") + [""]:
        if linea.strip():
            actual.append(linea.rstrip())
            continue
        # Línea en blanco: cierra el bloque (si lo hay).
        if len(actual) >= 2 and "-->" in actual[1]:
            bloques.append((actual[0].strip(), actual[1].strip(), actual[2:]))
        actual = []
    return bloques


def texto_de(lineas):
    """Las líneas de un subtítulo en una sola frase, para traducirla entera."""
    return " ".join(l.strip() for l in lineas if l.strip())


def reenvolver(texto, n_lineas):
    """
    Reparte `texto` en `n_lineas` líneas equilibradas, cortando entre palabras.

    Así un subtítulo de 2 líneas sigue ocupando 2 líneas en el otro idioma, en
    vez de convertirse en una línea larguísima que tape medio video. Probamos
    todos los cortes posibles (son pocas palabras) y nos quedamos con el que
    deja la línea más larga lo más corta posible.
    """
    palabras = texto.split()
    if n_lineas <= 1 or len(palabras) < 2:
        return [" ".join(palabras)]
    n_lineas = min(n_lineas, len(palabras))
    total = len(palabras)

    @lru_cache(maxsize=None)
    def mejor(inicio, lineas):
        """(largo de la línea más larga, cortes) para palabras[inicio:] en `lineas`."""
        if lineas == 1:
            return (len(" ".join(palabras[inicio:])), (total,))
        opciones = []
        for corte in range(inicio + 1, total - lineas + 2):
            resto = mejor(corte, lineas - 1)
            largo = max(len(" ".join(palabras[inicio:corte])), resto[0])
            opciones.append((largo, (corte,) + resto[1]))
        return min(opciones)

    lineas, desde = [], 0
    for hasta in mejor(0, n_lineas)[1]:
        lineas.append(" ".join(palabras[desde:hasta]))
        desde = hasta
    return lineas


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
    # cada posición que falte se rellena con SU texto original (el de la misma
    # posición), para que ningún subtítulo quede con el texto de otro.
    if len(partes) != len(textos):
        print(
            f"  aviso: esperaba {len(textos)} fragmentos y recibi {len(partes)}. "
            "Donde falte traduccion se deja el texto original."
        )
        partes = (partes + textos[len(partes) :])[: len(textos)]
    return partes


def reconstruir_srt(bloques, textos_traducidos, salto="\n"):
    """
    Vuelve a armar el .srt con los tiempos originales y el texto traducido.

    `textos_traducidos` puede traer un texto (str) o ya las líneas (list) de
    cada subtítulo. Un texto se reparte en tantas líneas como tenía el original.
    """
    piezas = []
    for (indice, tiempos, lineas_originales), texto in zip(bloques, textos_traducidos):
        lineas = texto if isinstance(texto, list) else reenvolver(texto, len(lineas_originales))
        piezas.append(salto.join([indice, tiempos] + lineas))
    return (salto * 2).join(piezas) + salto


def leer_srt(ruta):
    """Lee el archivo y devuelve (bloques, salto_de_linea, tiene_bom)."""
    crudo = Path(ruta).read_bytes().decode("utf-8")
    salto = "\r\n" if "\r\n" in crudo else "\n"
    return parsear_srt(crudo), salto, crudo.startswith(BOM)


def escribir_srt(ruta, bloques, textos, salto="\n", con_bom=False):
    """Escribe el .srt respetando el salto de línea y el BOM del original."""
    contenido = reconstruir_srt(bloques, textos, salto)
    Path(ruta).write_bytes(((BOM if con_bom else "") + contenido).encode("utf-8"))


def main():
    parser = nim.nuevo_parser("Traduce un archivo .srt de subtitulos.")
    parser.add_argument(
        "srt",
        nargs="?",
        default=str(nim.ruta_datos("subtitulos_ejemplo.srt")),
        help="Ruta al .srt de entrada (por defecto datos/subtitulos_ejemplo.srt).",
    )
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

    bloques, salto, con_bom = leer_srt(ruta)
    if not bloques:
        print("No se encontraron subtitulos validos en el archivo.")
        sys.exit(1)

    lote = max(1, args.lote)
    print(f"{len(bloques)} subtitulos. Traduciendo al {args.idioma} en lotes de {lote}...")

    textos = [texto_de(lineas) for _, _, lineas in bloques]
    traducidos = []
    for inicio in range(0, len(textos), lote):
        print(f"  lote {inicio // lote + 1}")
        traducidos.extend(traducir_lote(textos[inicio : inicio + lote], args.idioma))

    salida = Path(args.salida) if args.salida else ruta.with_name(ruta.stem + "_traducido.srt")
    escribir_srt(salida, bloques, traducidos, salto, con_bom)
    print(f"\nListo. Subtitulos traducidos en: {salida}")


if __name__ == "__main__":
    nim.ejecutar(main)
