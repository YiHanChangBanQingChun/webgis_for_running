"""从完整归档生成 activities.json、calendar.json 和轨迹 GeoJSON。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.derive import build_derived_files  # noqa: E402
from app.paths import FULL_ACTIVITIES_DIR, PROCESSED_DIR, TRACKS_DIR, ensure_processed_directories  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    ensure_processed_directories()
    result = build_derived_files(FULL_ACTIVITIES_DIR, PROCESSED_DIR, TRACKS_DIR)
    print(f"完成：活动 {result['activities']}，含 GPS 轨迹 {result['tracks']}。")


if __name__ == "__main__":
    main()
