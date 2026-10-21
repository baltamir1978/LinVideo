"""Buscador integrado: YouTube, SoundCloud y unas veinte webs más.

Las fuentes que leen HTML «a mano» (`SearchSource.is_scraped`) se romperán cuando la web
cambie su maquetación. Cada una tiene su función de lectura, separada de la petición de
red, para poder probarla con una página guardada (tests/test_search_parsing.py).

**La consola y la interfaz llaman a la misma función** para buscar en varias webs
(`search_many`). En AppVideo estaban duplicadas y se desincronizaron: la interfaz devolvía
cero resultados en todas las webs menos YouTube, sin que ninguna constara como fallida.
"""

import html as html_lib
import json
import re
import subprocess
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from . import formatters, tools
from .models import MediaKind

# El mismo de AppVideo, aunque esto sea Linux: las webs sirven maquetaciones distintas
# según el navegador, y los lectores se escribieron para la que reciben con este. Con el
# de Firefox en Linux, Pornhub manda otra página y no se lee nada (comprobado el 21-oct-2026).
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
TIMEOUT = 20


# --- Modelo ----------------------------------------------------------------------------


class SearchCategory(Enum):
    VIDEO = "video"
    AUDIO = "audio"
    ADULT = "adult"

    @property
    def title(self) -> str:
        return {SearchCategory.VIDEO: "Vídeo", SearchCategory.AUDIO: "Audio",
                SearchCategory.ADULT: "Para adultos"}[self]


class SearchSource(Enum):
    # Vídeo
    YOUTUBE = "youtube"
    DAILYMOTION = "dailymotion"
    PEERTUBE = "peertube"
    ARCHIVE = "archive"
    REDDIT = "reddit"
    # Audio
    SOUNDCLOUD = "soundcloud"
    MIXCLOUD = "mixcloud"
    # Para adultos
    XVIDEOS = "xvideos"
    XNXX = "xnxx"
    XHAMSTER = "xhamster"
    PORNHUB = "pornhub"
    REDTUBE = "redtube"
    YOUPORN = "youporn"
    EPORNER = "eporner"
    REDGIFS = "redgifs"
    TNAFLIX = "tnaflix"
    PORNTREX = "porntrex"
    YOUJIZZ = "youjizz"
    THISVID = "thisvid"

    @property
    def title(self) -> str:
        return _TITLES[self]

    @property
    def category(self) -> SearchCategory:
        if self in (SearchSource.YOUTUBE, SearchSource.DAILYMOTION, SearchSource.PEERTUBE,
                    SearchSource.ARCHIVE, SearchSource.REDDIT):
            return SearchCategory.VIDEO
        if self in (SearchSource.SOUNDCLOUD, SearchSource.MIXCLOUD):
            return SearchCategory.AUDIO
        return SearchCategory.ADULT

    @staticmethod
    def in_category(category: SearchCategory) -> list["SearchSource"]:
        return [s for s in SearchSource if s.category is category]

    @property
    def preferred_kind(self) -> MediaKind:
        """El formato que tiene más sentido al descargar desde esta fuente."""
        if self in (SearchSource.SOUNDCLOUD, SearchSource.MIXCLOUD):
            return MediaKind.AUDIO_MP3
        if self is SearchSource.REDGIFS:
            return MediaKind.GIF
        return MediaKind.VIDEO_MAX

    @property
    def hint(self) -> str:
        """Texto de ayuda que se muestra antes de la primera búsqueda."""
        hints = {
            SearchSource.YOUTUBE: "Escribe lo que quieras encontrar. Los resultados se pueden "
                                  "descargar como vídeo o como MP3.",
            SearchSource.DAILYMOTION: "Buscador oficial de Dailymotion.",
            SearchSource.PEERTUBE: "Red descentralizada de servidores PeerTube, a través del "
                                   "buscador Sepia.",
            SearchSource.ARCHIVE: "Fondo público de Archive.org: películas, conciertos y "
                                  "grabaciones de dominio público.",
            SearchSource.REDDIT: "Vídeos subidos a Reddit. Sólo se muestran las publicaciones "
                                 "con vídeo, no las de imagen o texto.",
            SearchSource.SOUNDCLOUD: "Pistas y mezclas de SoundCloud. Lo habitual aquí es "
                                     "descargar en MP3.",
            SearchSource.MIXCLOUD: "Sesiones y programas de Mixcloud. Lo habitual aquí es "
                                   "descargar en MP3.",
            SearchSource.REDGIFS: "Búsqueda por etiquetas en RedGifs. «GIF» convierte el clip; "
                                  "«Vídeo» guarda el MP4 original.",
            SearchSource.THISVID: "Se consulta el buscador de ThisVid. Los vídeos privados se "
                                  "omiten porque no se pueden descargar.",
        }
        return hints.get(self, f"Se consulta el buscador de {self.title} y se muestran los "
                               "vídeos encontrados.")

    @property
    def is_scraped(self) -> bool:
        """Fuentes que leen la web «a mano» y pueden romperse si el sitio cambia."""
        return self in (SearchSource.XVIDEOS, SearchSource.XNXX, SearchSource.XHAMSTER,
                        SearchSource.PORNHUB, SearchSource.YOUPORN, SearchSource.REDDIT,
                        SearchSource.TNAFLIX, SearchSource.PORNTREX, SearchSource.YOUJIZZ,
                        SearchSource.THISVID)


