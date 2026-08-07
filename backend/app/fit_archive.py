"""将 FIT 中所有可解析消息无损地归档为 JSON 友好的结构。"""

from __future__ import annotations

import base64
import hashlib
import json
import warnings
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from fitparse import FitFile
import fitdecode


SCHEMA_VERSION = 1


def json_value(value: Any) -> Any:
    """将 fitparse 返回的值转换为 JSON；未知值保留其字符串表示。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return str(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_fit_file(fit_path: Path, source_root: Path) -> dict[str, Any]:
    """解析一个 FIT，并返回全部可识别消息。

    即使部分解析失败，调用方也可将已解析内容连同错误状态写入磁盘。
    原始 FIT 始终由本函数外的原文件保留。
    """
    message_counts: Counter[str] = Counter()
    messages: list[dict[str, Any]] = []
    parse_error: str | None = None

    try:
        for message in FitFile(str(fit_path)).get_messages():
            message_name = message.name
            fields: dict[str, Any] = {}
            field_metadata: dict[str, dict[str, Any]] = {}
            for field in message:
                fields[field.name] = json_value(field.value)
                metadata = {
                    key: json_value(getattr(field, key, None))
                    for key in ("units", "type", "def_num")
                    if getattr(field, key, None) is not None
                }
                if metadata:
                    field_metadata[field.name] = metadata
            item: dict[str, Any] = {"message_type": message_name, "fields": fields}
            if field_metadata:
                item["field_metadata"] = field_metadata
            messages.append(item)
            message_counts[message_name] += 1
    except Exception as error:  # 单个坏 FIT 不应阻断批次
        parse_error = f"{type(error).__name__}: {error}"

    try:
        source_path = fit_path.relative_to(source_root).as_posix()
    except ValueError:
        source_path = fit_path.name

    return {
        "schema_version": SCHEMA_VERSION,
        "activity_id": fit_path.stem,
        "source": {
            "path": source_path,
            "filename": fit_path.name,
            "bytes": fit_path.stat().st_size,
            "sha256": sha256_file(fit_path),
        },
        "parse": {
            "status": "complete" if parse_error is None else "partial_or_failed",
            "parser": "fitparse",
            "error": parse_error,
            "message_counts": dict(sorted(message_counts.items())),
        },
        "messages": messages,
    }


def archive_fitdecode_file(fit_path: Path, source_root: Path) -> dict[str, Any]:
    """用 fitdecode 的宽容模式恢复 fitparse 无法完整读取的 FIT。"""
    message_counts: Counter[str] = Counter()
    messages: list[dict[str, Any]] = []
    parse_error: str | None = None
    parser_warnings: list[str] = []
    try:
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            with fitdecode.FitReader(
                str(fit_path),
                check_crc=fitdecode.CrcCheck.WARN,
                error_handling=fitdecode.ErrorHandling.WARN,
            ) as reader:
                for message in reader:
                    if not isinstance(message, fitdecode.FitDataMessage):
                        continue
                    fields: dict[str, Any] = {}
                    field_metadata: dict[str, dict[str, Any]] = {}
                    for field in message.fields:
                        # 重名字段极少见；保留全部值而不是静默覆盖。
                        value = json_value(field.value)
                        if field.name in fields:
                            fields[field.name] = fields[field.name] + [value] if isinstance(fields[field.name], list) else [fields[field.name], value]
                        else:
                            fields[field.name] = value
                        metadata = {
                            key: json_value(getattr(field, key, None))
                            for key in ("units", "field_type", "type", "def_num")
                            if getattr(field, key, None) is not None
                        }
                        if metadata:
                            field_metadata[field.name] = metadata
                    item: dict[str, Any] = {"message_type": message.name, "fields": fields}
                    if field_metadata:
                        item["field_metadata"] = field_metadata
                    messages.append(item)
                    message_counts[message.name] += 1
            parser_warnings = [str(item.message) for item in caught_warnings]
    except Exception as error:
        parse_error = f"{type(error).__name__}: {error}"

    try:
        source_path = fit_path.relative_to(source_root).as_posix()
    except ValueError:
        source_path = fit_path.name
    return {
        "schema_version": SCHEMA_VERSION,
        "activity_id": fit_path.stem,
        "source": {
            "path": source_path,
            "filename": fit_path.name,
            "bytes": fit_path.stat().st_size,
            "sha256": sha256_file(fit_path),
        },
        "parse": {
            "status": "partial_or_failed" if parse_error else ("complete_with_warnings" if parser_warnings else "complete"),
            "parser": "fitdecode",
            "error": parse_error,
            "warnings": parser_warnings,
            "message_counts": dict(sorted(message_counts.items())),
        },
        "messages": messages,
    }


def write_json(path: Path, payload: Any) -> None:
    """以 UTF-8 JSON 写入，不修改任何原始数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
