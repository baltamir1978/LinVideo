"""La línea de órdenes que se le pasa a yt-dlp: si esto se tuerce, no descarga nada o
descarga otra cosa."""

from pathlib import Path

from linvideo.download import (FILE_TAG, PROGRESS_TAG, TITLE_TAG, DownloadRequest, Progress,
                               download_section, normalize_timestamp, parse_progress, unique_path)
from linvideo.models import CookieSource, DownloadOptions, MediaKind, VideoResolution

DEST = Path("/tmp/linvideo-pruebas")


def arguments(kind: MediaKind, options: DownloadOptions | None = None) -> list[str]:
    return DownloadRequest("https://ejemplo.test/video", kind, DEST,
                           options or DownloadOptions()).ytdlp_arguments(DEST)


def value_after(flag: str, args: list[str]) -> str | None:
    if flag not in args:
        return None
    i = args.index(flag)
    return args[i + 1] if i + 1 < len(args) else None


def test_el_enlace_va_al_final() -> None:
    assert arguments(MediaKind.VIDEO_MAX)[-1] == "https://ejemplo.test/video"


def test_techo_de_resolucion() -> None:
    options = DownloadOptions(resolution=VideoResolution.FHD)
    assert "[height<=1080]" in (value_after("-f", arguments(MediaKind.VIDEO_MAX, options)) or "")
    # «Máxima» no debe poner ningún filtro.
    assert "height" not in (value_after("-f", arguments(MediaKind.VIDEO_MAX)) or "")


def test_formato_elegido_a_mano() -> None:
    options = DownloadOptions(resolution=VideoResolution.SD, format_override="137+bestaudio")
    args = arguments(MediaKind.VIDEO_MAX, options)
    assert value_after("-f", args) == "137+bestaudio"
    assert "height<=" not in " ".join(args)


def test_recorte() -> None:
    args = arguments(MediaKind.VIDEO_MAX, DownloadOptions(clip_start="1:30", clip_end="2:45"))
    assert value_after("--download-sections", args) == "*1:30-2:45"
    assert "--force-keyframes-at-cuts" in args


def test_recorte_parcial() -> None:
    assert download_section("0:30", "") == "*0:30-inf"
    assert download_section("", "1:00") == "*0-1:00"
    assert download_section("", "") is None


def test_recorte_invalido() -> None:
    assert normalize_timestamp("hola") is None
    assert normalize_timestamp(" 1:30 ") == "1:30"


def test_etiquetas_de_audio() -> None:
    args = arguments(MediaKind.AUDIO_MP3)
    text = " ".join(args)
    assert "--embed-metadata" in args
    assert "--embed-thumbnail" in args
    assert value_after("--convert-thumbnails", args) == "jpg"
    assert "meta_artist" in text and "meta_title" in text
    # El álbum se deja en manos de yt-dlp: forzarlo escribía «NA».
    assert "meta_album" not in text


def test_etiquetas_simples() -> None:
    text = " ".join(arguments(MediaKind.AUDIO_MP3, DownloadOptions(smart_audio_tags=False)))
    assert "(?P<meta_artist>" not in text


def test_gif_sin_audio() -> None:
    assert "ba" not in (value_after("-f", arguments(MediaKind.GIF)) or "")


def test_modo_compatible() -> None:
    selector = value_after("-f", arguments(MediaKind.VIDEO_COMPAT)) or ""
    assert "avc1" in selector and "mp4a" in selector


def test_listas_de_reproduccion() -> None:
    assert "--no-playlist" in arguments(MediaKind.VIDEO_MAX)
    assert "--yes-playlist" in arguments(MediaKind.VIDEO_MAX, DownloadOptions(download_playlist=True))


def test_limite_de_velocidad() -> None:
    assert "--limit-rate" not in arguments(MediaKind.VIDEO_MAX)
    args = arguments(MediaKind.VIDEO_MAX, DownloadOptions(speed_limit="500K"))
    assert value_after("--limit-rate", args) == "500K"


def test_cookies() -> None:
    assert "--cookies-from-browser" not in arguments(MediaKind.VIDEO_MAX)
    args = arguments(MediaKind.VIDEO_MAX, DownloadOptions(cookie_source=CookieSource.FIREFOX))
    assert value_after("--cookies-from-browser", args) == "firefox"


def test_opciones_extra() -> None:
    args = arguments(MediaKind.VIDEO_MAX, DownloadOptions(extra_arguments="--limit-rate 2M"))
    assert "--limit-rate" in args and "2M" in args


def test_opciones_extra_con_comillas() -> None:
    # Nuevo en LinVideo: las comillas se respetan.
    args = arguments(MediaKind.VIDEO_MAX,
                     DownloadOptions(extra_arguments='--user-agent "Navegador raro 1.0"'))
    assert value_after("--user-agent", args) == "Navegador raro 1.0"


def test_ffmpeg_del_sistema() -> None:
    args = DownloadRequest("https://x.test", MediaKind.VIDEO_MAX, DEST,
                           DownloadOptions()).ytdlp_arguments(DEST, Path("/usr/bin"))
    assert value_after("--ffmpeg-location", args) == "/usr/bin"


def test_marcas_de_progreso() -> None:
    text = " ".join(arguments(MediaKind.VIDEO_MAX))
    assert PROGRESS_TAG in text and TITLE_TAG in text and FILE_TAG in text


def test_lectura_del_progreso() -> None:
    event = parse_progress(f"{PROGRESS_TAG}524288|1048576|NA|262144|2")
    assert isinstance(event, Progress)
    assert event.fraction == 0.5
    assert event.speed == "256,0 KB/s"
    assert event.eta == "0:02"
    assert event.size == "512,0 KB / 1,0 MB"
    # Sin total conocido, barra indeterminada.
    unknown = parse_progress(f"{PROGRESS_TAG}1024|NA|NA|NA|NA")
    assert unknown is not None and unknown.fraction == -1 and unknown.speed == ""
    # El total estimado sirve si no hay exacto.
    estimated = parse_progress(f"{PROGRESS_TAG}100|NA|400|NA|NA")
    assert estimated is not None and estimated.fraction == 0.25


def test_nombre_unico(tmp_path: Path) -> None:
    (tmp_path / "vídeo.mp4").write_text("")
    (tmp_path / "vídeo (2).mp4").write_text("")
    assert unique_path(tmp_path / "vídeo.mp4").name == "vídeo (3).mp4"
    assert unique_path(tmp_path / "otro.mp4").name == "otro.mp4"
