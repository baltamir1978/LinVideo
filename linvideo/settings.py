"""Ajustes guardados entre sesiones (~/.config/linvideo/ajustes.json) y cola pendiente
(~/.local/share/linvideo/pendientes.json)."""

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import paths
from .models import DownloadOptions, MediaKind


def _write_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


@dataclass
class Settings:
    kind: MediaKind = MediaKind.VIDEO_MAX
    destination: str = ""             # vacío: la carpeta de descargas del usuario
    options: DownloadOptions = field(default_factory=DownloadOptions)
    max_concurrent: int = 2
    auto_update: bool = True          # yt-dlp se actualiza solo (Bruno, sept. 2026)

    @staticmethod
    def file() -> Path:
        return paths.config_dir() / "ajustes.json"

    def destination_path(self) -> Path:
        return Path(self.destination).expanduser() if self.destination else paths.downloads_dir()

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "destination": self.destination,
            "options": self.options.to_json(persistent_only=True),
            "max_concurrent": self.max_concurrent,
            "auto_update": self.auto_update,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Settings":
        settings = cls()
        try:
            settings.kind = MediaKind(data.get("kind", settings.kind.value))
        except ValueError:
            pass
        if isinstance(data.get("destination"), str):
            settings.destination = data["destination"]
        if isinstance(data.get("options"), dict):
            settings.options = DownloadOptions.from_json(data["options"])
        if isinstance(data.get("max_concurrent"), int) and data["max_concurrent"] > 0:
            settings.max_concurrent = data["max_concurrent"]
        if isinstance(data.get("auto_update"), bool):
            settings.auto_update = data["auto_update"]
        return settings

    @classmethod
    def load(cls) -> "Settings":
        try:
            with cls.file().open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return cls()
        return cls.from_json(data) if isinstance(data, dict) else cls()

    def save(self) -> None:
        _write_atomic(self.file(), self.to_json())


# --- Cola pendiente ------------------------------------------------------------------


@dataclass
class PendingEntry:
    url: str
    kind: MediaKind
    destination: str
    title: str
    options: DownloadOptions
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "url": self.url, "kind": self.kind.value,
                "destination": self.destination, "title": self.title,
                "options": self.options.to_json()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PendingEntry | None":
        try:
            return cls(id=str(data["id"]), url=str(data["url"]), kind=MediaKind(data["kind"]),
                       destination=str(data["destination"]), title=str(data.get("title", "")),
                       options=DownloadOptions.from_json(data.get("options") or {}))
        except (KeyError, ValueError, TypeError):
            return None


class PendingQueue:
    """Las descargas **sin terminar**, para recuperarlas si la app se cierra a medias.

    No es un historial (Bruno lo rechazó): lo que se completa desaparece del archivo, y
    cuando no queda nada pendiente el archivo se borra. Al volver a abrir no se reanuda
    nada solo: se enseña la lista para elegir.
    """

    @staticmethod
    def file() -> Path:
        return paths.data_dir() / "pendientes.json"

    @classmethod
    def save(cls, entries: list[PendingEntry]) -> None:
        if not entries:
            cls.clear()
            return
        try:
            _write_atomic(cls.file(), [e.to_json() for e in entries])
        except OSError:
            # Que no se pueda guardar la cola no debe estropear la descarga en curso.
            pass

    @classmethod
    def load(cls) -> list[PendingEntry]:
        try:
            with cls.file().open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [e for e in (PendingEntry.from_json(d) for d in data if isinstance(d, dict)) if e]

    @classmethod
    def clear(cls) -> None:
        cls.file().unlink(missing_ok=True)


def extract_urls(text: str) -> list[str]:
    """Enlaces pegados o arrastrados: separados por espacios, saltos o comas, sin las
    comillas ni los ángulos de alrededor."""
    parts = text.replace(",", " ").split()
    cleaned = (p.strip("<>\"'") for p in parts)
    return [p for p in cleaned if p.startswith(("http://", "https://"))]
