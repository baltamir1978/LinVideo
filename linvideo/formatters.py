"""Cifras que ve el usuario."""

import math


def human_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    if unit == 0:
        return f"{int(value)} B"
    # Coma decimal, como se escribe en español.
    return f"{value:.1f} {units[unit]}".replace(".", ",")


def duration(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds < 0:
        return ""
    total = int(seconds)
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
