"""基于完整归档生成导入质量报告，并判断页面 API 是否可安全启用。"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.fit_archive import write_json  # noqa: E402
from app.paths import DEFAULT_FIT_SOURCE, FULL_ACTIVITIES_DIR, PROCESSED_DIR  # noqa: E402

SUCCESS_STATUSES = {"complete", "complete_with_warnings"}
MIN_SUCCESS_RATIO = 0.98
MAX_PARTIAL_RATIO = 0.02


def build_report(source_dir: Path, full_dir: Path) -> dict[str, Any]:
    fit_files = sorted(source_dir.glob("*.fit"))
    activities_path = PROCESSED_DIR / "activities.json"
    if not activities_path.is_file():
        raise FileNotFoundError("缺少 activities.json；请先运行 build_derived.py。")
    summaries: list[dict[str, Any]] = json.loads(activities_path.read_text(encoding="utf-8"))
    source_ids = {path.stem for path in fit_files}
    archive_ids = {path.name.removesuffix(".full.json") for path in full_dir.glob("*.full.json")}
    statuses = Counter(item["parse_status"] for item in summaries)
    sports = Counter(str(item["sport"]) for item in summaries if item["sport"] is not None)
    dates = sorted(item["date"] for item in summaries if item["date"])
    archive_count = len(archive_ids)
    success_count = sum(statuses[status] for status in SUCCESS_STATUSES)
    partial_count = statuses["partial_or_failed"]
    success_ratio = success_count / archive_count if archive_count else 0.0
    partial_ratio = partial_count / archive_count if archive_count else 1.0
    missing = sorted(source_ids - archive_ids)
    rules = {
        "source_fully_archived": not missing and len(fit_files) == archive_count,
        "derived_index_matches_archives": len(summaries) == archive_count,
        "success_ratio_at_least_0_98": success_ratio >= MIN_SUCCESS_RATIO,
        "partial_ratio_at_most_0_02": partial_ratio <= MAX_PARTIAL_RATIO,
        "has_at_least_one_activity": archive_count > 0,
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "directory": str(source_dir),
            "fit_file_count": len(fit_files),
            "archived_activity_count": archive_count,
            "derived_activity_count": len(summaries),
            "missing_archive_ids": missing,
        },
        "parse_quality": {
            "status_counts": dict(sorted(statuses.items())),
            "parser_counts": {"note": "解析器详情保存在每个 .full.json 中；轻量索引不重复保存该字段。"},
            "successful_activity_count": success_count,
            "partial_or_failed_count": partial_count,
            "success_ratio": round(success_ratio, 6),
            "partial_ratio": round(partial_ratio, 6),
            "activities_with_parser_warnings": None,
        },
        "data_coverage": {
            "activities_with_gps": sum(item["has_gps"] for item in summaries),
            "activities_with_dates": len(dates),
            "date_range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
            "sport_counts": dict(sorted(sports.items())),
            "total_distance_m": round(sum(item["distance_m"] or 0 for item in summaries), 2),
            "total_elapsed_s": round(sum(item["elapsed_s"] or 0 for item in summaries), 2),
            "total_record_count": sum(item["record_count"] for item in summaries),
        },
        "readiness": {
            "rules": rules,
            "api_ready": all(rules.values()),
            "message": "派生数据质量满足最小只读 API 条件。" if all(rules.values()) else "请先解决未归档或部分解析比例过高的问题。",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_FIT_SOURCE)
    parser.add_argument("--output", type=Path, default=PROCESSED_DIR / "import-report.json")
    args = parser.parse_args()
    report = build_report(args.source.resolve(), FULL_ACTIVITIES_DIR)
    write_json(args.output, report)
    print(f"质量报告：{args.output}")
    print(f"API 就绪：{report['readiness']['api_ready']}；{report['readiness']['message']}")


if __name__ == "__main__":
    main()
