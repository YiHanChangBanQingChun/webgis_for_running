"""项目路径定义；所有处理结果都写入 data/processed。"""

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
DEFAULT_FIT_SOURCE = DATA_DIR / "running" / "exportfrom20260806"
PROCESSED_DIR = DATA_DIR / "processed"
FULL_ACTIVITIES_DIR = PROCESSED_DIR / "activities"
TRACKS_DIR = PROCESSED_DIR / "tracks"


def ensure_processed_directories() -> None:
    """创建派生数据目录，不触碰原始 FIT 目录。"""
    FULL_ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
