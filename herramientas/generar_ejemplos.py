"""
Genera los archivos de ejemplo binarios de `datos/` usando solo la librería
estándar de Python, para que cualquiera pueda ver (y rehacer) cómo se crearon:

  datos/informe_ejemplo.pdf    -> entrada de la receta 01 (resumir PDF)
  datos/producto_ejemplo.png   -> entrada de la receta 10 (describir imágenes)

Uso:  python herramientas/generar_ejemplos.py

El PDF se escribe "a mano" (objetos, flujo de contenido y tabla xref) y el PNG
se dibuja píxel a píxel y se comprime con zlib. Ambos son deterministas: mismo
script, mismos bytes.
"""

import math
import struct
import textwrap
import zlib
from pathlib import Path

DATOS = Path(__file__).resolve().parent.parent / "datos"

# --------------------------------------------------------------------------- #
# PDF                                                                          #
# --------------------------------------------------------------------------- #

TITULO = "Informe de resultados - Café Aroma"
SUBTITULO = "Primer trimestre de 2026 (enero a marzo)"

SECCIONES = [
    (
        "1. Resumen del trimestre",
        "Café Aroma cerró el primer trimestre de 2026 con ventas de 48.600 USD, "
        "un 12% más que en el mismo periodo de 2025. El crecimiento vino sobre todo "
        "del canal de pedidos para llevar, que ya representa el 31% de la "
        "facturación. El margen bruto se mantuvo en el 64%, a pesar de la subida "
        "del precio del café verde.",
    ),
    (
        "2. Ventas por línea de producto",
        "Las bebidas calientes aportaron 29.200 USD (60% del total). La repostería "
        "de la casa sumó 11.700 USD (24%), impulsada por el pan de masa madre, que "
        "se agotó casi todos los sábados. El café en grano para llevar a casa "
        "facturó 7.700 USD (16%) y fue la línea que más creció: un 27% frente al "
        "trimestre anterior.",
    ),
    (
        "3. Costos y márgenes",
        "El costo del café verde subió un 9% por la sequía en la región productora. "
        "Para no trasladar todo el aumento al cliente, se renegoció el contrato con "
        "el tostador y se redujo la merma de leche del 6% al 3,5% gracias a un "
        "mejor control de inventario. La nómina se mantuvo estable con 9 personas.",
    ),
    (
        "4. Clientes y reseñas",
        "La nota media en reseñas públicas fue de 4,6 sobre 5. Los comentarios "
        "positivos destacan la atención y el ambiente para trabajar. Las quejas se "
        "concentran en la espera en horas pico: 14 reseñas mencionan demoras de más "
        "de 15 minutos entre las 8:00 y las 9:30.",
    ),
    (
        "5. Riesgos",
        "El principal riesgo es el precio del café verde, que podría subir otro 5% "
        "en el segundo trimestre. También preocupa la dependencia de un solo "
        "proveedor de repostería congelada y la capacidad de la cafetera principal, "
        "que ya trabaja al límite en horas pico.",
    ),
    (
        "6. Decisiones para el segundo trimestre",
        "Se aprobó comprar una segunda máquina de espresso (3.800 USD) antes del 30 "
        "de abril para reducir las esperas. Se lanzará una suscripción mensual de "
        "café en grano a 22 USD con entrega a domicilio. Se buscará un segundo "
        "proveedor de repostería y se revisarán los precios de las bebidas en junio "
        "si el costo del café sigue subiendo.",
    ),
    (
        "7. Indicadores clave del trimestre",
        [
            "- Ventas totales: 48.600 USD (+12% interanual).",
            "- Ticket promedio: 6,80 USD (+4%).",
            "- Clientes atendidos: 7.150 (+8%).",
            "- Margen bruto: 64% (igual que en 2025).",
            "- Merma de leche: 3,5% (antes 6%).",
            "- Nota media en reseñas: 4,6 de 5 (212 reseñas).",
        ],
    ),
]


