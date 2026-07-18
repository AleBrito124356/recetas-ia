"""
Receta 06 - Generar publicaciones para redes
============================================

Qué automatiza
--------------
De un solo tema saca tres piezas listas para publicar, cada una con el estilo de
su plataforma:
  - un post de LinkedIn (profesional, aporta valor),
  - un hilo de X/Twitter (varios tuits encadenados),
  - un caption de Instagram (cercano, con emojis y hashtags).

Cada plataforma tiene su PROMPT visible abajo. Editar esos prompts es la forma
de ajustar la voz de tu marca sin tocar la lógica del programa.

Uso
---
  python recetas/06_generar_posts.py "Como una PYME puede empezar a usar IA"
  python recetas/06_generar_posts.py "Beneficios del trabajo remoto" --red linkedin
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from comun import nim  # noqa: E402

# --- PROMPTS EDITABLES --------------------------------------------------------
# Aquí vive el "estilo". Cambia estos textos para que suene a ti o a tu cliente.

PROMPT_LINKEDIN = """Escribe un post de LinkedIn en espanol sobre: {tema}

Estilo: profesional pero humano, en primera persona. Empieza con un gancho de
una linea. Desarrolla 2 o 3 ideas con parrafos cortos. Cierra con una pregunta
para invitar a comentar. Usa saltos de linea para que se lea facil. Sin hashtags
excesivos (maximo 3 al final). Nada de lenguaje corporativo vacio."""

PROMPT_X = """Escribe un hilo de X (Twitter) en espanol sobre: {tema}

Formato: numera cada tuit como "1/", "2/", etc. Entre 4 y 6 tuits. El primero
debe enganchar. Cada tuit por debajo de 280 caracteres. Directo, sin relleno.
El ultimo tuit cierra con una idea memorable o un llamado a la accion."""

PROMPT_INSTAGRAM = """Escribe un caption de Instagram en espanol sobre: {tema}

Estilo: cercano y visual, con algunos emojis bien puestos (sin abusar). Un
gancho corto arriba, 2 o 3 frases de valor, y al final una linea de 5 a 8
hashtags relevantes en espanol."""

# Mapa de redes disponibles: nombre -> (titulo para mostrar, prompt).
REDES = {
    "linkedin": ("LinkedIn", PROMPT_LINKEDIN),
    "x": ("Hilo de X / Twitter", PROMPT_X),
    "instagram": ("Caption de Instagram", PROMPT_INSTAGRAM),
}


def generar(tema, prompt_plantilla):
    """Rellena la plantilla con el tema y pide el contenido al modelo."""
    return nim.chat(
        prompt=prompt_plantilla.format(tema=tema),
        sistema="Eres un redactor de redes sociales experto en espanol.",
        temperatura=0.8,  # más alto: queremos variedad y chispa en el copy.
        max_tokens=700,
    )


def main():
    parser = argparse.ArgumentParser(description="Genera posts para redes desde un tema.")
    parser.add_argument("tema", help="El tema sobre el que generar el contenido.")
    parser.add_argument(
        "--red",
        choices=list(REDES.keys()),
        help="Genera solo una red. Si se omite, genera las tres.",
    )
    args = parser.parse_args()

    redes_a_generar = [args.red] if args.red else list(REDES.keys())

    for clave in redes_a_generar:
        titulo, plantilla = REDES[clave]
        print("=" * 60)
        print(titulo.upper())
        print("=" * 60)
        print(generar(args.tema, plantilla))
        print()


if __name__ == "__main__":
    main()
