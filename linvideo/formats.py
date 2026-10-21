"""Los formatos que ofrece la web para un enlace (botón «Formatos…» y `--formats`)."""

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from . import errors, formatters, tools


class InspectError(Exception):
    pass


@dataclass(frozen=True)
class MediaFormat:
    id: str                    # format_id de yt-dlp
    ext: str
    resolution: str
    height: int
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    size_bytes: float | None
    bitrate: float | None      # kbit/s
    note: str | None

    @property
    def is_audio_only(self) -> bool:
        return self.video_codec is None and self.audio_codec is not None

    @property
    def is_video_only(self) -> bool:
        return self.video_codec is not None and self.audio_codec is None

    @property
    def is_complete(self) -> bool:
        return self.video_codec is not None and self.audio_codec is not None

    @property
    def size_text(self) -> str:
        if not self.size_bytes or self.size_bytes <= 0:
            return "—"
        return formatters.human_bytes(self.size_bytes)

    @property
    def quality_text(self) -> str:
        if self.is_audio_only:
            if self.bitrate:
                return f"{int(self.bitrate)} kbps"
            return self.note or "audio"
        text = self.resolution
        if self.fps and self.fps > 0:
            text += f" · {int(self.fps)} fps"
        return text

    @property
    def codec_text(self) -> str:
        video = short_codec(self.video_codec) if self.video_codec else "—"
        audio = short_codec(self.audio_codec) if self.audio_codec else "—"
        if self.is_audio_only:
            return audio
        if self.is_video_only:
            return video
        return f"{video} + {audio}"

    @property
    def selector(self) -> str:
        """Lo que se le pasa a `-f`. A un formato de sólo vídeo se le añade el mejor audio,
        prefiriendo AAC para que el MP4 lo abra cualquier cosa."""
        if self.is_video_only:
            return f"{self.id}+bestaudio[ext=m4a]/{self.id}+bestaudio/{self.id}"
        return self.id


def short_codec(raw: str) -> str:
    """Nombre corto del códec, sin el perfil que le cuelga yt-dlp."""
    base = raw.split(".")[0]
    return {
        "avc1": "H.264", "h264": "H.264",
        "hev1": "HEVC", "hvc1": "HEVC",
        "av01": "AV1",
        "vp9": "VP9", "vp09": "VP9",
        "mp4a": "AAC",
        "opus": "Opus",
        "vorbis": "Vorbis",
        "ec-3": "E-AC3", "eac3": "E-AC3",
    }.get(base.lower(), base)


def run_json(link: str) -> dict[str, Any]:
    """`yt-dlp -J`: todo lo que yt-dlp sabe de un enlace, sin descargar."""
    ytdlp = tools.ytdlp()
    if ytdlp is None:
        raise InspectError("No se encuentra yt-dlp. Instálalo con: linvideo --update")
    argv = [*tools.command(ytdlp), "--ignore-config", "--no-warnings", "--no-playlist", "-J", link]
    try:
        out = subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL,
                             env=tools.child_env(), timeout=180)
    except (OSError, subprocess.SubprocessError) as error:
        raise InspectError(str(error)) from error
    if out.returncode != 0 or not out.stdout:
        lines = out.stderr.decode("utf-8", errors="replace").splitlines()
        raise InspectError(errors.explain(lines, out.returncode))
    try:
        root = json.loads(out.stdout)
    except ValueError as error:
        raise InspectError("La respuesta de yt-dlp no se entiende.") from error
    if not isinstance(root, dict):
        raise InspectError("La respuesta de yt-dlp no se entiende.")
    return root


def number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_formats(root: dict[str, Any]) -> list[MediaFormat]:
    formats: list[MediaFormat] = []
    for raw in root.get("formats") or []:
        if not isinstance(raw, dict) or not isinstance(raw.get("format_id"), str):
            continue
        # yt-dlp marca «none» cuando la pista no existe.
        video = raw.get("vcodec") if raw.get("vcodec") not in (None, "none") else None
        audio = raw.get("acodec") if raw.get("acodec") not in (None, "none") else None
        if video is None and audio is None:
            continue
        formats.append(MediaFormat(
            id=raw["format_id"],
            ext=str(raw.get("ext") or ""),
            resolution=str(raw.get("resolution") or "—"),
            height=int(number_or_none(raw.get("height")) or 0),
            fps=number_or_none(raw.get("fps")),
            video_codec=str(video) if video else None,
            audio_codec=str(audio) if audio else None,
            size_bytes=number_or_none(raw.get("filesize")) or number_or_none(raw.get("filesize_approx")),
            bitrate=number_or_none(raw.get("abr")) or number_or_none(raw.get("tbr")),
            note=raw.get("format_note") if isinstance(raw.get("format_note"), str) else None,
        ))
    # De mayor a menor calidad: primero los que traen vídeo.
    formats.sort(key=lambda f: (f.height, f.bitrate or 0), reverse=True)
    return formats


def inspect(link: str) -> tuple[str, list[MediaFormat]]:
    """Pregunta a la web qué formatos ofrece para ese enlace."""
    root = run_json(link)
    if not isinstance(root.get("formats"), list):
        raise InspectError("La respuesta de yt-dlp no trae la lista de formatos.")
    title = root.get("title") if isinstance(root.get("title"), str) else link
    return str(title), parse_formats(root)
