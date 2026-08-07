"""诊断 FIT 结构与解析兼容性；不会修改原始文件或派生数据。"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import fitdecode
from fitparse import FitFile

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.paths import DEFAULT_FIT_SOURCE, PROCESSED_DIR  # noqa: E402


def fit_header(path: Path) -> dict[str, Any]:
    """读取 FIT 公开头字段及文件长度一致性，不对文件作任何写操作。"""
    raw = path.read_bytes()
    if not raw:
        return {"file_bytes": 0, "valid": False, "error": "empty file"}
    header_size = raw[0]
    result: dict[str, Any] = {"file_bytes": len(raw), "header_size": header_size}
    if len(raw) < 12 or header_size < 12 or len(raw) < header_size:
        result.update({"valid": False, "error": "truncated FIT header"})
        return result
    data_size = int.from_bytes(raw[4:8], "little")
    result.update(
        {
            "protocol_version": raw[1],
            "profile_version": int.from_bytes(raw[2:4], "little"),
            "data_size": data_size,
            "magic": raw[8:12].decode("ascii", errors="replace"),
            "expected_file_bytes": header_size + data_size + 2,
            "size_matches_header": len(raw) == header_size + data_size + 2,
            "valid": raw[8:12] == b".FIT",
        }
    )
    return result


def probe_fitparse(path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    try:
        for message in FitFile(str(path)).get_messages():
            counts[message.name] += 1
    except Exception as error:
        return {"status": "error", "error": f"{type(error).__name__}: {error}", "message_counts": dict(counts)}
    return {"status": "complete", "error": None, "message_counts": dict(counts)}


def probe_fitdecode(path: Path) -> dict[str, Any]:
    """用第二个解析器尝试读取。WARN 模式可忽略部分 CRC/格式警告继续前进。"""
    counts: Counter[str] = Counter()
    try:
        with fitdecode.FitReader(
            str(path),
            check_crc=fitdecode.CrcCheck.WARN,
            error_handling=fitdecode.ErrorHandling.WARN,
        ) as reader:
            for frame in reader:
                if isinstance(frame, fitdecode.FitDataMessage):
                    counts[frame.name] += 1
    except Exception as error:
        return {"status": "error", "error": f"{type(error).__name__}: {error}", "message_counts": dict(counts)}
    return {"status": "complete", "error": None, "message_counts": dict(counts)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fit_file", type=Path, help="待诊断的单个 FIT 文件")
    parser.add_argument("--report-dir", type=Path, default=PROCESSED_DIR / "diagnostics")
    args = parser.parse_args()
    path = args.fit_file.resolve()
    if not path.is_file() or path.suffix.lower() != ".fit":
        raise SystemExit(f"不是有效 FIT 文件：{path}")

    report = {
        "source_file": str(path),
        "header": fit_header(path),
        "fitparse": probe_fitparse(path),
        "fitdecode": probe_fitdecode(path),
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report_dir / f"{path.stem}.diagnostic.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"报告：{report_path}")
    print(f"头部：magic={report['header'].get('magic')}，长度匹配={report['header'].get('size_matches_header')}")
    for parser_name in ("fitparse", "fitdecode"):
        result = report[parser_name]
        records = result["message_counts"].get("record", 0)
        print(f"{parser_name}: {result['status']}，record={records}，error={result['error']}")


if __name__ == "__main__":
    main()
