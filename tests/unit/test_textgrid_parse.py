"""TextGrid 短格式解析器单元测试。"""

from __future__ import annotations

from jrh.importers.textgrid import parse_textgrid

SAMPLE = """File type = "ooTextFile"
Object class = "TextGrid"

xmin = 0
xmax = 1.5
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = 1.5
        intervals: size = 1
        intervals [1]:
            xmin = 0.0
            xmax = 1.5
            text = "dummy"
    item [2]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = 1.5
        intervals: size = 3
        intervals [1]:
            xmin = 0.0
            xmax = 0.3
            text = "k"
        intervals [2]:
            xmin = 0.3
            xmax = 0.8
            text = "a"
        intervals [3]:
            xmin = 0.8
            xmax = 1.5
            text = ""
"""


class TestParseTextGrid:
    def test_tiers_and_intervals(self):
        grid = parse_textgrid(SAMPLE)
        assert grid.xmin == 0.0 and grid.xmax == 1.5
        phones = grid.tier("phones")
        assert len(phones) == 3
        assert [(p.text, p.xmin, p.xmax) for p in phones] == [
            ("k", 0.0, 0.3),
            ("a", 0.3, 0.8),
            ("", 0.8, 1.5),
        ]
        assert [p.text for p in grid.tier("words")] == ["dummy"]

    def test_missing_tier_returns_empty(self):
        grid = parse_textgrid(SAMPLE)
        assert grid.tier("nope") == []

    def test_empty_text_preserved(self):
        grid = parse_textgrid(SAMPLE)
        assert grid.tier("phones")[-1].text == ""
