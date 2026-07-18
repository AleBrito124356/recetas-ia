"""
Receta 02 - Clasificar gastos bancarios
=======================================

Qué automatiza
--------------
Toma un CSV con los movimientos de tu cuenta o tarjeta (fecha, descripción,
monto) y le pone una categoría a cada uno. Después arma una tabla de cuánto
gastaste por categoría y por mes. Es la base de cualquier control de gastos
personal o de una PYME.

Idea clave: en vez de llamar al modelo una vez por movimiento (lento y caro en
créditos), le mandamos TODAS las descripciones juntas y pedimos un JSON con la
categoría de cada una. Una sola llamada para cientos de movimientos.

Uso
---
  python recetas/02_clasificar_gastos.py
  python recetas/02_clasificar_gastos.py --csv datos/movimientos.csv
"""

import sys
import csv
import json
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

# Categorías fijas. Que sean cerradas ayuda al modelo a ser consistente: no
# queremos que un mes invente "Comida" y al siguiente "Alimentacion".
CATEGORIAS = [
    "Alimentacion",
    "Transporte",
    "Servicios",       # luz, agua, internet, telefono
    "Salud",
    "Entretenimiento",
    "Compras",
    "Educacion",
    "Ingresos",
    "Otros",
]


def leer_movimientos(ruta_csv):
    """Lee el CSV y devuelve una lista de diccionarios con los movimientos."""
    with open(ruta_csv, encoding="utf-8") as f:
        # DictReader usa la primera fila como nombres de columna.
        filas = list(csv.DictReader(f))
    if not filas:
        print("El CSV esta vacio.")
        sys.exit(1)
    return filas


def clasificar(descripciones):
    """
    Devuelve una lista de categorías, una por cada descripción de entrada.

    Enviamos las descripciones numeradas y pedimos un JSON {indice: categoria}.
    Numerar evita que se desalineen las respuestas si el modelo reordena algo.
    """
    lista_num = "\n".join(f"{i}. {d}" for i, d in enumerate(descripciones))
    sistema = (
        "Eres un asistente de finanzas personales. Clasificas movimientos "
        "bancarios en categorias fijas. Respondes SOLO con JSON valido."
    )
    prompt = (
        f"Clasifica cada movimiento en UNA de estas categorias exactas:\n"
        f"{', '.join(CATEGORIAS)}\n\n"
        "Devuelve un objeto JSON donde la clave es el numero del movimiento "
        '(como texto) y el valor es la categoria. Ejemplo: {"0": "Transporte"}.\n\n'
        f"Movimientos:\n{lista_num}"
    )
    respuesta = nim.chat(prompt=prompt, sistema=sistema, temperatura=0.0, max_tokens=2000)
    mapa = nim.extraer_json(respuesta)

    # Reconstruimos la lista en orden, con un respaldo por si falta algún índice.
    categorias = []
    for i in range(len(descripciones)):
        categoria = mapa.get(str(i), "Otros")
        # Si el modelo devuelve algo fuera de la lista, lo normalizamos.
        categorias.append(categoria if categoria in CATEGORIAS else "Otros")
    return categorias


def mes_de(fecha_texto):
    """
    Extrae el 'AAAA-MM' de una fecha. Acepta formatos comunes en LATAM
    (AAAA-MM-DD y DD/MM/AAAA) sin depender de librerías externas.
    """
    fecha_texto = fecha_texto.strip()
    if "/" in fecha_texto:  # DD/MM/AAAA
        partes = fecha_texto.split("/")
        if len(partes) == 3:
            return f"{partes[2]}-{partes[1].zfill(2)}"
    if "-" in fecha_texto:  # AAAA-MM-DD
        partes = fecha_texto.split("-")
        if len(partes) >= 2:
            return f"{partes[0]}-{partes[1].zfill(2)}"
    return "sin-fecha"


def imprimir_tabla(resumen, meses, categorias_usadas):
    """Imprime una tabla mes x categoría en la consola, alineada con f-strings."""
    ancho_cat = max(len(c) for c in categorias_usadas) + 2
    encabezado = "Categoria".ljust(ancho_cat) + "".join(m.rjust(12) for m in meses)
    print(encabezado)
    print("-" * len(encabezado))
    for categoria in categorias_usadas:
        fila = categoria.ljust(ancho_cat)
        for mes in meses:
            fila += f"{resumen[mes][categoria]:12,.2f}"
        print(fila)
    # Fila de totales por mes.
    print("-" * len(encabezado))
    fila_total = "TOTAL".ljust(ancho_cat)
    for mes in meses:
        total_mes = sum(resumen[mes][c] for c in categorias_usadas)
        fila_total += f"{total_mes:12,.2f}"
    print(fila_total)


def main():
    parser = argparse.ArgumentParser(description="Clasifica gastos de un CSV bancario.")
    parser.add_argument(
        "--csv",
        default=str(nim.ruta_datos("movimientos.csv")),
        help="Ruta al CSV de movimientos (por defecto usa el de ejemplo).",
    )
    args = parser.parse_args()

    ruta = Path(args.csv)
    if not ruta.exists():
        print(f"No encuentro el CSV: {ruta}")
        sys.exit(1)

    movimientos = leer_movimientos(ruta)
    descripciones = [m.get("descripcion", "") for m in movimientos]

    print(f"Clasificando {len(movimientos)} movimientos en una sola llamada...")
    categorias = clasificar(descripciones)

    # Agregamos: resumen[mes][categoria] = suma de montos (solo gastos, es decir
    # montos negativos, que convertimos a positivo para la tabla de gasto).
    resumen = defaultdict(lambda: defaultdict(float))
    for movimiento, categoria in zip(movimientos, categorias):
        mes = mes_de(movimiento.get("fecha", ""))
        monto = float(movimiento.get("monto", 0) or 0)
        resumen[mes][categoria] += monto

    meses = sorted(m for m in resumen if m != "sin-fecha")
    categorias_usadas = [c for c in CATEGORIAS if any(resumen[m][c] for m in meses)]

    print("\nTabla de montos por categoria y mes (positivo = ingreso, negativo = gasto):\n")
    imprimir_tabla(resumen, meses, categorias_usadas)

    # También dejamos el detalle clasificado por si quieres exportarlo.
    detalle = [
        {**mov, "categoria": cat} for mov, cat in zip(movimientos, categorias)
    ]
    salida = nim.ruta_datos("movimientos_clasificados.json")
    salida.write_text(json.dumps(detalle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalle clasificado guardado en: {salida}")


if __name__ == "__main__":
    main()
