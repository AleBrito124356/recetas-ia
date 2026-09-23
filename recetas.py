"""
Lanzador de las 15 recetas.

  python recetas.py                    lista las recetas con lo que hace cada una
  python recetas.py 05                 ejecuta la receta 05 (acepta sus argumentos)
  python recetas.py 05 --demo          la ejecuta en modo demo: sin clave ni internet
  python recetas.py demo               recorre las 15 recetas en modo demo
  python recetas.py demo --salida DIR  igual, guardando los archivos generados en DIR

Cada receta sigue siendo un script independiente: esto solo te ahorra escribir
la ruta completa y te enseña el catálogo.
"""

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CARPETA = RAIZ / "recetas"
SALIDA_DEMO = RAIZ / "results" / "demo"


def recetas():
    """{'01': ruta, '02': ruta, ...} ordenadas por número."""
    return {r.name[:2]: r for r in sorted(CARPETA.glob("[0-9][0-9]_*.py"))}


def ficha(ruta):
    """(título, qué automatiza) leídos del docstring, sin ejecutar la receta."""
    doc = ast.get_docstring(ast.parse(ruta.read_text(encoding="utf-8"))) or ""
    lineas = doc.splitlines()
    titulo = lineas[0].split(" - ", 1)[-1].strip() if lineas else ruta.stem
    resumen = ""
    for i, linea in enumerate(lineas):
        if linea.strip().lower().startswith("qué automatiza") or linea.strip().lower().startswith("que automatiza"):
            parrafo = []
            for siguiente in lineas[i + 2 :]:
                if not siguiente.strip():
                    break
                parrafo.append(siguiente.strip())
            resumen = " ".join(parrafo)
            break
    # Nos quedamos con la primera frase (hasta un punto o dos puntos).
    cortes = [i for i in (resumen.find(". "), resumen.find(": ")) if i != -1]
    if cortes:
        resumen = resumen[: min(cortes)] + "."
    if len(resumen) > 100:
        resumen = resumen[:97].rsplit(" ", 1)[0] + "..."
    return titulo, resumen


def listar():
    print("Recetas de IA en espanol\n")
    for numero, ruta in recetas().items():
        titulo, resumen = ficha(ruta)
        print(f"  {numero}  {titulo}")
        if resumen:
            print(f"      {resumen}")
    print(
        "\nEjecuta una:        python recetas.py 05"
        "\nSin clave (demo):   python recetas.py 05 --demo"
        "\nRecorrido completo: python recetas.py demo"
        "\nOpciones de una:    python recetas.py 05 --help"
    )


def ejecutar(numero, argumentos, entorno=None):
    """Ejecuta una receta como proceso aparte y devuelve su código de salida."""
    ruta = recetas()[numero]
    return subprocess.call([sys.executable, str(ruta)] + list(argumentos), env=entorno)


def argumentos_demo(salida):
    """Argumentos del recorrido demo: datos de ejemplo y archivos a `salida`."""
    return {
        "02": ["--salida", str(salida / "movimientos_clasificados.json")],
        "03": ["--con-tiempos"],
        "05": ["--salida", str(salida / "factura.json")],
        "07": ["--salida", str(salida / "subtitulos_en.srt")],
        "08": ["--pregunta", "Cuanto cuesta el plan Pro?", "--cache", str(salida / "cache")],
        "11": ["--salida", str(salida / "sinteticos"), "--pedidos", "5", "--semilla", "42"],
        "14": ["--salida", str(salida / "minuta.json")],
    }


def recorrido_demo(salida):
    """Ejecuta las 15 recetas en modo demo, una tras otra, y resume el resultado."""
    salida.mkdir(parents=True, exist_ok=True)
    entorno = dict(os.environ, NIM_DEMO="1")
    extra = argumentos_demo(salida)
    resultados = []
    for numero, ruta in recetas().items():
        titulo, _ = ficha(ruta)
        print("\n" + "#" * 70)
        print(f"#  Receta {numero}: {titulo}  (modo demo)")
        print("#" * 70 + "\n", flush=True)
        inicio = time.perf_counter()
        codigo = ejecutar(numero, extra.get(numero, []), entorno)
        resultados.append((numero, titulo, codigo, time.perf_counter() - inicio))

    print("\n" + "=" * 70)
    print("RESUMEN DEL RECORRIDO DEMO")
    print("=" * 70)
    for numero, titulo, codigo, segundos in resultados:
        estado = "OK" if codigo == 0 else f"FALLO (codigo {codigo})"
        print(f"  {numero}  {titulo:<48} {estado:<18} {segundos:5.1f} s")
    fallos = sum(1 for r in resultados if r[2] != 0)
    print(f"\n{len(resultados) - fallos} de {len(resultados)} recetas OK. Archivos generados en: {salida}")
    return 1 if fallos else 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "lista", "listar"):
        if argv and argv[0] in ("-h", "--help"):
            print(__doc__)
        listar()
        return 0
    if argv[0] == "demo":
        salida = SALIDA_DEMO
        if len(argv) >= 3 and argv[1] == "--salida":
            salida = Path(argv[2]).resolve()
        return recorrido_demo(salida)
    numero = argv[0].zfill(2)
    if numero not in recetas():
        print(f"No existe la receta '{argv[0]}'. Usa un numero del 01 al 15, o 'demo'.\n")
        listar()
        return 2
    return ejecutar(numero, argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
