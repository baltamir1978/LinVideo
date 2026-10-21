"""La línea de órdenes de yt-dlp y la ejecución de una descarga."""

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import errors, filenames, formatters, tools
from .models import DownloadOptions, FilenameCleanup, MediaKind

# --- Eventos que el motor emite hacia la interfaz o la consola --------------------


@dataclass(frozen=True)
class Title:
    text: str


@dataclass(frozen=True)
class Progress:
    fraction: float        # 0…1, o -1 si no se sabe el total
    speed: str
    speed_bytes: float
    eta: str
    size: str


@dataclass(frozen=True)
class Stage:
    text: str              # «Uniendo vídeo y audio», «Convirtiendo a GIF»…


@dataclass(frozen=True)
class Log:
    line: str


@dataclass(frozen=True)
class ProducedFile:
    path: Path


@dataclass(frozen=True)
class Failed:
    message: str


Event = Title | Progress | Stage | Log | ProducedFile | Failed
Emit = Callable[[Event], None]

# --- Construcción de la línea de órdenes ------------------------------------------

# Marcas para leer la salida de yt-dlp sin ambigüedad.
TITLE_TAG = "LV-TITLE|"
FILE_TAG = "LV-FILE|"
PROGRESS_TAG = "LV-PROG|"


@dataclass
class DownloadRequest:
    url: str
    kind: MediaKind
    destination: Path
    options: DownloadOptions

    def ytdlp_arguments(self, output_directory: Path, ffmpeg_dir: Path | None = None) -> list[str]:
        options = self.options
        args = [
            "--ignore-config",
            "--no-color",
            "--newline",
            "--progress",
            "--no-simulate",
            "--no-quiet",
            "--no-warnings",
            "--no-mtime",
            "--concurrent-fragments", str(max(1, options.concurrent_fragments)),
            "--retries", "10",
            "--fragment-retries", "10",
            "--progress-template",
            f"download:{PROGRESS_TAG}%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
            "%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s",
            "--print", f"{TITLE_TAG}%(title)s",
            "--print", f"after_move:{FILE_TAG}%(filepath)s",
            "--paths", str(output_directory),
            "-o", "%(title).150B [%(id)s].%(ext)s",
        ]

        args += ["--yes-playlist"] if options.download_playlist else ["--no-playlist"]

        if ffmpeg_dir is not None:
            args += ["--ffmpeg-location", str(ffmpeg_dir)]

        browser = options.cookie_source.browser_argument
        if browser:
            args += ["--cookies-from-browser", browser]

        section = download_section(options.clip_start, options.clip_end)
        if section:
            args += ["--download-sections", section, "--force-keyframes-at-cuts"]

        limit = options.speed_limit.strip()
        if limit:
            args += ["--limit-rate", limit]

        height = options.resolution.height_filter

        # Formato elegido a mano: manda sobre el modo y la calidad.
        chosen = options.format_override.strip()
        if chosen and self.kind is not MediaKind.GIF and not self.kind.is_audio:
            args += ["-f", chosen, "--merge-output-format", "mp4"]
            if options.embed_metadata:
                args.append("--embed-metadata")
            args.append(self.url)
            return args

        match self.kind:
            case MediaKind.VIDEO_MAX:
                args += ["-f", f"bv*{height}+ba/b{height}/bv*+ba/b",
                         "--merge-output-format", "mp4", "--remux-video", "mp4"]
            case MediaKind.VIDEO_COMPAT:
                args += ["-f",
                         f"bv*{height}[vcodec^=avc1]+ba[acodec^=mp4a]/bv*{height}[vcodec^=avc1]+ba/"
                         f"b{height}[ext=mp4]/bv*{height}+ba/b",
                         "--merge-output-format", "mp4"]
            case MediaKind.AUDIO_MP3:
                args += ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0"]
            case MediaKind.AUDIO_ORIGINAL:
                args += ["-f", "ba/b", "-x", "--audio-format", "best"]
            case MediaKind.GIF:
                # El GIF sale de una conversión posterior: aquí sólo hace falta el vídeo.
                args += ["-f", f"bv*{height}/b{height}/bv*/b"]

        if options.embed_metadata:
            args.append("--embed-metadata")
            if self.kind.is_audio:
                args += self._audio_tagging_arguments()
        # La miniatura sólo se incrusta en audio: en MP4 haría falta AtomicParsley.
        if options.embed_thumbnail and self.kind.is_audio:
            # JPG y recorte cuadrado: es lo que esperan los reproductores como portada, en
            # vez del fotograma 16:9 que trae YouTube.
            args += ["--embed-thumbnail", "--convert-thumbnails", "jpg",
                     "--postprocessor-args", "ThumbnailsConvertor:-vf crop=ih:ih"]
        if options.embed_subtitles and not self.kind.is_audio and self.kind is not MediaKind.GIF:
            args += ["--embed-subs", "--sub-langs", "es.*,en.*", "--compat-options", "no-keep-subs"]

        extra = options.extra_arguments.strip()
        if extra:
            # A diferencia del original, se respetan las comillas («--opción "con espacios"»).
            try:
                args += shlex.split(extra)
            except ValueError:
                args += extra.split()

        args.append(self.url)
        return args

    def _audio_tagging_arguments(self) -> list[str]:
        """Etiquetas para los archivos de audio.

        YouTube casi nunca rellena artista o álbum, así que se toman los campos de música si
        existen y, si no, se cae al canal. Cuando el título tiene forma «Artista - Canción»,
        se reparte en los dos campos. El álbum no se toca: forzarlo con alternativas
        acababa escribiendo el literal «NA».
        """
        args = [
            "--parse-metadata", "%(artist,album_artist,creator,uploader)s:%(meta_artist)s",
            "--parse-metadata", "%(track,title)s:%(meta_title)s",
        ]
        if self.options.smart_audio_tags:
            # Si el patrón no encaja, yt-dlp deja los valores anteriores intactos.
            args += ["--parse-metadata", "title:(?P<meta_artist>[^-]+?) - (?P<meta_title>.+)"]
        # Fuera «(Official Video)», «[HD]» y compañía del título de la etiqueta.
        args += ["--replace-in-metadata", "meta_title",
                 r"(?i)\s*[\(\[](?:official|video|audio|lyric|visualizer|hd|4k)[^)\]]*[\)\]]", ""]
        return args


