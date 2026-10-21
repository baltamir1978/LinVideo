"""Elige qué flujo reproducir en la vista previa, sin descargar nada.

En el Mac, AVPlayer sólo abría HLS y MP4 con códecs de Apple. Aquí reproduce GStreamer
(con gstreamer1.0-libav), que abre también WebM, VP9, AV1, Opus y Matroska, así que hay
mucho más donde elegir. Se mantiene el orden que se aprendió allí: YouTube ya no da ningún
archivo con vídeo y audio juntos, y su manifiesto HLS maestro une las dos pistas y arranca
en un par de segundos, así que va primero.

Lo que sigue fuera son los segmentos DASH sueltos: su `url` no es un archivo reproducible.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from . import formats


class PreviewKind(Enum):
    VIDEO = "Vídeo"                     # imagen y sonido
    VIDEO_ONLY = "Vídeo sin sonido"     # la web no da nada mejor
    AUDIO = "Sólo audio"


@dataclass(frozen=True)
class PreviewStream:
    url: str
    kind: PreviewKind
    title: str
    # Cabeceras que pide la web (User-Agent, Referer…); sin ellas algunas dan 403.
    headers: dict[str, str] = field(default_factory=dict)


class _Absent:
    """yt-dlp distingue «none» (la pista no existe) de ausente (no lo sabe)."""


ABSENT = _Absent()
UNKNOWN = None

_AUDIO_CONTAINERS = {"mp3", "m4a", "aac", "ogg", "opus", "wav", "flac"}
_PLAYABLE_CONTAINERS = {"mp4", "m4a", "m4v", "mov", "mp3", "aac", "webm", "mkv",
                        "ogg", "opus", "flac", "wav"}
_WANTED_HEADERS = {"user-agent", "referer", "origin", "cookie"}


@dataclass
class _Candidate:
    url: str
    manifest_url: str | None
    proto: str
    ext: str
    video: str | _Absent | None
    audio: str | _Absent | None
    height: int | None
    bitrate: float | None
    headers: dict[str, str]

    @property
    def has_video(self) -> bool:
        return self.video is not ABSENT

    @property
    def has_audio(self) -> bool:
        return self.audio is not ABSENT

    @property
    def is_hls(self) -> bool:
        return self.proto.startswith("m3u8")

    @property
    def is_playable(self) -> bool:
        if self.is_hls:
            return True
        if self.proto not in ("https", "http"):
            return False
        return self.ext in _PLAYABLE_CONTAINERS


def _track(value: Any) -> str | _Absent | None:
    if not isinstance(value, str):
        return UNKNOWN
    return ABSENT if value == "none" else value


def _candidate(raw: dict[str, Any]) -> _Candidate | None:
    url = raw.get("url")
    if not isinstance(url, str) or not url:
        return None
    ext = str(raw.get("ext") or "").lower()
    # En un .mp3 o .m4a no hay imagen aunque yt-dlp no lo diga.
    video = ABSENT if ext in _AUDIO_CONTAINERS else _track(raw.get("vcodec"))
    audio = _track(raw.get("acodec"))
    # Las miniaturas en mosaico también vienen como «formato».
    if ext == "mhtml" or (video is ABSENT and audio is ABSENT):
        return None
    headers_raw = raw.get("http_headers") or {}
    headers = {k: v for k, v in headers_raw.items()
               if isinstance(k, str) and isinstance(v, str) and k.lower() in _WANTED_HEADERS}
    manifest = raw.get("manifest_url")
    proto = raw.get("protocol")
    return _Candidate(
        url=url,
        manifest_url=manifest if isinstance(manifest, str) else None,
        proto=proto if isinstance(proto, str) else url.split(":", 1)[0],
        ext=ext,
        video=video,
        audio=audio,
        height=int(raw["height"]) if isinstance(raw.get("height"), (int, float)) else None,
        bitrate=formats.number_or_none(raw.get("abr")) or formats.number_or_none(raw.get("tbr")),
        headers=headers,
    )


def _closest_to_720(candidates: list[_Candidate]) -> _Candidate | None:
    """La calidad más alta sin pasar de 720p (basta para una vista previa y arranca antes);
    si todas pasan, la más baja. Sin altura conocida cuenta como aceptable."""
    if not candidates:
        return None
    fitting = [c for c in candidates if (c.height or 0) <= 720]
    if fitting:
        return max(fitting, key=lambda c: c.height or 0)
    return min(candidates, key=lambda c: c.height or 0)


def pick(root: dict[str, Any]) -> PreviewStream | None:
    """De mejor a peor: manifiesto HLS maestro, archivo con vídeo y audio, vídeo sin sonido
    y, en último caso, sólo audio."""
    # Archive.org y otras devuelven una lista de pistas: basta con la primera que suene.
    entries = root.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                found = pick(entry)
                if found:
                    return found
        return None

    title = root.get("title") if isinstance(root.get("title"), str) else ""
    raw_list = root.get("formats") or []
    # Algunos extractores devuelven un único formato en la raíz, sin lista.
    if not raw_list and root.get("url"):
        raw_list = [root]
    candidates = [c for c in (_candidate(r) for r in raw_list if isinstance(r, dict)) if c]

    def stream(url: str, c: _Candidate, kind: PreviewKind) -> PreviewStream:
        return PreviewStream(url=url, kind=kind, title=str(title), headers=c.headers)

    # 1. HLS maestro: agrupa varias calidades y, si hace falta, el audio aparte.
    for c in candidates:
        if c.is_hls and c.manifest_url and c.has_video:
            # Los vídeos mudos de Reddit no traen ninguna pista de audio en toda la lista.
            has_audio = any(other.has_audio for other in candidates)
            return stream(c.manifest_url, c,
                          PreviewKind.VIDEO if has_audio else PreviewKind.VIDEO_ONLY)

    playable = [c for c in candidates if c.is_playable]

    # 2. Un archivo o lista HLS con las dos pistas, lo más cerca posible de 720p.
    best = _closest_to_720([c for c in playable if c.has_video and c.has_audio])
    if best:
        return stream(best.url, best, PreviewKind.VIDEO)

    # 3. Vídeo sin sonido.
    best = _closest_to_720([c for c in playable if c.has_video])
    if best:
        return stream(best.url, best, PreviewKind.VIDEO_ONLY)

    # 4. Sólo audio, el de más calidad.
    audio = [c for c in playable if not c.has_video and c.has_audio]
    for c in audio:
        if c.is_hls and c.manifest_url:
            return stream(c.manifest_url, c, PreviewKind.AUDIO)
    if audio:
        best = max(audio, key=lambda c: c.bitrate or 0)
        return stream(best.url, best, PreviewKind.AUDIO)
    return None


def resolve(link: str) -> PreviewStream:
    root = formats.run_json(link)
    found = pick(root)
    if found is None:
        raise formats.InspectError(
            "Esta web sólo ofrece formatos que no se pueden previsualizar. Se puede descargar "
            "igualmente o abrir en el navegador.")
    return found
