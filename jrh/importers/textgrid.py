"""Praat TextGrid（short format）解析器（仅 IntervalTier 的 words/phones 层需求）。

纯 stdlib；与 jrh/core 无依赖（导入器专用）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Interval:
    xmin: float
    xmax: float
    text: str


@dataclass
class TextGrid:
    xmin: float = 0.0
    xmax: float = 0.0
    tiers: dict[str, list[Interval]] = field(default_factory=dict)

    def tier(self, name: str) -> list[Interval]:
        return self.tiers.get(name, [])


_NAME_RE = re.compile(r'^\s*name = "(.*)"\s*$')
_XMIN_RE = re.compile(r"^\s*xmin = ([\d.eE+-]+)\s*$")
_XMAX_RE = re.compile(r"^\s*xmax = ([\d.eE+-]+)\s*$")
_TEXT_RE = re.compile(r'^\s*text = "(.*)"\s*$')


def parse_textgrid(text: str) -> TextGrid:
    """解析 short-format TextGrid 文本（容错：缺 tiers 头/空文本均可）。"""
    grid = TextGrid()
    current: str | None = None
    cur_xmin: float | None = None
    cur_xmax: float | None = None
    top_seen = False

    def flush() -> None:
        nonlocal cur_xmin, cur_xmax
        if current is not None and cur_xmin is not None and cur_xmax is not None:
            grid.tiers.setdefault(current, []).append(Interval(cur_xmin, cur_xmax, ""))
        cur_xmin = cur_xmax = None

    for line in text.splitlines():
        if not line.strip():
            continue
        m = _NAME_RE.match(line)
        if m:
            flush()
            current = m.group(1)
            grid.tiers.setdefault(current, [])
            continue
        m = _XMIN_RE.match(line)
        if m:
            if current is None and not top_seen:
                grid.xmin = float(m.group(1))
                top_seen = True
            elif current is not None:
                cur_xmin = float(m.group(1))
            continue
        m = _XMAX_RE.match(line)
        if m:
            if current is None:
                grid.xmax = float(m.group(1))
            else:
                cur_xmax = float(m.group(1))
            continue
        m = _TEXT_RE.match(line)
        if m and current is not None:
            if cur_xmin is not None and cur_xmax is not None:
                grid.tiers[current].append(Interval(cur_xmin, cur_xmax, m.group(1)))
                cur_xmin = cur_xmax = None
            continue
    flush()
    return grid


def read_textgrid(path: Path) -> TextGrid:
    return parse_textgrid(path.read_text(encoding="utf-8", errors="replace"))
