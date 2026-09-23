"""
Escribe los casetes del modo demo con respuestas REDACTADAS A MANO.

¿Para qué existe?
-----------------
El modo demo (`--demo` / NIM_DEMO=1) reproduce respuestas guardadas en
`datos/demo/*.json`, buscándolas por el hash de los mensajes que envía cada
receta. Las respuestas que vienen con el repositorio NO salen de un modelo:
están escritas a mano aquí, a partir de los datos de ejemplo, y cada entrada
lo dice en su campo "origen": "redactada a mano".

Este script ejecuta cada receta con sus argumentos de ejemplo usando un
cliente "guion" que devuelve estas respuestas en orden y las guarda en el
casete con la clave correcta. Úsalo si cambias un prompt o un dato de ejemplo
y no tienes clave para regrabar. Con clave, lo mejor es grabar respuestas
reales:  NIM_GRABAR=1 python recetas/05_extraer_facturas.py

Uso:  python herramientas/escribir_casetes_demo.py [05 08 ...]
"""

import os
import runpy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ["NIM_IGNORAR_DOTENV"] = "1"
os.environ.pop("NIM_DEMO", None)
os.environ.pop("NIM_GRABAR", None)

from comun import demo, nim  # noqa: E402

ORIGEN = "redactada a mano"

# --------------------------------------------------------------------------- #
# Respuestas                                                                   #
# --------------------------------------------------------------------------- #

R01 = """RESUMEN EJECUTIVO:
Café Aroma cerró el primer trimestre de 2026 con ventas de 48.600 USD, un 12% más que un año antes, impulsadas por los pedidos para llevar (31% de la facturación). El margen bruto se sostuvo en el 64% pese a la subida del café verde, gracias a la renegociación con el tostador y a una menor merma. Para el segundo trimestre se aprobaron una segunda máquina de espresso y una suscripción mensual de café en grano.

PUNTOS CLAVE:
- Ventas de 48.600 USD (+12% interanual), con un ticket promedio de 6,80 USD (+4%) y 7.150 clientes atendidos (+8%).
- Bebidas calientes: 29.200 USD (60%); repostería: 11.700 USD (24%); café en grano: 7.700 USD (16%), la línea que más creció (+27%).
- El café verde subió un 9%; se compensó renegociando con el tostador y bajando la merma de leche del 6% al 3,5%.
- Nota media de 4,6 sobre 5 en reseñas; las quejas se concentran en esperas de más de 15 minutos entre las 8:00 y las 9:30.
- Riesgos: otra posible subida del 5% del café verde, dependencia de un único proveedor de repostería y la cafetera principal al límite.
- Decisiones: segunda máquina de espresso (3.800 USD) antes del 30 de abril, suscripción de café en grano a 22 USD al mes y búsqueda de un segundo proveedor de repostería."""

_CATEGORIAS_02 = [
    "Alimentacion", "Transporte", "Ingresos", "Entretenimiento", "Salud", "Transporte",
    "Alimentacion", "Servicios", "Alimentacion", "Alimentacion", "Salud", "Entretenimiento",
    "Alimentacion", "Salud", "Educacion", "Alimentacion", "Transporte", "Ingresos",
    "Entretenimiento", "Transporte", "Salud", "Alimentacion", "Servicios", "Alimentacion",
    "Educacion", "Transporte", "Alimentacion", "Salud", "Entretenimiento",
]
R02 = "```json\n{\n" + ",\n".join(
    f'  "{i}": "{c}"' for i, c in enumerate(_CATEGORIAS_02)
) + "\n}\n```"

