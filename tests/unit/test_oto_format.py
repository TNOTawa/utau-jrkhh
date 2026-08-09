"""oto.ini 格式适配层单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from jrh.core.errors import DataError
from jrh.formats.oto_ini import OtoLine, fmt_ms, read_oto, write_oto


class TestFmtMs:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (50.0, "50"),
            (250.0, "250"),
            (-800.0, "-800"),
            (0.0, "0"),
            (-0.0, "0"),
            (85.6, "85.6"),
            (85.633, "85.633"),
            (85.6334, "85.633"),
            (0.005, "0.005"),
            (1e-12, "0"),
        ],
    )
    def test_formatting(self, value, expected):
        assert fmt_ms(value) == expected


class TestOtoRoundTrip:
    def test_write_read_roundtrip(self, tmp_path: Path):
        lines = [
            OtoLine("sentence_001.wav", "1-2-ni-hao-a", 800.0, 250.0, -900.0, 100.0, 100.0),
            OtoLine("sentence_001.wav", "hao", 900.0, 150.0, -800.0, 0.0, 0.0),
        ]
        p = tmp_path / "oto.ini"
        write_oto(p, lines)
        got = read_oto(p)
        assert [line.alias for line in got] == ["1-2-ni-hao-a", "hao"]
        assert got[0].offset_ms == 800.0
        assert got[0].cutoff_ms == -900.0

    def test_read_shift_jis(self, tmp_path: Path):
        p = tmp_path / "oto.ini"
        raw = "あ.wav=あ,50,250,-800,100,100\n".encode("shift_jis")
        p.write_bytes(raw)
        got = read_oto(p)
        assert got[0].wav == "あ.wav"
        assert got[0].alias == "あ"

    def test_read_missing(self, tmp_path: Path):
        with pytest.raises(DataError):
            read_oto(tmp_path / "nope.ini")

    def test_read_ignores_comments_and_blanks(self, tmp_path: Path):
        p = tmp_path / "oto.ini"
        p.write_text("# comment\n\nx.wav=a,1,2,-3,4,5\n", encoding="utf-8")
        assert len(read_oto(p)) == 1
