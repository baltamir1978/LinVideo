"""Mantiene yt-dlp al día. Las webs cambian a menudo y una versión vieja falla.

La copia propia va en ~/.local/share/linvideo/bin, no en /usr: así se actualiza sin
permisos de root. Se baja el «zipapp» de yt-dlp, que es un script de Python y sirve en
cualquier arquitectura (amd64, arm64…), igual que el .deb, que es `Architecture: all`.
"""

import json
import os
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from dataclasses import dataclass

from . import paths, tools

LATEST_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
BINARY_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
CHECK_INTERVAL = 24 * 60 * 60     # como mucho una comprobación al día
_USER_AGENT = "LinVideo (https://github.com/baltamir1978/LinVideo)"


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class CheckResult:
    installed: str | None
    latest: str

    @property
    def up_to_date(self) -> bool:
        return self.installed == self.latest


def installed_version() -> str | None:
    found = tools.ytdlp()
    return tools.version(found) if found else None


def check() -> CheckResult:
    """Consulta la última versión publicada y la compara con la instalada."""
    request = urllib.request.Request(LATEST_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
    except (OSError, ValueError) as error:
        raise UpdateError(f"No se pudo comprobar: {error}") from error
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str):
        raise UpdateError("No se pudo leer la última versión publicada.")
    return CheckResult(installed=installed_version(), latest=tag)


def update(on_progress: Callable[[float], None] | None = None) -> str:
    """Descarga yt-dlp y lo deja listo para usar. Devuelve la versión instalada."""
    directory = paths.bin_dir()
    destination = directory / "yt-dlp"
    temporary = directory / "yt-dlp.download"
    directory.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(BINARY_URL, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, \
                temporary.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while chunk := response.read(256 * 1024):
                out.write(chunk)
                done += len(chunk)
                if on_progress and total > 0:
                    on_progress(min(1.0, done / total))
        os.chmod(temporary, 0o755)
        if not tools.is_zipapp(temporary):
            raise UpdateError("Lo descargado no es yt-dlp.")
        # Se sustituye de golpe: una descarga a medias nunca deja un yt-dlp roto.
        os.replace(temporary, destination)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise UpdateError(str(error)) from error
    except UpdateError:
        temporary.unlink(missing_ok=True)
        raise

    version = tools.version(destination)
    if version is None:
        raise UpdateError("El yt-dlp descargado no se ejecuta correctamente.")
    return version


# --- Comprobación automática ---------------------------------------------------------


def _state_file() -> Path:
    return paths.state_dir() / "actualizacion.json"


def due_for_check(now: float | None = None) -> bool:
    try:
        with open(_state_file(), encoding="utf-8") as handle:
            last = float(json.load(handle).get("ultima_comprobacion", 0))
    except (OSError, ValueError, AttributeError):
        return True
    return (now or time.time()) - last >= CHECK_INTERVAL


def mark_checked(now: float | None = None) -> None:
    """Sólo se llama si la comprobación llegó a la red: sin red no cuenta como comprobado
    y se reintenta en el próximo arranque."""
    paths.state_dir().mkdir(parents=True, exist_ok=True)
    with open(_state_file(), "w", encoding="utf-8") as handle:
        json.dump({"ultima_comprobacion": now or time.time()}, handle)


def check_automatically(install: bool) -> str | None:
    """Comprueba una vez al día. Devuelve la versión nueva si la hay (ya instalada si
    `install`), o None. Nunca lanza: un fallo aquí no debe estorbar al arrancar."""
    if not due_for_check():
        return None
    try:
        result = check()
    except UpdateError:
        return None
    mark_checked()
    if result.up_to_date:
        return None
    if install:
        try:
            return update()
        except UpdateError:
            return None
    return result.latest
