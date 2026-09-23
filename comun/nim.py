"""
Cliente compartido para la API gratuita de NVIDIA NIM (y cualquier API
compatible con OpenAI).

¿Por qué existe este archivo?
-----------------------------
Las 15 recetas necesitan lo mismo: leer la clave, conectarse a un endpoint
compatible con el formato de OpenAI y, sobre todo, avisar en español y con
pasos concretos cuando algo falla. En vez de copiar ese código quince veces,
vive aquí una sola vez.

NVIDIA NIM regala créditos para usar modelos como Llama 3.3 70B. Conseguir la
clave toma dos minutos en https://build.nvidia.com y no requiere tarjeta.

Configuración (variables de entorno o archivo .env)
---------------------------------------------------
  NIM_API_KEY / NVIDIA_API_KEY  Tu clave. NIM_API_KEY tiene prioridad.
  NIM_BASE_URL      Endpoint. Por defecto https://integrate.api.nvidia.com/v1.
                    Cambiándolo usas OpenAI, Groq, Ollama local, etc.
  NIM_MODEL         Modelo de chat (por defecto meta/llama-3.3-70b-instruct).
  NIM_VISION_MODEL  Modelo de visión (receta 10).
  NIM_EMBED_MODEL   Modelo de embeddings (receta 08).
  NIM_REINTENTOS    Reintentos ante límite de peticiones o fallos de red (2).
  NIM_TIMEOUT       Segundos máximos por petición (120).
  NIM_DEMO=1        Modo demo: respuestas pregrabadas, sin clave ni internet.
  NIM_GRABAR=1      Graba las respuestas reales para el modo demo.
  NIM_DEBUG=1       Muestra la traza completa de Python cuando algo falla.

La idea central: cada receta llama a `nim.chat(...)`, `nim.vision(...)` o
`nim.embeddings(...)` y se olvida de todo lo demás. Si falla la red, la clave
o el modelo, `nim.ejecutar(main)` traduce el error a un mensaje en español con
la solución, en vez de una traza de 40 líneas en inglés.
"""

import argparse
import base64
import json
import logging
import mimetypes
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent

# `python-dotenv` es opcional pero muy cómodo: permite guardar la clave en un
# archivo .env en vez de exportarla a mano en cada terminal. Si no está
# instalado, seguimos funcionando siempre que la variable exista en el entorno.
# NIM_IGNORAR_DOTENV=1 lo desactiva (lo usan las pruebas para ser herméticas).
if os.getenv("NIM_IGNORAR_DOTENV", "").strip().lower() not in ("1", "true", "si"):
    try:
        from dotenv import load_dotenv

        # Cargamos el .env de la raíz del proyecto y también el del directorio
        # actual, por si el usuario ejecuta la receta desde otro sitio.
        load_dotenv(RAIZ / ".env")
        load_dotenv()
    except ImportError:
        pass


# --------------------------------------------------------------------------- #
# Configuración                                                               #
# --------------------------------------------------------------------------- #

BASE_URL_NVIDIA = "https://integrate.api.nvidia.com/v1"

# Endpoint efectivo al importar el módulo. Para cambiarlo usa la variable
# NIM_BASE_URL (no hace falta tocar código); ver base_url().
BASE_URL = os.getenv("NIM_BASE_URL", "").strip() or BASE_URL_NVIDIA

# Modelos por defecto. Todos se pueden sobreescribir con variables de entorno
# para experimentar sin editar el código de las recetas.
MODELO_CHAT = os.getenv("NIM_MODEL", "meta/llama-3.3-70b-instruct")
MODELO_VISION = os.getenv("NIM_VISION_MODEL", "meta/llama-3.2-90b-vision-instruct")
MODELO_EMBEDDINGS = os.getenv("NIM_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5")

# Cuántos textos mandamos por petición de embeddings. Los endpoints limitan el
# tamaño del lote; 32 es seguro para NVIDIA, OpenAI y Ollama.
LOTE_EMBEDDINGS = 32

_VERDADERO = ("1", "true", "si", "sí", "yes", "on")


def _bandera(nombre):
    """True si la variable de entorno `nombre` está activada (1, true, si...)."""
    return os.getenv(nombre, "").strip().lower() in _VERDADERO


