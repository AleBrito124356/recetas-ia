"""
Cliente compartido para la API gratuita de NVIDIA NIM.

¿Por qué existe este archivo?
-----------------------------
Las 15 recetas necesitan lo mismo: leer la clave de la variable de entorno,
conectarse al endpoint de NVIDIA (que es compatible con el formato de OpenAI)
y, sobre todo, avisar en español y con pasos concretos cuando falta la clave.
En vez de copiar ese código quince veces, vive aquí una sola vez.

NVIDIA NIM regala créditos para usar modelos como Llama 3.3 70B. Conseguir la
clave toma dos minutos en https://build.nvidia.com y no requiere tarjeta.

Convención de todo el repositorio:
  - Endpoint compatible con OpenAI: https://integrate.api.nvidia.com/v1
  - Variable de entorno: NVIDIA_API_KEY (la clave empieza con "nvapi-")
  - Modelo de chat por defecto: meta/llama-3.3-70b-instruct
  - Se puede cambiar el modelo con la variable NIM_MODEL sin tocar el código.
"""

import json
import os
import re
import sys
import base64
import mimetypes
from pathlib import Path

# `python-dotenv` es opcional pero muy cómodo: permite guardar la clave en un
# archivo .env en vez de exportarla a mano en cada terminal. Si no está
# instalado, seguimos funcionando siempre que la variable exista en el entorno.
try:
    from dotenv import load_dotenv

    # Cargamos el .env de la raíz del proyecto (dos carpetas arriba de este
    # archivo: comun/ -> raíz) y también el del directorio actual, por si el
    # usuario ejecuta la receta desde otro sitio.
    _RAIZ = Path(__file__).resolve().parent.parent
    load_dotenv(_RAIZ / ".env")
    load_dotenv()  # también busca un .env en el directorio de trabajo actual
except ImportError:
    pass


# --------------------------------------------------------------------------- #
# Configuración                                                               #
# --------------------------------------------------------------------------- #

BASE_URL = "https://integrate.api.nvidia.com/v1"

# Modelos por defecto. Todos se pueden sobreescribir con variables de entorno
# para experimentar sin editar el código de las recetas.
MODELO_CHAT = os.getenv("NIM_MODEL", "meta/llama-3.3-70b-instruct")
MODELO_VISION = os.getenv("NIM_VISION_MODEL", "meta/llama-3.2-90b-vision-instruct")
MODELO_EMBEDDINGS = os.getenv("NIM_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5")


_MENSAJE_SIN_CLAVE = """
============================================================
  Falta tu clave de NVIDIA NIM  (variable NVIDIA_API_KEY)
============================================================
NVIDIA regala creditos para usar modelos como Llama 3.3 70B.
Conseguir la clave toma 2 minutos y es gratis (sin tarjeta):

  1. Entra a  https://build.nvidia.com
  2. Crea una cuenta o inicia sesion con Google/GitHub.
  3. Elige un modelo, por ejemplo "llama-3.3-70b-instruct".
  4. Pulsa el boton "Get API Key" (Generar clave).
  5. Copia la clave: empieza con  nvapi-...

Despues, en la raiz del proyecto, crea tu archivo .env:

  cp .env.example .env        (en Windows:  copy .env.example .env)

y pega tu clave dentro:

  NVIDIA_API_KEY=nvapi-tu_clave_real_aqui

Vuelve a ejecutar la receta y listo.
============================================================
"""


class ErrorDeConfiguracion(RuntimeError):
    """Se lanza cuando falta configuración imprescindible (p. ej. la clave)."""


def _obtener_clave():
    """
    Devuelve la clave de la API o corta el programa con un mensaje amable.

    Preferimos `sys.exit` a lanzar una excepción con traza técnica: quien usa
    estas recetas puede no ser programador, y una traza de Python asusta más
    de lo que ayuda. El mensaje explica exactamente qué hacer.
    """
    clave = os.getenv("NVIDIA_API_KEY", "").strip()
    if not clave:
        print(_MENSAJE_SIN_CLAVE)
        sys.exit(1)
    # Un despiste típico: dejar el valor de ejemplo con las X. Lo detectamos
    # para no gastar una llamada que fallará con un error críptico del servidor.
    if clave.startswith("nvapi-X") or "XXXX" in clave:
        print(_MENSAJE_SIN_CLAVE)
        print(">> Parece que dejaste la clave de ejemplo (nvapi-XXXX...).")
        print(">> Reemplazala por tu clave real de build.nvidia.com.\n")
        sys.exit(1)
    return clave


def _crear_cliente():
    """
    Crea el cliente de OpenAI apuntando al endpoint de NVIDIA.

    Usamos la librería `openai` porque NVIDIA NIM expone una API compatible:
    el mismo código sirve para OpenAI, NVIDIA, Groq, etc. cambiando base_url.
    """
    try:
        from openai import OpenAI
    except ImportError:
        print(
            "Falta la libreria 'openai'. Instala las dependencias con:\n\n"
            "  pip install -r requirements.txt\n"
        )
        sys.exit(1)

    return OpenAI(base_url=BASE_URL, api_key=_obtener_clave())


# Creamos el cliente una sola vez y lo reutilizamos (patrón singleton simple).
# Así evitamos reconstruir la conexión en cada llamada dentro de un bucle.
_cliente = None


def cliente():
    """Devuelve el cliente compartido, creándolo la primera vez que se usa."""
    global _cliente
    if _cliente is None:
        _cliente = _crear_cliente()
    return _cliente


