"""最小只读 FastAPI 服务：只读取预处理数据，不解析或修改 FIT。"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.paths import PROCESSED_DIR, TRACKS_DIR

ACTIVITIES_PATH = PROCESSED_DIR / "activities.json"
CALENDAR_PATH = PROCESSED_DIR / "calendar.json"
REPORT_PATH = PROCESSED_DIR / "import-report.json"
SPATIAL_GRID_PATH = PROCESSED_DIR / "spatial-grid.json"
ATHLETE_PROFILE_PATH = PROCESSED_DIR / "athlete-profile.json"

app = FastAPI(title="Running WebGIS API", version="0.1.0", description="跑步 FIT 派生数据的只读查询 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def _activities() -> list[dict[str, Any]]:
    if not ACTIVITIES_PATH.exists():
        raise HTTPException(status_code=503, detail="派生活动数据不存在；请先运行 build_derived.py。")
    return json.loads(ACTIVITIES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _calendar() -> list[dict[str, Any]]:
    if not CALENDAR_PATH.exists():
        raise HTTPException(status_code=503, detail="日历数据不存在；请先运行 build_derived.py。")
    return json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _report() -> dict[str, Any]:
    if not REPORT_PATH.exists():
        raise HTTPException(status_code=503, detail="质量报告不存在；请先运行 build_quality_report.py。")
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _spatial_grid() -> dict[str, Any]:
    if not SPATIAL_GRID_PATH.exists():
        raise HTTPException(status_code=503, detail="空间网格不存在；请先运行 build_spatial_grid.py。")
    return json.loads(SPATIAL_GRID_PATH.read_text(encoding="utf-8"))


def _athlete_profile() -> dict[str, Any]:
    if not ATHLETE_PROFILE_PATH.exists():
        raise HTTPException(status_code=404, detail="Athlete profile has not been synced yet.")
    return json.loads(ATHLETE_PROFILE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=256)
def _activity_insights(activity_id: str) -> dict[str, Any]:
    track_path = TRACKS_DIR / f"{activity_id}.geojson"
    if not track_path.is_file():
        raise HTTPException(status_code=404, detail="该活动没有可分析的 GPS 轨迹。")
    feature = json.loads(track_path.read_text(encoding="utf-8"))["features"][0]
    series = feature.get("properties", {}).get("series", {})
    distances = series.get("distance", [])
    speeds = series.get("enhanced_speed") or series.get("speed") or []
    heart_rates = series.get("heart_rate", [])
    altitudes = series.get("enhanced_altitude") or series.get("altitude") or []
    usable_speed = [float(value) for value in speeds if isinstance(value, (int, float)) and .8 <= value <= 8]
    paces = [1000 / speed for speed in usable_speed]
    pace_cv = statistics.pstdev(paces) / statistics.mean(paces) * 100 if len(paces) > 2 else None
    numeric_speed_count = sum(isinstance(value, (int, float)) for value in speeds)
    stopped_count = sum(isinstance(value, (int, float)) and value < .5 for value in speeds)
    stopped_ratio = stopped_count / numeric_speed_count if numeric_speed_count else None

    total_distance = max((float(value) for value in distances if isinstance(value, (int, float))), default=0)
    halves: list[list[float]] = [[], []]
    for index, distance_value in enumerate(distances):
        speed = speeds[index] if index < len(speeds) else None
        heart_rate = heart_rates[index] if index < len(heart_rates) else None
        if not isinstance(distance_value, (int, float)) or not isinstance(speed, (int, float)) or not isinstance(heart_rate, (int, float)) or speed < .8 or heart_rate <= 0:
            continue
        half = 0 if distance_value <= total_distance / 2 else 1
        halves[half].append(float(speed) / float(heart_rate))
    heart_rate_drift = None
    if len(halves[0]) >= 30 and len(halves[1]) >= 30:
        first_efficiency, second_efficiency = statistics.mean(halves[0]), statistics.mean(halves[1])
        heart_rate_drift = (first_efficiency - second_efficiency) / first_efficiency * 100 if first_efficiency else None

    if pace_cv is None:
        training_type = "数据不足"
    elif pace_cv < 6 and (stopped_ratio or 0) < .04:
        training_type = "稳定跑"
    elif pace_cv >= 14 or (stopped_ratio or 0) >= .08:
        training_type = "变速 / 间歇特征"
    else:
        training_type = "节奏变化跑"

    split_buckets: dict[int, dict[str, list[float]]] = defaultdict(lambda: {"speed": [], "heart_rate": [], "altitude": []})
    for index, distance_value in enumerate(distances):
        if not isinstance(distance_value, (int, float)):
            continue
        kilometer = math.floor(float(distance_value) / 1000) + 1
        if kilometer > math.ceil(total_distance / 1000):
            continue
        for field, values in (("speed", speeds), ("heart_rate", heart_rates), ("altitude", altitudes)):
            value = values[index] if index < len(values) else None
            if isinstance(value, (int, float)) and (field != "speed" or value > .8):
                split_buckets[kilometer][field].append(float(value))
    splits = []
    for kilometer, values in sorted(split_buckets.items()):
        average_speed = statistics.mean(values["speed"]) if values["speed"] else None
        splits.append({
            "kilometer": kilometer,
            "pace_s_per_km": round(1000 / average_speed, 1) if average_speed else None,
            "average_heart_rate": round(statistics.mean(values["heart_rate"]), 1) if values["heart_rate"] else None,
            "average_altitude_m": round(statistics.mean(values["altitude"]), 1) if values["altitude"] else None,
        })
    return {
        "activity_id": activity_id,
        "pace_cv_percent": round(pace_cv, 1) if pace_cv is not None else None,
        "heart_rate_drift_percent": round(heart_rate_drift, 1) if heart_rate_drift is not None else None,
        "stopped_ratio_percent": round(stopped_ratio * 100, 1) if stopped_ratio is not None else None,
        "training_type": training_type,
        "splits": splits,
        "notes": {
            "heart_rate_drift": "比较前后半程速度/心率效率变化，仅作为训练观察。",
            "classification": "由配速波动与低速占比自动推测，可与实际训练内容不同。",
        },
    }


def _assert_ready() -> None:
    if not _report()["readiness"]["api_ready"]:
        raise HTTPException(status_code=503, detail="数据质量尚未满足 API 启动条件。")


@app.get("/api/health")
def health(response: Response) -> dict[str, Any]:
    report = _report()
    if not report["readiness"]["api_ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if report["readiness"]["api_ready"] else "not_ready", "readiness": report["readiness"]}


@app.get("/api/quality-report")
def quality_report() -> dict[str, Any]:
    return _report()


@app.get("/api/athlete-profile")
def athlete_profile() -> dict[str, Any]:
    """Return verified personal fitness references used by activity charts."""
    return _athlete_profile()


@app.get("/api/activities")
def list_activities(
    start: Annotated[str | None, Query(description="起始日期 YYYY-MM-DD")] = None,
    end: Annotated[str | None, Query(description="结束日期 YYYY-MM-DD")] = None,
    sport: str | None = None,
    has_gps: bool | None = None,
    min_distance_km: float | None = Query(default=None, ge=0),
    max_distance_km: float | None = Query(default=None, ge=0),
    sort: str = Query(default="date_desc", pattern=r"^(date_desc|date_asc|distance_desc|distance_asc)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=576),
) -> dict[str, Any]:
    _assert_ready()
    rows = _activities()
    if start:
        rows = [row for row in rows if row["date"] and row["date"] >= start]
    if end:
        rows = [row for row in rows if row["date"] and row["date"] <= end]
    if sport:
        rows = [row for row in rows if str(row["sport"]) == sport]
    if has_gps is not None:
        rows = [row for row in rows if row["has_gps"] is has_gps]
    if min_distance_km is not None:
        rows = [row for row in rows if (row["distance_m"] or 0) >= min_distance_km * 1000]
    if max_distance_km is not None:
        rows = [row for row in rows if (row["distance_m"] or 0) <= max_distance_km * 1000]
    if sort.startswith("distance"):
        rows = sorted(rows, key=lambda row: row["distance_m"] or 0, reverse=sort.endswith("desc"))
    else:
        rows = sorted(rows, key=lambda row: row["start_time"] or "", reverse=sort.endswith("desc"))
    return {"total": len(rows), "items": rows[offset : offset + limit]}


@app.get("/api/calendar")
def calendar() -> list[dict[str, Any]]:
    _assert_ready()
    return _calendar()


@app.get("/api/stats/monthly")
def monthly_stats(
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="月份 YYYY-MM")],
) -> dict[str, Any]:
    """汇总指定月份的训练指标，供首页月度卡片使用。"""
    _assert_ready()
    rows = [row for row in _activities() if row["date"] and row["date"].startswith(month) and not row.get("training_excluded", False)]
    total_distance = sum(row["distance_m"] or 0 for row in rows)
    total_elapsed = sum(row["elapsed_s"] or 0 for row in rows)
    active_days = len({row["date"] for row in rows})
    sport_counts = Counter(str(row["sport"] or "unknown") for row in rows)
    return {
        "month": month,
        "activity_count": len(rows),
        "active_days": active_days,
        "total_distance_m": round(total_distance, 2),
        "total_elapsed_s": round(total_elapsed, 2),
        "average_distance_m": round(total_distance / active_days, 2) if active_days else None,
        "average_pace_s_per_km": round(total_elapsed / total_distance * 1000, 2) if total_distance else None,
        "total_ascent_m": round(sum(row["total_ascent_m"] or 0 for row in rows), 2),
        "activities_with_gps": sum(bool(row["has_gps"]) for row in rows),
        "sport_counts": dict(sorted(sport_counts.items())),
    }


@app.get("/api/stats/range")
def range_stats(
    start: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
    end: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
) -> dict[str, Any]:
    """日期范围统计与个人滚动训练负荷；负荷是相对观察指标，不是医疗建议。"""
    _assert_ready()
    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="起始日期不能晚于结束日期。")
    if (end_date - start_date).days > 1095:
        raise HTTPException(status_code=422, detail="单次统计范围不能超过三年。")

    history_start = start_date - timedelta(days=27)
    rows = [row for row in _activities() if row.get("date") and history_start.isoformat() <= row["date"] <= end
            and row.get("sport") == "running" and not row.get("training_excluded", False)]
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(row)

    daily: list[dict[str, Any]] = []
    cursor = history_start
    while cursor <= end_date:
        key = cursor.isoformat()
        items = by_day.get(key, [])
        elapsed = sum(float(item.get("elapsed_s") or 0) for item in items)
        weighted_hr_seconds = sum(float(item.get("average_heart_rate") or 0) * float(item.get("elapsed_s") or 0) for item in items if item.get("average_heart_rate"))
        hr_seconds = sum(float(item.get("elapsed_s") or 0) for item in items if item.get("average_heart_rate"))
        average_hr = weighted_hr_seconds / hr_seconds if hr_seconds else None
        duration_minutes = elapsed / 60
        relative_load = duration_minutes * ((average_hr / 150) ** 2 if average_hr else .65)
        daily.append({
            "date": key,
            "activity_count": len(items),
            "distance_m": round(sum(float(item.get("distance_m") or 0) for item in items), 2),
            "elapsed_s": round(elapsed, 2),
            "total_ascent_m": round(sum(float(item.get("total_ascent_m") or 0) for item in items), 2),
            "calories": round(sum(float(item.get("calories") or 0) for item in items), 2),
            "average_heart_rate": round(average_hr, 1) if average_hr else None,
            "relative_load": round(relative_load, 2),
        })
        cursor += timedelta(days=1)

    loads = [item["relative_load"] for item in daily]
    for index, item in enumerate(daily):
        item["load_7d"] = round(sum(loads[max(0, index - 6):index + 1]), 2)
        load_28d = sum(loads[max(0, index - 27):index + 1])
        item["load_28d"] = round(load_28d, 2)
        baseline_week = load_28d / min(4, (index + 1) / 7) if load_28d else 0
        item["load_ratio"] = round(item["load_7d"] / baseline_week, 2) if baseline_week else None

    visible = [item for item in daily if item["date"] >= start]
    weekly_map: dict[str, dict[str, Any]] = {}
    for item in visible:
        day = date.fromisoformat(item["date"])
        week = (day - timedelta(days=day.weekday())).isoformat()
        bucket = weekly_map.setdefault(week, {"week": week, "activity_count": 0, "distance_m": 0.0, "elapsed_s": 0.0, "relative_load": 0.0})
        for field in ("activity_count", "distance_m", "elapsed_s", "relative_load"):
            bucket[field] += item[field]
    weekly = [{**item, "distance_m": round(item["distance_m"], 2), "elapsed_s": round(item["elapsed_s"], 2), "relative_load": round(item["relative_load"], 2)} for item in weekly_map.values()]

    selected_rows = [row for row in rows if start <= row["date"] <= end]
    total_distance = sum(float(row.get("distance_m") or 0) for row in selected_rows)
    total_elapsed = sum(float(row.get("elapsed_s") or 0) for row in selected_rows)
    active_days = len({row["date"] for row in selected_rows})
    current_ratio = visible[-1]["load_ratio"] if visible else None
    load_status = "insufficient"
    if current_ratio is not None:
        load_status = "recovery" if current_ratio < .75 else "balanced" if current_ratio <= 1.25 else "rising" if current_ratio <= 1.5 else "high"
    return {
        "start": start,
        "end": end,
        "summary": {
            "activity_count": len(selected_rows),
            "active_days": active_days,
            "total_distance_m": round(total_distance, 2),
            "total_elapsed_s": round(total_elapsed, 2),
            "total_ascent_m": round(sum(float(row.get("total_ascent_m") or 0) for row in selected_rows), 2),
            "calories": round(sum(float(row.get("calories") or 0) for row in selected_rows), 2),
            "average_pace_s_per_km": round(total_elapsed / total_distance * 1000, 2) if total_distance else None,
            "average_distance_m": round(total_distance / active_days, 2) if active_days else None,
            "load_ratio": current_ratio,
            "load_status": load_status,
        },
        "daily": visible,
        "weekly": weekly,
        "load_note": "仅统计正式跑步；相对负荷基于时长与平均心率，不是 COROS 负荷。混合／排除活动与其他运动保留在活动列表。",
    }


@app.get("/api/map/heat-grid")
def heat_grid(
    start: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    end: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    min_visits: int = Query(default=1, ge=1, le=100),
) -> dict[str, Any]:
    """读取预计算的 250 米探索网格，并按活动日期过滤。"""
    _assert_ready()
    source = _spatial_grid()
    features: list[dict[str, Any]] = []
    for cell in source["cells"]:
        matches = [item for item in cell["activities"] if (not start or item["date"] >= start) and (not end or item["date"] <= end)]
        if len(matches) < min_visits:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [cell["longitude"], cell["latitude"]]},
            "properties": {
                "cell_id": cell["cell_id"],
                "visits": len(matches),
                "distance_m": round(sum(item["distance_m"] for item in matches), 1),
                "first_date": min(item["date"] for item in matches),
                "last_date": max(item["date"] for item in matches),
            },
        })
    return {"type": "FeatureCollection", "cell_size_m": source["cell_size_m"], "feature_count": len(features), "features": features}


@app.get("/api/activities/{activity_id}")
def activity_detail(activity_id: str) -> dict[str, Any]:
    _assert_ready()
    for row in _activities():
        if row["id"] == activity_id:
            return row
    raise HTTPException(status_code=404, detail="未找到该活动。")


@app.get("/api/activities/{activity_id}/track")
def activity_track(activity_id: str) -> dict[str, Any]:
    _assert_ready()
    track_path = TRACKS_DIR / f"{activity_id}.geojson"
    if not track_path.is_file():
        raise HTTPException(status_code=404, detail="该活动没有可用 GPS 轨迹。")
    return json.loads(track_path.read_text(encoding="utf-8"))


@app.get("/api/activities/{activity_id}/insights")
def activity_insights(activity_id: str) -> dict[str, Any]:
    _assert_ready()
    return _activity_insights(activity_id)