def base_url():
    """Endpoint efectivo: NIM_BASE_URL si existe; si no, BASE_URL (NVIDIA)."""
    return os.getenv("NIM_BASE_URL", "").strip() or BASE_URL


def es_local(url):
    """True si el endpoint está en tu propia máquina (Ollama, LM Studio...)."""
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".localhost")


def es_nvidia(url):
    """True si el endpoint es el de NVIDIA (acepta parámetros propios de NIM)."""
    return (urlparse(url).hostname or "").endswith("nvidia.com")


def modo_demo():
    """True si hay que usar respuestas pregrabadas en vez del modelo real."""
    return _bandera("NIM_DEMO")


def activar_demo():
    """Activa el modo demo para este proceso (lo usa la opción --demo)."""
    global _cliente
    os.environ["NIM_DEMO"] = "1"
    _cliente = None


def _entero_env(nombre, por_defecto, minimo=0):
    valor = os.getenv(nombre, "").strip()
    if not valor:
        return por_defecto
    try:
        return max(minimo, int(float(valor)))
    except ValueError:
        print(f"aviso: {nombre}='{valor}' no es un numero; uso {por_defecto}.", file=sys.stderr)
        return por_defecto


def reintentos():
    """Reintentos automáticos ante 429, 5xx o fallos de red (NIM_REINTENTOS)."""
    return _entero_env("NIM_REINTENTOS", 2)


def timeout():
    """Segundos máximos por petición antes de rendirse (NIM_TIMEOUT)."""
    return _entero_env("NIM_TIMEOUT", 120, minimo=1)


# --------------------------------------------------------------------------- #
# Errores propios (todos con mensaje en español)                              #
# --------------------------------------------------------------------------- #


class ErrorNIM(RuntimeError):
    """Base de los errores de este módulo: su texto ya es el mensaje final."""


class ErrorDeConfiguracion(ErrorNIM):
    """Se lanza cuando falta configuración imprescindible."""


class RespuestaVacia(ErrorNIM):
    """El modelo devolvió una respuesta sin texto (filtro de contenido, etc.)."""


class RespuestaInvalida(ValueError):
    """El modelo no devolvió el JSON que le pedimos."""


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

Solo quieres verla funcionar? Anade --demo al comando (o
define NIM_DEMO=1): respuestas pregrabadas, sin clave.
============================================================
"""

_MENSAJE_SIN_CLAVE_OTRO = """
============================================================
  Falta la clave para {url}
============================================================
Estas usando otro proveedor (NIM_BASE_URL). Pon su clave en tu
archivo .env con la variable NIM_API_KEY, por ejemplo:

  NIM_API_KEY=tu_clave_del_proveedor

