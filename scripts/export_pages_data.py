"""Export only the explicitly selected public activities; never update the source DB."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.derive import activity_summary, activity_track, calendar_rows
from app.fit_archive import archive_fit_file
from scripts import build_spatial_grid

START, END = "2026-09-01", "2026-09-14"
RACES = {"481437585388896557": "2026-11-01", "481600047625044669": "2026-11-08"}
PUBLIC_FIELDS = (
    "id", "date", "start_time", "sport", "sub_sport", "distance_m", "elapsed_s",
    "timer_s", "calories", "average_heart_rate", "max_heart_rate",
    "average_speed_mps", "average_pace_s_per_km", "total_ascent_m", "total_descent_m",
    "record_count", "has_gps", "training_excluded", "include_in_running_stats",
)


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def clean_track(track: dict, summary: dict) -> dict:
    """Keep aligned public sensor arrays and coordinates, excluding device/source metadata."""
    feature = track["features"][0]
    series = feature["properties"]["series"]
    # These record timestamps come from FIT date_time (UTC), not local_date_time.
    series["timestamp"] = [
        datetime.fromisoformat(t.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).isoformat()
        if t and datetime.fromisoformat(t.replace("Z", "+00:00")).tzinfo is None else t
        for t in series["timestamp"]
    ]
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [
            [round(p[0], 7), round(p[1], 7)] for p in feature["geometry"]["coordinates"]
        ]},
        "properties": {"activity_id": summary["id"], "date": summary["date"], "sport": summary["sport"], "series": series},
    }]}


def building_center(feature: dict) -> tuple[float, float]:
    polygons = [feature["geometry"]["coordinates"]] if feature["geometry"]["type"] == "Polygon" else feature["geometry"]["coordinates"]
    points = [p for polygon in polygons for p in polygon[0]]
    return tuple((min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in (0, 1))


def export(database: Path, race_fits: Path, output: Path) -> None:
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = list(connection.execute("SELECT * FROM fit_archive WHERE date_cn BETWEEN ? AND ? ORDER BY date_cn,activity_id", (START, END)))
    indexed_ids = {r["activity_id"] for r in rows}
    database_ids = {r[0] for r in connection.execute("SELECT activity_id FROM activities WHERE date_cn BETWEEN ? AND ?", (START, END))}
    if not rows or not database_ids.issubset(indexed_ids):
        raise ValueError("The selected interval must include every database activity with its local FIT archive.")
    # Check all inputs before replacing the generated public dataset.
    for row in rows:
        if not Path(row["track_path"]).is_file():
            raise FileNotFoundError(row["track_path"])
    for activity_id in RACES:
        if not (race_fits / f"{activity_id}.fit").is_file():
            raise FileNotFoundError(f"Missing half-marathon FIT: {activity_id}")
    data = output / "data"
    if data.exists():
        shutil.rmtree(data)
    tracks = data / "tracks"
    activities = []
    for row in rows:
        summary = json.loads(row["summary_json"])
        if summary.get("timezone_evidence") not in ("fit_date_time_UTC", "explicit_offset"):
            raise ValueError(f"Unverified FIT timestamp timezone: {row['activity_id']}")
        summary["date"] = row["date_cn"]
        activity = {k: summary[k] for k in PUBLIC_FIELDS if k in summary}
        activities.append(activity)
        write(tracks / f"{activity['id']}.geojson", clean_track(json.loads(Path(row["track_path"]).read_text()), activity))
    for activity_id, expected_date in RACES.items():
        path = race_fits / f"{activity_id}.fit"
        archive = archive_fit_file(path, race_fits)
        archive["activity_id"] = activity_id
        summary = activity_summary(archive)
        if summary["date"] != expected_date:
            raise ValueError(f"Race date mismatch: {activity_id}: {summary['date']}")
        activity = {k: summary[k] for k in PUBLIC_FIELDS if k in summary}
        activity["include_in_running_stats"] = True
        activities.append(activity)
        write(tracks / f"{activity_id}.geojson", clean_track(activity_track(archive, summary), activity))
    activities.sort(key=lambda a: a["start_time"] or "")
    write(data / "activities.json", activities)
    write(data / "calendar.json", calendar_rows(activities))
    build_spatial_grid.ACTIVITIES_PATH = data / "activities.json"
    build_spatial_grid.TRACKS_DIR = tracks
    grid = build_spatial_grid.build(250)
    grid.pop("generated_at", None)
    write(data / "spatial-grid.json", grid)
    from app import main as api
    api.TRACKS_DIR = tracks
    for activity in activities:
        write(data / "insights" / f"{activity['id']}.json", api._activity_insights(activity["id"]))
    # Personal profile/health snapshots are outside the authorized public selection.
    write(data / "athlete-profile.json", {"running_fitness": {}, "source": "未公开个人阈值"})
    write(data / "quality-report.json", {
        "readiness": {"api_ready": True},
        "data_coverage": {"activities_with_gps": sum(bool(a["has_gps"]) for a in activities),
                          "date_range": {"start": START, "end": max(RACES.values())}},
    })
    source_buildings = json.loads((ROOT / "frontend/public/cesium-data/guangzhou-buildings.geojson").read_text())
    source_features = source_buildings["features"]
    # A coherent central Guangzhou neighborhood, rather than scattered random buildings.
    source_features.sort(key=lambda f: sum((a-b)**2 for a,b in zip(building_center(f), (113.34, 23.14))))
    keep = source_features[:math.ceil(len(source_features) * .2)]
    buildings = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": f["geometry"],
        "properties": {k: f["properties"].get(k) for k in ("name", "height_m", "osm_id")},
    } for f in keep]}
    write(data / "guangzhou-buildings.geojson", buildings)
    manifest = {
        "schema_version": 1, "default_month": START[:7],
        "default_range": {"start": START, "end": END},
        "continuous_ranges": [{"start": START, "end": END}],
        "featured_activity_ids": list(RACES), "default_activity_id": rows[-1]["activity_id"],
        "activity_ids": [a["id"] for a in activities], "activity_count": len(activities),
        "building_count": len(keep), "source_building_count": len(source_features),
        "coverage_note": "公开选集：2026-09-01 至 09-14 的全部活动，以及 11-01、11-08 两场半马。其余日期未公开，空白不代表休息；统计仅针对公开数据。",
    }
    write(output / "manifest.json", manifest)
    for name in ("favicon.svg", "icons.svg"):
        shutil.copyfile(ROOT / "frontend/public" / name, output / name)
    connection.close()
    print(json.dumps({"activities": len(activities), "interval": [START, END], "buildings": len(keep),
                      "public_bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file())}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT.parent / "training_database/training.sqlite3")
    parser.add_argument("--race-fits", type=Path, default=ROOT / ".runtime/pages-races")
    parser.add_argument("--output", type=Path, default=ROOT / "frontend/public-demo")
    args = parser.parse_args()
    export(args.database, args.race_fits, args.output)
