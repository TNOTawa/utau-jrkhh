"""通用工具：原子写、严格 JSON 读写、确定性排序辅助。"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import DataError, NotFoundError

JSON_OPTS = {"sort_keys": True, "ensure_ascii": False, "indent": 2}


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """原子写文本：同目录临时文件 + os.replace。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def write_json(path: Path, obj: Any) -> None:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, text)


def read_json_strict(path: Path, what: str = "JSON 文件") -> Any:
    """读取 JSON；文件缺失/损坏时抛出带上下文的 DataError。"""
    path = Path(path)
    if not path.exists():
        raise NotFoundError(f"{what}不存在: {path}")
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise DataError(f"无法读取 {what} {path}: {e}") from e
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise DataError(f"{what}损坏（不是合法 UTF-8 JSON）: {path}: {e}") from e


def expect_dict(obj: Any, what: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise DataError(f"{what}结构错误：应为对象（dict），实际为 {type(obj).__name__}")
    return obj


def expect_list(obj: Any, what: str) -> list:
    if not isinstance(obj, list):
        raise DataError(f"{what}结构错误：应为数组（list），实际为 {type(obj).__name__}")
    return obj