Los endpoints locales (Ollama en http://localhost:11434/v1,
LM Studio...) no necesitan clave.
============================================================
"""


def _obtener_clave():
    """
    Devuelve la clave de la API o corta el programa con un mensaje amable.

    Preferimos `sys.exit` a lanzar una excepción con traza técnica: quien usa
    estas recetas puede no ser programador, y una traza de Python asusta más
    de lo que ayuda. El mensaje explica exactamente qué hacer.
    """
    url = base_url()
    clave = (os.getenv("NIM_API_KEY", "") or os.getenv("NVIDIA_API_KEY", "")).strip()

    # Un servidor en tu propia máquina (Ollama, LM Studio) no pide clave, pero
    # la librería `openai` exige un texto no vacío: le pasamos uno cualquiera.
    if es_local(url):
        return clave or "sin-clave-local"

    mensaje = _MENSAJE_SIN_CLAVE if es_nvidia(url) else _MENSAJE_SIN_CLAVE_OTRO.format(url=url)
    if not clave:
        print(mensaje)
        sys.exit(1)
    # Un despiste típico: dejar el valor de ejemplo con las X. Lo detectamos
    # para no gastar una llamada que fallará con un error críptico del servidor.
    if clave.startswith("nvapi-X") or "XXXX" in clave:
        print(mensaje)
        print(">> Parece que dejaste la clave de ejemplo (nvapi-XXXX...).")
        print(">> Reemplazala por tu clave real.\n")
        sys.exit(1)
    return clave


class _AvisoReintentos(logging.Handler):
    """
    La librería `openai` reintenta sola ante un 429 o un fallo de red, pero en
    silencio. Este pequeño manejador de logging lo cuenta en español para que
    no parezca que el programa se colgó.
    """

    def emit(self, record):
        if not str(record.msg).startswith("Retrying request"):
            return
        try:
            espera, numero, total = record.args
            print(
                f"  aviso: el servidor no respondio bien; reintento {numero} de {total} "
                f"en {float(espera):.1f} s...",
                file=sys.stderr,
            )
        except (TypeError, ValueError):
            pass


def _activar_avisos_de_reintento():
    registro = logging.getLogger("openai._base_client")
    if not any(isinstance(h, _AvisoReintentos) for h in registro.handlers):
        registro.addHandler(_AvisoReintentos(level=logging.INFO))
        if registro.level == logging.NOTSET or registro.level > logging.INFO:
            registro.setLevel(logging.INFO)


def _crear_cliente():
    """
    Crea el cliente: el de demostración, o el de OpenAI apuntando al endpoint.

    Usamos la librería `openai` porque NVIDIA NIM expone una API compatible:
    el mismo código sirve para OpenAI, NVIDIA, Groq, Ollama... cambiando solo
    NIM_BASE_URL. Si NIM_GRABAR=1, envolvemos el cliente real para guardar sus
    respuestas y poder reproducirlas después en modo demo.
    """
    if modo_demo():
        from . import demo

        return demo.ClienteDemo()

    try:
        from openai import OpenAI
    except ImportError:
        print(
            "Falta la libreria 'openai'. Instala las dependencias con:\n\n"
            "  pip install -r requirements.txt\n\n"
            "(o prueba la receta sin instalar nada de IA con --demo)"
        )
        sys.exit(1)

    _activar_avisos_de_reintento()
    real = OpenAI(
        base_url=base_url(),
        api_key=_obtener_clave(),
        max_retries=reintentos(),
        timeout=timeout(),
    )
    if _bandera("NIM_GRABAR"):
        from . import demo

        return demo.ClienteGrabador(real)
    return real


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


def _completar(modelo, mensajes, temperatura, max_tokens, stop=None):
    """Hace la petición de chat y devuelve el texto, sin sorpresas con None."""
    parametros = dict(
        model=modelo,
        messages=mensajes,
        temperature=temperatura,
        max_tokens=max_tokens,
    )
    if stop:
        parametros["stop"] = [stop] if isinstance(stop, str) else list(stop)

    respuesta = cliente().chat.completions.create(**parametros)

    # Algunos modelos (o un filtro de contenido) devuelven `content = None` o
    # ninguna opción. Antes eso rompía con AttributeError; ahora lo explicamos.
    opciones = getattr(respuesta, "choices", None) or []
    if not opciones:
        raise RespuestaVacia(
            "El modelo no devolvio ninguna respuesta. Vuelve a intentarlo o prueba "
            "otro modelo con la variable NIM_MODEL."
        )
    motivo = getattr(opciones[0], "finish_reason", None)
    contenido = (getattr(opciones[0].message, "content", None) or "").strip()
    if not contenido:
        pista = ""
        if motivo == "content_filter":
            pista = " El filtro de contenido del proveedor bloqueo la respuesta."
        elif motivo == "length":
            pista = " Se agoto max_tokens antes de escribir nada."
        raise RespuestaVacia(
            f"El modelo devolvio una respuesta vacia (motivo: {motivo or 'desconocido'})."
            f"{pista}\nReformula la peticion o prueba otro modelo con NIM_MODEL."
        )
    return contenido


def chat(
    prompt=None,
    sistema=None,
    mensajes=None,
    modelo=None,
    temperatura=0.3,
    max_tokens=1024,
    stop=None,
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
    stop : str o list[str]
        Texto(s) donde el modelo debe dejar de escribir. La receta 15 lo usa
        para que el agente no invente la "Observacion" de una herramienta.

    Devuelve
    --------
    str : el contenido de texto de la respuesta del modelo.
    """
    if mensajes is None:
        mensajes = []
        if sistema:
            mensajes.append({"role": "system", "content": sistema})
        mensajes.append({"role": "user", "content": prompt})

    return _completar(modelo or MODELO_CHAT, mensajes, temperatura, max_tokens, stop)


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
        raise FileNotFoundError(2, "No encuentro la imagen", str(ruta))

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
    return _completar(modelo or MODELO_VISION, mensajes, temperatura, max_tokens)


