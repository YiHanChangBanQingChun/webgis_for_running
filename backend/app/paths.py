"""Portable project paths; environment overrides support staged data imports."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

def default_fit_source() -> Path:
    configured = os.environ.get("RUNNING_WEBGIS_FIT_SOURCE")
    if configured:
        return Path(configured).expanduser().resolve()
    exports = sorted(DATA_DIR.glob("newdata*/export*"))
    for export in reversed(exports):
        if export.is_dir() and any(export.glob("*.fit")):
            return export
    return DATA_DIR / "running" / "exportfrom20260806"

DEFAULT_FIT_SOURCE = default_fit_source()
PROCESSED_DIR = Path(os.environ.get("RUNNING_WEBGIS_DATA_DIR", DATA_DIR / "processed")).expanduser().resolve()
FULL_ACTIVITIES_DIR = PROCESSED_DIR / "activities"
TRACKS_DIR = PROCESSED_DIR / "tracks"

def ensure_processed_directories() -> None:
    FULL_ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
