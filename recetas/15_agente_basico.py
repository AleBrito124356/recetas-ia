"""
Receta 15 - Un agente ReAct mínimo (el "hola mundo" de los agentes)
===================================================================

Qué automatiza
--------------
Nada por sí solo: esta receta es para APRENDER. Es el agente más simple que
merece llamarse agente, explicado casi línea por línea, en español. Si entiendes
esto, entiendes cómo funcionan por dentro herramientas mucho más grandes.

¿Qué es un agente?
------------------
Un modelo de lenguaje, solo, únicamente predice texto. Un AGENTE es un modelo
metido en un bucle donde además puede USAR HERRAMIENTAS (calcular, buscar la
fecha, consultar algo) y decidir por sí mismo cuándo usarlas.

El patrón ReAct (Reasoning + Acting)
------------------------------------
En cada vuelta del bucle el modelo produce:
  Pensamiento: razona qué hacer.
  Accion: el nombre de una herramienta.
  Entrada: el argumento para esa herramienta.
Nuestro código EJECUTA la herramienta y le devuelve al modelo:
  Observacion: el resultado.
El modelo repite el ciclo hasta que sabe la respuesta y escribe:
  Respuesta final: ...

La trampa que hay que evitar
----------------------------
Un modelo, como solo predice texto, a veces escribe él mismo la línea
"Observacion: 9999" (¡inventada!) y a continuación una "Respuesta final" basada
en ese dato falso. Este agente se defiende de tres formas:
  1. Le pide a la API que pare de escribir al llegar a "Observacion:" (stop).
  2. Si aun así aparece una observación, se descarta todo lo que venga después.
  3. Si en la misma vuelta hay una Accion y una Respuesta final, gana la
     Accion: primero se ejecuta la herramienta de verdad.

Uso
---
  python recetas/15_agente_basico.py "Cuanto es 145 * 32 y cuantas letras tiene el resultado?"
  python recetas/15_agente_basico.py "Que dia es hoy y cuantos dias faltan para fin de mes?"
  python recetas/15_agente_basico.py --demo
"""

import ast
import math
import operator
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402
from comun.formatos import quitar_tildes  # noqa: E402

PREGUNTA_EJEMPLO = "Cuanto es 145 * 32 y cuantas letras tiene el resultado?"


# --------------------------------------------------------------------------- #
# 1. LAS HERRAMIENTAS                                                          #
# --------------------------------------------------------------------------- #
# Una herramienta es simplemente una función de Python. El agente solo puede
# hacer aquello para lo que le demos una herramienta.

# Operadores permitidos en la calculadora. Usamos el módulo `ast` para evaluar
# expresiones matemáticas sin `eval()` (que ejecutaría código arbitrario y es
# un agujero de seguridad clásico).
_OPERADORES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Límites: sin ellos, "9**9**9" tendría a Python calculando un número de
# cientos de millones de cifras y el agente se quedaría colgado. "Seguro" no es
# solo "sin eval": también es "sin poder agotar la CPU o la memoria".
MAX_LARGO_EXPRESION = 200
MAX_EXPONENTE = 1000
MAX_CIFRAS = 100  # ningún resultado (ni intermedio) puede pasar de 10**100


class ErrorCalculo(ValueError):
    """La expresión no es válida o se sale de los límites de la calculadora."""


def _comprobar(valor):
    if isinstance(valor, complex):
        raise ErrorCalculo("el resultado no es un numero real")
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ErrorCalculo("resultado demasiado grande")
    if abs(valor) >= 10**MAX_CIFRAS:
        raise ErrorCalculo(f"resultado de mas de {MAX_CIFRAS} cifras")
    return valor


def _potencia(base, exponente):
    """base ** exponente, pero comprobando ANTES de calcular que no se dispara."""
    if abs(exponente) > MAX_EXPONENTE:
        raise ErrorCalculo(f"exponente mayor que {MAX_EXPONENTE}")
    if base != 0 and abs(exponente * math.log10(abs(base))) > MAX_CIFRAS:
        raise ErrorCalculo(f"resultado de mas de {MAX_CIFRAS} cifras")
    return operator.pow(base, exponente)


def _evaluar_nodo(nodo):
    """Recorre el árbol de la expresión permitiendo solo números y operadores."""
    if isinstance(nodo, ast.Constant) and type(nodo.value) in (int, float):
        return _comprobar(nodo.value)
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
        izquierda, derecha = _evaluar_nodo(nodo.left), _evaluar_nodo(nodo.right)
        if isinstance(nodo.op, ast.Pow):
            return _comprobar(_potencia(izquierda, derecha))
        return _comprobar(_OPERADORES[type(nodo.op)](izquierda, derecha))
    if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES:
        return _comprobar(_OPERADORES[type(nodo.op)](_evaluar_nodo(nodo.operand)))
    if isinstance(nodo, ast.Tuple):
        raise ErrorCalculo("usa punto para los decimales y sin separador de miles (ej. 1234.5)")
    raise ErrorCalculo("solo se permiten numeros y los operadores + - * / // % **")


