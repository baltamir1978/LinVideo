"""Las webs que se leen a mano son lo más frágil del proyecto: cuando cambien su
maquetación, estos casos fallarán y dirán exactamente cuál.

Los fragmentos reproducen la estructura real de cada sitio con datos inventados (son los
mismos de AppVideo).
"""

import pytest

from linvideo.search import (SearchError, XVideosSite, extract_balanced_json, parse_porntrex,
                             parse_pornhub, parse_reddit, parse_thisvid, parse_tnaflix,
                             parse_xhamster, parse_xvideos_style, parse_youjizz, parse_youporn,
                             parse_ytdlp_entries, slugify)

XVIDEOS_HTML = """
<div class="mozaique">
<div id="video_abc123" data-id="12345678" class="frame-block thumb-block">
  <div class="thumb-inside"><div class="thumb">
    <a href="/video.abc123/paseo_por_la_playa">
      <img src="blank.gif" data-src="https://thumb.example/imagen.jpg" />
    </a>
  </div></div>
  <div class="thumb-under">
    <p class="title"><a href="/video.abc123/paseo_por_la_playa"
       title="Paseo por la playa &amp; monta&ntilde;a">Paseo por la playa</a></p>
    <p class="metadata"><span class="bg"><span class="duration">32 min</span>
      <span><a href="/profiles/quien"><span class="name">Quien Sea</span></a></span></span></p>
  </div>
</div>
<div id="video_def456" data-id="87654321" class="frame-block thumb-block">
  <div class="thumb"><a href="/video.def456/otro_video">
    <img data-src="https://thumb.example/otra.jpg" /></a></div>
  <div class="thumb-under"><p class="title">
    <a href="/video.def456/otro_video" title="Otro vídeo">Otro vídeo</a></p>
    <p class="metadata"><span class="duration">5 min</span></p></div>
</div>
</div>
"""


def test_xvideos() -> None:
    results = parse_xvideos_style(XVIDEOS_HTML, XVideosSite.XVIDEOS, 24)
    assert len(results) == 2
    first = results[0]
    assert first.title == "Paseo por la playa & montaña"      # entidades decodificadas
    assert first.page_url == "https://www.xvideos.com/video.abc123/paseo_por_la_playa"
    assert first.thumbnail_url == "https://thumb.example/imagen.jpg"
    assert first.duration == 32 * 60
    assert first.uploader == "Quien Sea"
    assert first.id == "12345678"


def test_xnxx() -> None:
    page = """
    <div id="video_100xo195" data-id="60509809" class="thumb-block">
      <div class="thumb"><a href="/video-100xo195/prueba">
        <img data-src="https://thumb.example/xn.jpg" /></a></div>
      <div class="thumb-under"><p><a href="/video-100xo195/prueba"
         title="Prueba de m&aacute;quina">Prueba</a></p>
        <p class="metadata"><span class="right">1.2M <span class="icon-f icf-eye"></span></span>
        6min</p></div>
    </div>
    """
    first = parse_xvideos_style(page, XVideosSite.XNXX, 24)[0]
    assert first.page_url == "https://www.xnxx.com/video-100xo195/prueba"
    assert first.title == "Prueba de máquina"
    assert first.duration == 6 * 60          # «6min» suelto en los metadatos
    assert first.views == 1_200_000          # «1.2M» antes del icono del ojo


def test_xvideos_con_enlace_ofuscado() -> None:
    # Desde julio de 2026 parte de las sesiones reciben `/search-video/<blob>` en lugar de
    # `/video.ID/slug`. El bloque conserva `data-eid`.
    page = """
    <div id="video_optvacm03b5" data-id="90217159" data-eid="optvacm03b5"
         class="frame-block thumb-block">
      <div class="thumb"><a href="/search-video/eAE9Ue1q3EAMfJWyv4Uja_Q==/e045c0e3">
        <img data-src="https://thumb.example/of.jpg" /></a></div>
      <div class="thumb-under"><p class="title">
        <a href="/search-video/eAE9Ue1q3EAMfJWyv4Uja_Q==/e045c0e3"
           title="La cachonda experimenta su primera vez">Título</a></p>
        <p class="metadata"><span class="duration">32 min</span>
        <span><a href="/profiles/quien"><span class="name">Quien Sea</span></a></span></p>
      </div>
    </div>
    """
    first = parse_xvideos_style(page, XVideosSite.XVIDEOS, 24)[0]
    assert first.page_url == \
        "https://www.xvideos.com/video.optvacm03b5/la_cachonda_experimenta_su_primera_vez"
    assert first.title == "La cachonda experimenta su primera vez"
    assert first.duration == 32 * 60
    assert first.id == "90217159"


