"""
Paquete `comun`: utilidades compartidas por todas las recetas.

- `comun.nim`: el cliente de la API (NVIDIA NIM o cualquier endpoint compatible
  con OpenAI). Lee la clave, conecta, reintenta y traduce los errores a
  mensajes claros en español.
- `comun.demo`: el modo demo (grabar y reproducir respuestas), para probar las
  recetas sin clave ni internet.
- `comun.formatos`: números y textos al estilo LATAM ("1.234,56", "Acción").
"""

from . import nim  # noqa: F401  (se reexporta para poder hacer `from comun import nim`)
