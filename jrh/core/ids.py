"""永久坐标与 ID 分配器。

坐标格式：`s:u`（sentence_id:unit_id），程序内部唯一身份。
五段式别名后三项只是可读说明，身份定位一律通过本模块。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import InvalidInputError

_COORD_RE = re.compile(r"^([0-9]+):([0-9]+)$")


def format_coordinate(sentence_id: int, unit_id: int) -> str:
    return f"{sentence_id}:{unit_id}"


def parse_coordinate(text: str) -> tuple[int, int]:
    """解析 `s:u`；非法输入抛 InvalidInputError。"""
    if not isinstance(text, str):
        raise InvalidInputError(f"坐标必须是字符串 's:u'，实际为 {text!r}")
    m = _COORD_RE.match(text.strip())
    if not m:
        raise InvalidInputError(f"非法坐标: {text!r}（应为 '句号:字号'，如 12:6）")
    return int(m.group(1)), int(m.group(2))


def is_coordinate(text: str) -> bool:
    return bool(_COORD_RE.match(text.strip())) if isinstance(text, str) else False


@dataclass
class IdCounters:
    """冻结后编号只增不改、不复用的计数器。"""

    max_sentence_id_ever: int = 0
    max_unit_id_ever: int = 0

    def to_dict(self) -> dict:
        return {
            "max_sentence_id_ever": self.max_sentence_id_ever,
            "max_unit_id_ever": self.max_unit_id_ever,
        }

    @classmethod
    def from_dict(cls, d: dict) -> IdCounters:
        ms = d.get("max_sentence_id_ever", 0)
        mu = d.get("max_unit_id_ever", 0)
        if not isinstance(ms, int) or not isinstance(mu, int) or ms < 0 or mu < 0:
            raise InvalidInputError("id_counters 结构错误")
        return cls(ms, mu)


class IdAllocator:
    """为冻结后的新增对象分配永不重复的编号。"""

    def __init__(self, counters: IdCounters):
        self._counters = counters

    @property
    def counters(self) -> IdCounters:
        return self._counters

    def next_sentence_id(self) -> int:
        self._counters.max_sentence_id_ever += 1
        return self._counters.max_sentence_id_ever

    def next_unit_id(self) -> int:
        self._counters.max_unit_id_ever += 1
        return self._counters.max_unit_id_ever
