"""Timing 派生公式单元测试（JRH_SPEC §4.5、§5.1，手工计算值）。"""

from __future__ import annotations

import pytest

from jrh.core.errors import InvalidInputError
from jrh.core.model import Timing


def t(**kw):
    base = Timing(48000.0, 22000.0, -115200.0, 14400.0, 9600.0)
    for k, v in kw.items():
        setattr(base, k, v)
    return base


class TestTimingConstants:
    def test_window(self):
        x = t()
        assert x.window_end() == 48000 + 115200
        assert x.window_duration() == 115200
        assert x.body_start() == 48000 + 14400

    def test_to_ms_formula(self):
        x = Timing(2205, 11025, -35280, 4410, 4410)
        ms = x.to_ms(44100)
        assert ms == {
            "offset": 50.0,
            "consonant": 250.0,
            "cutoff": -800.0,
            "preutterance": 100.0,
            "overlap": 100.0,
        }

    def test_to_ms_rounding_3(self):
        x = Timing(1, 2, -3, 4, 5)
        ms = x.to_ms(44100)
        assert ms["offset"] == round(1 * 1000 / 44100, 3)


class TestTransitionFormula:
    def test_transition_params(self):
        x = Timing(35280, 11025, -39690, 4410, 4410)
        tr = x.transition_timing()
        assert tr is not None
        assert tr.offset == 35280
        assert tr.consonant == 11025
        assert tr.cutoff == -11025  # 区域 = [offset, offset+consonant]
        assert tr.preutterance == 0
        assert tr.overlap == min(4410, 11025)

    def test_transition_none_when_consonant_zero(self):
        x = Timing(66150, 0, -17640, 0, 0)
        assert x.transition_timing() is None

    def test_transition_overlap_clamped(self):
        x = Timing(0, 100, -1000, 0, 500)
        tr = x.transition_timing()
        assert tr.overlap == 100  # min(overlap, consonant)


class TestBodyFormula:
    def test_body_params(self):
        x = Timing(35280, 11025, -39690, 4410, 4410)
        b = x.body_timing()
        assert b.offset == 35280 + 4410
        assert b.cutoff == -39690 + 4410
        assert b.consonant == max(11025 - 4410, 0)
        assert b.preutterance == 0
        assert b.overlap == 0

    def test_body_consonant_clamped_zero(self):
        x = Timing(0, 100, -1000, 500, 0)
        assert x.body_timing().consonant == 0  # max(100-500, 0)

    def test_body_cutoff_never_positive(self):
        x = Timing(0, 100, -1000, 1000, 0)
        assert x.body_timing().cutoff == 0

    def test_identity_full_window_vowel(self):
        # 纯元音：consonant/preutterance/overlap 全 0
        x = Timing(66150, 0, -17640, 0, 0)
        assert x.transition_timing() is None
        b = x.body_timing()
        assert b.offset == 66150 and b.cutoff == -17640 and b.consonant == 0


class TestConstraints:
    def test_valid_vcv_window(self):
        assert t().constraint_errors() == []

    def test_cutoff_must_be_negative(self):
        errs = t(cutoff=100).constraint_errors()
        assert any("负值" in e for e in errs)

    def test_zero_length_window(self):
        errs = t(cutoff=0).constraint_errors()
        assert any("窗口时长必须 > 0" in e for e in errs)

    def test_overlap_le_preutterance(self):
        errs = t(overlap=20000, preutterance=10000).constraint_errors()
        assert any("overlap ≤ preutterance" in e for e in errs)

    def test_preutterance_le_window(self):
        errs = t(preutterance=200000).constraint_errors()
        assert any("preutterance ≤ |cutoff|" in e for e in errs)

    def test_consonant_le_window(self):
        errs = t(consonant=200000).constraint_errors()
        assert any("consonant ≤ |cutoff|" in e for e in errs)

    def test_negative_values(self):
        for kw in ("offset", "consonant", "preutterance", "overlap"):
            errs = t(**{kw: -5.0}).constraint_errors()
            assert len(errs) >= 1


class TestTimingSerialization:
    def test_roundtrip(self):
        x = t()
        assert Timing.from_dict(x.to_dict()) == x

    def test_nan_rejected(self):
        with pytest.raises(InvalidInputError):
            Timing.from_dict(
                {
                    "offset": float("nan"),
                    "consonant": 1,
                    "cutoff": -1,
                    "preutterance": 0,
                    "overlap": 0,
                }
            )
