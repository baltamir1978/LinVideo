"""Qué se descarga y con qué ajustes."""

from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any


class MediaKind(Enum):
    """Qué queremos obtener del enlace."""

    VIDEO_MAX = "videoMax"            # mejor vídeo + mejor audio, en MP4 sin recodificar
    VIDEO_COMPAT = "videoCompat"      # H.264 + AAC en MP4: lo abre cualquier cosa
    AUDIO_MP3 = "audioMP3"            # extrae el audio y lo codifica a MP3
    AUDIO_ORIGINAL = "audioOriginal"  # extrae el audio sin recodificar (m4a, opus…)
    GIF = "gif"                       # descarga el vídeo y lo convierte a GIF

    @property
    def title(self) -> str:
        return {
            MediaKind.VIDEO_MAX: "Vídeo (máxima calidad)",
            MediaKind.VIDEO_COMPAT: "Vídeo (máxima compatibilidad)",
            MediaKind.AUDIO_MP3: "Audio MP3",
            MediaKind.AUDIO_ORIGINAL: "Audio original",
            MediaKind.GIF: "GIF",
        }[self]

    @property
    def short_title(self) -> str:
        return {
            MediaKind.VIDEO_MAX: "Vídeo",
            MediaKind.VIDEO_COMPAT: "Vídeo compat.",
            MediaKind.AUDIO_MP3: "MP3",
            MediaKind.AUDIO_ORIGINAL: "Audio orig.",
            MediaKind.GIF: "GIF",
        }[self]

    @property
    def help(self) -> str:
        return {
            MediaKind.VIDEO_MAX:
                "Descarga la pista de vídeo y audio de mayor calidad disponible (VP9/AV1/H.264) "
                "y las une en .mp4 sin recodificar. Calidad original.",
            MediaKind.VIDEO_COMPAT:
                "Elige la mejor pista H.264 + AAC. Algo menos de calidad en YouTube, pero "
                "reproducible en cualquier aparato, incluidos móviles y teles viejas.",
            MediaKind.AUDIO_MP3:
                "Extrae el audio y lo convierte a MP3 a la máxima calidad (recodifica, por "
                "compatibilidad).",
            MediaKind.AUDIO_ORIGINAL:
                "Extrae la pista de audio tal cual viene (m4a, opus, webm). Sin pérdida añadida.",
            MediaKind.GIF:
                "Descarga el vídeo y genera un GIF optimizado con paleta propia (ideal para "
                "RedGifs y clips cortos).",
        }[self]

    @property
    def is_audio(self) -> bool:
        return self in (MediaKind.AUDIO_MP3, MediaKind.AUDIO_ORIGINAL)


class CookieSource(Enum):
    """De qué navegador tomar las cookies (verificación de edad, contenido tras sesión).

    Son los navegadores de Linux que yt-dlp sabe leer; Safari no existe aquí.
    """

    NONE = "none"
    FIREFOX = "firefox"
    CHROMIUM = "chromium"
    CHROME = "chrome"
    BRAVE = "brave"
    EDGE = "edge"
    VIVALDI = "vivaldi"

    @property
    def title(self) -> str:
        return "Sin cookies" if self is CookieSource.NONE else self.value.capitalize()

    @property
    def browser_argument(self) -> str | None:
        """Valor para `--cookies-from-browser`."""
        return None if self is CookieSource.NONE else self.value


class VideoResolution(Enum):
    """Techo de resolución para las descargas de vídeo."""

    BEST = 0
    UHD = 2160
    QHD = 1440
    FHD = 1080
    HD = 720
    SD = 480

    @property
    def title(self) -> str:
        return {
            VideoResolution.BEST: "Máxima",
            VideoResolution.UHD: "4K · 2160p",
            VideoResolution.QHD: "1440p",
            VideoResolution.FHD: "1080p",
            VideoResolution.HD: "720p",
            VideoResolution.SD: "480p",
        }[self]

    @property
    def height_filter(self) -> str:
        """Filtro de altura para el selector de formato de yt-dlp."""
        return "" if self is VideoResolution.BEST else f"[height<={self.value}]"


class FilenameCleanup(Enum):
    """Cuánto se limpia el nombre del archivo descargado."""

    NONE = "none"
    BASIC = "basic"
    STRICT = "strict"

    @property
    def title(self) -> str:
        return {
            FilenameCleanup.NONE: "Dejarlo como viene",
            FilenameCleanup.BASIC: "Limpieza básica",
            FilenameCleanup.STRICT: "Limpieza estricta",
        }[self]

    @property
    def help(self) -> str:
        return {
            FilenameCleanup.NONE:
                "Se guarda con el título tal cual, incluido el identificador del vídeo.",
            FilenameCleanup.BASIC:
                "Quita el identificador, los emojis, los hashtags, las direcciones web y las "
                "etiquetas de relleno («Official Video», «HD», «4K»…), y ordena espacios y guiones.",
            FilenameCleanup.STRICT:
                "Además de lo anterior, quita todo lo que va entre paréntesis o corchetes, "
                "arregla los títulos escritos en mayúsculas y acorta más el nombre.",
        }[self]


@dataclass
class DownloadOptions:
    """Ajustes que se aplican a la descarga.

    Se guardan enteros en los ajustes, menos el recorte y el formato elegido a mano, que
    son de cada descarga.
    """

    cookie_source: CookieSource = CookieSource.NONE
    resolution: VideoResolution = VideoResolution.BEST
    # Recorte por tiempo, en `mm:ss` o `hh:mm:ss`. Vacío: sin recorte.
    clip_start: str = ""
    clip_end: str = ""
    # Selector de yt-dlp elegido a mano para esta descarga. Vacío: decide el modo.
    format_override: str = ""
    download_playlist: bool = False
    # Límite de velocidad en formato de yt-dlp («500K», «2M»). Vacío: sin límite.
    speed_limit: str = ""
    filename_cleanup: FilenameCleanup = FilenameCleanup.BASIC
    # Conservar el identificador del vídeo al final del nombre.
    keep_identifier: bool = False
    embed_metadata: bool = True
    # En audio: deducir artista y título cuando el vídeo se llama «Artista - Título».
    smart_audio_tags: bool = True
    embed_subtitles: bool = False
    embed_thumbnail: bool = True
    concurrent_fragments: int = 4
    gif_fps: int = 15
    gif_width: int = 480
    extra_arguments: str = ""

    # Lo que es propio de cada descarga y no se guarda entre sesiones.
    TRANSIENT = ("clip_start", "clip_end", "format_override")

    def to_json(self, *, persistent_only: bool = False) -> dict[str, Any]:
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Enum):
                data[key] = value.value
        if persistent_only:
            for key in self.TRANSIENT:
                data.pop(key, None)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "DownloadOptions":
        """Lee lo que se pueda; lo desconocido o mal formado se queda con su valor por omisión."""
        options = cls()
        for field in fields(cls):
            if field.name not in data:
                continue
            current = getattr(options, field.name)
            raw = data[field.name]
            try:
                if isinstance(current, Enum):
                    value: Any = type(current)(raw)
                elif isinstance(current, bool):
                    if not isinstance(raw, bool):
                        continue
                    value = raw
                elif isinstance(current, int):
                    if isinstance(raw, bool) or not isinstance(raw, int):
                        continue
                    value = raw
                else:
                    if not isinstance(raw, str):
                        continue
                    value = raw
            except ValueError:
                continue
            setattr(options, field.name, value)
        return options
