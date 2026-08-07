"""批量归档 FIT：保留全部可解析消息，不修改原始文件。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.fit_archive import archive_fit_file, archive_fitdecode_file, write_json  # noqa: E402
from app.paths import DEFAULT_FIT_SOURCE, FULL_ACTIVITIES_DIR, PROCESSED_DIR, ensure_processed_directories  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_FIT_SOURCE, help="FIT 文件目录")
    parser.add_argument("--force", action="store_true", help="即使归档已存在也重新解析")
    parser.add_argument("--repair-partial", action="store_true", help="仅重新尝试已标记为部分解析的文件")
    parser.add_argument("--limit", type=int, help="仅处理前 N 个文件，供开发调试")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_dir():
        raise SystemExit(f"FIT 源目录不存在：{source}")
    ensure_processed_directories()
    files = sorted(source.glob("*.fit"))
    if args.limit:
        files = files[: args.limit]
    failures: list[dict[str, str]] = []
    written = skipped = 0
    for index, fit_path in enumerate(files, start=1):
        target = FULL_ACTIVITIES_DIR / f"{fit_path.stem}.full.json"
        if target.exists() and not args.force:
            if not args.repair_partial:
                skipped += 1
                continue
            existing = __import__("json").loads(target.read_text(encoding="utf-8"))
            if existing.get("parse", {}).get("status") != "partial_or_failed":
                skipped += 1
                continue
        archive = archive_fit_file(fit_path, source)
        if archive["parse"]["status"] == "partial_or_failed":
            recovered = archive_fitdecode_file(fit_path, source)
            if recovered["parse"]["status"] != "partial_or_failed" and len(recovered["messages"]) > len(archive["messages"]):
                recovered["parse"]["recovered_from"] = archive["parse"]
                archive = recovered
        write_json(target, archive)
        written += 1
        if archive["parse"]["status"] == "partial_or_failed":
            failures.append({"activity_id": fit_path.stem, "source_file": fit_path.name, "error": archive["parse"]["error"] or "unknown"})
        print(f"[{index}/{len(files)}] {fit_path.name}: {archive['parse']['status']}")
    write_json(PROCESSED_DIR / "invalid-files.json", failures)
    print(f"完成：写入 {written}，跳过 {skipped}，异常/部分解析 {len(failures)}。")


if __name__ == "__main__":
    main()