def test_slug_limpio() -> None:
    assert slugify("Paseo por la playa & montaña") == "paseo_por_la_playa_montana"
    assert slugify("¡¿...!!") == "video"            # sin nada aprovechable
    assert slugify("recorte.78C2-DE83.MOV") == "recorte_78c2_de83_mov"


def test_pagina_vacia() -> None:
    assert parse_xvideos_style("<html>nada</html>", XVideosSite.XVIDEOS, 24) == []


def test_respeta_el_limite() -> None:
    assert len(parse_xvideos_style(XVIDEOS_HTML, XVideosSite.XVIDEOS, 1)) == 1


def test_paginacion_xvideos_y_xnxx() -> None:
    assert XVideosSite.XVIDEOS.paged_url("a b", 1) == "https://www.xvideos.com/?k=a%20b"
    assert XVideosSite.XVIDEOS.paged_url("a", 3) == "https://www.xvideos.com/?k=a&p=2"
    assert XVideosSite.XNXX.paged_url("a", 2) == "https://www.xnxx.com/search/a/1"


def test_pornhub() -> None:
    page = """
    <li data-block-position="1" data-video-id="475426235">
      <a class="js-pop" href="/view_video.php?viewkey=68e2bb7570170" data-video-id="475426235"
         data-poster="https://pix.example/poster.jpg"
         alt="Un t&iacute;tulo cualquiera"></a>
      <div class="duration thumbOverlay"><span class="bgEffect time">10:30</span></div>
      <a class="uploaderLink" href="/model/alguien">Alguien</a>
    </li>
    """
    first = parse_pornhub(page, 24)[0]
    assert first.title == "Un título cualquiera"
    assert first.page_url == "https://www.pornhub.com/view_video.php?viewkey=68e2bb7570170"
    assert first.duration == 10 * 60 + 30
    assert first.uploader == "Alguien"


def test_youporn() -> None:
    page = """
    <div data-video-id="223611391" data-uploader-name="Quien Sea"
         aria-label="Detr&aacute;s de las c&aacute;maras">
      <a href="/watch/223611391/" class="video-box-image">
        <img class="thumb-image" data-src="https://pix.example/yp.jpg" />
      </a>
      <div class="video-properties">
        <div class="video-duration tm_video_duration"><span>
        01:46
        </span></div>
      </div>
    </div>
    """
    first = parse_youporn(page, 24)[0]
    assert first.title == "Detrás de las cámaras"
    assert first.page_url == "https://www.youporn.com/watch/223611391/"
    assert first.uploader == "Quien Sea"
    assert first.duration == 106


def test_xhamster() -> None:
    page = r"""
    <script>window.initials={"searchResult":{"videoThumbProps":[
      {"id":28952176,"title":"Un título","pageURL":"https://xhamster.com/videos/uno-abc",
       "duration":612,"thumbURL":"https://ic.example/uno.webp","views":3088683,
       "landing":{"type":"channel","name":"Un canal"}}
    ]},"otraCosa":{"anidado":{"llaves":"}"}}};</script>
    """
    first = parse_xhamster(page, 24)[0]
    assert first.title == "Un título"
    assert first.page_url == "https://xhamster.com/videos/uno-abc"
    assert first.duration == 612
    assert first.uploader == "Un canal"
    assert first.views == 3_088_683
    assert first.id == "28952176"


