"""
Receta 09 - Analizar respuestas abiertas de una encuesta
========================================================

Qué automatiza
--------------
Toma un CSV con respuestas de texto libre (lo más difícil de analizar de
cualquier encuesta) y saca: los temas recurrentes, el sentimiento general,
citas representativas de cada tema y un resumen ejecutivo. Lo que a mano te
tomaría una tarde, en una llamada.

Uso
---
  python recetas/09_analizar_encuesta.py
  python recetas/09_analizar_encuesta.py --csv datos/encuesta.csv --columna respuesta
"""

import sys
import csv
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


def leer_respuestas(ruta_csv, columna):
    """Lee la columna indicada del CSV y devuelve la lista de respuestas no vacías."""
    with open(ruta_csv, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    if not filas:
        print("El CSV esta vacio.")
        sys.exit(1)
    if columna not in filas[0]:
        print(f"La columna '{columna}' no existe. Columnas disponibles: {list(filas[0].keys())}")
        sys.exit(1)
    return [fila[columna].strip() for fila in filas if fila.get(columna, "").strip()]


def analizar(respuestas):
    """
    Pide al modelo un análisis estructurado en JSON.

    Numeramos las respuestas para que las citas puedan referirse a ellas y no se
    inventen. Pedimos JSON para poder formatear el informe nosotros.
    """
    lista = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(respuestas))
    sistema = (
        "Eres un analista de investigacion de mercado. Analizas respuestas "
        "abiertas de encuestas y devuelves SOLO JSON valido en espanol."
    )
    prompt = (
        "Analiza estas respuestas de encuesta y devuelve un JSON con esta forma:\n"
        "{\n"
        '  "sentimiento_general": {"positivo": 0, "neutral": 0, "negativo": 0},  '
        "(porcentajes que sumen 100)\n"
        '  "temas": [\n'
        '     {"tema": "nombre corto", "menciones": 0, "resumen": "1 frase", '
        '"cita": "una cita textual representativa"}\n'
        "  ],\n"
        '  "resumen_ejecutivo": "3 a 5 frases con los hallazgos principales"\n'
        "}\n\n"
        "Identifica entre 3 y 6 temas, ordenados por numero de menciones.\n\n"
        f"RESPUESTAS:\n{lista}"
    )
    respuesta = nim.chat(prompt=prompt, sistema=sistema, temperatura=0.2, max_tokens=1800)
    return nim.extraer_json(respuesta)


def imprimir_informe(analisis, total):
    """Da formato legible al JSON del análisis."""
    print("=" * 60)
    print(f"ANALISIS DE ENCUESTA  ({total} respuestas)")
    print("=" * 60)

    sent = analisis.get("sentimiento_general", {})
    print("\nSENTIMIENTO GENERAL")
    for etiqueta in ("positivo", "neutral", "negativo"):
        valor = sent.get(etiqueta, 0)
        barra = "#" * int(valor / 5)  # una barrita simple de texto
        print(f"  {etiqueta.capitalize():9} {valor:3}%  {barra}")

    print("\nTEMAS PRINCIPALES")
    for i, tema in enumerate(analisis.get("temas", []), start=1):
        print(f"\n  {i}. {tema.get('tema')}  ({tema.get('menciones')} menciones)")
        print(f"     {tema.get('resumen')}")
        cita = tema.get("cita")
        if cita:
            print(f"     Cita: \"{cita}\"")

    print("\nRESUMEN EJECUTIVO")
    print(f"  {analisis.get('resumen_ejecutivo')}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Analiza respuestas abiertas de una encuesta.")
    parser.add_argument(
        "--csv",
        default=str(nim.ruta_datos("encuesta.csv")),
        help="CSV con las respuestas (por defecto el de ejemplo).",
    )
    parser.add_argument(
        "--columna", default="respuesta", help="Nombre de la columna con el texto libre."
    )
    args = parser.parse_args()

    ruta = Path(args.csv)
    if not ruta.exists():
        print(f"No encuentro el CSV: {ruta}")
        sys.exit(1)

    respuestas = leer_respuestas(ruta, args.columna)
    print(f"Analizando {len(respuestas)} respuestas...\n")
    analisis = analizar(respuestas)
    imprimir_informe(analisis, len(respuestas))


if __name__ == "__main__":
    main()
