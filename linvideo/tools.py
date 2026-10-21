"""Localiza los programas externos: yt-dlp, ffmpeg y ffprobe.

Orden de búsqueda de yt-dlp:
 1. ~/.local/share/linvideo/bin: la copia que mantiene la propia app (ver `updater`);
 2. el sistema: /usr/bin (el paquete de Debian, que va atrasado), /usr/local/bin,
    ~/.local/bin y, para desarrollar en el Mac, Homebrew.

ffmpeg y ffprobe salen siempre del sistema (`sudo apt install ffmpeg`).
"""

import os
import subprocess
import sys
from pathlib import Path

from . import paths


def _system_dirs() -> list[Path]:
    dirs = [Path("/usr/bin"), Path("/usr/local/bin"), Path.home() / ".local/bin"]
    if sys.platform == "darwin":
        dirs = [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), *dirs]
    return dirs


def search_dirs() -> list[Path]:
    return [paths.bin_dir(), *_system_dirs()]


def find(name: str) -> Path | None:
    for directory in search_dirs():
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def ytdlp() -> Path | None:
    return find("yt-dlp")


def ffmpeg() -> Path | None:
    return find("ffmpeg")


def child_path() -> str:
    """PATH para los procesos hijos, para que yt-dlp encuentre ffmpeg."""
    extra = os.environ.get("PATH", "")
    return os.pathsep.join([*(str(d) for d in search_dirs()), extra])


def is_zipapp(path: Path) -> bool:
    """¿Es el yt-dlp «zipapp» (un script de Python), en vez de un ejecutable nativo?"""
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def command(executable: Path) -> list[str]:
    """Cómo ejecutar un programa.

    El yt-dlp que descarga la app es el zipapp, que sirve en cualquier arquitectura pero
    empieza por `#!/usr/bin/env python3`. Se le pasa el intérprete que está ejecutando
    LinVideo para no depender de cuál sea el `python3` del PATH (en el Mac, el del sistema
    es demasiado viejo para yt-dlp).
    """
    if executable.parent == paths.bin_dir() and is_zipapp(executable):
        return [sys.executable, str(executable)]
    return [str(executable)]


def version(executable: Path) -> str | None:
    try:
        out = subprocess.run([*command(executable), "--version"], capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    first = out.stdout.strip().splitlines()
    return first[0] if first else None


def uses_own_ytdlp() -> bool:
    found = ytdlp()
    return found is not None and found.parent == paths.bin_dir()


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = child_path()
    # Salida de yt-dlp en UTF-8 y en inglés, que es lo que se interpreta. C.UTF-8 existe
    # siempre en Debian; en el Mac no, y allí basta con en_US.
    env["LC_ALL"] = "en_US.UTF-8" if sys.platform == "darwin" else "C.UTF-8"
    env["PYTHONIOENCODING"] = "utf-8"
    return env