def _formatear(valor):
    """4640.0 -> '4640'; 10/3 -> '3.333333333'."""
    if isinstance(valor, float):
        if valor.is_integer() and abs(valor) < 1e15:
            return str(int(valor))
        return f"{valor:.10g}"
    return str(valor)


def herramienta_calcular(expresion):
    """Evalua una operacion matematica. Ej: '145 * 32'."""
    expresion = str(expresion).strip().strip("`'\"").strip()
    # Lo que un modelo (o una persona) suele escribir y Python no entiende.
    expresion = expresion.replace("×", "*").replace("÷", "/").replace("^", "**")
    expresion = re.sub(r"\s*=\s*\??\s*$", "", expresion)
    expresion = re.sub(r"(?<=\d)\s*[xX]\s*(?=[\d(])", " * ", expresion)  # "145 x 32"
    if len(expresion) > MAX_LARGO_EXPRESION:
        return f"Error: la expresion supera {MAX_LARGO_EXPRESION} caracteres."
    try:
        arbol = ast.parse(expresion, mode="eval").body
        return _formatear(_evaluar_nodo(arbol))
    except ZeroDivisionError:
        return "Error: division entre cero."
    except ErrorCalculo as error:
        return f"Error: {error}."
    except (SyntaxError, ValueError, TypeError, OverflowError, RecursionError):
        return "Error: expresion matematica invalida."


def herramienta_fecha(_):
    """Devuelve la fecha y hora actuales. Ignora su entrada."""
    return datetime.now().strftime("Hoy es %Y-%m-%d y son las %H:%M.")


def herramienta_dias_fin_mes(_):
    """Calcula cuantos dias faltan para el fin del mes actual."""
    hoy = date.today()
    # El último día del mes es el día anterior al 1 del mes siguiente.
    if hoy.month == 12:
        primero_siguiente = date(hoy.year + 1, 1, 1)
    else:
        primero_siguiente = date(hoy.year, hoy.month + 1, 1)
    ultimo_dia = (primero_siguiente - date.resolution).day
    return f"Faltan {ultimo_dia - hoy.day} dias para el fin de mes."


def herramienta_contar_letras(texto):
    """Cuenta cuantos caracteres alfanumericos (letras y cifras) tiene un texto."""
    texto = str(texto).strip().strip("`'\"")
    solo_letras = [c for c in texto if c.isalnum()]
    return f"El texto '{texto}' tiene {len(solo_letras)} caracteres alfanumericos."


# El "catálogo" de herramientas: nombre -> (función, descripción para el modelo).
HERRAMIENTAS = {
    "calcular": (herramienta_calcular, "Evalua una operacion matematica. Entrada: la expresion, ej '2 + 2 * 3'."),
    "fecha_actual": (herramienta_fecha, "Devuelve la fecha y hora de hoy. Entrada: cualquier cosa."),
    "dias_fin_mes": (herramienta_dias_fin_mes, "Dias que faltan para fin de mes. Entrada: cualquier cosa."),
    "contar_letras": (herramienta_contar_letras, "Cuenta caracteres de un texto. Entrada: el texto."),
}


# --------------------------------------------------------------------------- #
# 2. EL PROMPT DEL SISTEMA                                                     #
# --------------------------------------------------------------------------- #
# Aquí le enseñamos al modelo el formato ReAct y qué herramientas tiene. Este
# texto es, literalmente, todo el "cerebro" del agente.

def construir_prompt_sistema():
    catalogo = "\n".join(f"  - {nombre}: {desc}" for nombre, (_, desc) in HERRAMIENTAS.items())
    return (
        "Eres un agente que responde preguntas usando herramientas. Razonas paso "
        "a paso y respondes SIEMPRE en espanol.\n\n"
        "Herramientas disponibles:\n"
        f"{catalogo}\n\n"
        "Usa EXACTAMENTE este formato, una linea por campo:\n"
        "Pensamiento: <tu razonamiento>\n"
        "Accion: <nombre exacto de una herramienta>\n"
        "Entrada: <el argumento para la herramienta>\n\n"
        "Espera a recibir una linea 'Observacion:' con el resultado antes de "
        "continuar. Cuando ya tengas la respuesta, escribe en su lugar:\n"
        "Respuesta final: <la respuesta para el usuario>\n"
    )


# --------------------------------------------------------------------------- #
# 3. EL BUCLE DEL AGENTE                                                       #
# --------------------------------------------------------------------------- #

# Dónde debe parar el modelo: justo antes de inventarse una observación.
PARADAS = ["Observacion:", "Observación:"]

# Una línea con etiqueta: admite tildes, mayúsculas y adornos de Markdown como
# "**Acción:** calcular". Se compara sobre el texto sin tildes.
_ETIQUETA = re.compile(
    r"^[\s*_#>-]*(pensamiento|accion|entrada|observacion|respuesta final)[\s*_]*:",
    re.IGNORECASE,
)
_NOMBRES = {
    "pensamiento": "Pensamiento",
    "accion": "Accion",
    "entrada": "Entrada",
    "observacion": "Observacion",
    "respuesta final": "Respuesta final",
}