_TITLES = {
    SearchSource.YOUTUBE: "YouTube", SearchSource.DAILYMOTION: "Dailymotion",
    SearchSource.PEERTUBE: "PeerTube", SearchSource.ARCHIVE: "Archive.org",
    SearchSource.REDDIT: "Reddit", SearchSource.SOUNDCLOUD: "SoundCloud",
    SearchSource.MIXCLOUD: "Mixcloud", SearchSource.XVIDEOS: "XVideos",
    SearchSource.XNXX: "XNXX", SearchSource.XHAMSTER: "xHamster",
    SearchSource.PORNHUB: "Pornhub", SearchSource.REDTUBE: "RedTube",
    SearchSource.YOUPORN: "YouPorn", SearchSource.EPORNER: "Eporner",
    SearchSource.REDGIFS: "RedGifs", SearchSource.TNAFLIX: "TNAFlix",
    SearchSource.PORNTREX: "PornTrex", SearchSource.YOUJIZZ: "YouJizz",
    SearchSource.THISVID: "ThisVid",
}


@dataclass(frozen=True)
class SearchScope:
    """Una web, una categoría o todas."""

    source: SearchSource | None = None
    category: SearchCategory | None = None

    @staticmethod
    def everywhere() -> "SearchScope":
        return SearchScope()

    @staticmethod
    def parse(text: str) -> "SearchScope | None":
        text = text.lower()
        if text in ("all", "todas"):
            return SearchScope.everywhere()
        try:
            return SearchScope(category=SearchCategory(text))
        except ValueError:
            pass
        try:
            return SearchScope(source=SearchSource(text))
        except ValueError:
            return None

    @property
    def sources(self) -> list[SearchSource]:
        if self.source is not None:
            return [self.source]
        if self.category is not None:
            return SearchSource.in_category(self.category)
        return list(SearchSource)

    @property
    def is_multi(self) -> bool:
        return self.source is None

    @property
    def title(self) -> str:
        if self.source is not None:
            return self.source.title
        if self.category is not None:
            return self.category.title
        return "Todas las webs"

    @property
    def preferred_kind(self) -> MediaKind:
        kinds = {s.preferred_kind for s in self.sources}
        return kinds.pop() if len(kinds) == 1 else MediaKind.VIDEO_MAX


@dataclass(frozen=True)
class SearchResult:
    id: str
    title: str
    page_url: str
    thumbnail_url: str | None = None
    duration: float | None = None
    uploader: str | None = None
    views: int | None = None
    # Se rellena al devolver los resultados; importa cuando se busca en varias webs.
    source: SearchSource = SearchSource.YOUTUBE

    @property
    def duration_text(self) -> str | None:
        if not self.duration or self.duration <= 0:
            return None
        return formatters.duration(self.duration)

    @property
    def views_text(self) -> str | None:
        if not self.views or self.views <= 0:
            return None
        if self.views >= 1_000_000:
            return f"{self.views / 1_000_000:.1f}M visitas".replace(".", ",")
        if self.views >= 1_000:
            return f"{self.views // 1_000}K visitas"
        return f"{self.views} visitas"


class SearchError(Exception):
    pass


# --- Búsqueda -----------------------------------------------------------------------------


def search(query: str, source: SearchSource, limit: int = 24, page: int = 1) -> list[SearchResult]:
    query = query.strip()
    if not query:
        return []
    page = max(1, page)
    finder = _FINDERS[source]
    return [replace(r, source=source) for r in finder(query, limit, page)]


@dataclass
class FederatedResults:
    results: list[SearchResult] = field(default_factory=list)
    # Fuentes que fallaron, con su motivo, para avisar sin bloquear el resto.
    failures: list[tuple[SearchSource, str]] = field(default_factory=list)


def search_many(query: str, sources: list[SearchSource], limit_per_source: int = 10,
                page: int = 1,
                on_partial: Callable[[FederatedResults, int], None] | None = None
                ) -> FederatedResults:
    """Busca en varias webs a la vez y mezcla los resultados por rondas, para que ninguna
    web acapare el principio de la lista.

    `on_partial(resultados_hasta_ahora, webs_que_faltan)` se llama cada vez que contesta
    una, para que la interfaz enseñe lo que va llegando. La consola no lo usa, pero el
    reparto y la mezcla son los mismos para las dos.
    """
    query = query.strip()
    if not query or not sources:
        return FederatedResults()

    per_source: dict[SearchSource, list[SearchResult]] = {}
    failures: list[tuple[SearchSource, str]] = []

    def snapshot() -> FederatedResults:
        return FederatedResults(
            results=interleave(per_source, sources),
            failures=sorted(failures, key=lambda f: f[0].title))

    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        # La fuente va en el diccionario del futuro, no en lo que devuelve la tarea: así
        # no hay forma de archivar unos resultados bajo la web equivocada.
        futures = {pool.submit(search, query, s, limit_per_source, page): s for s in sources}
        remaining = len(futures)
        for future in as_completed(futures):
            source = futures[future]
            try:
                per_source[source] = future.result()
            except Exception as error:      # cualquier fallo de una web, sin tirar el resto
                failures.append((source, describe(error)))
            remaining -= 1
            if on_partial:
                on_partial(snapshot(), remaining)
    return snapshot()


