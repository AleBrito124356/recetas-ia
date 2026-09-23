"""
Receta 01 - Resumir un PDF
==========================

Qué automatiza
--------------
Convierte cualquier PDF (un contrato, un informe, un paper, un manual) en un
resumen ejecutivo de pocas líneas más una lista de puntos clave. Ideal para
decidir en 30 segundos si un documento merece que lo leas entero.

Cómo funciona
-------------
1. Extrae el texto del PDF con `pypdf` (sin conexión, todo local).
2. Si el documento es largo, lo parte en trozos de como mucho `--tam-trozo`
   caracteres y resume cada trozo. Esto se llama estrategia "map-reduce":
   primero resumes las partes (map) y luego resumes los resúmenes (reduce).
   Si los resúmenes juntos siguen sin caber, se repite la reducción por
   rondas. Ningún trozo supera el límite: los párrafos gigantes se parten por
   líneas, frases o palabras. Así cabe en la ventana de contexto del modelo
   por muy largo que sea el PDF.
3. Pide al modelo un resumen ejecutivo + puntos clave en un formato limpio.

Uso
---
  python recetas/01_resumir_pdf.py                      (usa datos/informe_ejemplo.pdf)
  python recetas/01_resumir_pdf.py ruta/al/documento.pdf
  python recetas/01_resumir_pdf.py informe.pdf --puntos 8
  python recetas/01_resumir_pdf.py --demo               (sin clave: respuesta pregrabada)
"""

import re
import sys
from pathlib import Path

# Añadimos la raíz del repo al path para poder importar `comun` sin instalar
# nada. Este mismo bloque aparece en todas las recetas: hace que funcionen
# desde cualquier carpeta.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

TAM_TROZO = 9000  # caracteres por trozo: holgado para modelos de 8k+ tokens
MAX_RONDAS = 4  # rondas de reducción; cada una divide el texto ~5 veces


