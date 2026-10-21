"""Textos legales, en un único sitio: el aviso de bienvenida, «Acerca de», `--legal` y el
README dicen lo mismo."""

SUMMARY = ("LinVideo es una interfaz para yt-dlp y FFmpeg pensada para uso personal. "
           "Quien la usa es responsable de lo que descarga.")

POINTS: list[tuple[str, str]] = [
    ("Derechos de autor",
     "Descargar obras protegidas sin autorización puede infringir los derechos de sus "
     "titulares. Que una herramienta permita hacerlo no significa que sea legal en tu caso: "
     "depende del contenido, del uso que le des y de la legislación de tu país."),
    ("Condiciones de uso de las webs",
     "Varias plataformas —YouTube entre ellas— prohíben en sus condiciones descargar "
     "contenido salvo con las funciones que ellas mismas ofrecen. Usar esta app puede "
     "incumplir ese contrato con la plataforma, aunque no haya infracción de copyright."),
    ("Contenido para adultos",
     "Las webs para adultos incluidas sólo deben usarse por personas mayores de edad y donde "
     "ese contenido sea legal. Queda fuera de toda justificación el material ilegal o "
     "publicado sin el consentimiento de quien aparece."),
    ("Sin afiliación",
     "Esta app no está asociada ni respaldada por YouTube, Google, ni por ninguna de las webs "
     "a las que se conecta. Los nombres pertenecen a sus titulares y se usan sólo para "
     "identificar cada fuente."),
    ("Sin garantía",
     "El programa se entrega tal cual, sin garantía de ningún tipo, y su autor no responde de "
     "los daños o consecuencias de su uso. Este texto es informativo y no constituye "
     "asesoramiento legal."),
    ("Privacidad",
     "No hay telemetría ni historial de descargas. Las peticiones van sólo a las webs que "
     "buscas o descargas. Las cookies del navegador, si activas esa opción, las lee yt-dlp en "
     "tu propio equipo y no salen de él."),
]

DEPENDENCIES: list[tuple[str, str, str]] = [
    ("yt-dlp", "Dominio público (The Unlicense)",
     "Hace todo el trabajo de extracción y descarga. LinVideo baja y actualiza su propia "
     "copia en ~/.local/share/linvideo/bin."),
    ("FFmpeg y ffprobe", "LGPL / GPL",
     "Los del sistema (paquete ffmpeg de Debian), que sí se pueden redistribuir. LinVideo no "
     "lleva ninguno dentro."),
]


def as_text() -> str:
    lines = [SUMMARY, ""]
    for title, detail in POINTS:
        lines += [f"■ {title}", f"  {detail}", ""]
    lines.append("Programas que usa:")
    for name, licence, detail in DEPENDENCIES:
        lines.append(f"  · {name} ({licence}): {detail}")
    return "\n".join(lines)
