"""
Receta 08 - Chatea con tus documentos (RAG mínimo)
==================================================

Qué automatiza
--------------
Responde preguntas usando SOLO el contenido de una carpeta de archivos .md.
Es un RAG (Retrieval-Augmented Generation) explicado paso a paso, en menos de
150 líneas, para entender la técnica más usada de la IA aplicada sin frameworks
que escondan la magia.

Las 4 fases del RAG, que verás numeradas abajo:
  1. TROCEAR  : partir los documentos en fragmentos manejables.
  2. INDEXAR  : convertir cada fragmento en un vector (embedding) y guardarlo.
  3. RECUPERAR: al preguntar, buscar los fragmentos más parecidos a la pregunta.
  4. GENERAR  : darle esos fragmentos al modelo como contexto para que responda.

La "similitud" entre vectores se mide con distancia coseno, que calculamos a
mano con numpy: es literalmente un producto punto normalizado.

Uso
---
  python recetas/08_chatbot_docs.py --pregunta "Cuanto cuesta el plan Pro?"
  python recetas/08_chatbot_docs.py --carpeta datos/docs        (modo interactivo)
"""

import sys
import argparse
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402


def trocear_texto(texto, tam=800, solape=100):
    """
    FASE 1 - Partir un documento en fragmentos con un poco de solape.

    El solape (que el final de un trozo se repita al inicio del siguiente) evita
    perder contexto justo en los cortes. `tam` está en caracteres.
    """
    trozos = []
    inicio = 0
    while inicio < len(texto):
        trozos.append(texto[inicio : inicio + tam])
        inicio += tam - solape
    return [t.strip() for t in trozos if t.strip()]


def construir_indice(carpeta):
    """
    FASE 2 - Leer los .md, trocearlos y calcular el embedding de cada trozo.

    Devuelve (fragmentos, matriz_de_vectores). En un proyecto real esto se
    guardaría en una base de datos vectorial; aquí lo tenemos en memoria porque
    para una carpeta de documentos es más que suficiente.
    """
    archivos = sorted(Path(carpeta).glob("*.md"))
    if not archivos:
        print(f"No hay archivos .md en {carpeta}")
        sys.exit(1)

    fragmentos = []
    for archivo in archivos:
        for trozo in trocear_texto(archivo.read_text(encoding="utf-8")):
            # Guardamos de qué archivo salió cada trozo para poder citar la fuente.
            fragmentos.append({"fuente": archivo.name, "texto": trozo})

    print(f"Indexando {len(fragmentos)} fragmentos de {len(archivos)} documentos...")
    vectores = nim.embeddings([f["texto"] for f in fragmentos], input_type="passage")
    matriz = np.array(vectores, dtype=np.float32)
    # Normalizamos cada vector a longitud 1: así el coseno se reduce a un simple
    # producto punto, más rápido y numéricamente estable.
    matriz /= np.linalg.norm(matriz, axis=1, keepdims=True)
    return fragmentos, matriz


def recuperar(pregunta, fragmentos, matriz, k=3):
    """
    FASE 3 - Buscar los k fragmentos más parecidos a la pregunta.

    Embebemos la pregunta con input_type="query" (no "passage") y calculamos la
    similitud coseno contra todo el índice de una sola vez con álgebra vectorial.
    """
    vector_pregunta = np.array(nim.embeddings(pregunta, input_type="query")[0], dtype=np.float32)
    vector_pregunta /= np.linalg.norm(vector_pregunta)
    # Producto punto de la pregunta contra cada fila = similitud coseno.
    similitudes = matriz @ vector_pregunta
    # argsort ordena de menor a mayor; tomamos los k mayores invirtiendo.
    mejores = np.argsort(similitudes)[::-1][:k]
    return [(fragmentos[i], float(similitudes[i])) for i in mejores]


def responder(pregunta, contexto):
    """
    FASE 4 - Generar la respuesta usando solo el contexto recuperado.

    La instrucción de sistema es clave: le prohibimos inventar. Si la respuesta
    no está en los documentos, debe decirlo. Eso es lo que hace confiable a un
    RAG frente a un chatbot suelto.
    """
    sistema = (
        "Responde en espanol usando UNICAMENTE el contexto proporcionado. "
        "Si la respuesta no esta en el contexto, di claramente que no aparece en "
        "los documentos. Cita la fuente entre parentesis cuando puedas."
    )
    prompt = f"CONTEXTO:\n{contexto}\n\nPREGUNTA: {pregunta}"
    return nim.chat(prompt=prompt, sistema=sistema, temperatura=0.2, max_tokens=600)


def contestar_pregunta(pregunta, fragmentos, matriz):
    """Encadena recuperar + generar y muestra también las fuentes usadas."""
    recuperados = recuperar(pregunta, fragmentos, matriz)
    contexto = "\n\n".join(
        f"[{frag['fuente']}] {frag['texto']}" for frag, _ in recuperados
    )
    respuesta = responder(pregunta, contexto)
    print(f"\n{respuesta}\n")
    fuentes = ", ".join(f"{frag['fuente']} ({score:.2f})" for frag, score in recuperados)
    print(f"Fuentes: {fuentes}")


def main():
    parser = argparse.ArgumentParser(description="RAG minimo sobre una carpeta de .md")
    parser.add_argument(
        "--carpeta",
        default=str(nim.ruta_datos("docs")),
        help="Carpeta con los .md (por defecto la de ejemplo).",
    )
    parser.add_argument("--pregunta", help="Pregunta unica. Sin ella, entra en modo interactivo.")
    args = parser.parse_args()

    fragmentos, matriz = construir_indice(args.carpeta)

    if args.pregunta:
        contestar_pregunta(args.pregunta, fragmentos, matriz)
        return

    print("\nModo interactivo. Escribe tu pregunta (o 'salir' para terminar).")
    while True:
        try:
            pregunta = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if pregunta.lower() in {"salir", "exit", "quit", ""}:
            break
        contestar_pregunta(pregunta, fragmentos, matriz)


if __name__ == "__main__":
    main()
