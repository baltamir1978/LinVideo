"""Dónde vive cada cosa, según las carpetas XDG de freedesktop."""

import os
import shutil
import subprocess
from pathlib import Path

APP = "linvideo"


def _xdg(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable, "")
    # La especificación pide ignorar las rutas relativas.
    if value and os.path.isabs(value):
        return Path(value)
    return Path.home() / fallback


def config_dir() -> Path:
    """Ajustes: ~/.config/linvideo."""
    return _xdg("XDG_CONFIG_HOME", ".config") / APP


def data_dir() -> Path:
    """Datos: ~/.local/share/linvideo (cola pendiente y yt-dlp actualizable)."""
    return _xdg("XDG_DATA_HOME", ".local/share") / APP


def state_dir() -> Path:
    """Estado que no importa perder: ~/.local/state/linvideo."""
    return _xdg("XDG_STATE_HOME", ".local/state") / APP


def bin_dir() -> Path:
    """yt-dlp descargado por la app, que se puede actualizar sin permisos de root."""
    return data_dir() / "bin"


def downloads_dir() -> Path:
    """La carpeta de descargas del usuario («Descargas» en un Debian en español)."""
    if shutil.which("xdg-user-dir"):
        try:
            out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
            # Si no está configurada, xdg-user-dir devuelve la carpeta personal.
            if out and Path(out) != Path.home():
                return Path(out)
        except (OSError, subprocess.SubprocessError):
            pass
    for name in ("Descargas", "Downloads"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return candidate
    return Path.home() / "Downloads"