def extraer_texto_pdf(ruta_pdf):
    """Devuelve (texto plano de todas las páginas, número de páginas)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Falta 'pypdf'. Instala dependencias con: pip install -r requirements.txt")
        sys.exit(1)

    lector = PdfReader(str(ruta_pdf))
    # `extract_text` puede devolver None en páginas sin capa de texto (por
    # ejemplo, escaneos). Filtramos esos casos para no romper el join.
    paginas = [(pagina.extract_text() or "") for pagina in lector.pages]
    return limpiar_texto("\n\n".join(paginas)), len(lector.pages)


def limpiar_texto(texto):
    """
    Normaliza espacios: quita espacios repetidos y líneas vacías sobrantes.
    Ahorra tokens y hace que el mismo PDF dé siempre el mismo texto.
    """
    lineas = [" ".join(linea.split()) for linea in texto.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()


# Niveles de corte, de más a menos natural: líneas, frases y palabras.
_NIVELES = (
    ("\n", re.compile(r"\n")),
    (" ", re.compile(r"(?<=[.!?;:])\s+")),
    (" ", re.compile(r"\s+")),
)


def _empaquetar(piezas, tam_max, union):
    """Junta piezas consecutivas mientras quepan en `tam_max`."""
    trozos, actual = [], ""
    for pieza in piezas:
        candidato = f"{actual}{union}{pieza}" if actual else pieza
        if len(candidato) > tam_max and actual:
            trozos.append(actual)
            actual = pieza
        else:
            actual = candidato
    if actual:
        trozos.append(actual)
    return trozos


def _partir(texto, tam_max, nivel=0):
    """Parte un bloque demasiado largo por el corte más natural posible."""
    if len(texto) <= tam_max:
        return [texto]
    if nivel >= len(_NIVELES):
        # Una "palabra" más larga que el límite (p. ej. una URL enorme): a cuchillo.
        return [texto[i : i + tam_max] for i in range(0, len(texto), tam_max)]
    union, patron = _NIVELES[nivel]
    piezas = [p for p in patron.split(texto) if p.strip()]
    if len(piezas) <= 1:
        return _partir(texto, tam_max, nivel + 1)
    menores = []
    for pieza in piezas:
        menores.extend(_partir(pieza, tam_max, nivel + 1))
    return _empaquetar(menores, tam_max, union)


def trocear(texto, tam_max=TAM_TROZO):
    """
    Parte el texto en trozos de como mucho `tam_max` caracteres (garantizado).

    Primero corta por párrafos (líneas en blanco) para no partir una idea por
    la mitad. Si un párrafo solo ya es más largo que el límite, lo corta por
    líneas, luego por frases y, como último recurso, por palabras.
    """
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    piezas = []
    for parrafo in parrafos:
        piezas.extend(_partir(parrafo, tam_max))
    return _empaquetar(piezas, tam_max, "\n\n")


def resumir_trozo(trozo):
    """Resume un fragmento en un párrafo denso. Es la fase 'map'."""
    return nim.chat(
        prompt=f"Resume el siguiente fragmento en un parrafo, sin perder datos "
        f"ni cifras importantes:\n\n{trozo}",
        sistema="Eres un analista que hace resumenes precisos y concisos en espanol.",
        temperatura=0.2,
        max_tokens=400,
    )


def condensar(texto, tam_max=TAM_TROZO, max_rondas=MAX_RONDAS):
    """
    Reduce el texto por rondas de map-reduce hasta que cabe en un solo trozo.

    Ronda 1: 40 trozos -> 40 resúmenes. Si esos resúmenes juntos aún no caben,
    ronda 2: se trocean y se resumen otra vez, y así hasta `max_rondas`.
    """
    trozos = trocear(texto, tam_max)
    ronda = 0
    while len(trozos) > 1 and ronda < max_rondas:
        ronda += 1
        print(f"Documento largo: ronda {ronda}, resumiendo {len(trozos)} partes...")
        resumenes = []
        for i, trozo in enumerate(trozos, start=1):
            print(f"  parte {i}/{len(trozos)}")
            resumenes.append(resumir_trozo(trozo))
        trozos = trocear("\n\n".join(resumenes), tam_max)
    return "\n\n".join(trozos)


def resumen_final(texto, num_puntos):
    """Genera el resumen ejecutivo y los puntos clave. Es la fase 'reduce'."""
    sistema = (
        "Eres un analista experto. Escribes en espanol claro y profesional. "
        "No inventas informacion que no este en el texto."
    )
    prompt = (
        "A partir del siguiente contenido, entrega EXACTAMENTE este formato:\n\n"
        "RESUMEN EJECUTIVO:\n"
        "(2 a 4 frases que capturen la esencia)\n\n"
        f"PUNTOS CLAVE:\n"
        f"(exactamente {num_puntos} vinetas, cada una empezando con '- ', "
        "concretas y con datos si los hay)\n\n"
        f"CONTENIDO:\n{texto}"
    )
    return nim.chat(prompt=prompt, sistema=sistema, temperatura=0.3, max_tokens=900)


def main():
    parser = nim.nuevo_parser("Resume un PDF con NVIDIA NIM.")
    parser.add_argument(
        "pdf",
        nargs="?",
        default=str(nim.ruta_datos("informe_ejemplo.pdf")),
        help="Ruta al PDF a resumir (por defecto datos/informe_ejemplo.pdf).",
    )
    parser.add_argument(
        "--puntos", type=int, default=6, help="Numero de puntos clave (por defecto 6)."
    )
    parser.add_argument(
        "--tam-trozo",
        type=int,
        default=TAM_TROZO,
        help=f"Caracteres maximos por trozo en el map-reduce (por defecto {TAM_TROZO}).",
    )
    args = parser.parse_args()

    ruta = Path(args.pdf)
    if not ruta.exists():
        print(f"No encuentro el archivo: {ruta}")
        sys.exit(1)

    print(f"Leyendo {ruta.name} ...")
    texto, num_paginas = extraer_texto_pdf(ruta)
    if not texto:
        print(
            "No pude extraer texto. Puede que el PDF sea un escaneo (imagenes).\n"
            "En ese caso primero pasalo por un motor de OCR y vuelve a probar."
        )
        sys.exit(1)

    print(f"{num_paginas} paginas, {len(texto):,} caracteres extraidos.")
    contenido = condensar(texto, max(500, args.tam_trozo))

    print("Generando resumen final...\n")
    salida = resumen_final(contenido, args.puntos)

    print("=" * 60)
    print(salida)
    print("=" * 60)


if __name__ == "__main__":
    nim.ejecutar(main)