def embeddings(textos, input_type="passage", modelo=None):
    """
    Convierte una lista de textos en vectores numéricos (embeddings).

    Los embeddings son la base de la búsqueda semántica y del RAG (receta 08):
    textos con significado parecido quedan cerca en el espacio vectorial.

    `input_type` es específico de los modelos de NVIDIA para recuperación:
      - "passage" para los documentos que guardas en tu índice.
      - "query"   para la pregunta del usuario en el momento de buscar.
    Usar el tipo correcto mejora bastante la calidad de los resultados. Con
    otros proveedores (OpenAI, Ollama) ese parámetro no existe y no se envía.
    """
    if isinstance(textos, str):
        textos = [textos]

    extra = {}
    if es_nvidia(base_url()):
        # `extra_body` deja pasar parámetros propios de NVIDIA que no forman
        # parte del estándar de OpenAI (otros proveedores los rechazarían).
        extra["extra_body"] = {"input_type": input_type, "truncate": "NONE"}

    vectores = []
    # Mandamos por lotes: los endpoints limitan cuántos textos caben por petición.
    for inicio in range(0, len(textos), LOTE_EMBEDDINGS):
        lote = textos[inicio : inicio + LOTE_EMBEDDINGS]
        respuesta = cliente().embeddings.create(
            model=modelo or MODELO_EMBEDDINGS, input=lote, **extra
        )
        datos = sorted(respuesta.data, key=lambda d: getattr(d, "index", 0) or 0)
        vectores.extend(list(dato.embedding) for dato in datos)
    return vectores


def id_embeddings(modelo=None):
    """
    Identifica de dónde salen los vectores (proveedor + modelo). La receta 08
    lo usa en la clave de su caché: vectores de modelos distintos no son
    comparables y nunca deben mezclarse.
    """
    if modo_demo():
        from . import demo

        return demo.ID_VECTORES
    return f"{base_url()}|{modelo or MODELO_EMBEDDINGS}"


# --------------------------------------------------------------------------- #
# Utilidades                                                                   #
# --------------------------------------------------------------------------- #

_VALLA = re.compile(r"```[a-zA-Z0-9_-]*[ \t]*\r?\n?(.*?)```", re.DOTALL)


def _candidatos_json(texto):
    """
    Recorre el texto y devuelve cada valor JSON de primer nivel que encuentre,
    como (posicion, longitud, valor). Usa `json.JSONDecoder.raw_decode`, que
    parsea un valor a partir de una posición y dice dónde termina: así no hay
    que adivinar con find/rfind dónde acaba el bloque.
    """
    decodificador = json.JSONDecoder()
    candidatos = []
    i = 0
    while i < len(texto):
        if texto[i] in "{[":
            try:
                valor, fin = decodificador.raw_decode(texto, i)
            except json.JSONDecodeError:
                i += 1
                continue
            candidatos.append((i, fin - i, valor))
            i = fin  # saltamos lo ya parseado: no nos interesan sus trozos internos
        else:
            i += 1
    return candidatos


