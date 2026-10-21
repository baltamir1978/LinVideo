"""Traduce la salida de error de yt-dlp a algo que se pueda leer y accionar.

yt-dlp escribe sus errores en inglés y a veces con detalles internos; aquí se reconocen
los casos habituales y se dice qué hacer con ellos.
"""

import re

_RULES: list[tuple[tuple[str, ...], str]] = [
    (("unable to obtain file audio codec",),
     "Este vídeo no tiene pista de audio, así que no se puede sacar de él un archivo de "
     "sonido. Descárgalo como vídeo o como GIF."),
    (("requested format is not available", "requested format not available"),
     "No hay ningún formato que cumpla los filtros elegidos. Prueba con «Máxima» en calidad "
     "o con otro formato."),
    (("sign in to confirm your age", "age-restricted", "confirm your age",
      "inappropriate for some users"),
     "La web exige confirmar la edad. En Ajustes › Red, elige el navegador donde tengas la "
     "sesión abierta para que use tus cookies."),
    (("sign in to confirm", "not a bot", "cookies are no longer valid"),
     "La web pide iniciar sesión para seguir. En Ajustes › Red, elige el navegador donde "
     "tengas la sesión abierta."),
    (("video unavailable", "video is unavailable", "this video has been removed",
      "has been terminated"),
     "El vídeo ya no está disponible: lo han retirado o la cuenta ha desaparecido."),
    (("private video", "this video is private"),
     "El vídeo es privado."),
    (("members-only", "join this channel", "premium", "paid"),
     "El contenido es de pago o sólo para suscriptores."),
    (("not available in your country", "geo restricted", "geo-restricted",
      "blocked it in your country"),
     "No está disponible en tu país."),
    (("unsupported url",),
     "yt-dlp no reconoce esa dirección. Comprueba que sea la página del vídeo y no un "
     "resultado de búsqueda o una portada."),
    (("http error 403", "forbidden"),
     "La web ha rechazado la descarga (403). Suele arreglarse actualizando yt-dlp en "
     "Ajustes › Herramientas, o usando cookies del navegador."),
    # Antes que la del 404: «ffmpeg not found» contiene «not found». En AppVideo iba
    # detrás y un ffmpeg ausente se explicaba como una página inexistente.
    (("ffmpeg not found", "ffprobe not found", "ffmpeg is not installed"),
     "Falta ffmpeg, que hace falta para unir y convertir. Instálalo con: sudo apt install ffmpeg"),
    (("http error 404", "not found"),
     "La página no existe (404). El enlace puede estar mal o el vídeo borrado."),
    (("http error 429", "too many requests"),
     "La web ha cortado por exceso de peticiones. Espera un rato o baja las descargas "
     "simultáneas en Ajustes › Red."),
    (("precondition failed", "http error 412"),
     "La web bloquea las peticiones automáticas desde aquí."),
    (("no space left",),
     "No queda espacio en el disco."),
    (("permission denied", "read-only file system"),
     "No hay permiso para escribir en la carpeta de destino. Elige otra en Ajustes › General."),
    (("unable to download webpage", "temporary failure in name resolution",
      "network is unreachable", "connection reset", "timed out"),
     "Fallo de red al contactar con la web. Comprueba la conexión y reinténtalo."),
    (("postprocessing",),
     "Falló el paso de conversión posterior a la descarga. El registro tiene el detalle "
     "de ffmpeg."),
]


def explain(raw_lines: list[str], exit_code: int) -> str:
    """Mensaje en claro a partir de las líneas de error de yt-dlp.

    Si no reconoce el caso, devuelve el propio texto de yt-dlp, ya limpio.
    """
    joined = " ".join(raw_lines).lower()
    for needles, message in _RULES:
        if any(needle in joined for needle in needles):
            return message

    # Sin regla conocida: se muestra el texto de yt-dlp sin su prefijo.
    for line in reversed(raw_lines):
        if line:
            return clean(line)
    return f"La descarga no se completó (código {exit_code}). El registro tiene el detalle."


def clean(line: str) -> str:
    """Quita los prefijos y adornos con los que yt-dlp escribe sus errores."""
    text = line
    for prefix in ("ERROR: ", "WARNING: ", "ERROR:", "WARNING:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    # «[youtube] abc123: mensaje» → «mensaje»
    text = re.sub(r"^\[[^\]]+\]\s*[^:]*:\s*", "", text, count=1)
    # Se recorta la explicación entre paréntesis que yt-dlp añade al final.
    cut = text.find(" (caused by")
    if cut >= 0:
        text = text[:cut]
    return text.strip()
