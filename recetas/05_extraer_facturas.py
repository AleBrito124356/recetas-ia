"""
Receta 05 - Extraer datos de facturas a JSON
============================================

Qué automatiza
--------------
Convierte el texto de una factura (pegado, copiado de un PDF o salido de un OCR)
en un JSON estructurado y validado, listo para meter en tu contabilidad o base
de datos. Los campos están pensados para LATAM: RUC/NIT, ITBMS/IVA, etc.

Por qué validamos
-----------------
Un modelo puede "alucinar" un total que no cuadra. Después de extraer, hacemos
comprobaciones aritméticas simples (subtotal + impuesto ≈ total) y avisamos si
algo no cierra, en vez de confiar a ciegas.

Uso
---
  python recetas/05_extraer_facturas.py
  python recetas/05_extraer_facturas.py --archivo datos/factura_ejemplo.txt
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

# Esquema que le describimos al modelo. Mantenerlo como texto explícito hace que
# la salida sea predecible y fácil de mapear a columnas de una tabla.
ESQUEMA = """{
  "emisor": {
    "nombre": "razon social de quien emite",
    "ruc_nit": "RUC (Panama/Peru) o NIT (Colombia) del emisor, o null",
    "direccion": "direccion o null"
  },
  "cliente": {
    "nombre": "nombre del cliente o null",
    "ruc_nit": "identificacion fiscal del cliente o null"
  },
  "documento": {
    "tipo": "factura, boleta o recibo",
    "numero": "numero de la factura o null",
    "fecha": "fecha en formato AAAA-MM-DD o null",
    "moneda": "codigo de moneda, p.ej. PAB, USD, COP"
  },
  "items": [
    {"descripcion": "texto", "cantidad": 0, "precio_unitario": 0.0, "importe": 0.0}
  ],
  "subtotal": 0.0,
  "impuesto": {"nombre": "ITBMS o IVA", "tasa": 0.07, "monto": 0.0},
  "total": 0.0
}"""


def extraer(texto_factura):
    """Pide al modelo el JSON estructurado siguiendo el esquema."""
    sistema = (
        "Eres un sistema de extraccion de facturas para LATAM. Devuelves SOLO "
        "JSON valido que cumpla el esquema dado. Si un dato no aparece, usa null. "
        "No inventes numeros: copia los que veas en el texto."
    )
    prompt = (
        f"Extrae los datos de esta factura al siguiente esquema JSON:\n\n{ESQUEMA}\n\n"
        f"TEXTO DE LA FACTURA:\n{texto_factura}"
    )
    respuesta = nim.chat(prompt=prompt, sistema=sistema, temperatura=0.0, max_tokens=1500)
    return nim.extraer_json(respuesta)


def validar(datos):
    """
    Devuelve una lista de advertencias si la aritmética no cuadra.

    Lista vacía = todo consistente. No lanzamos error: solo señalamos, porque a
    veces la propia factura tiene redondeos raros y quien decide es la persona.
    """
    avisos = []
    try:
        suma_items = round(sum(float(i.get("importe", 0)) for i in datos.get("items", [])), 2)
        subtotal = round(float(datos.get("subtotal", 0)), 2)
        if abs(suma_items - subtotal) > 0.02:
            avisos.append(
                f"La suma de items ({suma_items}) no coincide con el subtotal ({subtotal})."
            )

        impuesto = round(float(datos.get("impuesto", {}).get("monto", 0)), 2)
        total = round(float(datos.get("total", 0)), 2)
        esperado = round(subtotal + impuesto, 2)
        if abs(esperado - total) > 0.02:
            avisos.append(
                f"subtotal + impuesto = {esperado} no coincide con el total ({total})."
            )
    except (TypeError, ValueError) as e:
        avisos.append(f"No se pudieron validar los numeros: {e}")
    return avisos


def main():
    parser = argparse.ArgumentParser(description="Extrae una factura a JSON validado.")
    parser.add_argument(
        "--archivo",
        default=str(nim.ruta_datos("factura_ejemplo.txt")),
        help="Archivo de texto con la factura (por defecto el de ejemplo).",
    )
    parser.add_argument("--salida", help="Archivo donde guardar el JSON resultante.")
    args = parser.parse_args()

    ruta = Path(args.archivo)
    if not ruta.exists():
        print(f"No encuentro el archivo: {ruta}")
        sys.exit(1)

    texto = ruta.read_text(encoding="utf-8")
    print("Extrayendo datos de la factura...\n")
    datos = extraer(texto)

    salida_json = json.dumps(datos, ensure_ascii=False, indent=2)
    print(salida_json)

    avisos = validar(datos)
    print("\n" + "-" * 60)
    if avisos:
        print("Validacion: hay puntos que revisar")
        for aviso in avisos:
            print(f"  - {aviso}")
    else:
        print("Validacion: la aritmetica cuadra (subtotal, impuesto y total consistentes).")

    if args.salida:
        Path(args.salida).write_text(salida_json, encoding="utf-8")
        print(f"\nJSON guardado en: {args.salida}")


if __name__ == "__main__":
    main()