def extraer_json(texto, esperado=None):
    """
    Extrae y parsea el JSON que aparezca en la respuesta de un modelo.

    Los modelos, aunque les pidas "responde solo JSON", a veces envuelven la
    respuesta en ```json ... ``` o añaden una frase antes o después. Esta
    función encuentra el bloque JSON correcto en esos casos.

    `esperado` puede ser `list` o `dict`. Si lo indicas:
      - se elige el primer bloque de ese tipo;
      - si pides `list` y el modelo devolvió {"clientes": [...]}, se desenvuelve.
    Sin `esperado` se devuelve el bloque JSON más largo del texto (así una
    lista precedida de una frase vuelve entera, no solo su primer objeto).

    Lanza `RespuestaInvalida` (un ValueError) si no hay JSON utilizable.
    """
    texto = (texto or "").strip()

    # 1) Intento directo: lo más habitual cuando el modelo se porta bien.
    candidatos = []
    try:
        candidatos.append((0, len(texto), json.loads(texto)))
    except json.JSONDecodeError:
        # 2) Bloques de código ```json ... ``` (van primero: son intencionados).
        for bloque in _VALLA.findall(texto):
            try:
                candidatos.append((0, len(bloque), json.loads(bloque.strip())))
            except json.JSONDecodeError:
                pass
        # 3) Cualquier objeto o lista de primer nivel dentro del texto.
        candidatos.extend(_candidatos_json(texto))

    candidatos = [c for c in candidatos if isinstance(c[2], (dict, list))]

    if esperado is not None:
        for _, _, valor in candidatos:
            if isinstance(valor, esperado):
                return valor
        if esperado is list:
            for _, _, valor in candidatos:
                if isinstance(valor, dict):
                    listas = [v for v in valor.values() if isinstance(v, list)]
                    if len(listas) == 1:
                        return listas[0]
        nombre = "una lista" if esperado is list else "un objeto"
        raise RespuestaInvalida(
            f"Se esperaba {nombre} JSON en la respuesta del modelo y no aparece.\n"
            "Respuesta recibida:\n" + texto[:500]
        )

    if candidatos:
        # El bloque más largo es el "de verdad", no un [1] suelto en una frase.
        return max(candidatos, key=lambda c: c[1])[2]

    raise RespuestaInvalida(
        "No se pudo extraer JSON valido de la respuesta del modelo.\n"
        "Respuesta recibida:\n" + texto[:500]
    )


def ruta_datos(*partes):
    """
    Devuelve una ruta dentro de la carpeta `datos/` del repositorio.

    Sirve para que las recetas encuentren los archivos de ejemplo sin importar
    desde qué carpeta las ejecutes.
    """
    return RAIZ / "datos" / Path(*partes)


# --------------------------------------------------------------------------- #
# Línea de comandos: opción --demo y errores en español                       #
# --------------------------------------------------------------------------- #


class _OpcionDemo(argparse.Action):
    """`--demo`: activa el modo demo en cuanto argparse ve la opción."""

    def __init__(self, option_strings, dest, **kwargs):
        kwargs.setdefault(
            "help",
            "Modo demo: respuestas pregrabadas de datos/demo/, sin clave ni "
            "internet (equivale a NIM_DEMO=1).",
        )
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        activar_demo()


def nuevo_parser(descripcion, **kwargs):
    """ArgumentParser con la opción --demo ya incluida (lo usan todas las recetas)."""
    parser = argparse.ArgumentParser(description=descripcion, **kwargs)
    parser.add_argument("--demo", action=_OpcionDemo)
    return parser


def _detalle_servidor(exc):
    """Extrae el mensaje que mandó el servidor, recortado a una línea legible."""
    cuerpo = getattr(exc, "body", None)
    texto = ""
    if isinstance(cuerpo, dict):
        error = cuerpo.get("error", cuerpo)
        texto = error.get("message", "") if isinstance(error, dict) else str(error)
        texto = texto or cuerpo.get("detail", "")
    texto = str(texto or getattr(exc, "message", "") or exc)
    return " ".join(texto.split())[:240]


