"""Modo consola: `linvideo <url> [opciones]`.

Recorre el mismo código que la interfaz, así que es la forma de comprobar la lógica sin
abrir la ventana.
"""

import json
import sys
import threading
from pathlib import Path

from . import __version__, filenames, formats, legal, paths, preview, preview_check, tools, updater
from .download import (DownloadJob, DownloadRequest, Event, Failed, Log, ProducedFile, Progress,
                       Stage, Title)
from .models import CookieSource, DownloadOptions, FilenameCleanup, MediaKind, VideoResolution
from .search import SearchResult, SearchScope, SearchSource, SearchCategory, search, search_many
from .settings import PendingQueue, Settings

USAGE = """\
LinVideo — descargas con yt-dlp

Uso:
  linvideo <url> [más urls…] [opciones]

Formato:
  --video          Vídeo en máxima calidad, MP4 (por omisión)
  --video-compat   Vídeo H.264/AAC en MP4 (máxima compatibilidad)
  --mp3            Audio en MP3
  --audio          Audio original sin recodificar
  --gif            GIF a partir del vídeo

Opciones:
  --dir <ruta>     Carpeta de destino (por omisión, la de descargas)
  --cookies <nav>  firefox | chromium | chrome | brave | edge | vivaldi
  --playlist       Descargar la lista completa si el enlace es una lista
  --max <altura>   Techo de resolución: 2160, 1440, 1080, 720, 480
  --format <id>    Un formato concreto de los que lista --formats
  --from <t>       Recortar desde (mm:ss o hh:mm:ss)
  --to <t>         Recortar hasta (mm:ss o hh:mm:ss)
  --fps <n>        FPS del GIF (por omisión 15)
  --width <px>     Ancho del GIF (por omisión 480)
  -h, --help       Esta ayuda

Buscar:
  linvideo --search <fuente> <términos…> [--page N]
  fuentes: youtube | reddit | soundcloud | xvideos | xhamster | redgifs | tnaflix…
           o una categoría: video | audio | adult | all

Otras:
  linvideo --formats <url>        formatos reales de un enlace
  linvideo --preview <url>        qué flujo usaría la vista previa y si arranca
  linvideo --clean-name "título"  probar la limpieza de nombres
  linvideo --prefs                ajustes guardados
  linvideo --tools                qué programas se están usando
  linvideo --pending              descargas que quedaron a medias
  linvideo --update [--force]     actualizar yt-dlp
  linvideo --legal                avisos legales
  linvideo --version
"""


def _err(text: str) -> None:
    print(text, file=sys.stderr)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 2
    command, rest = argv[0], argv[1:]
    match command:
        case "--version":
            print(f"LinVideo {__version__}")
            return 0
        case "--search":
            return run_search(rest)
        case "--formats":
            return run_formats(" ".join(rest))
        case "--preview":
            return run_preview(" ".join(rest))
        case "--clean-name":
            return run_clean_name(" ".join(rest))
        case "--prefs":
            return run_prefs()
        case "--tools":
            return run_tools()
        case "--pending":
            return run_pending()
        case "--update":
            return run_update(force="--force" in rest)
        case "--legal":
            print(legal.as_text())
            return 0
    return run_download(argv)


# --- Descargar ---------------------------------------------------------------------------


def run_download(argv: list[str]) -> int:
    settings = Settings.load()
    kind = MediaKind.VIDEO_MAX
    options = DownloadOptions.from_json(settings.options.to_json())
    destination = settings.destination_path()
    urls: list[str] = []

    index = 0

    def value() -> str | None:
        nonlocal index
        index += 1
        return argv[index] if index < len(argv) else None

    while index < len(argv):
        argument = argv[index]
        match argument:
            case "--video":
                kind = MediaKind.VIDEO_MAX
            case "--video-compat":
                kind = MediaKind.VIDEO_COMPAT
            case "--mp3":
                kind = MediaKind.AUDIO_MP3
            case "--audio":
                kind = MediaKind.AUDIO_ORIGINAL
            case "--gif":
                kind = MediaKind.GIF
            case "--playlist":
                options.download_playlist = True
            case "--max":
                raw = value()
                try:
                    options.resolution = VideoResolution(int(raw or ""))
                except ValueError:
                    _err(f"Resolución no válida: {raw}")
                    return 2
            case "--format":
                options.format_override = value() or ""
            case "--from":
                options.clip_start = value() or ""
            case "--to":
                options.clip_end = value() or ""
            case "--dir":
                destination = Path(value() or ".").expanduser()
            case "--cookies":
                raw = value()
                try:
                    options.cookie_source = CookieSource(raw or "")
                except ValueError:
                    _err(f"Navegador no válido: {raw}")
                    return 2
            case "--fps":
                raw = value()
                if raw and raw.isdigit():
                    options.gif_fps = int(raw)
            case "--width":
                raw = value()
                if raw and raw.isdigit():
                    options.gif_width = int(raw)
            case _ if argument.startswith(("http://", "https://")):
                urls.append(argument)
            case _:
                _err(f"Opción desconocida: {argument}")
                return 2
        index += 1

    if not urls:
        print(USAGE)
        return 2
    destination.mkdir(parents=True, exist_ok=True)

    failures = 0
    for url in urls:
        job = DownloadJob(DownloadRequest(url=url, kind=kind, destination=destination,
                                          options=options))
        try:
            ok = job.run(_report)
        except KeyboardInterrupt:
            job.cancel()
            with _ProgressLine.lock:
                _ProgressLine.clear()
                sys.stdout.flush()
            _err("✗ Cancelado (lo descargado se conserva para reanudar)")
            return 130
        if not ok:
            failures += 1
    return 0 if failures == 0 else 1


