"""将全部派生轨迹汇总为可快速查询的 250 米空间探索网格。"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TRACKS_DIR = PROCESSED_DIR / "tracks"
ACTIVITIES_PATH = PROCESSED_DIR / "activities.json"
OUTPUT_PATH = PROCESSED_DIR / "spatial-grid.json"
EARTH_RADIUS_M = 6_378_137.0


def mercator_cell(longitude: float, latitude: float, cell_size_m: int) -> tuple[int, int]:
    latitude = max(-85.05112878, min(85.05112878, latitude))
    x = EARTH_RADIUS_M * math.radians(longitude)
    y = EARTH_RADIUS_M * math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))
    return math.floor(x / cell_size_m), math.floor(y / cell_size_m)


def cell_center(cell_x: int, cell_y: int, cell_size_m: int) -> tuple[float, float]:
    x = (cell_x + .5) * cell_size_m
    y = (cell_y + .5) * cell_size_m
    longitude = math.degrees(x / EARTH_RADIUS_M)
    latitude = math.degrees(2 * math.atan(math.exp(y / EARTH_RADIUS_M)) - math.pi / 2)
    return longitude, latitude


def haversine(a: list[float], b: list[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_000 * math.asin(min(1.0, math.sqrt(value)))


def build(cell_size_m: int) -> dict[str, Any]:
    activities = json.loads(ACTIVITIES_PATH.read_text(encoding="utf-8"))
    activity_dates = {str(item["id"]): item.get("date") for item in activities}
    cells: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    track_paths = sorted(TRACKS_DIR.glob("*.geojson"))

    for index, path in enumerate(track_paths, start=1):
        activity_id = path.stem
        activity_date = activity_dates.get(activity_id)
        if not activity_date:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        feature = data.get("features", [{}])[0]
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        distances = feature.get("properties", {}).get("series", {}).get("distance", [])
        if not coordinates:
            continue
        previous: list[float] | None = None
        previous_distance: float | None = None
        visited: set[tuple[int, int]] = set()
        for point_index, coordinate in enumerate(coordinates):
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            cell = mercator_cell(float(coordinate[0]), float(coordinate[1]), cell_size_m)
            visited.add(cell)
            current_distance = distances[point_index] if point_index < len(distances) and isinstance(distances[point_index], (int, float)) else None
            segment = current_distance - previous_distance if current_distance is not None and previous_distance is not None else (haversine(previous, coordinate) if previous else 0)
            if 0 <= segment <= 100:
                cells[cell][activity_id] += segment
            previous = coordinate
            previous_distance = current_distance
        for cell in visited:
            cells[cell].setdefault(activity_id, 0.0)
        if index % 50 == 0 or index == len(track_paths):
            print(f"[{index}/{len(track_paths)}] cells={len(cells)}")

    output_cells = []
    for (cell_x, cell_y), activity_distances in cells.items():
        longitude, latitude = cell_center(cell_x, cell_y, cell_size_m)
        output_cells.append({
            "cell_id": f"{cell_x}:{cell_y}",
            "longitude": round(longitude, 7),
            "latitude": round(latitude, 7),
            "activities": [
                {"id": activity_id, "date": activity_dates[activity_id], "distance_m": round(distance, 1)}
                for activity_id, distance in sorted(activity_distances.items(), key=lambda item: activity_dates[item[0]])
            ],
        })
    output_cells.sort(key=lambda item: item["cell_id"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cell_size_m": cell_size_m,
        "track_count": len(track_paths),
        "cell_count": len(output_cells),
        "cells": output_cells,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-size", type=int, default=250, choices=(100, 250, 500, 1000))
    args = parser.parse_args()
    result = build(args.cell_size)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {OUTPUT_PATH} ({result['cell_count']} cells)")


if __name__ == "__main__":
    main()
