"""Conversiones de texto, mezcla de resultados, alcance, formatos y cifras."""

from linvideo import formatters
from linvideo.formats import MediaFormat, short_codec
from linvideo.models import DownloadOptions, MediaKind, VideoResolution
from linvideo.search import (SearchCategory, SearchResult, SearchScope, SearchSource,
                             decode_entities, interleave, parse_compact_number,
                             parse_loose_duration)
from linvideo.settings import Settings, extract_urls


def test_duraciones_en_palabras() -> None:
    assert parse_loose_duration("32 min") == 32 * 60
    assert parse_loose_duration("6min") == 6 * 60
    assert parse_loose_duration("1 h 5 min") == 3900
    assert parse_loose_duration("45 sec") == 45
    assert parse_loose_duration("10:30") == 630
    assert parse_loose_duration("1:02:03") == 3723
    assert parse_loose_duration("sin datos") is None


def test_visitas_abreviadas() -> None:
    assert parse_compact_number("1.2M") == 1_200_000
    assert parse_compact_number("340K") == 340_000
    assert parse_compact_number("5.320") == 5320     # punto de millares
    assert parse_compact_number("42") == 42
    assert parse_compact_number("nada") is None


def test_entidades_html() -> None:
    assert decode_entities("caf&eacute; &amp; t&eacute;") == "café & té"
    assert decode_entities("resist&ecirc;ncia") == "resistência"
    assert decode_entities("&#233;xito") == "éxito"
    assert decode_entities("&#x41;BC") == "ABC"
    assert decode_entities("sin entidades") == "sin entidades"
    assert decode_entities("a&nbsp;b") == "a b"


def _result(identifier: str) -> SearchResult:
    return SearchResult(id=identifier, title=identifier, page_url=f"https://e.test/{identifier}")


def test_intercala_por_rondas() -> None:
    mixed = interleave({SearchSource.YOUTUBE: [_result("y1"), _result("y2")],
                        SearchSource.DAILYMOTION: [_result("d1"), _result("d2")]},
                       [SearchSource.YOUTUBE, SearchSource.DAILYMOTION])
    assert [r.id for r in mixed] == ["y1", "d1", "y2", "d2"]


def test_fuentes_desiguales() -> None:
    mixed = interleave({SearchSource.YOUTUBE: [_result("y1"), _result("y2"), _result("y3")],
                        SearchSource.PEERTUBE: [_result("p1")]},
                       [SearchSource.YOUTUBE, SearchSource.PEERTUBE])
    assert [r.id for r in mixed] == ["y1", "p1", "y2", "y3"]


def test_sin_resultados() -> None:
    assert interleave({}, [SearchSource.YOUTUBE]) == []


def test_categorias() -> None:
    assert SearchSource.in_category(SearchCategory.AUDIO) == [SearchSource.SOUNDCLOUD,
                                                             SearchSource.MIXCLOUD]
    assert SearchSource.YOUTUBE in SearchSource.in_category(SearchCategory.VIDEO)
    assert SearchSource.REDGIFS in SearchSource.in_category(SearchCategory.ADULT)
    grouped = [s for c in SearchCategory for s in SearchSource.in_category(c)]
    assert set(grouped) == set(SearchSource)


def test_todas_las_webs() -> None:
    assert len(SearchScope.everywhere().sources) == len(SearchSource)
    assert SearchScope.everywhere().is_multi
    assert not SearchScope(source=SearchSource.YOUTUBE).is_multi
    assert SearchScope.parse("adult") == SearchScope(category=SearchCategory.ADULT)
    assert SearchScope.parse("todas") == SearchScope.everywhere()
    assert SearchScope.parse("nada") is None


def test_formato_propuesto() -> None:
    assert SearchScope(source=SearchSource.SOUNDCLOUD).preferred_kind is MediaKind.AUDIO_MP3
    assert SearchScope(source=SearchSource.REDGIFS).preferred_kind is MediaKind.GIF
    assert SearchScope(category=SearchCategory.AUDIO).preferred_kind is MediaKind.AUDIO_MP3
    assert SearchScope(source=SearchSource.YOUTUBE).preferred_kind is MediaKind.VIDEO_MAX


def _format(identifier: str, video: str | None, audio: str | None) -> MediaFormat:
    return MediaFormat(id=identifier, ext="mp4", resolution="1920x1080", height=1080, fps=24,
                       video_codec=video, audio_codec=audio, size_bytes=1024 * 1024,
                       bitrate=500, note=None)


def test_selector_con_audio() -> None:
    selector = _format("137", "avc1.640028", None).selector
    assert selector.startswith("137+") and "m4a" in selector
    assert selector.endswith("/137")     # alternativa por si no hay audio suelto


def test_selector_completo() -> None:
    assert _format("18", "avc1", "mp4a").selector == "18"


def test_nombres_de_codecs() -> None:
    assert short_codec("avc1.640028") == "H.264"
    assert short_codec("av01.0.00M.08") == "AV1"
    assert short_codec("vp9") == "VP9"
    assert short_codec("mp4a.40.2") == "AAC"
    assert short_codec("opus") == "Opus"


def test_clasificacion() -> None:
    assert _format("1", None, "opus").is_audio_only
    assert _format("2", "vp9", None).is_video_only
    assert _format("3", "vp9", "opus").is_complete


def test_tamanos() -> None:
    assert formatters.human_bytes(512) == "512 B"
    assert formatters.human_bytes(1024 * 1024) == "1,0 MB"


def test_duraciones() -> None:
    assert formatters.duration(65) == "1:05"
    assert formatters.duration(3725) == "1:02:05"
    assert formatters.duration(0) == "0:00"


def test_varios_enlaces() -> None:
    assert len(extract_urls("https://uno.test/a\nhttps://dos.test/b, https://tres.test/c")) == 3


def test_descarta_texto_suelto() -> None:
    assert extract_urls("esto no es un enlace") == []
    assert extract_urls("ftp://viejo.test/x") == []


def test_limpia_adornos() -> None:
    assert extract_urls("<https://uno.test/a>") == ["https://uno.test/a"]


def test_ajustes_ida_y_vuelta() -> None:
    settings = Settings(kind=MediaKind.AUDIO_MP3, destination="~/Música",
                        options=DownloadOptions(resolution=VideoResolution.HD, clip_start="1:00",
                                                format_override="137"))
    loaded = Settings.from_json(settings.to_json())
    assert loaded.kind is MediaKind.AUDIO_MP3
    assert loaded.options.resolution is VideoResolution.HD
    # El recorte y el formato a mano son de cada descarga: no se guardan.
    assert loaded.options.clip_start == "" and loaded.options.format_override == ""


def test_ajustes_estropeados() -> None:
    # Un valor raro no tira el resto.
    loaded = Settings.from_json({"kind": "inventado", "max_concurrent": "tres",
                                 "options": {"resolution": 999, "gif_fps": 30}})
    assert loaded.kind is MediaKind.VIDEO_MAX
    assert loaded.max_concurrent == 2
    assert loaded.options.resolution is VideoResolution.BEST
    assert loaded.options.gif_fps == 30