R04 = [
    "Muchas gracias por su reseña y por destacar la atención de nuestro equipo. Nos alegra "
    "saber que disfrutó del café y del ambiente; le haremos llegar sus palabras a quien le "
    "atendió. Será un gusto recibirle de nuevo.",
    "Lamentamos mucho la espera de 40 minutos y que su capuchino llegara frío: no es la "
    "experiencia que queremos ofrecer. Ya lo estamos revisando con el equipo para mejorar los "
    "tiempos en las horas de más afluencia. Si nos escribe por mensaje directo, nos gustaría "
    "invitarle a una próxima visita.",
    "Gracias por su reseña y por valorar el wifi y los enchufes; nos alegra que sea un buen "
    "lugar para trabajar. Tomamos nota de que a veces cuesta encontrar mesa y estamos "
    "estudiando cómo aprovechar mejor el espacio. Esperamos verle pronto.",
    "Gracias por tomarse el tiempo de escribirnos y por su comentario sobre el sabor. "
    "Entendemos su punto sobre el tamaño de las porciones en relación con el precio y lo "
    "trasladaremos al equipo que revisa la carta. Su opinión nos ayuda a mejorar.",
    "Lamentamos que le sirvieran un pastel distinto al que pidió y, sobre todo, la forma en "
    "que se atendió su reclamo. No es el trato que queremos dar y ya lo estamos hablando con "
    "el equipo. Le agradeceríamos que nos escriba por mensaje directo para ofrecerle una "
    "solución.",
    "¡Qué alegría leer su reseña! Gracias por elegirnos cada sábado; que el equipo ya le "
    "conozca es lo mejor que nos puede pasar. Le esperamos con el pan de la casa recién hecho.",
]

R05 = """{
  "emisor": {
    "nombre": "DISTRIBUIDORA CENTRAL, S.A.",
    "ruc_nit": "155612345-2-2021 DV 33",
    "direccion": "Ave. Ricardo J. Alfaro, Edificio Plaza Norte, Local 4, Ciudad de Panama, Panama"
  },
  "cliente": {
    "nombre": "Cafeteria La Esquina",
    "ruc_nit": "8-912-3456"
  },
  "documento": {
    "tipo": "factura",
    "numero": "000148723",
    "fecha": "2026-02-12",
    "moneda": "PAB"
  },
  "items": [
    {"descripcion": "Saco de cafe grano 5 lb", "cantidad": 4, "precio_unitario": 18.50, "importe": 74.00},
    {"descripcion": "Caja de vasos 12oz (50u)", "cantidad": 2, "precio_unitario": 9.75, "importe": 19.50},
    {"descripcion": "Jarabe vainilla botella 1L", "cantidad": 6, "precio_unitario": 6.25, "importe": 37.50},
    {"descripcion": "Molino electrico industrial", "cantidad": 1, "precio_unitario": 145.00, "importe": 145.00}
  ],
  "subtotal": 276.00,
  "impuesto": {"nombre": "ITBMS", "tasa": 0.07, "monto": 19.32},
  "total": 295.32
}"""

R06 = [
    """La IA no es solo para empresas con departamento de datos.

La semana pasada una panadería con 6 empleados me contó que ahorra 5 horas semanales respondiendo pedidos por WhatsApp con ayuda de un asistente. No compraron software caro: empezaron con una tarea pequeña y repetitiva.

Si tienes una PYME, este es el camino que más veo funcionar:
1. Elige UNA tarea que hoy te quite tiempo (responder correos, clasificar gastos, resumir reuniones).
2. Pruébala dos semanas con herramientas gratuitas y mide cuánto tiempo ahorras.
3. Solo si funciona, intégrala en tu proceso y forma a tu equipo.

Lo difícil no es la tecnología: es elegir bien el primer problema.

¿Cuál sería esa primera tarea en tu negocio?

#PYME #InteligenciaArtificial #Productividad""",
    """1/ Tu PYME no necesita un "proyecto de IA". Necesita quitarse de encima una tarea aburrida. Te cuento cómo empezar esta semana 👇

2/ Haz una lista de tareas repetitivas: responder las mismas preguntas, pasar facturas a Excel, redactar correos. Elige la que más horas te coma.

3/ Prueba una herramienta gratuita durante 2 semanas. Anota cuánto tardabas antes y cuánto tardas ahora. Sin datos, no hay decisión.

4/ Revisa siempre lo que produce la IA. Es un asistente rápido, no un empleado infalible: la última palabra es tuya.

5/ Si funcionó, documenta el proceso y enséñaselo a tu equipo. Si no, pasa a la siguiente tarea de la lista.

6/ La ventaja no la tiene quien usa más IA, sino quien la aplica al problema correcto. ¿Por cuál empezarías tú?""",
    """¿Tu negocio es pequeño? Perfecto: la IA también es para ti 🚀

Empieza por una sola tarea que te robe tiempo cada semana (responder mensajes, ordenar gastos, escribir correos) y pruébala gratis durante 15 días ⏱️

Mide el tiempo que ahorras y decide con datos. ¡Tu próximo empleado estrella puede ser un asistente! 🤖✨

#PYMEs #Emprendedores #InteligenciaArtificial #NegociosLocales #Productividad #Latam #Innovacion""",
]