def interleave(per_source: dict[SearchSource, list[SearchResult]],
               order: list[SearchSource]) -> list[SearchResult]:
    """Uno de cada web, luego el segundo de cada una…, respetando el orden pedido."""
    deepest = max((len(v) for v in per_source.values()), default=0)
    mixed: list[SearchResult] = []
    for index in range(deepest):
        for source in order:
            found = per_source.get(source, [])
            if index < len(found):
                mixed.append(found[index])
    return mixed


def describe(error: BaseException) -> str:
    if isinstance(error, SearchError):
        return str(error)
    if isinstance(error, urllib.error.HTTPError):
        return f"Fallo de red: el servidor respondió {error.code}"
    if isinstance(error, (urllib.error.URLError, OSError)):
        return f"Fallo de red: {getattr(error, 'reason', error)}"
    return f"No se pudieron leer los resultados: {error}"


# --- Red --------------------------------------------------------------------------------


def _quote(text: str) -> str:
    return urllib.parse.quote(text, safe="")


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw: bytes = response.read()
    return raw.decode("utf-8", errors="replace")


def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    try:
        return json.loads(fetch_text(url, headers))
    except ValueError as error:
        raise SearchError("No se pudieron leer los resultados: la respuesta no es JSON") from error


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


# --- YouTube y SoundCloud (a través de yt-dlp) ----------------------------------------


def _ytdlp_search(prefix: str, query: str, limit: int, page: int) -> list[SearchResult]:
    ytdlp = tools.ytdlp()
    if ytdlp is None:
        raise SearchError("No se encuentra yt-dlp para buscar.")
    # yt-dlp no admite desplazamiento: se piden todas las páginas hasta la actual y se
    # descartan las anteriores.
    wanted = limit * page
    argv = [*tools.command(ytdlp), "--ignore-config", "--no-warnings", "--flat-playlist",
            "-J", f"{prefix}{wanted}:{query}"]
    try:
        out = subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL,
                             env=tools.child_env(), timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise SearchError(f"Fallo de red: {error}") from error
    if out.returncode != 0 or not out.stdout:
        lines = out.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise SearchError(f"No se pudieron leer los resultados: "
                          f"{lines[-1] if lines else 'búsqueda sin resultados'}")
    try:
        root = json.loads(out.stdout)
    except ValueError as error:
        raise SearchError("respuesta inesperada de yt-dlp") from error
    return parse_ytdlp_entries(root, skip=limit * (page - 1))


def parse_ytdlp_entries(root: Any, skip: int = 0) -> list[SearchResult]:
    entries = root.get("entries") if isinstance(root, dict) else None
    if not isinstance(entries, list):
        raise SearchError("respuesta inesperada de yt-dlp")
    results = []
    for entry in entries[skip:]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        # En SoundCloud `url` apunta a la API; la página buena es `webpage_url`.
        page_url = _str(entry.get("webpage_url")) or _str(entry.get("url"))
        if not page_url:
            continue
        # La lista de miniaturas viene de menor a mayor calidad.
        thumbs = entry.get("thumbnails") or []
        thumb = _str(thumbs[-1].get("url")) if thumbs and isinstance(thumbs[-1], dict) else None
        results.append(SearchResult(
            id=entry["id"],
            title=_str(entry.get("title")) or "(sin título)",
            page_url=page_url,
            thumbnail_url=thumb,
            duration=_float(entry.get("duration")),
            uploader=_str(entry.get("uploader")) or _str(entry.get("channel")),
            views=_int(entry.get("view_count")),
        ))
    return results


# --- APIs abiertas -----------------------------------------------------------------------


def _dailymotion(query: str, limit: int, page: int) -> list[SearchResult]:
    data = fetch_json(
        f"https://api.dailymotion.com/videos?search={_quote(query)}&page={page}&limit={limit}"
        "&fields=id,title,duration,thumbnail_360_url,owner.screenname,views_total,url")
    items = data.get("list") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SearchError("respuesta inesperada de Dailymotion")
    return [SearchResult(
        id=v["id"], title=_str(v.get("title")) or "(sin título)", page_url=v["url"],
        thumbnail_url=_str(v.get("thumbnail_360_url")), duration=_float(v.get("duration")),
        uploader=_str(v.get("owner.screenname")), views=_int(v.get("views_total")),
    ) for v in items if isinstance(v, dict) and _str(v.get("id")) and _str(v.get("url"))]


def _peertube(query: str, limit: int, page: int) -> list[SearchResult]:
    data = fetch_json(f"https://search.joinpeertube.org/api/v1/search/videos?search="
                      f"{_quote(query)}&count={limit}&start={limit * (page - 1)}")
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SearchError("respuesta inesperada de PeerTube")
    results = []
    for v in items:
        if not isinstance(v, dict) or not _str(v.get("uuid")) or not _str(v.get("url")):
            continue
        account = _dict(v.get("account"))
        # thumbnailUrl es absoluta; thumbnailPath es relativa al servidor que la aloja.
        thumb = _str(v.get("thumbnailUrl"))
        if not thumb and _str(v.get("thumbnailPath")) and _str(account.get("host")):
            thumb = f"https://{account['host']}{v['thumbnailPath']}"
        name = _str(account.get("displayName"))
        results.append(SearchResult(
            id=v["uuid"], title=_str(v.get("name")) or "(sin título)", page_url=v["url"],
            thumbnail_url=thumb, duration=_float(v.get("duration")),
            uploader=name.strip() if name else None, views=_int(v.get("views"))))
    return results