def test_xhamster_cambiado() -> None:
    # Si cambia el formato, se avisa en vez de devolver vacío en silencio.
    with pytest.raises(SearchError):
        parse_xhamster("<html>sin datos</html>", 24)


def test_json_balanceado() -> None:
    text = 'basura window.initials={"a":{"b":"}"},"c":1}; más basura'
    assert extract_balanced_json(text, "window.initials") == '{"a":{"b":"}"},"c":1}'


def test_reddit() -> None:
    def context(post_id: str, title: str) -> str:
        return ("{&quot;action_info&quot;:{&quot;type&quot;:&quot;post&quot;},&quot;post&quot;:"
                f"{{&quot;id&quot;:&quot;{post_id}&quot;,&quot;nsfw&quot;:false,&quot;title&quot;:"
                f"&quot;{title}&quot;}},&quot;subreddit&quot;:{{&quot;name&quot;:&quot;cats&quot;}}}}")

    page = f"""
    <search-telemetry-tracker data-faceplate-tracking-context="{context("t3_abc", "Gato &amp; perro")}">
      <a href="/r/cats/comments/abc/gato_perro/">
      <shreddit-player src="https://packaged-media.redd.it/x.mp4"
        packaged-media-json="{{&quot;playbackMp4s&quot;:{{&quot;duration&quot;:41,&quot;permutations&quot;:[]}}}}"
        poster="https://external-preview.redd.it/p.png?format=pjpg&amp;s=1"></shreddit-player></a>
    </search-telemetry-tracker>
    <search-telemetry-tracker data-faceplate-tracking-context="{context("t3_img", "Sólo una foto")}">
      <a href="/r/cats/comments/img/foto/"><img src="https://preview.redd.it/f.jpg"></a>
    </search-telemetry-tracker>
    <faceplate-partial src="/svc/shreddit/search/?q=gatos&amp;type=media&amp;cursor=eyJhIjoxfQ%3D%3D">
    """
    results, cursor = parse_reddit(page)
    assert len(results) == 1          # la foto se descarta
    video = results[0]
    assert video.id == "t3_abc"
    assert video.title == "Gato & perro"
    assert video.page_url == "https://www.reddit.com/r/cats/comments/abc/gato_perro/"
    assert video.thumbnail_url == "https://external-preview.redd.it/p.png?format=pjpg&s=1"
    assert video.duration == 41
    assert video.uploader == "r/cats"
    assert cursor == "eyJhIjoxfQ%3D%3D"


def test_tnaflix() -> None:
    page = """
    <div data-vid="7233056" data-num="59" class="col-xs-6">
      <a class="thumb" href="https://www.tnaflix.com/solo-porn/Un-Titulo/video7233056">
        <img class="lazyload" src="/placeholder.jpg" data-src="https://img.tnaflix.com/a/10.jpg" alt="Un título" />
        <div class="thumb-icon video-duration">12:02</div></a>
      <a href="https://www.tnaflix.com/solo-porn/Un-Titulo/video7233056" class="video-title text-break">
          Un t&iacute;tulo       </a>
      <div class="d-flex">
        <a href="https://www.tnaflix.com/profile/alguien" class="me-2 badge">
            alguien     </a>
        <div class="me-2"><i class="icon-eye"></i>8.4K   </div>
      </div>
    </div>
    """
    video = parse_tnaflix(page, 24)[0]
    assert video.id == "7233056"
    assert video.title == "Un título"
    assert video.page_url == "https://www.tnaflix.com/solo-porn/Un-Titulo/video7233056"
    assert video.thumbnail_url == "https://img.tnaflix.com/a/10.jpg"
    assert video.duration == 722
    assert video.uploader == "alguien"
    assert video.views == 8400


