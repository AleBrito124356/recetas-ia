"""
Receta 11 - Generar datos de prueba realistas
=============================================

Qué automatiza
--------------
Crea datos falsos pero verosímiles para probar tu app o tu base de datos:
clientes, productos y pedidos, con nombres, ciudades y precios propios de LATAM.
Se exporta a JSON o CSV.

Estrategia híbrida (a propósito):
  - Los CLIENTES y PRODUCTOS los inventa el modelo, porque ahí queremos realismo
    (nombres creíbles, ciudades reales, productos coherentes).
  - Los PEDIDOS los generamos con Python + random, porque ahí queremos control
    exacto sobre la distribución y garantía de que las referencias cuadran (cada
    pedido apunta a un cliente y a productos que existen). Mezclar IA para lo
    creativo y código para lo estructural es un patrón muy útil.

Y como lo que genera el modelo puede venir "sucio" (precios como texto, IDs
repetidos o ausentes, la lista envuelta en {"clientes": [...]}), todo pasa por
`normalizar_registros()` antes de usarse.

Con --semilla los pedidos son reproducibles: la misma semilla con los mismos
clientes y productos da exactamente los mismos pedidos. (Los clientes y
productos salen del modelo, que no es determinista, salvo en modo --demo.)

Uso
---
  python recetas/11_datos_sinteticos.py --clientes 10 --productos 8 --pedidos 25
  python recetas/11_datos_sinteticos.py --formato csv --salida datos_prueba --semilla 42
  python recetas/11_datos_sinteticos.py --demo
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402
from comun.formatos import parsear_numero  # noqa: E402

CAMPOS_CLIENTE = ["id", "nombre", "email", "ciudad", "pais"]
CAMPOS_PRODUCTO = ["id", "nombre", "categoria", "precio"]


def generar_clientes(cantidad):
    """Pide al modelo una lista de clientes verosímiles de LATAM en JSON."""
    prompt = (
        f"Genera {cantidad} clientes ficticios pero realistas de America Latina. "
        "Devuelve SOLO un array JSON. Cada cliente: "
        '{"id": 1, "nombre": "Nombre Apellido", "email": "correo@ejemplo.com", '
        '"ciudad": "Ciudad", "pais": "Pais"}. '
        "Usa nombres, ciudades y paises variados y creibles. IDs consecutivos desde 1."
    )
    respuesta = nim.chat(
        prompt=prompt,
        sistema="Generas datos de prueba en JSON valido. Nada de texto extra.",
        temperatura=0.9,
        max_tokens=2000,
    )
    return normalizar_registros(nim.extraer_json(respuesta, esperado=list), "clientes")


def generar_productos(cantidad):
    """Pide al modelo un catálogo de productos coherente en JSON."""
    prompt = (
        f"Genera {cantidad} productos ficticios para una tienda general. "
        "Devuelve SOLO un array JSON. Cada producto: "
        '{"id": 1, "nombre": "Nombre del producto", "categoria": "Categoria", '
        '"precio": 19.99}. Precios realistas en dolares. IDs consecutivos desde 1.'
    )
    respuesta = nim.chat(
        prompt=prompt,
        sistema="Generas datos de prueba en JSON valido. Nada de texto extra.",
        temperatura=0.9,
        max_tokens=2000,
    )
    return normalizar_registros(nim.extraer_json(respuesta, esperado=list), "productos")


def normalizar_registros(registros, tipo):
    """
    Limpia lo que devolvió el modelo antes de usarlo como dato.

    - Acepta la lista directa o envuelta en un objeto ({"clientes": [...]}).
    - Descarta lo que no sea un objeto o no tenga nombre (y en productos, lo
      que no tenga un precio positivo). Los precios en texto ("19.99",
      "$ 1.234,50") se convierten a número con 2 decimales.
    - Garantiza IDs enteros y únicos: si faltan o se repiten, se renumeran.
    """
    if isinstance(registros, dict):
        listas = [v for v in registros.values() if isinstance(v, list)]
        registros = listas[0] if len(listas) == 1 else []
    if not isinstance(registros, list):
        registros = []

    campos = CAMPOS_PRODUCTO if tipo == "productos" else CAMPOS_CLIENTE
    limpios, descartados = [], 0
    for registro in registros:
        if not isinstance(registro, dict) or not str(registro.get("nombre") or "").strip():
            descartados += 1
            continue
        limpio = {c: registro.get(c) for c in campos}
        limpio["nombre"] = str(limpio["nombre"]).strip()
        if tipo == "productos":
            precio = parsear_numero(registro.get("precio"))
            if precio is None or precio <= 0:
                descartados += 1
                continue
            limpio["precio"] = round(precio, 2)
        limpios.append(limpio)

    ids = [parsear_numero(r["id"]) for r in limpios]
    if any(i is None or i != int(i) for i in ids) or len(set(ids)) != len(ids):
        for numero, registro in enumerate(limpios, start=1):
            registro["id"] = numero
    else:
        for registro, valor in zip(limpios, ids):
            registro["id"] = int(valor)

    if descartados:
        print(f"  aviso: se descartaron {descartados} {tipo} con datos invalidos.")
    if not limpios:
        raise nim.ErrorNIM(
            f"El modelo no devolvio ningun registro valido de {tipo}. Vuelve a ejecutar "
            "o prueba otro modelo con NIM_MODEL."
        )
    return limpios


def generar_pedidos(cantidad, clientes, productos, max_items, rng=None):
    """
    Sintetiza pedidos con Python. Cada pedido referencia un cliente y de 1 a
    `max_items` productos existentes, con cantidades aleatorias. El total se
    calcula, nunca se inventa: los datos quedan íntegros y sumables.

    `rng` es un `random.Random`: pasándole una semilla fija los pedidos salen
    siempre iguales (útil para pruebas reproducibles).
    """
    rng = rng or random.Random()
    max_items = max(1, min(max_items, len(productos)))
    pedidos = []
    for numero in range(1, cantidad + 1):
        cliente = rng.choice(clientes)
        elegidos = rng.sample(productos, k=rng.randint(1, max_items))
        lineas, total = [], 0.0
        for producto in elegidos:
            # Defensa extra: aunque llegue un precio en texto ("19.99"), se convierte.
            precio = parsear_numero(producto.get("precio"))
            if precio is None:
                raise ValueError(f"El producto {producto.get('id')} no tiene un precio valido.")
            unidades = rng.randint(1, 5)
            importe = round(precio * unidades, 2)
            total += importe
            lineas.append(
                {
                    "producto_id": producto["id"],
                    "producto": producto["nombre"],
                    "cantidad": unidades,
                    "precio_unitario": precio,
                    "importe": importe,
                }
            )
        pedidos.append(
            {
                "id": numero,
                "cliente_id": cliente["id"],
                "cliente": cliente["nombre"],
                "items": lineas,
                "total": round(total, 2),
            }
        )
    return pedidos


def exportar_json(carpeta, datos):
    """Guarda cada conjunto de datos en su propio archivo .json."""
    for nombre, contenido in datos.items():
        ruta = carpeta / f"{nombre}.json"
        ruta.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {ruta}")


def exportar_csv(carpeta, clientes, productos, pedidos):
    """
    Guarda en CSV. Los pedidos se aplanan a una fila por línea de pedido, que es
    la forma normal de tener este dato en una hoja de cálculo o una tabla.
    """
    def escribir(ruta, filas, columnas):
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(filas)
        print(f"  {ruta}")

    escribir(carpeta / "clientes.csv", clientes, CAMPOS_CLIENTE)
    escribir(carpeta / "productos.csv", productos, CAMPOS_PRODUCTO)

    filas_pedidos = []
    for pedido in pedidos:
        for linea in pedido["items"]:
            filas_pedidos.append(
                {
                    "pedido_id": pedido["id"],
                    "cliente_id": pedido["cliente_id"],
                    "cliente": pedido["cliente"],
                    "producto_id": linea["producto_id"],
                    "producto": linea["producto"],
                    "cantidad": linea["cantidad"],
                    "importe": linea["importe"],
                }
            )
    escribir(
        carpeta / "pedidos.csv",
        filas_pedidos,
        ["pedido_id", "cliente_id", "cliente", "producto_id", "producto", "cantidad", "importe"],
    )


def main():
    parser = nim.nuevo_parser("Genera datos de prueba realistas.")
    parser.add_argument("--clientes", type=int, default=10, help="Numero de clientes.")
    parser.add_argument("--productos", type=int, default=8, help="Numero de productos.")
    parser.add_argument("--pedidos", type=int, default=25, help="Numero de pedidos.")
    parser.add_argument(
        "--max-items", type=int, default=4, help="Items maximos por pedido."
    )
    parser.add_argument(
        "--formato", choices=["json", "csv"], default="json", help="Formato de salida."
    )
    parser.add_argument(
        "--salida",
        default=str(nim.ruta_datos("sinteticos")),
        help="Carpeta donde guardar los archivos.",
    )
    parser.add_argument(
        "--semilla", type=int, help="Semilla para que los pedidos salgan siempre iguales."
    )
    args = parser.parse_args()

    print(f"Generando {args.clientes} clientes...")
    clientes = generar_clientes(args.clientes)
    print(f"Generando {args.productos} productos...")
    productos = generar_productos(args.productos)
    if len(clientes) < args.clientes or len(productos) < args.productos:
        print(f"  aviso: llegaron {len(clientes)} clientes y {len(productos)} productos validos.")

    semilla = f" (semilla {args.semilla})" if args.semilla is not None else ""
    print(f"Sintetizando {args.pedidos} pedidos{semilla}...")
    rng = random.Random(args.semilla)
    pedidos = generar_pedidos(args.pedidos, clientes, productos, args.max_items, rng)

    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)

    print(f"\nExportando en formato {args.formato}:")
    if args.formato == "json":
        exportar_json(carpeta, {"clientes": clientes, "productos": productos, "pedidos": pedidos})
    else:
        exportar_csv(carpeta, clientes, productos, pedidos)

    total = sum(p["total"] for p in pedidos)
    print(f"\nListo. {len(pedidos)} pedidos por un total de {total:,.2f} USD.")


if __name__ == "__main__":
    nim.ejecutar(main)
