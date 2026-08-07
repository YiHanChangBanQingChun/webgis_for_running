"""从完整归档生成面向页面的活动索引、日历和轨迹 GeoJSON。"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .fit_archive import write_json

SEMICIRCLES_PER_DEGREE = 2**31 / 180
TRACK_SERIES_FIELDS = (
    "timestamp",
    "distance",
    "heart_rate",
    "enhanced_speed",
    "speed",
    "altitude",
    "enhanced_altitude",
    "cadence",
    "power",
    "step_length",
    "stance_time",
    "vertical_oscillation",
    "vertical_ratio",
)


def _messages_by_type(archive: dict[str, Any], message_type: str) -> list[dict[str, Any]]:
    return [item["fields"] for item in archive["messages"] if item["message_type"] == message_type]


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _as_iso_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else None


def _as_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def activity_summary(archive: dict[str, Any]) -> dict[str, Any]:
    """提取日历、列表及筛选所需的小型活动摘要。"""
    sessions = _messages_by_type(archive, "session")
    session = sessions[0] if sessions else {}
    records = _messages_by_type(archive, "record")
    start_time = session.get("start_time") or (records[0].get("timestamp") if records else None)
    distance_m = _number(session.get("total_distance"))
    elapsed_s = _number(session.get("total_elapsed_time"))
    avg_speed = _number(session.get("enhanced_avg_speed") or session.get("avg_speed"))

    # 某些 FIT 在尾部损坏，session 消息可能尚未来得及解析。此时从已归档的
    # record 消息回退计算基础指标，既保持数据可用，也不伪装为设备原始汇总值。
    record_distances = [_number(record.get("distance")) for record in records]
    record_distances = [value for value in record_distances if value is not None]
    record_times = [_as_datetime(record.get("timestamp")) for record in records]
    record_times = [value for value in record_times if value is not None]
    derived_from_records = False
    if distance_m is None and record_distances:
        distance_m = max(record_distances)
        derived_from_records = True
    if elapsed_s is None and len(record_times) >= 2:
        elapsed_s = max((record_times[-1] - record_times[0]).total_seconds(), 0)
        derived_from_records = True
    if avg_speed is None and distance_m is not None and elapsed_s and elapsed_s > 0:
        avg_speed = distance_m / elapsed_s
        derived_from_records = True
    return {
        "id": archive["activity_id"],
        "source_file": archive["source"]["path"],
        "parse_status": archive["parse"]["status"],
        "parse_error": archive["parse"]["error"],
        "date": _as_iso_date(start_time),
        "start_time": start_time,
        "sport": session.get("sport"),
        "sub_sport": session.get("sub_sport"),
        "distance_m": distance_m,
        "elapsed_s": elapsed_s,
        "timer_s": _number(session.get("total_timer_time")),
        "calories": _number(session.get("total_calories")),
        "average_heart_rate": _number(session.get("avg_heart_rate")),
        "max_heart_rate": _number(session.get("max_heart_rate")),
        "average_speed_mps": avg_speed,
        "average_pace_s_per_km": (1000 / avg_speed) if avg_speed else None,
        "total_ascent_m": _number(session.get("total_ascent")),
        "total_descent_m": _number(session.get("total_descent")),
        "record_count": len(records),
        "has_gps": any("position_lat" in record and "position_long" in record for record in records),
        "metrics_derived_from_records": derived_from_records,
        "full_data_path": f"activities/{archive['activity_id']}.full.json",
        "track_path": f"tracks/{archive['activity_id']}.geojson",
    }


def activity_track(archive: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any] | None:
    """构建紧凑 GeoJSON。动态字段以与坐标一一对应的数组保存在 properties 中。"""
    coordinates: list[list[float]] = []
    series: dict[str, list[Any]] = {field: [] for field in TRACK_SERIES_FIELDS}
    for record in _messages_by_type(archive, "record"):
        lat = _number(record.get("position_lat"))
        lon = _number(record.get("position_long"))
        if lat is None or lon is None:
            continue
        coordinates.append([lon / SEMICIRCLES_PER_DEGREE, lat / SEMICIRCLES_PER_DEGREE])
        for field in TRACK_SERIES_FIELDS:
            series[field].append(record.get(field))

    if len(coordinates) < 2:
        return None
    properties = {
        "activity_id": summary["id"],
        "date": summary["date"],
        "sport": summary["sport"],
        "coordinate_series_schema": "Each array value aligns by index with geometry.coordinates.",
        "series": series,
    }
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        ],
    }


def calendar_rows(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按日期聚合，供 ECharts Calendar 直接使用。"""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for activity in activities:
        if activity["date"]:
            grouped[activity["date"]].append(activity)
    return [
        {
            "date": day,
            "activity_count": len(items),
            "distance_m": sum(item["distance_m"] or 0 for item in items),
            "elapsed_s": sum(item["elapsed_s"] or 0 for item in items),
            "calories": sum(item["calories"] or 0 for item in items),
            "activity_ids": [item["id"] for item in items],
        }
        for day, items in sorted(grouped.items())
    ]


def build_derived_files(full_dir: Path, processed_dir: Path, tracks_dir: Path) -> dict[str, int]:
    """从归档批量生成页面派生数据。"""
    activities: list[dict[str, Any]] = []
    track_count = 0
    for archive_path in sorted(full_dir.glob("*.full.json")):
        archive = json.loads(archive_path.read_text(encoding="utf-8"))
        summary = activity_summary(archive)
        activities.append(summary)
        track = activity_track(archive, summary)
        if track:
            write_json(tracks_dir / f"{summary['id']}.geojson", track)
            track_count += 1
    write_json(processed_dir / "activities.json", activities)
    write_json(processed_dir / "calendar.json", calendar_rows(activities))
    return {"activities": len(activities), "tracks": track_count}
