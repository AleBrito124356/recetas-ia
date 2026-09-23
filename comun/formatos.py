"""
Utilidades de formato pensadas para datos reales de LATAM.

Los modelos y los bancos escriben los números de mil maneras: "-84,50",
"1.234,56", "$ -12.30", "(45.00)", "B/. 1.500,00", "60%"... Estas funciones
convierten todo eso a números de Python sin depender de librerías externas.
"""

import re
import unicodedata

_SIMBOLOS = re.compile(r"(?i)b/\.|s/\.?|us\$|r\$|usd|pab|cop|mxn|pen|clp|ars|eur|[$€£¢\s\u00a0'’]")


def quitar_tildes(texto):
    """'Acción' -> 'Accion'. Útil para comparar sin que importen las tildes."""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar_texto(texto):
    """Minúsculas, sin tildes y con espacios simples: para comparar textos."""
    return " ".join(quitar_tildes(texto).lower().split())


def _es_grupo_de_miles(entero, decimales):
    """
    ¿El separador que hay entre `entero` y `decimales` separa miles?

    Solo si detrás hay exactamente 3 cifras y delante un grupo válido (1 a 3
    cifras que no empiece por 0, o varios grupos de 3). "1.234" y "12,500" son
    miles; "0.500" y "84,50" son decimales.
    """
    if len(decimales) != 3:
        return False
    return bool(re.fullmatch(r"[1-9]\d{0,2}", entero))


def parsear_monto(texto):
    """
    Convierte un importe escrito como texto en un float.

    Acepta coma o punto decimal, separadores de miles, símbolos de moneda,
    signo delante o detrás, y negativos contables entre paréntesis:

      "-84,50" -> -84.5        "1.234,56" -> 1234.56     "1,234.56" -> 1234.56
      "$ -12.30" -> -12.3      "(45.00)" -> -45.0        "84.50-" -> -84.5
      "B/. 1.500,00" -> 1500.0 "" -> 0.0

    Lanza ValueError con un mensaje en español si no es un número.
    """
    if isinstance(texto, (int, float)) and not isinstance(texto, bool):
        return float(texto)
    original = "" if texto is None else str(texto)
    s = original.strip()
    if not s:
        return 0.0

    negativo = False
    if s.startswith("(") and s.endswith(")"):
        negativo, s = True, s[1:-1]
    s = _SIMBOLOS.sub("", s)
    if s.endswith("-"):
        negativo, s = not negativo, s[:-1]
    if s.startswith(("-", "+")):
        negativo, s = (not negativo if s[0] == "-" else negativo), s[1:]
    s = _SIMBOLOS.sub("", s)

    if not s or not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        raise ValueError(f"'{original}' no es un importe reconocible")

    if "," in s and "." in s:
        # El separador que aparece el último es el decimal; el otro, de miles.
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        miles = "." if decimal == "," else ","
        s = s.replace(miles, "").replace(decimal, ".")
    elif "," in s or "." in s:
        separador = "," if "," in s else "."
        partes = s.split(separador)
        if len(partes) > 2 or _es_grupo_de_miles(partes[0], partes[1]):
            if not all(len(p) == 3 for p in partes[1:]):
                raise ValueError(f"'{original}' no es un importe reconocible")
            s = "".join(partes)
        else:
            s = s.replace(",", ".")

    valor = float(s)
    return -valor if negativo else valor


def parsear_numero(valor):
    """
    Como `parsear_monto` pero devuelve None en vez de lanzar error. Para campos
    que un modelo puede devolver como número, como texto o como null.
    """
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return parsear_monto(valor)
    except ValueError:
        return None


def parsear_porcentaje(valor):
    """'60%', '60', 60, '60,5 %' -> 60.0 / 60.5. None si no es un número."""
    if isinstance(valor, str):
        valor = valor.replace("%", "").strip()
    return parsear_numero(valor)