def describir_error(exc):
    """
    Traduce una excepción a un mensaje en español con la causa y la solución.

    Se apoya en el código HTTP (401, 429, 404...) en vez de en el nombre de cada
    clase, así funciona con cualquier versión de la librería `openai`.
    """
    url = base_url()
    if isinstance(exc, RespuestaInvalida):
        return (
            f"El modelo no devolvio el JSON esperado.\n{exc}\n\n"
            "Suele arreglarse volviendo a ejecutar. Si se repite, prueba otro "
            "modelo con la variable NIM_MODEL."
        )
    if isinstance(exc, ErrorNIM):
        return str(exc)
    if isinstance(exc, FileNotFoundError):
        return f"No encuentro el archivo: {exc.filename or exc}"

    try:
        import openai
    except ImportError:  # sin la librería no puede haber errores de la API
        openai = None

    if openai is not None:
        if isinstance(exc, openai.APITimeoutError):
            return (
                f"El servidor ({url}) tardo mas de {timeout()} s en responder.\n"
                "Vuelve a intentarlo; si pasa siempre, sube NIM_TIMEOUT en tu .env "
                "o usa un modelo mas pequeno con NIM_MODEL."
            )
        if isinstance(exc, openai.APIConnectionError):
            return (
                f"No pude conectar con {url}.\n"
                "Revisa tu conexion a internet (o que el servidor local este "
                "encendido si usas Ollama/LM Studio) y que NIM_BASE_URL sea correcta."
            )
        if isinstance(exc, openai.APIStatusError):
            codigo = getattr(exc, "status_code", 0) or 0
            if codigo == 401:
                texto = (
                    "La API rechazo tu clave (error 401: no autorizada).\n"
                    "Revisa NVIDIA_API_KEY (o NIM_API_KEY) en tu .env: puede estar mal "
                    "copiada, incompleta o revocada. Si hace falta, genera una nueva "
                    "en https://build.nvidia.com"
                )
            elif codigo == 403:
                texto = (
                    "Tu clave no tiene permiso para usar este modelo (error 403).\n"
                    "Comprueba en el catalogo del proveedor que el modelo esta "
                    "disponible para tu cuenta, o cambia NIM_MODEL."
                )
            elif codigo == 404:
                texto = (
                    f"El endpoint {url} no encuentra el modelo pedido (error 404).\n"
                    f"Modelos configurados: NIM_MODEL={MODELO_CHAT}, "
                    f"NIM_VISION_MODEL={MODELO_VISION}, NIM_EMBED_MODEL={MODELO_EMBEDDINGS}.\n"
                    "Revisa el nombre exacto en el catalogo del proveedor."
                )
            elif codigo == 429:
                texto = (
                    "Llegaste al limite de peticiones del proveedor (error 429), incluso "
                    f"tras {reintentos()} reintento(s) automatico(s).\n"
                    "El nivel gratuito limita las peticiones por minuto: espera un "
                    "minuto y vuelve a ejecutar. Si subes NIM_REINTENTOS en tu .env, "
                    "la receta esperara sola."
                )
            elif codigo in (400, 413, 422):
                texto = (
                    f"El servidor rechazo la peticion (error {codigo}).\n"
                    "Causa tipica: el texto de entrada es demasiado largo para el "
                    "modelo, o un parametro no es valido para este proveedor."
                )
            elif codigo >= 500:
                texto = (
                    f"El servidor del proveedor fallo (error {codigo}). Suele ser "
                    "temporal: espera unos minutos y vuelve a intentarlo."
                )
            else:
                texto = f"El servidor respondio con el error {codigo}."
            detalle = _detalle_servidor(exc)
            if detalle:
                texto += f"\nDetalle del servidor: {detalle}"
            return texto
        if isinstance(exc, openai.OpenAIError):
            return f"Error de la libreria openai: {exc}"

    return (
        f"Error inesperado ({type(exc).__name__}): {exc}\n"
        "Ejecuta de nuevo con NIM_DEBUG=1 para ver la traza completa."
    )


def _consola_tolerante():
    """
    En Windows, si rediriges la salida a un archivo, Python usa la codificación
    local (cp1252) y un emoji del modelo rompería el programa. Con
    errors="replace" el carácter raro se sustituye en vez de explotar.
    """
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def ejecutar(funcion_principal):
    """
    Ejecuta el `main()` de una receta con manejo de errores en español.

    Cualquier fallo de la API (clave inválida, límite de peticiones, modelo que
    no existe, sin conexión) o del propio modelo (JSON inválido, respuesta vacía)
    termina con un mensaje claro y código de salida 1, sin traza de Python.
    Con NIM_DEBUG=1 se muestra la traza completa, útil para depurar.
    """
    _consola_tolerante()
    try:
        return funcion_principal()
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - justamente queremos atraparlo todo
        if _bandera("NIM_DEBUG"):
            raise
        sys.stdout.flush()
        print("\n" + "=" * 60, file=sys.stderr)
        print(describir_error(exc), file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)