def _mixcloud(query: str, limit: int, page: int) -> list[SearchResult]:
    data = fetch_json(f"https://api.mixcloud.com/search/?q={_quote(query)}&type=cloudcast"
                      f"&limit={limit}&offset={limit * (page - 1)}")
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SearchError("respuesta inesperada de Mixcloud")
    results = []
    for c in items:
        if not isinstance(c, dict) or not _str(c.get("url")):
            continue
        pictures = _dict(c.get("pictures"))
        user = _dict(c.get("user"))
        results.append(SearchResult(
            id=_str(c.get("key")) or c["url"], title=_str(c.get("name")) or "(sin título)",
            page_url=c["url"],
            thumbnail_url=(_str(pictures.get("large")) or _str(pictures.get("medium"))
                           or _str(pictures.get("thumbnail"))),
            duration=_float(c.get("audio_length")), uploader=_str(user.get("name")),
            views=_int(c.get("play_count"))))
    return results


def _archive(query: str, limit: int, page: int) -> list[SearchResult]:
    expression = f"{query} AND (mediatype:movies OR mediatype:audio)"
    data = fetch_json(
        f"https://archive.org/advancedsearch.php?q={_quote(expression)}"
        "&fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=creator&fl%5B%5D=downloads"
        f"&fl%5B%5D=runtime&sort%5B%5D=downloads+desc&rows={limit}&page={page}&output=json")
    docs = data.get("response", {}).get("docs") if isinstance(data, dict) else None
    if not isinstance(docs, list):
        raise SearchError("respuesta inesperada de Archive.org")

    def first(value: Any) -> str | None:
        # `creator` y `title` llegan a veces como cadena y a veces como lista.
        if isinstance(value, list):
            return _str(value[0]) if value else None
        return _str(value)

    results = []
    for doc in docs:
        identifier = _str(doc.get("identifier")) if isinstance(doc, dict) else None
        if not identifier:
            continue
        runtime = _str(doc.get("runtime"))
        results.append(SearchResult(
            id=identifier, title=first(doc.get("title")) or identifier,
            page_url=f"https://archive.org/details/{identifier}",
            thumbnail_url=f"https://archive.org/services/img/{identifier}",
            duration=parse_loose_duration(runtime) if runtime else None,
            uploader=first(doc.get("creator")), views=_int(doc.get("downloads"))))
    return results


def _redtube(query: str, limit: int, page: int) -> list[SearchResult]:
    data = fetch_json("https://api.redtube.com/?data=redtube.Videos.searchVideos"
                      f"&output=json&thumbsize=medium&page={page}&search={_quote(query)}")
    items = data.get("videos") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SearchError("respuesta inesperada de RedTube")
    results = []
    for wrapper in items[:limit]:
        # Cada elemento envuelve el vídeo en una clave "video".
        video = wrapper.get("video") if isinstance(wrapper, dict) else None
        if not isinstance(video, dict) or not _str(video.get("url")):
            continue
        views = video.get("views")
        duration = _str(video.get("duration"))
        results.append(SearchResult(
            id=str(video.get("video_id") or video["url"]),
            title=_str(video.get("title")) or "(sin título)", page_url=video["url"],
            thumbnail_url=_str(video.get("default_thumb")),
            duration=parse_loose_duration(duration) if duration else None,
            views=_int(views) if not isinstance(views, str) else parse_compact_number(views)))
    return results


def _eporner(query: str, limit: int, page: int) -> list[SearchResult]:
    data = fetch_json(f"https://www.eporner.com/api/v2/video/search/?query={_quote(query)}"
                      f"&per_page={limit}&page={page}&thumbsize=medium&order=top-weekly"
                      "&format=json")
    items = data.get("videos") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise SearchError("respuesta inesperada de Eporner")
    results = []
    for v in items:
        if not isinstance(v, dict) or not _str(v.get("id")) or not _str(v.get("url")):
            continue
        thumb = _dict(v.get("default_thumb"))
        results.append(SearchResult(
            id=v["id"], title=_str(v.get("title")) or "(sin título)", page_url=v["url"],
            thumbnail_url=_str(thumb.get("src")), duration=_float(v.get("length_sec")),
            views=_int(v.get("views"))))
    return results


def _redgifs(query: str, limit: int, page: int) -> list[SearchResult]:
    # API pública con un token temporal que se pide en cada búsqueda.
    auth = fetch_json("https://api.redgifs.com/v2/auth/temporary")
    token = auth.get("token") if isinstance(auth, dict) else None
    if not isinstance(token, str):
        raise SearchError("RedGifs no devolvió un token")
    data = fetch_json(f"https://api.redgifs.com/v2/gifs/search?search_text={_quote(query)}"
                      f"&order=trending&count={limit}&page={page}",
                      headers={"Authorization": f"Bearer {token}"})
    gifs = data.get("gifs") if isinstance(data, dict) else None
    if not isinstance(gifs, list):
        raise SearchError("respuesta inesperada de RedGifs")
    results = []
    for g in gifs:
        if not isinstance(g, dict) or not _str(g.get("id")):
            continue
        urls = _dict(g.get("urls"))
        tags = [t for t in g.get("tags") or [] if isinstance(t, str)]
        results.append(SearchResult(
            id=g["id"], title=", ".join(tags) if tags else g["id"],
            page_url=f"https://www.redgifs.com/watch/{g['id']}",
            thumbnail_url=_str(urls.get("thumbnail")) or _str(urls.get("poster")),
            duration=_float(g.get("duration")), uploader=_str(g.get("userName")),
            views=_int(g.get("views"))))
    return results


