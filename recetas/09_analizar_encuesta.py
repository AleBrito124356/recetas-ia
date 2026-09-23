"""
Receta 09 - Analizar respuestas abiertas de una encuesta
========================================================

Qué automatiza
--------------
Toma un CSV con respuestas de texto libre (lo más difícil de analizar de
cualquier encuesta) y saca: los temas recurrentes, el sentimiento general,
citas representativas de cada tema y un resumen ejecutivo. Lo que a mano te
tomaría una tarde, en una llamada.

No nos fiamos a ciegas del modelo:
  - los porcentajes de sentimiento se normalizan para que sumen 100 aunque el
    modelo escriba "60%", "60" o 0.6;
  - cada cita se busca en las respuestas originales; si no aparece tal cual,
    el informe lo marca para que la revises (un modelo puede "mejorar" una
    cita o inventarla).

Uso
---
  python recetas/09_analizar_encuesta.py
  python recetas/09_analizar_encuesta.py --csv datos/encuesta.csv --columna respuesta
  python recetas/09_analizar_encuesta.py --demo
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402
from comun.formatos import normalizar_texto, parsear_numero, parsear_porcentaje  # noqa: E402

ETIQUETAS = ("positivo", "neutral", "negativo")
COMILLAS = "\"'«»“”‘’.…"


def leer_respuestas(ruta_csv, columna):
    """
    Lee la columna indicada del CSV y devuelve la lista de respuestas no vacías.

    Las respuestas abiertas suelen llevar comas ("Simple, directa y..."). Si el
    CSV se escribió a mano sin comillas, el lector las toma por separadores y
    corta la respuesta. Cuando la columna de texto es la última, volvemos a
    unir esos trozos sobrantes para no perder la mitad de cada opinión.
    """
    with open(ruta_csv, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        filas = list(lector)
    if not filas:
        print("El CSV esta vacio.")
        sys.exit(1)
    columnas = lector.fieldnames or []
    if columna not in columnas:
        print(f"La columna '{columna}' no existe. Columnas disponibles: {columnas}")
        sys.exit(1)

    respuestas = []
    for fila in filas:
        texto = fila.get(columna) or ""
        sobrante = fila.get(None)  # campos de más: comas sin comillas en el texto
        if sobrante and columna == columnas[-1]:
            texto = ",".join([texto] + sobrante)
        if texto.strip():
            respuestas.append(texto.strip())
    return respuestas


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
    return nim.extraer_json(respuesta, esperado=dict)


def normalizar_sentimiento(sentimiento):
    """
    Convierte lo que devuelva el modelo en porcentajes enteros que suman 100.

    Acepta "60%", "60", 60 o 0.6, claves con tilde o mayúsculas, y valores que
    no suman 100 (se reescalan). El redondeo usa el método del "mayor resto":
    se redondea hacia abajo y los puntos que faltan van a los decimales más
    grandes, así la suma es siempre exactamente 100.
    """
    if not isinstance(sentimiento, dict):
        sentimiento = {}
    por_clave = {normalizar_texto(k): v for k, v in sentimiento.items()}
    valores = {}
    for etiqueta in ETIQUETAS:
        numero = parsear_porcentaje(por_clave.get(etiqueta))
        valores[etiqueta] = max(0.0, numero) if numero is not None else 0.0
    total = sum(valores.values())
    if total <= 0:
        return {etiqueta: 0 for etiqueta in ETIQUETAS}
    escalados = {e: valores[e] * 100 / total for e in ETIQUETAS}
    enteros = {e: int(escalados[e]) for e in ETIQUETAS}
    faltan = 100 - sum(enteros.values())
    for e in sorted(ETIQUETAS, key=lambda e: escalados[e] - enteros[e], reverse=True)[:faltan]:
        enteros[e] += 1
    return enteros


def cita_textual(cita, respuestas):
    """True si la cita aparece tal cual (sin mirar tildes ni mayúsculas) en alguna respuesta."""
    buscada = normalizar_texto(str(cita).strip().strip(COMILLAS).strip())
    if not buscada:
        return False
    return any(buscada in normalizar_texto(r) for r in respuestas)


def imprimir_informe(analisis, total, respuestas=None):
    """Da formato legible al JSON del análisis."""
    print("=" * 60)
    print(f"ANALISIS DE ENCUESTA  ({total} respuestas)")
    print("=" * 60)

    sentimiento = normalizar_sentimiento(analisis.get("sentimiento_general"))
    print("\nSENTIMIENTO GENERAL")
    for etiqueta in ETIQUETAS:
        valor = sentimiento[etiqueta]
        barra = "#" * int(valor / 5)  # una barrita simple de texto
        print(f"  {etiqueta.capitalize():9} {valor:3}%  {barra}")

    print("\nTEMAS PRINCIPALES")
    temas = analisis.get("temas")
    for i, tema in enumerate(temas if isinstance(temas, list) else [], start=1):
        if not isinstance(tema, dict):
            tema = {"tema": str(tema)}
        menciones = parsear_numero(tema.get("menciones"))
        cuantas = f"{int(menciones)} menciones" if menciones is not None else "sin conteo"
        print(f"\n  {i}. {tema.get('tema', '(sin nombre)')}  ({cuantas})")
        if tema.get("resumen"):
            print(f"     {tema.get('resumen')}")
        cita = tema.get("cita")
        if cita:
            print(f'     Cita: "{cita}"')
            if respuestas is not None and not cita_textual(cita, respuestas):
                print("     (!) Esta cita no aparece tal cual en las respuestas: revisala.")

    print("\nRESUMEN EJECUTIVO")
    print(f"  {analisis.get('resumen_ejecutivo') or '(el modelo no lo incluyo)'}")
    print("=" * 60)


def main():
    parser = nim.nuevo_parser("Analiza respuestas abiertas de una encuesta.")
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
    if not respuestas:
        print(f"La columna '{args.columna}' no tiene respuestas con texto.")
        sys.exit(1)
    print(f"Analizando {len(respuestas)} respuestas...\n")
    analisis = analizar(respuestas)
    imprimir_informe(analisis, len(respuestas), respuestas)


if __name__ == "__main__":
    nim.ejecutar(main)
