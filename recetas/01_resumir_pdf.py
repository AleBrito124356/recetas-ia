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
2. Si el documento es largo, lo parte en trozos y resume cada trozo. Esto se
   llama estrategia "map-reduce": primero resumes las partes (map) y luego
   resumes los resúmenes (reduce). Así cabe en la ventana de contexto del
   modelo por muy largo que sea el PDF.
3. Pide al modelo un resumen ejecutivo + puntos clave en un formato limpio.

Uso
---
  python recetas/01_resumir_pdf.py ruta/al/documento.pdf
  python recetas/01_resumir_pdf.py informe.pdf --puntos 8
"""

import sys
import argparse
from pathlib import Path

# Añadimos la raíz del repo al path para poder importar `comun` sin instalar
# nada. Este mismo bloque aparece en todas las recetas: hace que funcionen
# desde cualquier carpeta.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


def extraer_texto_pdf(ruta_pdf):
    """Devuelve el texto plano de todas las páginas del PDF."""
    try:
        from pypdf import PdfReader
    except ImportError:
        print("Falta 'pypdf'. Instala dependencias con: pip install -r requirements.txt")
        sys.exit(1)

    lector = PdfReader(str(ruta_pdf))
    # `extract_text` puede devolver None en páginas sin capa de texto (por
    # ejemplo, escaneos). Filtramos esos casos para no romper el join.
    paginas = [(pagina.extract_text() or "") for pagina in lector.pages]
    texto = "\n\n".join(paginas).strip()
    return texto, len(lector.pages)


def trocear(texto, tam_max=9000):
    """
    Parte el texto en trozos de como mucho `tam_max` caracteres.

    Cortamos por párrafos (dobles saltos de línea) para no partir una frase por
    la mitad. Es una heurística simple pero suficiente para resumir.
    """
    parrafos = texto.split("\n\n")
    trozos, actual = [], ""
    for parrafo in parrafos:
        if len(actual) + len(parrafo) + 2 > tam_max and actual:
            trozos.append(actual)
            actual = parrafo
        else:
            actual = f"{actual}\n\n{parrafo}" if actual else parrafo
    if actual:
        trozos.append(actual)
    return trozos


def resumir_trozo(trozo):
    """Resume un fragmento en un párrafo denso. Es la fase 'map'."""
    return nim.chat(
        prompt=f"Resume el siguiente fragmento en un parrafo, sin perder datos "
        f"ni cifras importantes:\n\n{trozo}",
        sistema="Eres un analista que hace resumenes precisos y concisos en espanol.",
        temperatura=0.2,
        max_tokens=400,
    )


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
    parser = argparse.ArgumentParser(description="Resume un PDF con NVIDIA NIM.")
    parser.add_argument("pdf", help="Ruta al archivo PDF a resumir.")
    parser.add_argument(
        "--puntos", type=int, default=6, help="Numero de puntos clave (por defecto 6)."
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
            "En ese caso primero pasalo por OCR (mira la receta 03 para audio, o "
            "usa un motor de OCR sobre las imagenes)."
        )
        sys.exit(1)

    print(f"{num_paginas} paginas, {len(texto):,} caracteres extraidos.")

    trozos = trocear(texto)
    if len(trozos) == 1:
        contenido = trozos[0]
    else:
        # Documento largo: resumimos por partes y luego juntamos.
        print(f"Documento largo: resumiendo en {len(trozos)} partes...")
        resumenes = []
        for i, trozo in enumerate(trozos, start=1):
            print(f"  parte {i}/{len(trozos)}")
            resumenes.append(resumir_trozo(trozo))
        contenido = "\n\n".join(resumenes)

    print("Generando resumen final...\n")
    salida = resumen_final(contenido, args.puntos)

    print("=" * 60)
    print(salida)
    print("=" * 60)


if __name__ == "__main__":
    main()
