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

Uso
---
  python recetas/15_agente_basico.py "Cuanto es 145 * 32 y cuantas letras tiene el resultado?"
  python recetas/15_agente_basico.py "Que dia es hoy y cuantos dias faltan para fin de mes?"
"""

import sys
import ast
import operator
import argparse
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. LAS HERRAMIENTAS                                                          #
# --------------------------------------------------------------------------- #
# Una herramienta es simplemente una función de Python. El agente solo puede
# hacer aquello para lo que le demos una herramienta.

# Operadores permitidos en la calculadora. Usamos el módulo `ast` para evaluar
# expresiones matemáticas de forma SEGURA, sin `eval()` (que ejecutaría código
# arbitrario y es un agujero de seguridad clásico).
_OPERADORES = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _evaluar_nodo(nodo):
    """Recorre el árbol de la expresión permitiendo solo números y operadores."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
        return nodo.value
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
        return _OPERADORES[type(nodo.op)](_evaluar_nodo(nodo.left), _evaluar_nodo(nodo.right))
    if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES:
        return _OPERADORES[type(nodo.op)](_evaluar_nodo(nodo.operand))
    raise ValueError("Expresion no permitida")


def herramienta_calcular(expresion):
    """Evalua una operacion matematica. Ej: '145 * 32'."""
    try:
        arbol = ast.parse(expresion, mode="eval").body
        return str(_evaluar_nodo(arbol))
    except Exception:
        return "Error: expresion matematica invalida."


def herramienta_fecha(_):
    """Devuelve la fecha y hora actuales. Ignora su entrada."""
    return datetime.now().strftime("Hoy es %Y-%m-%d y son las %H:%M.")


def herramienta_dias_fin_mes(_):
    """Calcula cuantos dias faltan para el fin del mes actual."""
    hoy = date.today()
    # Truco: el día 28 siempre existe; sumamos 4 días y retrocedemos al día 1 del
    # mes siguiente para obtener el último día del mes actual sin librerías extra.
    if hoy.month == 12:
        primero_siguiente = date(hoy.year + 1, 1, 1)
    else:
        primero_siguiente = date(hoy.year, hoy.month + 1, 1)
    ultimo_dia = (primero_siguiente - date.resolution).day
    return f"Faltan {ultimo_dia - hoy.day} dias para el fin de mes."


def herramienta_contar_letras(texto):
    """Cuenta cuantas letras (sin espacios) tiene un texto."""
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

def parsear_respuesta(texto):
    """
    Lee la salida del modelo y extrae los campos que nos interesan.
    Devuelve un diccionario con lo que haya encontrado.
    """
    campos = {}
    for linea in texto.splitlines():
        for etiqueta in ("Pensamiento", "Accion", "Entrada", "Respuesta final"):
            prefijo = etiqueta + ":"
            if linea.strip().startswith(prefijo):
                campos[etiqueta] = linea.split(":", 1)[1].strip()
    return campos


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
        # temperatura baja: en un agente queremos obediencia al formato, no creatividad.
        salida = nim.chat(mensajes=mensajes, temperatura=0.1, max_tokens=500)
        campos = parsear_respuesta(salida)

        # ¿Ya terminó?
        if "Respuesta final" in campos:
            print(f"[paso {paso}] Respuesta final.")
            return campos["Respuesta final"]

        accion = campos.get("Accion", "")
        entrada = campos.get("Entrada", "")
        pensamiento = campos.get("Pensamiento", "")
        if pensamiento:
            print(f"[paso {paso}] Pensamiento: {pensamiento}")

        # Ejecutamos la herramienta pedida (si existe).
        if accion in HERRAMIENTAS:
            funcion = HERRAMIENTAS[accion][0]
            observacion = funcion(entrada)
            print(f"[paso {paso}] Accion: {accion}('{entrada}') -> {observacion}")
        else:
            observacion = f"Error: la herramienta '{accion}' no existe. Elige una de la lista."
            print(f"[paso {paso}] {observacion}")

        # Añadimos la respuesta del modelo y la observación al historial para la
        # siguiente vuelta. Así el modelo "recuerda" lo que ya hizo.
        mensajes.append({"role": "assistant", "content": salida})
        mensajes.append({"role": "user", "content": f"Observacion: {observacion}"})

    return "No llegue a una respuesta final dentro del limite de pasos."


def main():
    parser = argparse.ArgumentParser(description="Agente ReAct minimo con herramientas.")
    parser.add_argument("pregunta", help="La pregunta o tarea para el agente.")
    parser.add_argument("--pasos", type=int, default=6, help="Maximo de pasos del bucle.")
    args = parser.parse_args()

    print(f"Pregunta: {args.pregunta}\n")
    respuesta = ejecutar_agente(args.pregunta, max_pasos=args.pasos)
    print("\n" + "=" * 60)
    print(respuesta)
    print("=" * 60)


if __name__ == "__main__":
    main()