R07 = """Hello and welcome to this quick tutorial.
<<<>>>
Today we are going to learn how to use artificial intelligence in everyday tasks.
<<<>>>
You don't need to be an expert programmer to get the most out of it.
<<<>>>
Let's start with a simple example that you can try right now.
<<<>>>
If you like the video, don't forget to subscribe."""

R08 = (
    "El plan Pro cuesta 12 USD al mes (02_precios.md). Incluye facturas y clientes "
    "ilimitados, hasta 3 usuarios, recordatorios automáticos de cobro, reportes exportables "
    "a PDF y CSV, plantillas con tu logo y colores y soporte prioritario por chat "
    "(02_precios.md). Si eres estudiante o una organización sin fines de lucro, puedes "
    "pedir un 50% de descuento en el plan Pro escribiendo al soporte "
    "(03_preguntas_frecuentes.md)."
)

R09 = """{
  "sentimiento_general": {"positivo": 50, "neutral": 22, "negativo": 28},
  "temas": [
    {
      "tema": "Funciones que faltan",
      "menciones": 4,
      "resumen": "Piden app movil nativa, reportes exportables a Excel con filtros e integracion con la facturacion local.",
      "cita": "Falta integracion con mi sistema de facturacion local, tengo que copiar todo a mano."
    },
    {
      "tema": "Facilidad de uso",
      "menciones": 4,
      "resumen": "La herramienta se aprende rapido y la interfaz se percibe limpia y pensada para el usuario.",
      "cita": "La curva de aprendizaje fue corta, en una tarde ya tenia a todo mi equipo usandola."
    },
    {
      "tema": "Precio",
      "menciones": 3,
      "resumen": "El plan gratuito gusta, pero la ultima subida de precios y la comparacion con la competencia generan molestia.",
      "cita": "Me parece cara comparada con la competencia que ofrece casi lo mismo por menos."
    },
    {
      "tema": "Soporte y cancelacion",
      "menciones": 3,
      "resumen": "El soporte es irregular: a veces resuelve en minutos y otras tarda dias; cancelar la suscripcion es confuso.",
      "cita": "El soporte tardo dos dias en responderme y al final no resolvio mi problema con la facturacion."
    },
    {
      "tema": "Rendimiento y estabilidad",
      "menciones": 2,
      "resumen": "Se valora la velocidad, pero la app se cierra al subir archivos grandes.",
      "cita": "La app se cierra sola cuando subo archivos grandes."
    }
  ],
  "resumen_ejecutivo": "La mitad de las respuestas son positivas: se valoran sobre todo la facilidad de uso, la interfaz limpia y la velocidad. Las criticas se reparten entre funciones que faltan (app movil, exportacion a Excel, integracion con la facturacion local), la percepcion de precio alto tras la ultima subida y un soporte irregular. Priorizar la app movil y la exportacion de reportes atacaria las peticiones mas repetidas, y simplificar la cancelacion reduciria la frustracion."
}"""

R10 = [
    "Taza de cerámica roja llena de café, con el asa a la derecha, sobre una mesa de madera "
    "y con vapor saliendo.",
    "Taza de cerámica esmaltada en un rojo intenso con acabado brillante, de forma cilíndrica "
    "y con un asa amplia para sujetarla con comodidad. Su diseño clásico la hace ideal para el "
    "café de cada mañana, un té o un chocolate caliente. El color aporta un toque cálido tanto "
    "a la mesa del desayuno como al escritorio de trabajo.",
]

