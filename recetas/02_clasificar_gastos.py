"""
Receta 02 - Clasificar gastos bancarios
=======================================

Qué automatiza
--------------
Toma un CSV con los movimientos de tu cuenta o tarjeta (fecha, descripción,
monto) y le pone una categoría a cada uno. Después arma una tabla de cuánto
entró y salió por categoría y por mes. Es la base de cualquier control de
gastos personal o de una PYME.

Idea clave: en vez de llamar al modelo una vez por movimiento (lento y caro en
créditos), le mandamos las descripciones por lotes (60 por defecto) y pedimos
un JSON con la categoría de cada una. Una llamada para decenas de movimientos.

Pensada para exportaciones reales de bancos de LATAM:
  - montos con coma decimal y puntos de miles ("-84,50", "1.234,56"),
    símbolos de moneda ("B/. 12.30", "$ -12.30") y negativos entre paréntesis;
  - CSV separados por coma o por punto y coma (Excel en español usa ";");
  - columnas con otros nombres (Importe, Concepto, Descripción...);
  - fechas AAAA-MM-DD, DD/MM/AAAA o DD-MM-AAAA.

Uso
---
  python recetas/02_clasificar_gastos.py
  python recetas/02_clasificar_gastos.py --csv mi_banco.csv --salida clasificado.json
  python recetas/02_clasificar_gastos.py --demo
"""

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402
from comun.formatos import normalizar_texto, parsear_monto  # noqa: E402,F401

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

# Nombres de columna que usan distintos bancos para lo mismo.
ALIAS_COLUMNAS = {
    "fecha": ("fecha", "fecha operacion", "fecha valor", "date"),
    "descripcion": ("descripcion", "concepto", "detalle", "referencia", "description"),
    "monto": ("monto", "importe", "valor", "cantidad", "amount"),
}


def _normalizar_filas(filas):
    """Renombra las columnas a fecha / descripcion / monto usando los alias."""
    if not filas:
        return filas
    renombrar = {}
    for original in filas[0].keys():
        clave = normalizar_texto(original or "")
        for destino, alias in ALIAS_COLUMNAS.items():
            if clave in alias and destino not in renombrar.values():
                renombrar[original] = destino
    return [
        {renombrar.get(k, k): (v or "").strip() if isinstance(v, str) or v is None else v
         for k, v in fila.items()}
        for fila in filas
    ]


def leer_movimientos(ruta_csv):
    """Lee el CSV (coma o punto y coma, con o sin BOM) y devuelve una lista de dicts."""
    # utf-8-sig quita el BOM que Excel pone al principio de los CSV.
    with open(ruta_csv, encoding="utf-8-sig", newline="") as f:
        contenido = f.read()
    # El separador se deduce del encabezado: los nombres de columna no llevan
    # comas, pero los montos "-84,50" sí, así que mirar las filas engañaría.
    encabezado = contenido.splitlines()[0] if contenido.strip() else ""
    separador = max(",;\t", key=encabezado.count) if encabezado else ","
    # DictReader usa la primera fila como nombres de columna.
    lector = csv.DictReader(contenido.splitlines(), delimiter=separador)
    filas = _normalizar_filas(list(lector))
    if not filas:
        print("El CSV esta vacio.")
        sys.exit(1)
    faltan = [c for c in ALIAS_COLUMNAS if c not in filas[0]]
    if faltan:
        print(
            f"Al CSV le faltan columnas: {', '.join(faltan)}.\n"
            f"Columnas encontradas: {', '.join(filas[0].keys())}"
        )
        sys.exit(1)
    return filas


def _categoria_valida(valor):
    """Normaliza lo que diga el modelo ('alimentación' -> 'Alimentacion')."""
    buscada = normalizar_texto(valor or "")
    for categoria in CATEGORIAS:
        if normalizar_texto(categoria) == buscada:
            return categoria
    return "Otros"


def clasificar_lote(descripciones):
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

    # Algunos modelos devuelven una lista en orden en vez del objeto pedido.
    if isinstance(mapa, list):
        mapa = {str(i): valor for i, valor in enumerate(mapa)}

    # Reconstruimos la lista en orden, con un respaldo por si falta algún índice.
    faltan = [i for i in range(len(descripciones)) if str(i) not in mapa]
    if faltan:
        print(f"  aviso: el modelo no clasifico {len(faltan)} movimiento(s); quedan en 'Otros'.")
    return [_categoria_valida(mapa.get(str(i))) for i in range(len(descripciones))]


def clasificar(descripciones, lote=60):
    """Clasifica por lotes para no pasarnos de max_tokens con CSVs grandes."""
    categorias = []
    for inicio in range(0, len(descripciones), lote):
        categorias.extend(clasificar_lote(descripciones[inicio : inicio + lote]))
    return categorias


