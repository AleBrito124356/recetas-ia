"""
Receta 08 - Chatea con tus documentos (RAG mínimo)
==================================================

Qué automatiza
--------------
Responde preguntas usando SOLO el contenido de una carpeta de archivos .md.
Es un RAG (Retrieval-Augmented Generation) explicado paso a paso, sin
frameworks que escondan la magia, para entender la técnica más usada de la IA
aplicada.

Las 4 fases del RAG, que verás numeradas abajo:
  1. TROCEAR  : partir los documentos en fragmentos manejables, respetando su
                estructura (secciones, párrafos, listas) en vez de cortar a
                ciegas cada N caracteres.
  2. INDEXAR  : convertir cada fragmento en un vector (embedding) y guardarlo.
                Los vectores se guardan en una caché en disco: la segunda vez
                no se vuelve a pagar por los fragmentos que no cambiaron.
  3. RECUPERAR: al preguntar, buscar los fragmentos más parecidos a la pregunta.
  4. GENERAR  : darle esos fragmentos al modelo como contexto para que responda.

La "similitud" entre vectores se mide con distancia coseno, que calculamos a
mano con numpy: es literalmente un producto punto normalizado.

Uso
---
  python recetas/08_chatbot_docs.py --pregunta "Cuanto cuesta el plan Pro?"
  python recetas/08_chatbot_docs.py --carpeta datos/docs        (modo interactivo)
  python recetas/08_chatbot_docs.py --demo --pregunta "Cuanto cuesta el plan Pro?"
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

CARPETA_CACHE = nim.RAIZ / ".cache" / "embeddings"
PREGUNTA_EJEMPLO = "Cuanto cuesta el plan Pro?"


# --------------------------------------------------------------------------- #
# FASE 1 - TROCEAR                                                             #
# --------------------------------------------------------------------------- #


def secciones_markdown(texto):
    """
    Divide un Markdown en secciones: [(ruta_de_titulos, cuerpo), ...].

    La ruta de títulos ("Facturia — Planes y precios > Plan Pro — 12 USD/mes")
    se añade luego a cada fragmento: así un trozo que solo dice "- Hasta 3
    usuarios" sigue sabiendo que habla del plan Pro. Se ignoran los '#' que
    haya dentro de bloques de código.
    """
    secciones, titulos, cuerpo = [], [], []
    en_codigo = False

    def cerrar():
        if any(linea.strip() for linea in cuerpo):
            secciones.append((" > ".join(t for _, t in titulos), "\n".join(cuerpo).strip()))

    for linea in texto.splitlines():
        if linea.strip().startswith("```"):
            en_codigo = not en_codigo
        titulo = None if en_codigo else re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", linea)
        if titulo:
            cerrar()
            cuerpo = []
            nivel = len(titulo.group(1))
            titulos = [t for t in titulos if t[0] < nivel] + [(nivel, titulo.group(2))]
        else:
            cuerpo.append(linea)
    cerrar()
    return secciones


def _partir_bloque(bloque, limite):
    """Parte un bloque demasiado largo por líneas y, si hace falta, por palabras."""
    if len(bloque) <= limite:
        return [bloque]
    piezas = []
    for linea in bloque.split("\n"):
        if len(linea) <= limite:
            piezas.append(linea)
            continue
        actual = ""
        for palabra in linea.split():
            while len(palabra) > limite:  # palabra monstruosa (una URL, un hash)
                if actual:
                    piezas.append(actual)
                    actual = ""
                piezas.append(palabra[:limite])
                palabra = palabra[limite:]
            candidato = f"{actual} {palabra}" if actual else palabra
            if len(candidato) > limite:
                piezas.append(actual)
                actual = palabra
            else:
                actual = candidato
        if actual:
            piezas.append(actual)
    # Volvemos a juntar líneas consecutivas mientras quepan.
    juntas, actual = [], ""
    for pieza in piezas:
        candidato = f"{actual}\n{pieza}" if actual else pieza
        if len(candidato) > limite and actual:
            juntas.append(actual)
            actual = pieza
        else:
            actual = candidato
    if actual:
        juntas.append(actual)
    return juntas


def trocear_texto(texto, tam=800, solape=150):
    """
    FASE 1 - Partir un documento Markdown en fragmentos de como mucho `tam`
    caracteres, sin cortar nunca una línea ni un elemento de lista a la mitad.

    - Cada sección (título) se trocea por separado y cada fragmento lleva
      delante la ruta de títulos de su sección.
    - Dentro de una sección se juntan párrafos completos mientras quepan.
    - Solape: el final de un fragmento (párrafos completos, hasta `solape`
      caracteres) se repite al inicio del siguiente, para no perder contexto
      justo en el corte.
    """
    fragmentos = []
    for titulo, cuerpo in secciones_markdown(texto):
        cabecera = f"{titulo[:200]}\n" if titulo else ""
        limite = max(80, tam - len(cabecera))
        bloques = []
        for parrafo in re.split(r"\n\s*\n", cuerpo):
            if parrafo.strip():
                bloques.extend(_partir_bloque(parrafo.strip(), limite))

        actual = []
        for bloque in bloques:
            if actual and len("\n\n".join(actual + [bloque])) > limite:
                fragmentos.append(cabecera + "\n\n".join(actual))
                arrastre = []
                for previo in reversed(actual):
                    if len("\n\n".join([previo] + arrastre)) > solape:
                        break
                    arrastre.insert(0, previo)
                actual = arrastre
                if len("\n\n".join(actual + [bloque])) > limite:
                    actual = []
            actual.append(bloque)
        if actual:
            fragmentos.append(cabecera + "\n\n".join(actual))
    return fragmentos


# --------------------------------------------------------------------------- #
# FASE 2 - INDEXAR (con caché en disco)                                        #
# --------------------------------------------------------------------------- #


class CacheEmbeddings:
    """
    Guarda en disco el vector de cada fragmento para no pagarlo dos veces.

    La clave es el SHA-256 de (proveedor + modelo + tipo + texto): si cambias
    de modelo o editas un fragmento, su clave cambia y se vuelve a calcular.
    Vectores de modelos distintos viven en archivos distintos y no se mezclan.
    """

    def __init__(self, carpeta, id_modelo):
        self.id_modelo = id_modelo
        nombre = hashlib.sha256(id_modelo.encode("utf-8")).hexdigest()[:16]
        self.ruta = Path(carpeta) / f"{nombre}.json"
        self.vectores = {}
        if self.ruta.exists():
            try:
                self.vectores = json.loads(self.ruta.read_text(encoding="utf-8"))["vectores"]
            except (ValueError, KeyError):
                self.vectores = {}  # caché corrupta: se reconstruye sola
        self.nuevos = 0

    def clave(self, texto, input_type):
        base = f"{self.id_modelo}\n{input_type}\n{texto}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def vectores_de(self, textos, input_type="passage"):
        """Devuelve un vector por texto; solo llama a la API por los que faltan."""
        claves = [self.clave(t, input_type) for t in textos]
        faltan = [i for i, c in enumerate(claves) if c not in self.vectores]
        if faltan:
            calculados = nim.embeddings([textos[i] for i in faltan], input_type=input_type)
            for i, vector in zip(faltan, calculados):
                self.vectores[claves[i]] = vector
            self.nuevos += len(faltan)
        return [self.vectores[c] for c in claves]

    def guardar(self):
        if not self.nuevos:
            return
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = {"modelo": self.id_modelo, "vectores": self.vectores}
        self.ruta.write_text(json.dumps(datos), encoding="utf-8")


def construir_indice(carpeta, cache=None, tam=800, solape=150):
    """
    FASE 2 - Leer los .md, trocearlos y calcular el embedding de cada trozo.

    Devuelve (fragmentos, matriz_de_vectores). En un proyecto real esto se
    guardaría en una base de datos vectorial; aquí lo tenemos en memoria (y los
    vectores en una caché JSON) porque para una carpeta de documentos es más
    que suficiente.
    """
    archivos = sorted(Path(carpeta).glob("*.md"))
    if not archivos:
        print(f"No hay archivos .md en {carpeta}")
        sys.exit(1)

    fragmentos = []
    for archivo in archivos:
        for trozo in trocear_texto(archivo.read_text(encoding="utf-8"), tam, solape):
            # Guardamos de qué archivo salió cada trozo para poder citar la fuente.
            fragmentos.append({"fuente": archivo.name, "texto": trozo})

    textos = [f["texto"] for f in fragmentos]
    if cache is not None:
        vectores = cache.vectores_de(textos, "passage")
        reutilizados = len(textos) - cache.nuevos
        print(
            f"Indexando {len(fragmentos)} fragmentos de {len(archivos)} documentos "
            f"({reutilizados} desde la cache, {cache.nuevos} nuevos)..."
        )
        cache.guardar()
    else:
        print(f"Indexando {len(fragmentos)} fragmentos de {len(archivos)} documentos...")
        vectores = nim.embeddings(textos, input_type="passage")

    matriz = np.array(vectores, dtype=np.float32)
    # Normalizamos cada vector a longitud 1: así el coseno se reduce a un simple
    # producto punto, más rápido y numéricamente estable.
    normas = np.linalg.norm(matriz, axis=1, keepdims=True)
    matriz /= np.where(normas == 0, 1, normas)
    return fragmentos, matriz


# --------------------------------------------------------------------------- #
# FASES 3 y 4 - RECUPERAR y GENERAR                                            #
# --------------------------------------------------------------------------- #


def recuperar(pregunta, fragmentos, matriz, k=3, vector_pregunta=None):
    """
    FASE 3 - Buscar los k fragmentos más parecidos a la pregunta.

    Embebemos la pregunta con input_type="query" (no "passage") y calculamos la
    similitud coseno contra todo el índice de una sola vez con álgebra vectorial.
    """
    if vector_pregunta is None:
        vector_pregunta = nim.embeddings(pregunta, input_type="query")[0]
    vector = np.array(vector_pregunta, dtype=np.float32)
    vector /= np.linalg.norm(vector) or 1.0
    # Producto punto de la pregunta contra cada fila = similitud coseno.
    similitudes = matriz @ vector
    # Ordenamos de mayor a menor similitud; a igualdad, gana el que aparece antes.
    mejores = sorted(range(len(similitudes)), key=lambda i: (-float(similitudes[i]), i))[:k]
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


def contestar_pregunta(pregunta, fragmentos, matriz, k=3):
    """Encadena recuperar + generar y muestra también las fuentes usadas."""
    recuperados = recuperar(pregunta, fragmentos, matriz, k)
    contexto = "\n\n".join(f"[{frag['fuente']}] {frag['texto']}" for frag, _ in recuperados)
    respuesta = responder(pregunta, contexto)
    print(f"\n{respuesta}\n")
    fuentes = ", ".join(f"{frag['fuente']} ({score:.2f})" for frag, score in recuperados)
    print(f"Fuentes: {fuentes}")
    return respuesta, recuperados


def main():
    parser = nim.nuevo_parser("RAG minimo sobre una carpeta de .md")
    parser.add_argument(
        "--carpeta",
        default=str(nim.ruta_datos("docs")),
        help="Carpeta con los .md (por defecto la de ejemplo).",
    )
    parser.add_argument("--pregunta", help="Pregunta unica. Sin ella, entra en modo interactivo.")
    parser.add_argument("--k", type=int, default=3, help="Fragmentos a recuperar (por defecto 3).")
    parser.add_argument(
        "--cache",
        default=str(CARPETA_CACHE),
        help="Carpeta de la cache de embeddings (por defecto .cache/embeddings).",
    )
    parser.add_argument(
        "--sin-cache", action="store_true", help="Calcula todos los embeddings de nuevo."
    )
    args = parser.parse_args()

    cache = None if args.sin_cache else CacheEmbeddings(args.cache, nim.id_embeddings())
    fragmentos, matriz = construir_indice(args.carpeta, cache)

    if args.pregunta:
        print(f"\n> {args.pregunta}")
        contestar_pregunta(args.pregunta, fragmentos, matriz, max(1, args.k))
        return

    print("\nModo interactivo. Escribe tu pregunta (o 'salir' para terminar).")
    if nim.modo_demo():
        print(f"(En modo demo solo hay respuesta grabada para: \"{PREGUNTA_EJEMPLO}\")")
    while True:
        try:
            pregunta = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if pregunta.lower() in {"salir", "exit", "quit", ""}:
            break
        try:
            contestar_pregunta(pregunta, fragmentos, matriz, max(1, args.k))
        except Exception as error:  # noqa: BLE001 - en modo interactivo seguimos
            print(f"\n{nim.describir_error(error)}")


if __name__ == "__main__":
    nim.ejecutar(main)