class _ProgressLine:
    """La línea de progreso se reescribe en su sitio. Los eventos llegan desde el hilo que
    lee la salida de yt-dlp, así que se escribe siempre con el cerrojo cogido."""

    lock = threading.Lock()
    length = 0

    @classmethod
    def show(cls, line: str) -> None:
        padded = line.ljust(cls.length)
        cls.length = len(line)
        sys.stdout.write("\r" + padded)
        sys.stdout.flush()

    @classmethod
    def clear(cls) -> None:
        if cls.length:
            sys.stdout.write("\r" + " " * cls.length + "\r")
            cls.length = 0


def _report(event: Event) -> None:
    with _ProgressLine.lock:
        match event:
            case Title(text):
                _ProgressLine.clear()
                print(f"▸ {text}")
            case Progress(fraction, speed, _, eta, size):
                percent = f"{fraction * 100:5.1f}%" if fraction >= 0 else "  ··· "
                line = f"  {percent}  {size}"
                if speed:
                    line += f"  {speed}"
                if eta:
                    line += f"  faltan {eta}"
                _ProgressLine.show(line)
            case Stage(text):
                _ProgressLine.clear()
                print(f"  {text}…")
            case Log(line):
                if line.startswith(("ERROR", "WARNING")):
                    _ProgressLine.clear()
                    print(f"  {line}")
            case ProducedFile(path):
                _ProgressLine.clear()
                print(f"✓ {path}")
            case Failed(message):
                _ProgressLine.clear()
                _err(f"✗ {message}")
        # Por una tubería stdout va con búfer y stderr no: sin esto, el «✗» saldría antes
        # que las líneas de registro que lo explican.
        sys.stdout.flush()


# --- Buscar --------------------------------------------------------------------------


def run_search(argv: list[str]) -> int:
    if not argv:
        _err("Falta la fuente.")
        return 2
    scope = SearchScope.parse(argv[0])
    rest = argv[1:]
    page = 1
    if "--page" in rest:
        i = rest.index("--page")
        if i + 1 < len(rest) and rest[i + 1].isdigit():
            page = int(rest[i + 1])
        del rest[i:i + 2]
    query = " ".join(rest)
    if scope is None:
        _err("Fuente no válida.\n"
             f"  webs:        {' | '.join(s.value for s in SearchSource)}\n"
             f"  categorías:  {' | '.join(c.value for c in SearchCategory)}\n"
             "  todas:       all")
        return 2
    if not query:
        _err("Falta el término de búsqueda.")
        return 2

    sources = scope.sources
    if len(sources) == 1:
        try:
            results = search(query, sources[0], page=page)
        except Exception as error:      # el motivo ya viene explicado
            from .search import describe
            _err(f"✗ {describe(error)}")
            return 1
        _print_results(results, sources[0].title, query, show_source=False)
        return 0 if results else 1

    outcome = search_many(query, sources, limit_per_source=8, page=page)
    _print_results(outcome.results, scope.title, query, show_source=True)
    if outcome.failures:
        print("\n⚠︎ Sin respuesta de:")
        for source, message in outcome.failures:
            print(f"   {source.title}: {message}")
    return 0 if outcome.results else 1