def recortar_en_observacion(texto):
    """Devuelve el texto hasta la primera línea 'Observacion:' (sin incluirla)."""
    lineas = []
    for linea in texto.splitlines():
        coincide = _ETIQUETA.match(quitar_tildes(linea))
        if coincide and coincide.group(1).lower() == "observacion":
            break
        lineas.append(linea)
    return "\n".join(lineas).strip()


def parsear_respuesta(texto):
    """
    Lee la salida del modelo y extrae los campos que nos interesan.

    - Reconoce las etiquetas con o sin tilde y en cualquier mayúscula
      ("Acción:", "ACCION:", "**Accion:**").
    - Un campo puede ocupar varias líneas: todo lo que sigue hasta la próxima
      etiqueta es parte de él (útil en respuestas finales largas).
    - Todo lo que venga después de una línea "Observacion:" se ignora: esa
      observación la escribió el modelo, no una herramienta.
    Devuelve un diccionario con lo que haya encontrado.
    """
    campos, actual = {}, None
    for linea in recortar_en_observacion(texto).splitlines():
        coincide = _ETIQUETA.match(quitar_tildes(linea))
        if coincide:
            actual = _NOMBRES[coincide.group(1).lower()]
            campos[actual] = linea.split(":", 1)[1].strip().strip("*_").strip()
        elif actual is not None:
            campos[actual] = f"{campos[actual]}\n{linea.rstrip()}" if campos[actual] else linea.strip()
    return {clave: valor.strip() for clave, valor in campos.items()}


def _nombre_herramienta(texto):
    """'`Calcular()`' -> 'calcular'. Los modelos adornan el nombre de mil formas."""
    limpio = quitar_tildes(texto or "").strip().strip("`'\"*").strip().lower()
    return re.sub(r"\(.*\)$", "", limpio).strip()


def ejecutar_agente(pregunta, max_pasos=6):
    """
    El bucle central. En cada paso: preguntamos al modelo, ejecutamos la
    herramienta que pida y le devolvemos la observacion, hasta que da la
    respuesta final o se acaban los pasos (un tope de seguridad para que un
    agente confundido no se quede en un bucle infinito).
    """
    # `mensajes` es la memoria de la conversación: crece con cada vuelta.
    mensajes = [
        {"role": "system", "content": construir_prompt_sistema()},
        {"role": "user", "content": pregunta},
    ]

    for paso in range(1, max_pasos + 1):
        # temperatura baja: en un agente queremos obediencia al formato, no
        # creatividad. `stop` corta al modelo antes de que invente la observación.
        salida = nim.chat(mensajes=mensajes, temperatura=0.1, max_tokens=500, stop=PARADAS)
        campos = parsear_respuesta(salida)
        accion = _nombre_herramienta(campos.get("Accion"))
        entrada = campos.get("Entrada", "")

        if campos.get("Pensamiento"):
            print(f"[paso {paso}] Pensamiento: {campos['Pensamiento']}")

        # ¿Ya terminó? Solo si NO pidió también una herramienta en esta vuelta:
        # una respuesta final escrita antes de ver la observación es un invento.
        if "Respuesta final" in campos and not accion:
            print(f"[paso {paso}] Respuesta final.")
            return campos["Respuesta final"]
        if "Respuesta final" in campos:
            print(f"[paso {paso}] (se ignora una respuesta final escrita antes de usar la herramienta)")

        # Ejecutamos la herramienta pedida (si existe).
        if accion in HERRAMIENTAS:
            funcion = HERRAMIENTAS[accion][0]
            observacion = funcion(entrada)
            print(f"[paso {paso}] Accion: {accion}('{entrada}') -> {observacion}")
        elif accion:
            observacion = f"Error: la herramienta '{accion}' no existe. Elige una de la lista."
            print(f"[paso {paso}] {observacion}")
        else:
            observacion = (
                "Error de formato: responde con 'Accion:' y 'Entrada:', "
                "o con 'Respuesta final:'."
            )
            print(f"[paso {paso}] {observacion}")

        # Añadimos la respuesta del modelo (sin observaciones inventadas) y la
        # observación real al historial. Así el modelo "recuerda" lo que hizo.
        mensajes.append({"role": "assistant", "content": recortar_en_observacion(salida)})
        mensajes.append({"role": "user", "content": f"Observacion: {observacion}"})

    return "No llegue a una respuesta final dentro del limite de pasos."


def main():
    parser = nim.nuevo_parser("Agente ReAct minimo con herramientas.")
    parser.add_argument(
        "pregunta",
        nargs="?",
        default=PREGUNTA_EJEMPLO,
        help=f"La pregunta o tarea para el agente (por defecto: '{PREGUNTA_EJEMPLO}').",
    )
    parser.add_argument("--pasos", type=int, default=6, help="Maximo de pasos del bucle.")
    args = parser.parse_args()

    print(f"Pregunta: {args.pregunta}\n")
    respuesta = ejecutar_agente(args.pregunta, max_pasos=max(1, args.pasos))
    print("\n" + "=" * 60)
    print(respuesta)
    print("=" * 60)


if __name__ == "__main__":
    nim.ejecutar(main)
