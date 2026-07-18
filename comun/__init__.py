"""
Paquete `comun`: utilidades compartidas por todas las recetas.

La única pieza compartida es el cliente de NVIDIA NIM (`comun.nim`), para no
repetir en cada receta la lógica de leer la clave, conectar con la API y
mostrar mensajes de error claros en español.
"""

from . import nim  # noqa: F401  (se reexporta para poder hacer `from comun import nim`)