def _print_results(results: list[SearchResult], title: str, query: str, show_source: bool) -> None:
    print(f"▸ {len(results)} resultados en {title} para «{query}»\n")
    for number, result in enumerate(results, start=1):
        line = f"{number:3d}. "
        if show_source:
            line += f"[{result.source.title}] "
        line += result.title
        if result.duration_text:
            line += f"  [{result.duration_text}]"
        print(line)
        meta = [m for m in (result.uploader, result.views_text) if m]
        if meta:
            print(f"     {' · '.join(meta)}")
        print(f"     {result.page_url}")


# --- Formatos y vista previa ----------------------------------------------------------


def run_formats(link: str) -> int:
    if not link:
        _err("Uso: --formats <url>")
        return 2
    try:
        title, found = formats.inspect(link)
    except formats.InspectError as error:
        _err(f"✗ {error}")
        return 1
    print(f"▸ {title}\n")
    for f in found:
        line = "  " + f.id.ljust(8) + f.quality_text.ljust(20) + f.codec_text.ljust(18) + \
            f.size_text.ljust(10)
        if f.is_video_only:
            line += " (sin audio)"
        if f.is_audio_only:
            line += " (sólo audio)"
        print(line)
    return 0


def run_preview(link: str) -> int:
    if not link:
        _err("Uso: --preview <url>")
        return 2
    try:
        stream = preview.resolve(link)
    except formats.InspectError as error:
        _err(f"✗ {error}")
        return 1
    print(f"▸ {stream.title}")
    print(f"  tipo:      {stream.kind.value}")
    print(f"  flujo:     {stream.url[:110]}…")
    print(f"  cabeceras: {', '.join(sorted(stream.headers))}")
    try:
        started, picture = preview_check.check(stream)
    except preview_check.Unavailable:
        print("  (sin GStreamer no se comprueba si arranca)")
        return 0
    except RuntimeError as error:
        _err(f"✗ {error}")
        return 1
    print(f"✓ Reproduce: arrancó en {started:.1f} s ({picture})")
    return 0


# --- Diagnóstico ----------------------------------------------------------------------


def run_clean_name(name: str) -> int:
    if not name:
        _err('Uso: --clean-name "nombre de archivo"')
        return 2
    print(f"original: {name}")
    for level in (FilenameCleanup.BASIC, FilenameCleanup.STRICT):
        print(f"{level.value.ljust(7)}: {filenames.clean(name, level)}")
    return 0


def run_prefs() -> int:
    file = Settings.file()
    print(f"ajustes: {file} ({'existe' if file.exists() else 'no existe: valores por omisión'})")
    settings = Settings.load()
    print(json.dumps(settings.to_json(), ensure_ascii=False, indent=2))
    print(f"destino real: {settings.destination_path()}")
    return 0


def run_tools() -> int:
    ytdlp, ffmpeg = tools.ytdlp(), tools.ffmpeg()
    print(f"yt-dlp: {ytdlp or 'no encontrado (linvideo --update)'}")
    print(f"ffmpeg: {ffmpeg or 'no encontrado (sudo apt install ffmpeg)'}")
    if ytdlp:
        print(f"versión: {tools.version(ytdlp) or '?'}")
        print("origen: copia propia, autoactualizable" if tools.uses_own_ytdlp()
              else "origen: sistema")
    print(f"carpeta propia: {paths.bin_dir()}")
    return 0


def run_pending() -> int:
    entries = PendingQueue.load()
    if not entries:
        print("No hay descargas pendientes.")
        return 0
    for entry in entries:
        print(f"· {entry.title or entry.url}  [{entry.kind.short_title}]\n  {entry.url}")
    return 0


def run_update(force: bool) -> int:
    print(f"Instalado: {updater.installed_version() or 'ninguno'}")
    try:
        result = updater.check()
    except updater.UpdateError as error:
        _err(f"✗ {error}")
        return 1
    if result.up_to_date and tools.uses_own_ytdlp():
        print(f"✓ yt-dlp {result.latest} está al día.")
        if not force:
            updater.mark_checked()
            return 0
        print("Se reinstala igualmente (--force).")
    else:
        print(f"Versión publicada: {result.latest}")

    def progress(fraction: float) -> None:
        sys.stdout.write(f"\r  descargando… {fraction * 100:3.0f}%")
        sys.stdout.flush()

    try:
        version = updater.update(progress)
    except updater.UpdateError as error:
        print()
        _err(f"✗ {error}")
        return 1
    updater.mark_checked()
    print(f"\n✓ Actualizado a {version} en {paths.bin_dir()}")
    return 0