# --------------------------------------------------------------------------- #
# Funciones de alto nivel que usan las recetas                                #
# --------------------------------------------------------------------------- #


def chat(
    prompt=None,
    sistema=None,
    mensajes=None,
    modelo=None,
    temperatura=0.3,
    max_tokens=1024,
):
    """
    Envía un mensaje al modelo y devuelve el texto de la respuesta.

    Parámetros
    ----------
    prompt : str
        Lo que le pides al modelo (el mensaje del usuario). Se ignora si pasas
        `mensajes` directamente.
    sistema : str
        Instrucción de sistema: define el rol y las reglas del asistente.
    mensajes : list[dict]
        Conversación completa en formato [{"role": ..., "content": ...}].
        Útil para agentes que mantienen historial (ver receta 15).
    modelo : str
        Nombre del modelo. Por defecto usa MODELO_CHAT.
    temperatura : float
        0 = respuestas deterministas y precisas; valores altos = más creatividad.
        Para tareas de extracción y clasificación conviene un valor bajo.
    max_tokens : int
        Límite de longitud de la respuesta.

    Devuelve
    --------
    str : el contenido de texto de la respuesta del modelo.
    """
    if mensajes is None:
        mensajes = []
        if sistema:
            mensajes.append({"role": "system", "content": sistema})
        mensajes.append({"role": "user", "content": prompt})

    respuesta = cliente().chat.completions.create(
        model=modelo or MODELO_CHAT,
        messages=mensajes,
        temperature=temperatura,
        max_tokens=max_tokens,
    )
    return respuesta.choices[0].message.content.strip()


def vision(prompt, imagen, modelo=None, temperatura=0.2, max_tokens=1024):
    """
    Pregunta al modelo de visión sobre una imagen local.

    La imagen se envía codificada en base64 dentro de un "data URL". Es la forma
    estándar de mandar imágenes a modelos compatibles con OpenAI sin subirlas
    antes a ningún servidor: viaja dentro de la misma petición.

    `imagen` puede ser una ruta a un archivo (str o Path).
    """
    ruta = Path(imagen)
    if not ruta.exists():
        raise FileNotFoundError(f"No encuentro la imagen: {ruta}")

    # Detectamos el tipo (jpeg, png, webp...) para armar bien el data URL.
    tipo_mime = mimetypes.guess_type(str(ruta))[0] or "image/jpeg"
    datos_b64 = base64.b64encode(ruta.read_bytes()).decode("utf-8")
    data_url = f"data:{tipo_mime};base64,{datos_b64}"

    mensajes = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    respuesta = cliente().chat.completions.create(
        model=modelo or MODELO_VISION,
        messages=mensajes,
        temperature=temperatura,
        max_tokens=max_tokens,
    )
    return respuesta.choices[0].message.content.strip()


def embeddings(textos, input_type="passage", modelo=None):
    """
    Convierte una lista de textos en vectores numéricos (embeddings).

    Los embeddings son la base de la búsqueda semántica y del RAG (receta 08):
    textos con significado parecido quedan cerca en el espacio vectorial.

    `input_type` es específico de los modelos de NVIDIA para recuperación:
      - "passage" para los documentos que guardas en tu índice.
      - "query"   para la pregunta del usuario en el momento de buscar.
    Usar el tipo correcto mejora bastante la calidad de los resultados.
    """
    if isinstance(textos, str):
        textos = [textos]

    respuesta = cliente().embeddings.create(
        model=modelo or MODELO_EMBEDDINGS,
        input=textos,
        # `extra_body` deja pasar parámetros propios de NVIDIA que no forman
        # parte del estándar de OpenAI.
        extra_body={"input_type": input_type, "truncate": "NONE"},
    )
    return [dato.embedding for dato in respuesta.data]


# --------------------------------------------------------------------------- #
# Utilidades                                                                   #
# --------------------------------------------------------------------------- #


def extraer_json(texto):
    """
    Extrae y parsea el primer objeto o lista JSON que aparezca en un texto.

    Los modelos, aunque les pidas "responde solo JSON", a veces envuelven la
    respuesta en ```json ... ``` o añaden una frase antes. Esta función limpia
    esos casos comunes para que las recetas de extracción sean robustas.
    """
    texto = texto.strip()

    # 1) Quitar vallas de código tipo ```json ... ```
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-zA-Z]*\s*", "", texto)
        texto = re.sub(r"\s*```$", "", texto)
        texto = texto.strip()

    # 2) Intento directo: lo más habitual cuando el modelo se porta bien.
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # 3) Buscar el bloque delimitado por { } o [ ] más externo.
    for apertura, cierre in (("{", "}"), ("[", "]")):
        inicio = texto.find(apertura)
        fin = texto.rfind(cierre)
        if inicio != -1 and fin != -1 and fin > inicio:
            fragmento = texto[inicio : fin + 1]
            try:
                return json.loads(fragmento)
            except json.JSONDecodeError:
                continue

    raise ValueError(
        "No se pudo extraer JSON valido de la respuesta del modelo.\n"
        "Respuesta recibida:\n" + texto[:500]
    )


def ruta_datos(*partes):
    """
    Devuelve una ruta dentro de la carpeta `datos/` del repositorio.

    Sirve para que las recetas encuentren los archivos de ejemplo sin importar
    desde qué carpeta las ejecutes.
    """
    raiz = Path(__file__).resolve().parent.parent
    return raiz / "datos" / Path(*partes)
