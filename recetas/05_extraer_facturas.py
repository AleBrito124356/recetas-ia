"""
Receta 05 - Extraer datos de facturas a JSON
============================================

Qué automatiza
--------------
Convierte el texto de una factura (pegado, copiado de un PDF o salido de un OCR)
en un JSON estructurado y validado, listo para meter en tu contabilidad o base
de datos. Los campos están pensados para LATAM: RUC/NIT, ITBMS/IVA, etc.

Por qué validamos (y qué validamos)
-----------------------------------
Un modelo puede "alucinar" un número que no está en la factura o equivocarse
al copiar una línea. Después de extraer, `validar()` revisa sin llamar al
modelo:
  1. Campos obligatorios: emisor, fecha, total y al menos una línea.
  2. Fecha en formato AAAA-MM-DD y que exista de verdad (nada de 2026-02-30).
  3. Cada línea: cantidad x precio unitario = importe.
  4. Suma de importes = subtotal.
  5. Impuesto: tasa x subtotal = monto (ITBMS 7% de 276.00 = 19.32).
  6. Subtotal + impuesto = total.
  7. Anti-alucinación: el subtotal, el total y el RUC deben aparecer
     literalmente en el texto original.
No lanzamos error: señalamos, porque a veces la propia factura tiene redondeos
raros y quien decide es la persona. Con --estricto el programa termina con
código 2 si algo no cuadra (útil en un proceso automático).

Uso
---
  python recetas/05_extraer_facturas.py
  python recetas/05_extraer_facturas.py --archivo datos/factura_ejemplo.txt --salida factura.json
  python recetas/05_extraer_facturas.py --demo
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402
from comun.formatos import parsear_numero  # noqa: E402

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

TOLERANCIA = 0.02  # diferencia máxima aceptada por redondeos (2 centavos)
OBLIGATORIOS = ("emisor.nombre", "documento.fecha", "total")


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
    return nim.extraer_json(respuesta, esperado=dict)


def _obtener(datos, ruta):
    """_obtener(d, 'emisor.nombre') sin romper si un nivel falta o es null."""
    actual = datos
    for parte in ruta.split("."):
        if not isinstance(actual, dict):
            return None
        actual = actual.get(parte)
    return actual


def _cerca(a, b):
    return abs(round(a, 2) - round(b, 2)) <= TOLERANCIA + 1e-9


def _variantes(valor):
    """Formas de escribir 1234.5 en una factura: 1234.50, 1,234.50, 1.234,50..."""
    con_puntos = f"{valor:,.2f}"
    return {
        f"{valor:.2f}",
        con_puntos,
        f"{valor:.2f}".replace(".", ","),
        con_puntos.replace(",", "_").replace(".", ",").replace("_", "."),
    }


def aparece_en_texto(valor, texto):
    """True si el número aparece escrito en el texto en alguna forma habitual."""
    return any(variante in texto for variante in _variantes(valor))


def _solo_digitos(texto):
    return re.sub(r"\D", "", str(texto))


def validar(datos, texto_original=None):
    """
    Devuelve una lista de advertencias (lista vacía = todo consistente).

    Nunca lanza excepciones: si el modelo devolvió null, textos en vez de
    números o una estructura rara, se convierte en un aviso legible.
    """
    if not isinstance(datos, dict):
        return ["La respuesta del modelo no es un objeto JSON con los datos de la factura."]
    avisos = []

    def numero(valor, campo):
        """El valor como float; None si falta; aviso si no es un número."""
        if valor is None or valor == "":
            return None
        resultado = parsear_numero(valor)
        if resultado is None:
            avisos.append(f"El campo '{campo}' no es numerico: {valor!r}.")
        return resultado

    # 1) Campos obligatorios.
    for ruta in OBLIGATORIOS:
        if _obtener(datos, ruta) in (None, ""):
            avisos.append(f"Falta el campo obligatorio '{ruta}'.")
    items = datos.get("items")
    if not isinstance(items, list) or not items:
        avisos.append("La factura no tiene lineas de detalle ('items').")
        items = []

    # 2) Fecha ISO real.
    fecha = _obtener(datos, "documento.fecha")
    if fecha not in (None, ""):
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(fecha)):
                raise ValueError
            date.fromisoformat(str(fecha))
        except ValueError:
            avisos.append(f"La fecha '{fecha}' no es una fecha valida en formato AAAA-MM-DD.")

    # 3) y 4) Cada línea y su suma.
    suma, suma_completa = 0.0, True
    for n, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            avisos.append(f"Linea {n}: no tiene la forma esperada.")
            suma_completa = False
            continue
        nombre = str(item.get("descripcion") or f"linea {n}")[:40]
        cantidad = numero(item.get("cantidad"), f"items[{n}].cantidad")
        precio = numero(item.get("precio_unitario"), f"items[{n}].precio_unitario")
        importe = numero(item.get("importe"), f"items[{n}].importe")
        if importe is None:
            suma_completa = False
            avisos.append(f"Linea {n} ('{nombre}'): no tiene importe.")
            continue
        if cantidad is not None and precio is not None:
            calculado = round(cantidad * precio, 2)
            if not _cerca(calculado, importe):
                avisos.append(
                    f"Linea {n} ('{nombre}'): {cantidad:g} x {precio:.2f} = {calculado:.2f}, "
                    f"pero el importe dice {importe:.2f}."
                )
        suma += importe

    subtotal = numero(datos.get("subtotal"), "subtotal")
    if subtotal is None:
        avisos.append("Falta el subtotal.")
    elif items and suma_completa and not _cerca(suma, subtotal):
        avisos.append(
            f"La suma de las lineas ({suma:.2f}) no coincide con el subtotal ({subtotal:.2f})."
        )

    # 5) Impuesto: puede faltar (exento), ser un objeto o, a veces, un número suelto.
    impuesto = datos.get("impuesto")
    monto_impuesto = 0.0
    if isinstance(impuesto, dict):
        monto = numero(impuesto.get("monto"), "impuesto.monto")
        tasa = numero(impuesto.get("tasa"), "impuesto.tasa")
        if tasa is not None and tasa > 1:  # el modelo puso 7 en vez de 0.07
            tasa /= 100
        if monto is not None:
            monto_impuesto = monto
        if tasa is not None and monto is not None and subtotal is not None:
            esperado = round(subtotal * tasa, 2)
            if not _cerca(esperado, monto):
                avisos.append(
                    f"El impuesto no cuadra con su tasa: {tasa:.2%} de {subtotal:.2f} = "
                    f"{esperado:.2f}, pero el monto dice {monto:.2f}."
                )
    elif impuesto is not None:
        monto = numero(impuesto, "impuesto")
        monto_impuesto = monto or 0.0

    # 6) Subtotal + impuesto = total.
    total = numero(datos.get("total"), "total")
    if subtotal is not None and total is not None:
        esperado = round(subtotal + monto_impuesto, 2)
        if not _cerca(esperado, total):
            avisos.append(
                f"subtotal + impuesto = {esperado:.2f} no coincide con el total ({total:.2f})."
            )

    # 7) Anti-alucinación: las cifras clave tienen que estar en la factura.
    if texto_original:
        for campo, valor in (("subtotal", subtotal), ("total", total)):
            if valor is not None and not aparece_en_texto(valor, texto_original):
                avisos.append(
                    f"El {campo} ({valor:.2f}) no aparece en el texto de la factura: "
                    "comprueba que no sea inventado."
                )
        ruc = _obtener(datos, "emisor.ruc_nit")
        if ruc and _solo_digitos(ruc) not in _solo_digitos(texto_original):
            avisos.append(f"El RUC/NIT del emisor ('{ruc}') no aparece en el texto de la factura.")
    return avisos


def main():
    parser = nim.nuevo_parser("Extrae una factura a JSON validado.")
    parser.add_argument(
        "--archivo",
        default=str(nim.ruta_datos("factura_ejemplo.txt")),
        help="Archivo de texto con la factura (por defecto el de ejemplo).",
    )
    parser.add_argument("--salida", help="Archivo donde guardar el JSON resultante.")
    parser.add_argument(
        "--estricto",
        action="store_true",
        help="Termina con codigo 2 si la validacion encuentra problemas.",
    )
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

    avisos = validar(datos, texto)
    print("\n" + "-" * 60)
    if avisos:
        print("Validacion: hay puntos que revisar")
        for aviso in avisos:
            print(f"  - {aviso}")
    else:
        print(
            "Validacion: todo cuadra (lineas, subtotal, impuesto y total consistentes, "
            "y las cifras clave aparecen en la factura)."
        )

    if args.salida:
        Path(args.salida).write_text(salida_json, encoding="utf-8")
        print(f"\nJSON guardado en: {args.salida}")

    if avisos and args.estricto:
        sys.exit(2)


if __name__ == "__main__":
    nim.ejecutar(main)
