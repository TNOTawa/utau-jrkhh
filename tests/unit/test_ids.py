"""永久坐标与 ID 分配器单元测试。"""

from __future__ import annotations

import pytest

from jrh.core.errors import InvalidInputError
from jrh.core.ids import (
    IdAllocator,
    IdCounters,
    format_coordinate,
    is_coordinate,
    parse_coordinate,
)


class TestCoordinate:
    def test_format_parse_roundtrip(self):
        assert format_coordinate(12, 6) == "12:6"
        assert parse_coordinate("12:6") == (12, 6)

    def test_parse_strip_whitespace(self):
        assert parse_coordinate(" 1:2 ") == (1, 2)

    @pytest.mark.parametrize(
        "bad",
        ["", "1", "1-2", "1.2", "a:b", "1:", ":2", "1:2:3", "１２:２", None, 12],
    )
    def test_parse_invalid(self, bad):
        with pytest.raises(InvalidInputError):
            parse_coordinate(bad)

    def test_is_coordinate(self):
        assert is_coordinate("1:2")
        assert not is_coordinate("abc")
        assert not is_coordinate(12)


class TestIdCounters:
    def test_roundtrip(self):
        c = IdCounters(3, 9)
        assert IdCounters.from_dict(c.to_dict()) == c

    @pytest.mark.parametrize("d", [{"max_sentence_id_ever": -1}, {"max_unit_id_ever": "x"}])
    def test_invalid(self, d):
        with pytest.raises(InvalidInputError):
            IdCounters.from_dict(d)


class TestIdAllocator:
    def test_never_reuses_after_freeze(self):
        alloc = IdAllocator(IdCounters(0, 0))
        ids = [alloc.next_sentence_id() for _ in range(5)]
        assert ids == [1, 2, 3, 4, 5]
        assert alloc.next_unit_id() == 1
        assert alloc.next_unit_id() == 2
        # 即使中间编号已删除，新编号也继续递增（不复用）
        assert alloc.next_unit_id() == 3
        assert alloc.next_sentence_id() == 6

    def test_counters_persist(self):
        alloc = IdAllocator(IdCounters(7, 42))
        assert alloc.next_sentence_id() == 8
        assert alloc.next_unit_id() == 43
