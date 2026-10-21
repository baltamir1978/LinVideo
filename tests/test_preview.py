"""La vista previa sólo sirve si elige algo que GStreamer abra y que arranque rápido.

Los casos son los de AppVideo. Cambian dos, porque GStreamer abre más cosas que AVPlayer:
WebM/Opus ya valen, y lo único que se sigue descartando son los segmentos DASH sueltos.
"""

from typing import Any

from linvideo.preview import PreviewKind, pick


def fmt(identifier: str, url: str, proto: str = "https", ext: str = "mp4",
        vcodec: str | None = None, acodec: str | None = None, height: int | None = None,
        manifest: str | None = None, abr: float | None = None) -> dict[str, Any]:
    raw: dict[str, Any] = {"format_id": identifier, "url": url, "protocol": proto, "ext": ext,
                           "http_headers": {"User-Agent": "UA", "Accept": "*/*",
                                            "Referer": "https://web/"}}
    for key, value in (("vcodec", vcodec), ("acodec", acodec), ("height", height),
                       ("manifest_url", manifest), ("abr", abr)):
        if value is not None:
            raw[key] = value
    return raw


def test_youtube_usa_el_maestro() -> None:
    root = {"title": "Gatos", "formats": [
        fmt("sb0", "https://i.ytimg.com/sb", proto="mhtml", ext="mhtml", vcodec="none",
            acodec="none"),
        fmt("140", "https://gv/140", ext="m4a", vcodec="none", acodec="mp4a.40.2"),
        fmt("234", "https://m/234", proto="m3u8_native", vcodec="none", acodec="mp4a.40.2",
            manifest="https://m/master.m3u8"),
        fmt("135", "https://gv/135", vcodec="avc1.4d401f", acodec="none", height=480),
        fmt("230", "https://m/230", proto="m3u8_native", vcodec="avc1.4D401E", acodec="none",
            height=360, manifest="https://m/master.m3u8"),
    ]}
    stream = pick(root)
    assert stream is not None
    assert stream.url == "https://m/master.m3u8"
    assert stream.kind is PreviewKind.VIDEO
    assert stream.title == "Gatos"


def test_maestro_mudo() -> None:
    root = {"formats": [
        fmt("hls-994", "https://v.redd.it/x/HLS_480.m3u8", proto="m3u8_native",
            vcodec="avc1.4D401F", acodec="none", height=854,
            manifest="https://v.redd.it/x/HLSPlaylist.m3u8"),
        fmt("dash-4", "https://v.redd.it/x/DASH_480.mp4", vcodec="avc1.4d401f", acodec="none",
            height=854),
    ]}
    stream = pick(root)
    assert stream is not None
    assert stream.url == "https://v.redd.it/x/HLSPlaylist.m3u8"
    assert stream.kind is PreviewKind.VIDEO_ONLY


def test_mp4_completo_hasta_720() -> None:
    root = {"formats": [
        fmt("240", "https://v/240", vcodec="avc1", acodec="mp4a", height=240),
        fmt("720", "https://v/720", vcodec="avc1", acodec="mp4a", height=720),
        fmt("1080", "https://v/1080", vcodec="avc1", acodec="mp4a", height=1080),
        fmt("webm", "https://v/webm", ext="webm", vcodec="vp9", acodec="opus", height=480),
    ]}
    stream = pick(root)
    assert stream is not None and stream.url == "https://v/720"
    assert stream.kind is PreviewKind.VIDEO


def test_webm_vale_en_linux() -> None:
    # En el Mac esto no se podía previsualizar; con GStreamer, sí.
    root = {"formats": [fmt("webm", "https://v/webm", ext="webm", vcodec="vp9", acodec="opus",
                            height=480)]}
    stream = pick(root)
    assert stream is not None and stream.url == "https://v/webm"


def test_video_sin_sonido_antes_que_audio() -> None:
    root = {"formats": [
        fmt("a", "https://v/a", ext="m4a", vcodec="none", acodec="mp4a.40.2"),
        fmt("v", "https://v/v", vcodec="avc1.4d401f", acodec="none", height=480),
    ]}
    stream = pick(root)
    assert stream is not None and stream.url == "https://v/v"
    assert stream.kind is PreviewKind.VIDEO_ONLY


def test_solo_audio_el_de_mas_calidad() -> None:
    root = {"formats": [
        fmt("64", "https://s/64", ext="mp3", acodec="mp3", abr=64),
        fmt("128", "https://s/128", ext="mp3", acodec="mp3", abr=128),
        fmt("opus", "https://s/opus", ext="opus", vcodec="none", acodec="opus", abr=160),
    ]}
    stream = pick(root)
    # En el Mac ganaba el MP3 de 128; aquí el Opus de 160 también se puede oír.
    assert stream is not None and stream.url == "https://s/opus"
    assert stream.kind is PreviewKind.AUDIO


def test_lista_de_pistas() -> None:
    root = {"_type": "playlist", "entries": [
        {"formats": [fmt("x", "https://a/1.xyz", ext="xyz")]},
        {"formats": [fmt("mp3", "https://a/2.mp3", ext="mp3", acodec="mp3")]},
    ]}
    stream = pick(root)
    assert stream is not None and stream.url == "https://a/2.mp3"
    assert stream.kind is PreviewKind.AUDIO


def test_nada_reproducible() -> None:
    root = {"formats": [
        fmt("dash", "https://v/dash", proto="http_dash_segments", vcodec="avc1", acodec="mp4a",
            manifest="https://v/manifest.mpd"),
        fmt("sb", "https://v/sb", proto="mhtml", ext="mhtml"),
    ]}
    assert pick(root) is None


def test_cabeceras() -> None:
    root = {"formats": [fmt("hls", "https://x/hls", proto="m3u8_native",
                            manifest="https://x/master.m3u8")]}
    stream = pick(root)
    assert stream is not None
    assert stream.headers == {"User-Agent": "UA", "Referer": "https://web/"}