def test_porntrex() -> None:
    page = ('<div class="video-preview-screen video-item thumb-item  " data-item-id="3062828">'
            '<a href="https://www.porntrex.com/video/3062828/un-video"  class="thumb rotator-screen" >'
            '<img class="cover lazyload"data-src="//ptx.cdntrex.com/shots/1.jpg?v=3"    alt="Un vídeo" />'
            '</a><div class="viewsthumb">12 118 views</div><div class="durations">'
            '<i class="fa fa-clock-o"></i> 30:25</div><p class="inf">'
            '<a href="https://www.porntrex.com/video/3062828/un-video" title="Un v&iacute;deo" >'
            'Un vídeo</a></p></div>')
    video = parse_porntrex(page, 24)[0]
    assert video.id == "3062828"
    assert video.title == "Un vídeo"
    assert video.page_url == "https://www.porntrex.com/video/3062828/un-video"
    assert video.thumbnail_url == "https://ptx.cdntrex.com/shots/1.jpg?v=3"
    assert video.duration == 30 * 60 + 25
    assert video.views == 12_118


def test_youjizz() -> None:
    page = """
    <div class="video-thumb" data-videoId="2171023">
      <div class="frame-wrapper"><a data-video-id="2171023" class="frame video" href="/videos/music-lessons-2171023.html">
        <img class="img-responsive lazy" src="spacer.gif" data-original="//cdne-pics.youjizz.com/b/f.jpg" alt="" /></a></div>
      <div class="video-title">
        <a href='/videos/music-lessons-2171023.html' class="">Music lessons</a>
      </div>
      <span class="time"><i class="fa fa-clock-o"></i>&nbsp;25:02</span>
      <span class="views"><i class="fa fa-eye"></i>&nbsp;<span class="format-views">2395120</span></span>
    </div>
    """
    video = parse_youjizz(page, 24)[0]
    assert video.id == "2171023"
    assert video.title == "Music lessons"
    assert video.page_url == "https://www.youjizz.com/videos/music-lessons-2171023.html"
    assert video.thumbnail_url == "https://cdne-pics.youjizz.com/b/f.jpg"
    assert video.duration == 25 * 60 + 2
    assert video.views == 2_395_120


def test_thisvid() -> None:
    page = """
    <a href="https://thisvid.com/videos/">Todos los vídeos</a>
    <a href="https://thisvid.com/videos/publico/" title="Vídeo p&uacute;blico" class="tumbpu">
      <span class="thumb " ><img class="lazy-load" data-original="//static.thisvid.com/s/1.jpg" />
        <span class="duration">2:20</span>
        <span class="info"><span class="view"><i class="ico-view"></i>1204</span></span></span>
      <span class="title">Vídeo público</span></a>
    <a href="https://thisvid.com/videos/privado/" title="Privado" class="tumbpu">
      <span class="thumb private" style="background: url(//static.thisvid.com/s/2.jpg)">
        <span class="duration">1:00</span></span></a>
    """
    results = parse_thisvid(page, 24)
    assert len(results) == 1
    video = results[0]
    assert video.id == "publico"
    assert video.title == "Vídeo público"
    assert video.page_url == "https://thisvid.com/videos/publico/"
    assert video.thumbnail_url == "https://static.thisvid.com/s/1.jpg"
    assert video.duration == 140
    assert video.views == 1204


def test_resultados_de_ytdlp() -> None:
    root = {"entries": [
        {"id": "a", "title": "Uno", "url": "https://www.youtube.com/watch?v=a", "duration": 61,
         "channel": "Canal", "view_count": 1500,
         "thumbnails": [{"url": "https://i/peq.jpg"}, {"url": "https://i/grande.jpg"}]},
        # SoundCloud: la página buena es webpage_url, no url (la API).
        {"id": "b", "title": "Dos", "url": "https://api.soundcloud.com/x",
         "webpage_url": "https://soundcloud.com/x"},
        {"title": "sin id"},
    ]}
    results = parse_ytdlp_entries(root)
    assert [r.id for r in results] == ["a", "b"]
    assert results[0].thumbnail_url == "https://i/grande.jpg"
    assert results[0].uploader == "Canal" and results[0].views == 1500
    assert results[1].page_url == "https://soundcloud.com/x"
    # La página 2 descarta las anteriores.
    assert [r.id for r in parse_ytdlp_entries(root, skip=1)] == ["b"]