def mes_de(fecha_texto):
    """
    Extrae el 'AAAA-MM' de una fecha. Acepta los formatos comunes en LATAM
    (AAAA-MM-DD, DD/MM/AAAA, DD-MM-AAAA, DD.MM.AAAA) sin librerías externas.
    """
    partes = re.split(r"[-/.]", (fecha_texto or "").strip())
    if len(partes) == 3 and all(p.isdigit() for p in partes):
        if len(partes[0]) == 4:  # AAAA-MM-DD
            anio, mes = partes[0], partes[1]
        elif len(partes[2]) == 4:  # DD/MM/AAAA
            anio, mes = partes[2], partes[1]
        else:
            return "sin-fecha"
        if 1 <= int(mes) <= 12:
            return f"{anio}-{mes.zfill(2)}"
    return "sin-fecha"


def resumir(movimientos, categorias):
    """
    Agrega los montos: resumen[mes][categoria] = suma de montos CON SIGNO
    (los ingresos suman en positivo y los gastos en negativo, tal como vienen).
    """
    resumen = defaultdict(lambda: defaultdict(float))
    for movimiento, categoria in zip(movimientos, categorias):
        resumen[mes_de(movimiento["fecha"])][categoria] += movimiento["monto"]
    return resumen


def imprimir_tabla(resumen, meses, categorias_usadas):
    """Imprime una tabla mes x categoría en la consola, alineada con f-strings."""
    ancho_cat = max(len(c) for c in categorias_usadas + ["GASTO TOTAL"]) + 2
    encabezado = "Categoria".ljust(ancho_cat) + "".join(m.rjust(12) for m in meses)
    print(encabezado)
    print("-" * len(encabezado))
    for categoria in categorias_usadas:
        fila = categoria.ljust(ancho_cat)
        for mes in meses:
            fila += f"{resumen[mes][categoria]:12,.2f}"
        print(fila)
    print("-" * len(encabezado))
    gasto = "GASTO TOTAL".ljust(ancho_cat)
    neto = "TOTAL NETO".ljust(ancho_cat)
    for mes in meses:
        gasto += f"{sum(v for v in resumen[mes].values() if v < 0):12,.2f}"
        neto += f"{sum(resumen[mes][c] for c in categorias_usadas):12,.2f}"
    print(gasto)
    print(neto)


def preparar_montos(filas):
    """Convierte el texto de 'monto' en número; avisa y descarta las filas ilegibles."""
    validas = []
    for numero, fila in enumerate(filas, start=2):  # fila 1 = encabezado
        try:
            validas.append({**fila, "monto": parsear_monto(fila.get("monto"))})
        except ValueError as error:
            print(f"  aviso: fila {numero} descartada: {error}.")
    return validas


def main():
    parser = nim.nuevo_parser("Clasifica gastos de un CSV bancario.")
    parser.add_argument(
        "--csv",
        default=str(nim.ruta_datos("movimientos.csv")),
        help="Ruta al CSV de movimientos (por defecto usa el de ejemplo).",
    )
    parser.add_argument(
        "--salida",
        default=str(nim.ruta_datos("movimientos_clasificados.json")),
        help="Donde guardar el detalle clasificado (JSON).",
    )
    parser.add_argument("--lote", type=int, default=60, help="Movimientos por llamada al modelo.")
    args = parser.parse_args()

    ruta = Path(args.csv)
    if not ruta.exists():
        print(f"No encuentro el CSV: {ruta}")
        sys.exit(1)

    movimientos = preparar_montos(leer_movimientos(ruta))
    if not movimientos:
        print("No quedo ningun movimiento con un monto valido.")
        sys.exit(1)
    descripciones = [m.get("descripcion", "") for m in movimientos]

    llamadas = -(-len(movimientos) // max(1, args.lote))
    print(f"Clasificando {len(movimientos)} movimientos en {llamadas} llamada(s)...")
    categorias = clasificar(descripciones, max(1, args.lote))

    resumen = resumir(movimientos, categorias)
    meses = sorted(m for m in resumen if m != "sin-fecha")
    if "sin-fecha" in resumen:
        print("  aviso: hay movimientos con fecha no reconocida; no salen en la tabla.")
    categorias_usadas = [c for c in CATEGORIAS if any(resumen[m][c] for m in meses)]
    if not meses or not categorias_usadas:
        print("No hay movimientos con fecha valida para armar la tabla.")
        sys.exit(1)

    print("\nMontos por categoria y mes (positivo = ingreso, negativo = gasto):\n")
    imprimir_tabla(resumen, meses, categorias_usadas)

    # También dejamos el detalle clasificado por si quieres exportarlo.
    detalle = [{**mov, "categoria": cat} for mov, cat in zip(movimientos, categorias)]
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(detalle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalle clasificado guardado en: {salida}")


if __name__ == "__main__":
    nim.ejecutar(main)