def _cadena_pdf(texto):
    """Codifica un texto como cadena literal de PDF (WinAnsi, con escapes)."""
    salida = []
    for byte in texto.encode("cp1252"):
        caracter = chr(byte)
        if caracter in "()\\":
            salida.append("\\" + caracter)
        elif 32 <= byte < 127:
            salida.append(caracter)
        else:
            salida.append(f"\\{byte:03o}")
    return "(" + "".join(salida) + ")"


def _paginas_de_contenido():
    """Reparte las secciones en páginas y devuelve un flujo de contenido por página."""
    paginas, lineas = [], []
    y = 780

    def linea(texto, fuente, tam, x=56):
        lineas.append(f"BT /{fuente} {tam} Tf 1 0 0 1 {x} {y} Tm {_cadena_pdf(texto)} Tj ET")

    def salto(alto):
        nonlocal y, lineas
        if y - alto < 60:
            paginas.append("\n".join(lineas))
            lineas, y = [], 780
        y -= alto

    linea(TITULO, "F2", 18)
    salto(24)
    linea(SUBTITULO, "F1", 11)
    salto(30)
    for titulo, cuerpo in SECCIONES:
        filas = cuerpo if isinstance(cuerpo, list) else textwrap.wrap(cuerpo, width=88)
        # Si la sección entera no cabe, empieza en una página nueva.
        if y - (6 + 18 + 17 * len(filas)) < 60:
            salto(y)
        salto(6)
        linea(titulo, "F2", 12.5)
        salto(18)
        for fila in filas:
            linea(fila, "F1", 11)
            salto(17)
        salto(12)
    paginas.append("\n".join(lineas))
    return paginas


