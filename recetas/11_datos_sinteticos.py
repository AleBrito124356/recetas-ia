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

Uso
---
  python recetas/11_datos_sinteticos.py --clientes 10 --productos 8 --pedidos 25
  python recetas/11_datos_sinteticos.py --formato csv --salida datos_prueba
"""

import sys
import csv
import json
import random
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


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
    return nim.extraer_json(respuesta)


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
    return nim.extraer_json(respuesta)


def generar_pedidos(cantidad, clientes, productos, max_items):
    """
    Sintetiza pedidos con Python. Cada pedido referencia un cliente y de 1 a
    `max_items` productos existentes, con cantidades aleatorias. El total se
    calcula, nunca se inventa: los datos quedan íntegros y sumables.
    """
    pedidos = []
    for numero in range(1, cantidad + 1):
        cliente = random.choice(clientes)
        elegidos = random.sample(productos, k=random.randint(1, min(max_items, len(productos))))
        lineas, total = [], 0.0
        for producto in elegidos:
            unidades = random.randint(1, 5)
            importe = round(producto["precio"] * unidades, 2)
            total += importe
            lineas.append(
                {
                    "producto_id": producto["id"],
                    "producto": producto["nombre"],
                    "cantidad": unidades,
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
            escritor = csv.DictWriter(f, fieldnames=columnas)
            escritor.writeheader()
            escritor.writerows(filas)
        print(f"  {ruta}")

    escribir(carpeta / "clientes.csv", clientes, ["id", "nombre", "email", "ciudad", "pais"])
    escribir(carpeta / "productos.csv", productos, ["id", "nombre", "categoria", "precio"])

    filas_pedidos = []
    for pedido in pedidos:
        for linea in pedido["items"]:
            filas_pedidos.append(
                {
                    "pedido_id": pedido["id"],
                    "cliente": pedido["cliente"],
                    "producto": linea["producto"],
                    "cantidad": linea["cantidad"],
                    "importe": linea["importe"],
                }
            )
    escribir(
        carpeta / "pedidos.csv",
        filas_pedidos,
        ["pedido_id", "cliente", "producto", "cantidad", "importe"],
    )


def main():
    parser = argparse.ArgumentParser(description="Genera datos de prueba realistas.")
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
    args = parser.parse_args()

    print(f"Generando {args.clientes} clientes...")
    clientes = generar_clientes(args.clientes)
    print(f"Generando {args.productos} productos...")
    productos = generar_productos(args.productos)
    print(f"Sintetizando {args.pedidos} pedidos...")
    pedidos = generar_pedidos(args.pedidos, clientes, productos, args.max_items)

    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)

    print(f"\nExportando en formato {args.formato}:")
    if args.formato == "json":
        exportar_json(carpeta, {"clientes": clientes, "productos": productos, "pedidos": pedidos})
    else:
        exportar_csv(carpeta, clientes, productos, pedidos)

    print("\nListo. Datos de prueba generados.")


if __name__ == "__main__":
    main()
