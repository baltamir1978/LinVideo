"""Convierte el título que da la web en un nombre de archivo presentable.

Se aplica renombrando el archivo ya descargado, no con las plantillas de yt-dlp: así se
puede razonar sobre el texto completo y es fácil de probar.
"""

import re

from .models import FilenameCleanup

# Etiquetas de relleno que suelen colgar de los títulos.
FILLER_WORDS = [
    "official video", "official music video", "official audio", "official lyric video",
    "official visualizer", "official trailer", "lyric video", "lyrics", "visualizer",
    "video oficial", "audio oficial", "vídeo oficial", "videoclip oficial", "letra",
    "full hd", "fullhd", "hd", "hq", "sd", "4k", "8k", "2160p", "1440p", "1080p", "720p",
    "480p", "60fps", "50fps", "uhd", "remastered", "remasterizado",
    "free download", "descarga gratis", "download free", "watch free", "gratis",
    "full video", "vídeo completo", "video completo", "complete video",
    "porn", "xxx", "sex video",
]


def clean(raw_name: str, level: FilenameCleanup, keep_identifier: bool = False) -> str:
    if level is FilenameCleanup.NONE:
        return raw_name

    strict = level is FilenameCleanup.STRICT
    base, ext = split_extension(raw_name)
    name = base

    if not keep_identifier:
        name = remove_trailing_identifier(name)
    name = remove_emoji(name)
    name = remove_hashtags(name)
    name = remove_web_addresses(name)
    if strict:
        name = remove_bracketed_text(name)
    name = remove_filler_tags(name, strict=strict)
    name = replace_problematic_characters(name)
    name = collapse_separators(name)
    if strict:
        name = fix_shouting(name)

    name = truncate(name, 90 if strict else 120)
    name = name.strip(" -_.,;·|")

    # Si la limpieza se lo ha llevado todo, mejor el nombre original.
    if not name:
        return raw_name
    return f"{name}.{ext}" if ext else name


def split_extension(name: str) -> tuple[str, str]:
    """Separa nombre y extensión.

    Sólo cuenta como extensión un sufijo corto y alfanumérico tras el último punto, para
    no destrozar títulos con puntos. No se usa `os.path`: una barra en el título se
    tomaría por separador de carpetas y se perdería todo lo anterior.
    """
    dot = name.rfind(".")
    if dot <= 0:
        return name, ""
    candidate = name[dot + 1:]
    if 1 <= len(candidate) <= 5 and candidate.isalnum():
        return name[:dot], candidate
    return name, ""


# --- Pasos -------------------------------------------------------------------------


def remove_trailing_identifier(name: str) -> str:
    """Quita el « [dQw4w9WgXcQ]» final que añade la plantilla de descarga."""
    return re.sub(r"\s*[\[(][A-Za-z0-9_\-]{5,}[\])]\s*$", "", name)


def _is_emoji(cp: int) -> bool:
    # Python no trae la propiedad Unicode «Emoji»: se usan los bloques donde viven.
    # Se respetan letras, números, puntuación, flechas y los símbolos © ®.
    return (
        cp >= 0x1F000
        or 0x2600 <= cp <= 0x27BF        # símbolos varios y dingbats
        or 0x238D <= cp <= 0x23FF        # ⌚ ⏰ ⏩…
        or 0x25A0 <= cp <= 0x25FF        # ▪ ▶ ◀ ◻ ◼
        or 0x2B00 <= cp <= 0x2BFF        # ⭐ ⬛ ⬆…
        or 0xFE00 <= cp <= 0xFE0F        # selectores de variación
        or cp in (0x200D, 0x20E3, 0x24C2, 0x3030, 0x303D, 0x3297, 0x3299)
    )


def remove_emoji(name: str) -> str:
    return "".join(ch for ch in name if not _is_emoji(ord(ch)))


def remove_hashtags(name: str) -> str:
    return re.sub(r"#\w+", " ", name)


def remove_web_addresses(name: str) -> str:
    result = re.sub(r"(?i)\bhttps?://\S+", " ", name)
    return re.sub(
        r"(?i)\b(?:www\.)?[a-z0-9\-]{3,}\.(?:com|net|org|tv|xxx|es|to|cc|me)\b(?:/\S*)?",
        " ", result)


def remove_bracketed_text(name: str) -> str:
    result = re.sub(r"\([^()]*\)", " ", name)
    return re.sub(r"\[[^\[\]]*\]", " ", result)


def remove_filler_tags(name: str, strict: bool) -> str:
    """Quita etiquetas de relleno, tanto entre paréntesis como sueltas al final."""
    result = name
    for word in FILLER_WORDS:
        escaped = re.escape(word)
        # Entre paréntesis o corchetes: «(Official Video)», «[HD]».
        result = re.sub(rf"(?i)\s*[\[(]\s*{escaped}\s*[\])]", " ", result)
        # Suelta y pegada a un separador: «- Official Video», «| HD».
        result = re.sub(rf"(?i)\s*[-–—|·]\s*{escaped}\s*(?=$|[-–—|·])", " ", result)
        if strict:
            # Suelta en cualquier posición, como palabra completa.
            result = re.sub(rf"(?i)\b{escaped}\b", " ", result)
    # Etiquetas pegadas al final sin separador («… 4K FULL HD»). Varias pasadas porque
    # suelen ir en cadena.
    for _ in range(3):
        for word in FILLER_WORDS:
            result = re.sub(rf"(?i)\s*[-–—|·]?\s*{re.escape(word)}\s*$", "", result)
    return result


_SWAPS = [
    ("/", "-"), ("\\", "-"), (":", " -"), ("|", "-"),
    ("*", ""), ("?", ""), ('"', "'"), ("<", ""), (">", ""),
    (" ", " "),   # espacio duro
    ("​", ""),    # espacio de ancho cero
]


def replace_problematic_characters(name: str) -> str:
    """Cambia lo que da problemas en nombres de archivo, también al copiarlos a FAT y exFAT."""
    result = name
    for old, new in _SWAPS:
        result = result.replace(old, new)
    # Caracteres de control.
    return "".join(ch for ch in result if ord(ch) > 0x1F)


def collapse_separators(name: str) -> str:
    """Espacios y guiones repetidos, y paréntesis que se han quedado vacíos."""
    result = re.sub(r"[\[(]\s*[\])]", " ", name)
    result = re.sub(r"\s+", " ", result)
    result = re.sub(r"\s*([-–—|·])\s*\1+", r" \1 ", result)
    result = re.sub(r"^[\s\-–—|·,.]+", "", result)
    result = re.sub(r"[\s\-–—|·,.]+$", "", result)
    result = re.sub(r"\s+([,;.!?])", r"\1", result)
    return result.strip()


def fix_shouting(name: str) -> str:
    """«ESTO ES UN TÍTULO A GRITOS» → «Esto Es Un Título A Gritos»."""
    letters = [ch for ch in name if ch.isalpha()]
    if len(letters) < 8:
        return name
    uppercase = sum(1 for ch in letters if ch.isupper())
    if uppercase / len(letters) <= 0.8:
        return name
    # Palabra a palabra por espacios, no con `str.title()`, que deja «Don'T».
    return re.sub(r"\S+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), name)


def truncate(name: str, limit: int) -> str:
    """Recorta sin partir palabras por la mitad."""
    if len(name) <= limit:
        return name
    cut = name[:limit]
    space = cut.rfind(" ")
    if space > limit // 2:
        return cut[:space]
    return cut
