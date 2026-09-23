# Cambios

## 1.1.0

### Nuevo

- **Modo demo** (`--demo` en cualquier receta o `NIM_DEMO=1`): las 15 recetas
  funcionan sin clave ni internet reproduciendo casetes de `datos/demo/`. Cada
  respuesta indica su `origen` ("redactada a mano" o "grabada de <modelo> el
  <fecha>"); una entrada sin grabar da un error claro, nunca contenido
  inventado. `NIM_GRABAR=1` graba respuestas reales en el casete.
- **Lanzador `recetas.py`**: `python recetas.py` lista las recetas,
  `python recetas.py 05 [args]` ejecuta una y `python recetas.py demo` recorre
  las 15 en modo demo.
- **Proveedor configurable**: `NIM_BASE_URL`, `NIM_API_KEY` (con prioridad sobre
  `NVIDIA_API_KEY`), `NIM_REINTENTOS` y `NIM_TIMEOUT`. Los endpoints locales
  (Ollama, LM Studio) no necesitan clave.
- **Errores en español** para clave inválida (401), permisos (403), modelo
  inexistente (404), entrada demasiado larga (400/413/422), límite de
  peticiones (429, con avisos de reintento), errores del servidor (5xx), sin
  conexión, timeout, JSON inválido y respuesta vacía. `NIM_DEBUG=1` muestra la
  traza completa.
- Datos de ejemplo para las recetas que no tenían: `datos/informe_ejemplo.pdf`
  (01), `datos/producto_ejemplo.png` (10), `datos/borrador_ejemplo.txt` (12) y
  `datos/notas_correo.txt` (13), generados con `herramientas/generar_ejemplos.py`.
- Batería de pruebas con pytest (`tests/`), toda sin internet: cliente falso,
  servidor stub en 127.0.0.1, ejecuciones de extremo a extremo y una prueba de
  regresión por cada fallo corregido. `pyproject.toml` y `requirements-dev.txt`.

### Corregido

- `nim.extraer_json` devolvía el primer objeto de una lista precedida de texto
  (rompía la receta 11). Ahora usa `json.JSONDecoder.raw_decode` y acepta
  `esperado=list|dict`.
- `nim.chat` y `nim.vision` fallaban con `AttributeError` si la API devolvía
  `content = None`.
- 01: `trocear()` no partía los párrafos más largos que el límite (67.500
  caracteres en un solo trozo). Ahora ningún trozo lo supera y la reducción se
  repite por rondas si hace falta.
- 02: no leía montos con coma decimal (`-84,50`), miles (`1.234,56`), símbolos
  (`$ -12.30`, `B/.`) ni negativos entre paréntesis; tampoco CSV con `;` o BOM.
- 05: `validar()` fallaba con `impuesto: null` y daba por buena una factura con
  líneas e impuesto imposibles.
- 07: si el modelo devolvía menos fragmentos, rellenaba con el texto del primer
  subtítulo en vez del que faltaba.
- 08: el troceado cortaba listas y secciones a mitad de línea.
- 09: fallaba con porcentajes en texto (`"60%"`) y cortaba las respuestas del
  CSV que tenían comas sin comillas.
- 11: fallaba con precios en texto y no se podía reproducir.
- 15: aceptaba una "Observacion" inventada por el modelo como si fuera real, no
  entendía `Acción:` con tilde, cortaba respuestas finales de varias líneas y
  la calculadora se colgaba con `9**9**9`.

### Cambios de comportamiento

- 01, 06, 07, 10, 12, 13 y 15 ya no exigen argumentos: sin ellos usan los datos
  de ejemplo (los argumentos de antes siguen funcionando igual).
- 02: la fila `TOTAL` pasa a llamarse `TOTAL NETO` y se añade `GASTO TOTAL`;
  nuevas opciones `--salida` y `--lote`.
- 05: nueva opción `--estricto` (código 2 si la validación encuentra
  problemas); `validar(datos, texto_original=None)` comprueba además que las
  cifras aparezcan en la factura.
- 07: un subtítulo de dos líneas se traduce a dos líneas (antes se unían en
  una) y se conservan los saltos `\r\n` y el BOM del archivo original.
- 08: `trocear_texto(texto, tam, solape)` trocea por secciones y párrafos; el
  solape ahora son párrafos completos de hasta `solape` caracteres. Nuevas
  opciones `--k`, `--cache` y `--sin-cache`.
- 11: nueva opción `--semilla`; cada línea de pedido incluye `precio_unitario`
  y `pedidos.csv` incluye `cliente_id` y `producto_id`.
- 15: si en la misma vuelta el modelo escribe una `Accion` y una
  `Respuesta final`, primero se ejecuta la herramienta.
- Los embeddings solo envían `input_type`/`truncate` al endpoint de NVIDIA.