def generar_pdf(ruta):
    flujos = _paginas_de_contenido()
    objetos = {}
    n_paginas = len(flujos)
    # 1 catálogo, 2 árbol de páginas, 3-4 fuentes, luego (página, contenido) x N.
    objetos[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    hijos = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_paginas))
    objetos[2] = f"<< /Type /Pages /Kids [{hijos}] /Count {n_paginas} >>"
    objetos[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objetos[4] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    for i, flujo in enumerate(flujos):
        pagina, contenido = 5 + 2 * i, 6 + 2 * i
        objetos[pagina] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {contenido} 0 R >>"
        )
        datos = flujo.encode("latin-1")
        objetos[contenido] = (
            f"<< /Length {len(datos)} >>\nstream\n".encode("latin-1") + datos + b"\nendstream"
        )
    info = len(objetos) + 1
    objetos[info] = "<< /Title " + _cadena_pdf(TITULO) + " /Producer (recetas-ia) >>"

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posiciones = {}
    for numero in sorted(objetos):
        posiciones[numero] = len(salida)
        cuerpo = objetos[numero]
        if isinstance(cuerpo, str):
            cuerpo = cuerpo.encode("latin-1")
        salida += f"{numero} 0 obj\n".encode() + cuerpo + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {info + 1}\n0000000000 65535 f \n".encode()
    for numero in range(1, info + 1):
        salida += f"{posiciones[numero]:010d} 00000 n \n".encode()
    salida += (
        f"trailer\n<< /Size {info + 1} /Root 1 0 R /Info {info} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    ruta.write_bytes(bytes(salida))


# --------------------------------------------------------------------------- #
# PNG                                                                          #
# --------------------------------------------------------------------------- #

ANCHO, ALTO = 480, 360


def _mezclar(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _color_en(x, y):
    """Color del punto (x, y): fondo, mesa, sombra, taza, asa, café y vapor."""
    # Fondo: degradado cálido de arriba a abajo.
    color = _mezclar((243, 236, 226), (226, 212, 194), y / ALTO)
    # Mesa de madera en el tercio inferior, con vetas suaves.
    if y > 250:
        veta = 0.5 + 0.5 * math.sin(x * 0.045 + math.sin(y * 0.09) * 2.2)
        color = _mezclar((196, 150, 104), (176, 128, 86), veta * 0.6)

    cx, arriba, abajo, radio = 222, 120, 285, 78
    # Sombra suave bajo la taza.
    d = ((x - cx - 18) / 118) ** 2 + ((y - abajo - 4) / 16) ** 2
    if d < 1:
        color = _mezclar(color, (120, 84, 56), 0.45 * (1 - d))

    # Asa: un anillo a la derecha del cuerpo.
    ax, ay = cx + radio + 4, 200
    r = math.hypot((x - ax) / 1.0, (y - ay) / 1.25)
    if 26 < r < 44 and x > cx + radio - 10:
        luz = 0.75 + 0.25 * math.cos(math.atan2(y - ay, x - ax) + 2.2)
        color = tuple(c * luz for c in (178, 40, 36))

    # Cuerpo de la taza: un cilindro con luz desde la izquierda.
    elipse_base = ((x - cx) / radio) ** 2 + ((y - abajo) / 14) ** 2
    if (abs(x - cx) <= radio and arriba <= y <= abajo) or elipse_base <= 1:
        u = (x - cx) / radio
        luz = 0.62 + 0.42 * math.cos((u + 0.35) * 1.25)
        color = tuple(min(255, c * luz) for c in (196, 48, 42))
        # Reflejo vertical del esmalte.
        if -0.62 < u < -0.48 and arriba + 18 < y < abajo - 20:
            color = _mezclar(color, (255, 236, 228), 0.55)

    # Borde superior y café dentro.
    elipse_borde = ((x - cx) / radio) ** 2 + ((y - arriba) / 16) ** 2
    if elipse_borde <= 1:
        color = (214, 92, 82)
        elipse_cafe = ((x - cx) / (radio - 7)) ** 2 + ((y - arriba - 1) / 12) ** 2
        if elipse_cafe <= 1:
            color = _mezclar((92, 52, 28), (60, 32, 16), (y - arriba + 12) / 24)

    # Vapor: tres hilos ondulados y translúcidos.
    for i, desfase in enumerate((-30, 0, 30)):
        if 30 < y < 100:
            eje = cx + desfase + 9 * math.sin(y * 0.11 + i * 1.7)
            distancia = abs(x - eje)
            if distancia < 3.2:
                alfa = (1 - distancia / 3.2) * 0.55 * min(1, (y - 30) / 25) * min(1, (100 - y) / 20)
                color = _mezclar(color, (255, 255, 255), alfa)
    return color


def generar_png(ruta, sobremuestreo=2):
    filas = bytearray()
    paso = 1.0 / sobremuestreo
    for y in range(ALTO):
        filas.append(0)  # filtro "None" para cada fila
        for x in range(ANCHO):
            acumulado = [0.0, 0.0, 0.0]
            for sy in range(sobremuestreo):
                for sx in range(sobremuestreo):
                    c = _color_en(x + (sx + 0.5) * paso, y + (sy + 0.5) * paso)
                    for k in range(3):
                        acumulado[k] += c[k]
            n = sobremuestreo * sobremuestreo
            filas.extend(max(0, min(255, int(round(v / n)))) for v in acumulado)

    def bloque(tipo, datos):
        crc = zlib.crc32(tipo + datos) & 0xFFFFFFFF
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", crc)

    png = b"\x89PNG\r\n\x1a\n"
    png += bloque(b"IHDR", struct.pack(">IIBBBBB", ANCHO, ALTO, 8, 2, 0, 0, 0))
    png += bloque(b"IDAT", zlib.compress(bytes(filas), 9))
    png += bloque(b"IEND", b"")
    ruta.write_bytes(png)


if __name__ == "__main__":
    DATOS.mkdir(exist_ok=True)
    generar_pdf(DATOS / "informe_ejemplo.pdf")
    generar_png(DATOS / "producto_ejemplo.png")
    for nombre in ("informe_ejemplo.pdf", "producto_ejemplo.png"):
        print(f"{DATOS / nombre}  ({(DATOS / nombre).stat().st_size:,} bytes)")