# --- XVideos y XNXX (mismo grupo, misma maquetación) --------------------------------


class XVideosSite(Enum):
    XVIDEOS = "xvideos"
    XNXX = "xnxx"

    @property
    def base(self) -> str:
        return "https://www.xvideos.com" if self is XVideosSite.XVIDEOS else "https://www.xnxx.com"

    @property
    def display_name(self) -> str:
        return "XVideos" if self is XVideosSite.XVIDEOS else "XNXX"

    @property
    def link_pattern(self) -> str:
        """XVideos usa /video.ID/slug y XNXX /video-ID/slug."""
        return r'href="(/video\.[^"]+)"' if self is XVideosSite.XVIDEOS else r'href="(/video-[^"]+)"'

    def video_path(self, video_id: str, slug: str) -> str:
        """Ruta canónica del vídeo a partir del identificador corto (`data-eid`)."""
        sep = "." if self is XVideosSite.XVIDEOS else "-"
        return f"/video{sep}{video_id}/{slug}"

    def paged_url(self, query: str, page: int) -> str:
        """XVideos pagina con `&p=` y XNXX añadiendo `/N` a la ruta; los dos desde 0."""
        index = max(0, page - 1)
        if self is XVideosSite.XVIDEOS:
            return f"{self.base}/?k={_quote(query)}" + (f"&p={index}" if index else "")
        return f"{self.base}/search/{_quote(query)}" + (f"/{index}" if index else "")


def _xvideos_style(site: XVideosSite) -> Callable[[str, int, int], list[SearchResult]]:
    def finder(query: str, limit: int, page: int) -> list[SearchResult]:
        results = parse_xvideos_style(fetch_text(site.paged_url(query, page)), site, limit)
        if not results:
            raise SearchError(f"{site.display_name} no devolvió resultados legibles")
        return results
    return finder