def download_section(start: str, end: str) -> str | None:
    """Los campos de recorte en el formato de `--download-sections`: `*inicio-fin`."""
    a, b = normalize_timestamp(start), normalize_timestamp(end)
    if a is None and b is None:
        return None
    if b is None:
        return f"*{a}-inf"
    if a is None:
        return f"*0-{b}"
    return f"*{a}-{b}"


def normalize_timestamp(text: str) -> str | None:
    """Acepta `mm:ss`, `hh:mm:ss` o segundos sueltos; cualquier otra cosa se descarta."""
    trimmed = text.strip()
    if not trimmed or not re.fullmatch(r"[0-9:.]+", trimmed):
        return None
    return trimmed


def unique_path(path: Path) -> Path:
    """Añade « (2)», « (3)»… al nombre si el archivo ya existe."""
    if not path.exists():
        return path
    base, ext = filenames.split_extension(path.name)
    index = 2
    while True:
        name = f"{base} ({index}).{ext}" if ext else f"{base} ({index})"
        candidate = path.with_name(name)
        if not candidate.exists():
            return candidate
        index += 1


# --- Ejecución ---------------------------------------------------------------------


class LineBuffer:
    """Reconstruye líneas completas a partir de los trozos que llegan por la tubería.

    yt-dlp usa `\\r` para refrescar la línea de progreso: cuenta como salto de línea.
    """

    def __init__(self, on_line: Callable[[str], None]) -> None:
        self._pending = b""
        self._on_line = on_line

    def feed(self, data: bytes) -> None:
        self._pending += data
        parts = re.split(rb"[\r\n]", self._pending)
        self._pending = parts.pop()
        for raw in parts:
            text = raw.decode("utf-8", errors="replace").strip()
            if text:
                self._on_line(text)

    def flush(self) -> None:
        rest, self._pending = self._pending, b""
        text = rest.decode("utf-8", errors="replace").strip()
        if text:
            self._on_line(text)