R11_CLIENTES = """Aquí tienes los 10 clientes en formato JSON:

[
  {"id": 1, "nombre": "Mariana Castillo", "email": "mariana.castillo@ejemplo.com", "ciudad": "Ciudad de Panama", "pais": "Panama"},
  {"id": 2, "nombre": "Diego Ramirez", "email": "diego.ramirez@ejemplo.com", "ciudad": "Bogota", "pais": "Colombia"},
  {"id": 3, "nombre": "Valentina Rojas", "email": "valentina.rojas@ejemplo.com", "ciudad": "Santiago", "pais": "Chile"},
  {"id": 4, "nombre": "Andres Morales", "email": "andres.morales@ejemplo.com", "ciudad": "Lima", "pais": "Peru"},
  {"id": 5, "nombre": "Camila Herrera", "email": "camila.herrera@ejemplo.com", "ciudad": "Guadalajara", "pais": "Mexico"},
  {"id": 6, "nombre": "Luis Fernandez", "email": "luis.fernandez@ejemplo.com", "ciudad": "Quito", "pais": "Ecuador"},
  {"id": 7, "nombre": "Sofia Vargas", "email": "sofia.vargas@ejemplo.com", "ciudad": "San Jose", "pais": "Costa Rica"},
  {"id": 8, "nombre": "Javier Pineda", "email": "javier.pineda@ejemplo.com", "ciudad": "Tegucigalpa", "pais": "Honduras"},
  {"id": 9, "nombre": "Daniela Ortiz", "email": "daniela.ortiz@ejemplo.com", "ciudad": "Montevideo", "pais": "Uruguay"},
  {"id": 10, "nombre": "Mateo Gutierrez", "email": "mateo.gutierrez@ejemplo.com", "ciudad": "Cordoba", "pais": "Argentina"}
]"""

R11_PRODUCTOS = """{"productos": [
  {"id": 1, "nombre": "Cafe molido 500 g", "categoria": "Despensa", "precio": 6.75},
  {"id": 2, "nombre": "Taza de ceramica 350 ml", "categoria": "Hogar", "precio": 9.90},
  {"id": 3, "nombre": "Audifonos inalambricos", "categoria": "Tecnologia", "precio": 34.99},
  {"id": 4, "nombre": "Mochila urbana", "categoria": "Accesorios", "precio": 27.50},
  {"id": 5, "nombre": "Botella termica 750 ml", "categoria": "Hogar", "precio": "12.50"},
  {"id": 6, "nombre": "Cuaderno A5 rayado", "categoria": "Papeleria", "precio": 3.25},
  {"id": 7, "nombre": "Lampara LED de escritorio", "categoria": "Hogar", "precio": 18.90},
  {"id": 8, "nombre": "Cargador USB-C 20 W", "categoria": "Tecnologia", "precio": 15.00}
]}"""

R12 = """Hola, equipo: les escribo para contarles que el lanzamiento de la nueva versión se mueve al 22 de marzo. Habíamos quedado en el 15, pero desarrollo pidió una semana más para las pruebas y, la verdad, tiene sentido.

Por favor, revisen sus tareas y, si alguien tiene dudas, me avisan antes del viernes; así lo resolvemos rápido. Gracias a todos por el esfuerzo de estas semanas."""

R13 = """Asunto: Reunión con el proveedor de café: pasa al jueves a las 10:00

Hola, equipo:

Les cuento que la reunión con el proveedor de café se movió al jueves a las 10:00. Para aprovecharla, traigan por favor las cifras de consumo del trimestre.

En la reunión queremos preguntar si mantienen el precio del grano hasta junio y pedirles una muestra del nuevo tueste medio para probarlo.

¿Me confirman su asistencia antes del miércoles?

¡Gracias y un saludo!"""

R14 = """```json
{
  "titulo": "Plan de lanzamiento de la version 2.0",
  "resumen": "El equipo acordo mover el lanzamiento de la version 2.0 al 22 de marzo para dar una semana mas a las pruebas y repartio las tareas de comunicacion y del video de demostracion. El precio del plan Premium y el responsable de la documentacion tecnica quedaron pendientes.",
  "decisiones": [
    "Mover el lanzamiento del 15 al 22 de marzo para ampliar las pruebas una semana.",
    "El equipo de diseno grabara el video de demostracion con el guion de Carlos."
  ],
  "tareas": [
    {"tarea": "Actualizar el calendario y avisar a los clientes del cambio de fecha", "responsable": "Lucia", "fecha": "Sin fecha"},
    {"tarea": "Escribir el guion del video de demostracion", "responsable": "Carlos", "fecha": "Antes del lanzamiento"},
    {"tarea": "Coordinar con Diego la grabacion del video de demostracion", "responsable": "Lucia", "fecha": "18 de marzo"},
    {"tarea": "Preparar la comparativa de precios de la competencia", "responsable": "Ana", "fecha": "Proxima reunion"},
    {"tarea": "Hablar con soporte y asignar responsable de la documentacion tecnica", "responsable": "Ana", "fecha": "Manana"}
  ],
  "pendientes": [
    "Definir el precio del nuevo plan Premium con datos de la competencia.",
    "Asignar responsable para actualizar la documentacion tecnica."
  ]
}
```"""