def parse_xvideos_style(page: str, site: XVideosSite, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    # Cada resultado es un bloque que empieza por <div id="video_…">.
    for block in page.split('<div id="video_')[1:]:
        raw_title = first_match(block, r'title="([^"]*)"')
        if raw_title is None:
            continue
        title = decode_entities(raw_title)
        # Desde julio de 2026 XVideos sirve a parte de las sesiones un enlace ofuscado
        # (`/search-video/<blob>`) en vez de la ruta del vídeo. El identificador corto sigue
        # en `data-eid`, y con él se rehace la ruta: el sitio redirige al slug bueno sea
        # cual sea el que se pida.
        path = first_match(block, site.link_pattern)
        if path is None:
            eid = first_match(block, r'data-eid="([^"]+)"')
            if eid is None:
                continue
            path = site.video_path(eid, slugify(title))
        # XVideos marca la duración con <span class="duration">; XNXX la deja suelta
        # («6min») dentro del bloque de metadatos.
        span = first_match(block, r'<span class="duration">([^<]+)</span>')
        metadata = first_match(block, r'<p class="metadata">(.*?)</p>')
        duration = (parse_loose_duration(span) if span else None) \
            or (parse_loose_duration(metadata) if metadata else None)
        # Las visitas van justo antes del icono del ojo: «1.2M <span class="icon-f icf-eye">».
        views = first_match(block, r'([0-9][0-9.,]*[KMkm]?)\s*<span class="icon-f icf-eye"')
        uploader = first_match(block, r'<span class="name">([^<]+)</span>')
        results.append(SearchResult(
            id=first_match(block, r'data-id="([0-9]+)"') or path,
            title=title,
            page_url=site.base + path,
            thumbnail_url=first_match(block, r'data-src="([^"]+)"'),
            duration=duration,
            uploader=decode_entities(uploader) if uploader else None,
            views=parse_compact_number(views) if views else None))
        if len(results) >= limit:
            break
    return results


# --- Pornhub, xHamster y YouPorn -----------------------------------------------------


def _pornhub(query: str, limit: int, page: int) -> list[SearchResult]:
    results = parse_pornhub(fetch_text(
        f"https://www.pornhub.com/video/search?search={_quote(query)}&page={page}"), limit)
    if not results:
        raise SearchError("Pornhub no devolvió resultados legibles")
    return results


def parse_pornhub(page: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for block in page.split("<li data-block-position=")[1:]:
        path = first_match(block, r'href="(/view_video\.php\?viewkey=[^"]+)"')
        # El título viaja en el alt de la miniatura.
        raw_title = first_match(block, r'alt="([^"]{3,})"')
        if path is None or raw_title is None:
            continue
        duration = first_match(block, r'class="[^"]*\btime">([0-9:]+)<')
        uploader = first_match(block, r'class="uploaderLink"[^>]*>([^<]+)<')
        results.append(SearchResult(
            id=first_match(block, r'data-video-id="([0-9]+)"') or path,
            title=decode_entities(raw_title),
            page_url="https://www.pornhub.com" + path,
            thumbnail_url=(first_match(block, r'data-poster="([^"]+)"')
                           or first_match(block, r'data-path="([^"]+)"')),
            duration=parse_loose_duration(duration) if duration else None,
            uploader=decode_entities(uploader) if uploader else None))
        if len(results) >= limit:
            break
    return results


def _xhamster(query: str, limit: int, page: int) -> list[SearchResult]:
    slug = "-".join(w for w in re.split(r"[^0-9a-z]+", query.lower()) if w)
    if not slug:
        raise SearchError("consulta no válida")
    url = f"https://xhamster.com/search/{slug}" + (f"?page={page}" if page > 1 else "")
    return parse_xhamster(fetch_text(url), limit)


def parse_xhamster(page: str, limit: int) -> list[SearchResult]:
    """xHamster trae los resultados en un JSON incrustado en la página."""
    raw = extract_balanced_json(page, "window.initials")
    try:
        root = json.loads(raw) if raw else None
        thumbs = root["searchResult"]["videoThumbProps"] if isinstance(root, dict) else None
    except (ValueError, KeyError, TypeError):
        thumbs = None
    if not isinstance(thumbs, list):
        raise SearchError("xHamster cambió el formato de la página")
    results = []
    for t in thumbs[:limit]:
        if not isinstance(t, dict) or not _str(t.get("pageURL")):
            continue
        landing = _dict(t.get("landing"))
        results.append(SearchResult(
            id=str(t["id"]) if _int(t.get("id")) is not None else t["pageURL"],
            title=_str(t.get("title")) or "(sin título)", page_url=t["pageURL"],
            thumbnail_url=_str(t.get("thumbURL")), duration=_float(t.get("duration")),
            uploader=_str(landing.get("name")), views=_int(t.get("views"))))
    return results


def _youporn(query: str, limit: int, page: int) -> list[SearchResult]:
    results = parse_youporn(fetch_text(
        f"https://www.youporn.com/search/?query={_quote(query)}&page={page}"), limit)
    if not results:
        raise SearchError("YouPorn no devolvió resultados legibles")
    return results


def parse_youporn(page: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for block in page.split("data-video-id=")[1:]:
        path = first_match(block, r'href="(/watch/[^"]+)"')
        raw_title = first_match(block, r'aria-label="([^"]{3,})"')
        if path is None or raw_title is None:
            continue
        identifier = first_match(block, r'^"?([0-9]+)') or path
        if identifier in seen:
            continue
        seen.add(identifier)
        duration = (first_match(block, r"video-duration[^>]*>\s*<span>\s*([0-9:]+)")
                    or first_match(block, r'class="video-duration[^"]*"[^>]*>.{0,80}?'
                                          r"([0-9]{1,2}:[0-9]{2})"))
        uploader = first_match(block, r'data-uploader-name="([^"]+)"')
        results.append(SearchResult(
            id=identifier, title=decode_entities(raw_title),
            page_url="https://www.youporn.com" + path,
            thumbnail_url=first_match(block, r'data-src="(https://[^"]+\.(?:jpg|webp)[^"]*)"'),
            duration=parse_loose_duration(duration) if duration else None,
            uploader=decode_entities(uploader) if uploader else None))
        if len(results) >= limit:
            break
    return results


# --- Reddit (fragmento HTML del buscador) --------------------------------------------


def _reddit(query: str, limit: int, page: int) -> list[SearchResult]:
    """La API JSON de Reddit responde 403 sin sesión (septiembre de 2026), pero el fragmento
    que pinta la pestaña «Multimedia» del buscador sí se sirve. Con `site:v.redd.it` todas
    las publicaciones son vídeo (sin él, dos de cada siete). Pagina con un cursor opaco, así
    que se siguen cursores desde el principio hasta juntar la página pedida."""
    base = (f"https://www.reddit.com/svc/shreddit/search/?q={_quote(query + ' site:v.redd.it')}"
            "&type=media")
    wanted = limit * page
    collected: list[SearchResult] = []
    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(5 * page):
        found, cursor_next = parse_reddit(fetch_text(base + (f"&cursor={cursor}" if cursor else "")))
        for result in found:
            if result.id not in seen:
                seen.add(result.id)
                collected.append(result)
        if len(collected) >= wanted or not cursor_next:
            break
        cursor = cursor_next
    return collected[limit * (page - 1):][:limit]


def parse_reddit(page: str) -> tuple[list[SearchResult], str | None]:
    """Los vídeos de la página y el cursor de la siguiente, si la hay. Las publicaciones de
    imagen se descartan: no se pueden descargar como vídeo."""
    results: list[SearchResult] = []
    for block in page.split("<search-telemetry-tracker")[1:]:
        if "<shreddit-player" not in block:
            continue
        path = first_match(block, r'href="(/r/[^"]+/comments/[^"]+)"')
        raw_context = first_match(block, r'data-faceplate-tracking-context="([^"]+)"')
        if path is None or raw_context is None:
            continue
        try:
            context = json.loads(decode_entities(raw_context))
            post = context["post"]
            post_id = post["id"]
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(post_id, str):
            continue
        subreddit = context.get("subreddit", {}).get("name") if isinstance(context, dict) else None
        poster = first_match(block, r'poster="([^"]+)"')
        duration = first_match(block, r"&quot;duration&quot;:([0-9.]+)")
        results.append(SearchResult(
            id=post_id, title=_str(post.get("title")) or "(sin título)",
            page_url="https://www.reddit.com" + path,
            thumbnail_url=decode_entities(poster) if poster else None,
            duration=float(duration) if duration else None,
            uploader=f"r/{subreddit}" if isinstance(subreddit, str) else None))
    cursor = first_match(page, r'svc/shreddit/search/\?[^"]*?cursor=([^"&]+)')
    return results, cursor


# --- TNAFlix, PornTrex, YouJizz y ThisVid ---------------------------------------------


def _html_search(source: SearchSource) -> Callable[[str, int, int], list[SearchResult]]:
    def finder(query: str, limit: int, page: int) -> list[SearchResult]:
        # Las que llevan la búsqueda en la ruta quieren las palabras unidas por guiones.
        words = [_quote(w) for w in query.lower().split()]
        if not words:
            raise SearchError("consulta no válida")
        slug = "-".join(words)
        plus = urllib.parse.quote_plus(query)
        match source:
            case SearchSource.TNAFLIX:
                url = f"https://www.tnaflix.com/search?what={plus}" + (f"&page={page}" if page > 1 else "")
                parser = parse_tnaflix
            case SearchSource.PORNTREX:
                url = f"https://www.porntrex.com/search/{slug}/" + (f"{page}/" if page > 1 else "")
                parser = parse_porntrex
            case SearchSource.YOUJIZZ:
                url = f"https://www.youjizz.com/search/{slug}-{page}.html"
                parser = parse_youjizz
            case _:
                url = "https://thisvid.com/search/" + (f"{page}/" if page > 1 else "") + f"?q={plus}"
                parser = parse_thisvid
        results = parser(fetch_text(url), limit)
        if not results:
            raise SearchError(f"{source.title} no devolvió resultados legibles")
        return results
    return finder


def parse_tnaflix(page: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for block in page.split('<div data-vid="')[1:]:
        video_id = first_match(block, r'^([0-9]+)"')
        page_url = first_match(block, r'href="(https://www\.tnaflix\.com/[^"]+/video[0-9]+)"')
        raw_title = first_match(block, r'class="video-title[^"]*">\s*([^<]+?)\s*<')
        if not (video_id and page_url and raw_title):
            continue
        thumb = first_match(block, r'data-src="([^"]+)"')
        duration = first_match(block, r'video-duration">([0-9:]+)<')
        uploader = first_match(block, r'/profile/[^"]+"[^>]*>\s*([^<]+?)\s*<')
        views = first_match(block, r'icon-eye"></i>([0-9.,]+[KMkm]?)')
        results.append(SearchResult(
            id=video_id, title=decode_entities(raw_title), page_url=page_url,
            thumbnail_url=absolute_url(thumb) if thumb else None,
            duration=parse_loose_duration(duration) if duration else None,
            uploader=decode_entities(uploader) if uploader else None,
            views=parse_compact_number(views) if views else None))
        if len(results) >= limit:
            break
    return results


def parse_porntrex(page: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for block in page.split('data-item-id="')[1:]:
        video_id = first_match(block, r'^([0-9]+)"')
        page_url = first_match(block, r'href="(https://www\.porntrex\.com/video/[0-9]+/[^"]+)"')
        raw_title = (first_match(block, r'class="inf"><a [^>]*title="([^"]+)"')
                     or first_match(block, r'alt="([^"]+)"'))
        if not (video_id and page_url and raw_title):
            continue
        # «12 118 views»: el separador de miles es un espacio.
        views = first_match(block, r'viewsthumb">([0-9 .,]+) views')
        thumb = first_match(block, r'data-src="([^"]+)"')
        duration = first_match(block, r'durations">.*?([0-9]+:[0-9:]+)')
        results.append(SearchResult(
            id=video_id, title=decode_entities(raw_title), page_url=page_url,
            thumbnail_url=absolute_url(thumb) if thumb else None,
            duration=parse_loose_duration(duration) if duration else None,
            views=parse_compact_number(views.replace(" ", "")) if views else None))
        if len(results) >= limit:
            break
    return results


def parse_youjizz(page: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for block in page.split('<div class="video-thumb" data-videoId="')[1:]:
        # YouJizz mezcla comillas simples y dobles en los enlaces.
        video_id = first_match(block, r'^([0-9]+)"')
        path = first_match(block, r"""href=["'](/videos/[^"']+\.html)["']""")
        raw_title = first_match(block, r'class="video-title">\s*<a [^>]*>([^<]+)</a>')
        if not (video_id and path and raw_title):
            continue
        thumb = first_match(block, r'data-original="([^"]+)"')
        duration = first_match(block, r'class="time">.*?([0-9]+:[0-9:]+)')
        views = first_match(block, r'format-views">([0-9]+)<')
        results.append(SearchResult(
            id=video_id, title=decode_entities(raw_title).strip(),
            page_url="https://www.youjizz.com" + path,
            thumbnail_url=absolute_url(thumb) if thumb else None,
            duration=parse_loose_duration(duration) if duration else None,
            views=int(views) if views else None))
        if len(results) >= limit:
            break
    return results


def parse_thisvid(page: str, limit: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for block in page.split('<a href="https://thisvid.com/videos/')[1:]:
        # Sólo las tarjetas de resultado, y sin los vídeos privados, que piden amistad con
        # quien los subió y yt-dlp no puede bajar.
        tag = block.split(">", 1)[0]
        if "tumbpu" not in tag or "thumb private" in block:
            continue
        slug = first_match(block, r'^([^"/]+)/?"')
        raw_title = first_match(block, r'title="([^"]+)"')
        if not (slug and raw_title):
            continue
        thumb = first_match(block, r'data-original="([^"]+)"')
        duration = first_match(block, r'class="duration">([0-9:]+)<')
        views = first_match(block, r'ico-view"></i>([0-9]+)')
        results.append(SearchResult(
            id=slug, title=decode_entities(raw_title),
            page_url=f"https://thisvid.com/videos/{slug}/",
            thumbnail_url=absolute_url(thumb) if thumb else None,
            duration=parse_loose_duration(duration) if duration else None,
            views=int(views) if views else None))
        if len(results) >= limit:
            break
    return results


_FINDERS: dict[SearchSource, Callable[[str, int, int], list[SearchResult]]] = {
    SearchSource.YOUTUBE: lambda q, l, p: _ytdlp_search("ytsearch", q, l, p),
    SearchSource.SOUNDCLOUD: lambda q, l, p: _ytdlp_search("scsearch", q, l, p),
    SearchSource.DAILYMOTION: _dailymotion,
    SearchSource.PEERTUBE: _peertube,
    SearchSource.ARCHIVE: _archive,
    SearchSource.MIXCLOUD: _mixcloud,
    SearchSource.REDDIT: _reddit,
    SearchSource.XVIDEOS: _xvideos_style(XVideosSite.XVIDEOS),
    SearchSource.XNXX: _xvideos_style(XVideosSite.XNXX),
    SearchSource.XHAMSTER: _xhamster,
    SearchSource.PORNHUB: _pornhub,
    SearchSource.REDTUBE: _redtube,
    SearchSource.YOUPORN: _youporn,
    SearchSource.EPORNER: _eporner,
    SearchSource.REDGIFS: _redgifs,
    SearchSource.TNAFLIX: _html_search(SearchSource.TNAFLIX),
    SearchSource.PORNTREX: _html_search(SearchSource.PORNTREX),
    SearchSource.YOUJIZZ: _html_search(SearchSource.YOUJIZZ),
    SearchSource.THISVID: _html_search(SearchSource.THISVID),
}


# --- Utilidades de texto -------------------------------------------------------------


def first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.S)
    return match.group(1) if match else None


def absolute_url(text: str) -> str:
    """Las miniaturas llegan a veces sin esquema («//cdn…»)."""
    decoded = decode_entities(text)
    return "https:" + decoded if decoded.startswith("//") else decoded


def slugify(text: str) -> str:
    """Un título como parte legible de la URL. Sólo se usa al rehacer un enlace: el sitio
    redirige al slug real, así que basta con que salga algo válido y no vacío."""
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text)
                    if not unicodedata.combining(ch))
    words = re.findall(r"[A-Za-z0-9]+", plain)
    slug = "_".join(words)[:60].lower().rstrip("_")
    return slug or "video"


def extract_balanced_json(text: str, marker: str) -> str | None:
    """El primer objeto JSON completo que sigue a un marcador, contando llaves."""
    position = text.find(marker)
    if position < 0:
        return None
    start = text.find("{", position + len(marker))
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def parse_compact_number(text: str) -> int | None:
    """«1.2M», «340K» o «5.320» como número de visitas."""
    trimmed = text.strip()
    if not trimmed:
        return None
    multiplier = {"M": 1_000_000, "m": 1_000_000, "K": 1_000, "k": 1_000}.get(trimmed[-1], 1)
    if multiplier == 1:
        # Sin multiplicador, el punto y la coma separan miles.
        digits = trimmed.replace(".", "").replace(",", "")
    else:
        # Con multiplicador, son decimales («1.2M», «1,2M»).
        digits = trimmed[:-1].replace(",", ".")
    try:
        return int(float(digits) * multiplier)
    except ValueError:
        return None


def parse_loose_duration(text: str) -> float | None:
    """«32 min», «1 h 5 min», «12 sec» o «mm:ss» en segundos."""
    lower = text.lower()
    factors = {"h": 3600, "min": 60, "sec": 1, "s": 1}
    pairs = re.findall(r"([0-9]+)\s*(h|min|sec|s)\b", lower)
    if pairs:
        return float(sum(int(n) * factors[u] for n, u in pairs))
    parts: list[float] = []
    for piece in lower.split(":"):
        try:
            parts.append(float(piece))
        except ValueError:
            continue
    if len(parts) < 2:
        return None
    total = 0.0
    for part in parts:
        total = total * 60 + part
    return total


def decode_entities(text: str) -> str:
    """Entidades HTML de los títulos (`&amp;`, `&eacute;`, `&#233;`…)."""
    if "&" not in text:
        return text
    return html_lib.unescape(text).replace(" ", " ")