class DownloadJob:
    """Una descarga concreta. Un objeto por tarea; se puede cancelar desde otro hilo."""

    def __init__(self, request: DownloadRequest) -> None:
        self.request = request
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._cancelled = False
        # Líneas de error que ha ido soltando yt-dlp, para explicar el fallo al final.
        self._error_lines: list[str] = []

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def run(self, emit: Emit) -> bool:
        """Lanza yt-dlp (y ffmpeg si toca) y va emitiendo eventos. Bloquea hasta terminar.

        Devuelve True si terminó bien.
        """
        ytdlp = tools.ytdlp()
        if ytdlp is None:
            emit(Failed("No se encuentra yt-dlp. Instálalo con: linvideo --update"))
            return False
        ffmpeg = tools.ffmpeg()
        if ffmpeg is None:
            emit(Log("Aviso: no se encuentra ffmpeg; la unión de pistas y las conversiones "
                     "fallarán. Instálalo con: sudo apt install ffmpeg"))

        kind = self.request.kind
        # Para GIF se descarga el vídeo a un temporal y sólo se deja el .gif en destino.
        if kind is MediaKind.GIF:
            working = Path(tempfile.mkdtemp(prefix=f"linvideo-{uuid.uuid4().hex[:8]}-"))
        else:
            working = self.request.destination

        produced: list[Path] = []
        args = self.request.ytdlp_arguments(working, ffmpeg.parent if ffmpeg else None)
        emit(Log("$ yt-dlp " + " ".join(shlex.quote(a) for a in args)))

        def on_line(line: str) -> None:
            self._handle(line, emit, produced.append)

        exit_code = self._run_process([*tools.command(ytdlp), *args], on_line)

        try:
            if self.cancelled:
                return False
            if exit_code != 0:
                with self._lock:
                    lines = list(self._error_lines)
                emit(Failed(errors.explain(lines, exit_code)))
                return False
            if kind is not MediaKind.GIF:
                # Se arregla el nombre y se anuncia el archivo definitivo.
                for path in produced:
                    emit(ProducedFile(self._tidy_name(path, emit)))
                return True
            if not produced:
                emit(Failed("No se ha localizado el vídeo descargado para convertirlo a GIF."))
                return False
            return self._convert_to_gif(produced[-1], ffmpeg, emit)
        finally:
            if kind is MediaKind.GIF:
                shutil.rmtree(working, ignore_errors=True)

    def _tidy_name(self, path: Path, emit: Emit) -> Path:
        """Renombra según los ajustes de limpieza. Si algo falla, se queda el nombre original:
        nunca se pierde la descarga por esto."""
        options = self.request.options
        if options.filename_cleanup is FilenameCleanup.NONE:
            return path
        cleaned = filenames.clean(path.name, options.filename_cleanup, options.keep_identifier)
        if cleaned == path.name:
            return path
        target = unique_path(path.with_name(cleaned))
        try:
            path.rename(target)
        except OSError as error:
            emit(Log(f"No se pudo renombrar el archivo: {error}"))
            return path
        emit(Log(f"Renombrado: {path.name} → {target.name}"))
        return target

    # --- Lectura de la salida --------------------------------------------------------

    def _handle(self, line: str, emit: Emit, on_file: Callable[[Path], None]) -> None:
        if line.startswith(PROGRESS_TAG):
            event = parse_progress(line)
            if event is not None:
                emit(event)
            return
        if line.startswith(TITLE_TAG):
            title = line[len(TITLE_TAG):]
            if title and title != "NA":
                emit(Title(title))
            return
        if line.startswith(FILE_TAG):
            path = line[len(FILE_TAG):]
            if path and path != "NA":
                # Se anuncia al final de `run`, cuando ya se ha renombrado.
                on_file(Path(path))
            return

        emit(Log(line))

        # Se guardan los errores para poder explicar el fallo cuando termine.
        lower = line.lower()
        if lower.startswith("error") or "error:" in lower or lower.startswith("warning:"):
            with self._lock:
                self._error_lines.append(line)
                del self._error_lines[:-20]

        # Fases de posprocesado que merece la pena mostrar.
        if "[Merger]" in line:
            emit(Stage("Uniendo vídeo y audio"))
        elif "[ExtractAudio]" in line:
            emit(Stage("Extrayendo audio"))
        elif "[VideoRemuxer]" in line:
            emit(Stage("Empaquetando en MP4"))
        elif "[Metadata]" in line or "[ThumbnailsConvertor]" in line:
            emit(Stage("Añadiendo metadatos"))

    # --- GIF ---------------------------------------------------------------------

    def _convert_to_gif(self, source: Path, ffmpeg: Path | None, emit: Emit) -> bool:
        if ffmpeg is None:
            emit(Failed("Se necesita ffmpeg para crear el GIF. Instálalo con: "
                        "sudo apt install ffmpeg"))
            return False
        emit(Stage("Convirtiendo a GIF"))

        options = self.request.options
        # El GIF hereda el nombre del vídeo intermedio, ya limpio.
        name = filenames.split_extension(source.name)[0]
        if options.filename_cleanup is not FilenameCleanup.NONE:
            name = filenames.clean(name, options.filename_cleanup, options.keep_identifier)
        output = unique_path(self.request.destination / f"{name}.gif")

        fps = max(1, options.gif_fps)
        width = max(64, options.gif_width)
        video_filter = (
            f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];"
            "[s0]palettegen=stats_mode=diff[p];"
            "[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
        )
        args = ["-hide_banner", "-nostdin", "-y", "-i", str(source),
                "-vf", video_filter, "-loop", "0", str(output)]
        emit(Log("$ ffmpeg " + " ".join(shlex.quote(a) for a in args)))

        code = self._run_process([str(ffmpeg), *args], lambda line: emit(Log(line)))
        if self.cancelled:
            return False
        if code != 0:
            emit(Failed(f"ffmpeg falló al crear el GIF (código {code})."))
            return False
        emit(ProducedFile(output))
        return True

    # --- Proceso -----------------------------------------------------------------

    def _run_process(self, argv: list[str], on_line: Callable[[str], None]) -> int:
        with self._lock:
            if self._cancelled:
                return -1
            try:
                # stdout y stderr juntos: el orden de las líneas importa para el registro.
                process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           env=tools.child_env())
            except OSError as error:
                launch_failure: str | None = f"No se pudo ejecutar {Path(argv[0]).name}: {error}"
            else:
                launch_failure = None
                self._process = process
        if launch_failure is not None:
            on_line(launch_failure)
            return -1

        buffer = LineBuffer(on_line)
        assert process.stdout is not None
        fd = process.stdout.fileno()
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            buffer.feed(chunk)
        buffer.flush()
        code = process.wait()
        with self._lock:
            self._process = None
        return code


def parse_progress(line: str) -> Progress | None:
    fields = line[len(PROGRESS_TAG):].split("|")
    if len(fields) < 5:
        return None

    def number(text: str) -> float | None:
        try:
            return float(text)
        except ValueError:
            return None          # yt-dlp escribe «NA» cuando no lo sabe

    downloaded = number(fields[0]) or 0.0
    total = number(fields[1]) or number(fields[2]) or 0.0
    speed = number(fields[3])
    eta = number(fields[4])
    fraction = min(1.0, downloaded / total) if total > 0 else -1.0
    if total > 0:
        size = f"{formatters.human_bytes(downloaded)} / {formatters.human_bytes(total)}"
    else:
        size = formatters.human_bytes(downloaded)
    return Progress(
        fraction=fraction,
        speed=f"{formatters.human_bytes(speed)}/s" if speed is not None else "",
        speed_bytes=speed or 0.0,
        eta=formatters.duration(eta) if eta is not None else "",
        size=size,
    )