R15 = [
    "Pensamiento: Primero necesito multiplicar 145 por 32 con la calculadora.\n"
    "Accion: calcular\n"
    "Entrada: 145 * 32",
    "Pensamiento: El resultado es 4640. Ahora cuento cuantos caracteres tiene.\n"
    "Acción: contar_letras\n"
    "Entrada: 4640",
    "Pensamiento: Ya tengo los dos datos que necesitaba.\n"
    "Respuesta final: 145 * 32 = 4640. El resultado tiene 4 caracteres; en realidad son "
    "cifras, no letras (4, 6, 4 y 0).",
]

# receta -> (argumentos, respuestas en el orden en que la receta las pide)
GUIONES = {
    "01_resumir_pdf": ([], [R01]),
    "02_clasificar_gastos": (["--salida", "{tmp}/clasificados.json"], [R02]),
    "04_responder_resenas": ([], R04),
    "05_extraer_facturas": ([], [R05]),
    "06_generar_posts": ([], R06),
    "07_traducir_subtitulos": (["--salida", "{tmp}/subtitulos.srt"], [R07]),
    "08_chatbot_docs": (["--pregunta", "Cuanto cuesta el plan Pro?", "--sin-cache"], [R08]),
    "09_analizar_encuesta": ([], [R09]),
    "10_describir_imagenes": ([], R10),
    "11_datos_sinteticos": (["--salida", "{tmp}/sinteticos"], [R11_CLIENTES, R11_PRODUCTOS]),
    "12_revisar_texto": ([], [R12]),
    "13_email_profesional": ([], [R13]),
    "14_audio_a_notas": ([], [R14]),
    "15_agente_basico": ([], R15),
}


class ClienteGuion:
    """Cliente falso que devuelve las respuestas del guion y las guarda en el casete."""

    def __init__(self, casete, respuestas):
        self.casete = casete
        self.pendientes = list(respuestas)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.embeddings = SimpleNamespace(
            create=lambda model=None, input=None, **_: demo.embeddings_locales(input)
        )

    def _chat(self, messages=None, stop=None, **_):
        if not self.pendientes:
            raise RuntimeError(f"{self.casete}: la receta pidio mas respuestas que las del guion")
        respuesta = self.pendientes.pop(0)
        demo.guardar_entrada(
            self.casete,
            {
                "clave": demo.clave_mensajes(messages),
                "origen": ORIGEN,
                "peticion": demo._resumen_peticion(messages),
                "respuesta": respuesta,
            },
        )
        return demo._respuesta_chat(demo.aplicar_stop(respuesta, stop))


def escribir(casete, argumentos, respuestas, tmp):
    ruta_casete = demo.carpeta_casetes() / f"{casete}.json"
    if ruta_casete.exists():
        ruta_casete.unlink()
    cliente = ClienteGuion(casete, respuestas)
    nim._cliente = cliente
    sys.argv = [str(RAIZ / "recetas" / f"{casete}.py")] + [a.format(tmp=tmp) for a in argumentos]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as salida:
        if salida.code not in (None, 0):
            raise RuntimeError(f"{casete}: la receta termino con codigo {salida.code}")
    finally:
        nim._cliente = None
    if cliente.pendientes:
        raise RuntimeError(f"{casete}: sobraron {len(cliente.pendientes)} respuestas del guion")
    return ruta_casete


def main(filtro):
    with tempfile.TemporaryDirectory() as tmp:
        for casete, (argumentos, respuestas) in GUIONES.items():
            if filtro and casete[:2] not in filtro:
                continue
            ruta = escribir(casete, argumentos, respuestas, tmp)
            print(f"\n>>> casete escrito: {ruta.relative_to(RAIZ)}\n", file=sys.stderr)


if __name__ == "__main__":
    main([a.zfill(2) for a in sys.argv[1:]])
