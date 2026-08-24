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


class TestVcFormula:
    """VC 过渡派生公式（JRH_SPEC §5 VC 派生，手工计算值）。"""

    def test_vc_params_mid_vowel(self):
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)  # 元音侧：窗口 [0, 200)
        v = Timing(210.0, 60.0, -180.0, 0.0, 0.0)  # 辅音侧：元音起点 270
        vc = u.vc_timing(v, 0.5, 0.5)
        assert vc.offset == 100.0  # 元音中点（200 - 200*0.5）
        assert vc.preutterance == 100.0  # 边界位置 = 元音尾
        assert vc.consonant == 170.0  # 270 - 100（= 区域全长）
        assert vc.cutoff == -170.0
        assert vc.overlap == 50.0  # 100 * 0.5
        assert vc.constraint_errors() == []

    def test_vc_vowel_region_excludes_consonant(self):
        u = Timing(100.0, 40.0, -300.0, 0.0, 0.0)  # 元音区 = 300-40 = 260
        v = Timing(400.0, 60.0, -180.0, 0.0, 0.0)  # 元音起点 460
        vc = u.vc_timing(v, 0.5, 0.5)
        assert vc.preutterance == 130.0  # 260 * 0.5
        assert vc.offset == 400.0 - 130.0  # window_end=400
        assert vc.consonant == 460.0 - 270.0  # = 区域全长 190
        assert vc.cutoff == -190.0
        assert vc.overlap == 65.0
        assert vc.constraint_errors() == []

    def test_vc_none_when_next_consonant_zero(self):
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)
        v = Timing(210.0, 0.0, -180.0, 0.0, 0.0)
        assert u.vc_timing(v, 0.5, 0.5) is None

    def test_vc_none_when_vowel_region_empty(self):
        u = Timing(0.0, 200.0, -200.0, 0.0, 0.0)  # consonant == |cutoff|
        v = Timing(210.0, 60.0, -180.0, 0.0, 0.0)
        assert u.vc_timing(v, 0.5, 0.5) is None

    def test_vc_none_when_window_nonpositive(self):
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)  # offset = 100
        v = Timing(50.0, 20.0, -180.0, 0.0, 0.0)  # 元音起点 70 < 100
        assert u.vc_timing(v, 0.5, 0.5) is None

    def test_vc_none_when_pre_exceeds_window(self):
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)  # pre = 100
        v = Timing(170.0, 25.0, -180.0, 0.0, 0.0)  # 元音起点 195 → window 95 < 100
        assert u.vc_timing(v, 0.5, 0.5) is None

    def test_vc_ratio_validation(self):
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)
        v = Timing(210.0, 60.0, -180.0, 0.0, 0.0)
        with pytest.raises(InvalidInputError):
            u.vc_timing(v, 1.5, 0.5)
        with pytest.raises(InvalidInputError):
            u.vc_timing(v, 0.5, -0.1)

    def test_vc_ratio_boundary_zero_valid(self):
        # ratio 恰为 0：VC 区 = 下一辅音整段（preutterance=0）
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)
        v = Timing(210.0, 60.0, -180.0, 0.0, 0.0)
        vc = u.vc_timing(v, 0.0, 0.0)
        assert vc is not None
        assert vc.offset == 200.0
        assert vc.consonant == 70.0
        assert vc.cutoff == -70.0
        assert vc.preutterance == 0.0
        assert vc.overlap == 0.0
        assert vc.constraint_errors() == []

    def test_vc_ratio_boundary_one_valid(self):
        # ratio 恰为 1：offset = 元音起点（窗口 = 全元音尾 + 辅音）
        u = Timing(0.0, 40.0, -200.0, 0.0, 0.0)  # 元音起点 40
        v = Timing(210.0, 60.0, -180.0, 0.0, 0.0)
        vc = u.vc_timing(v, 1.0, 1.0)
        assert vc is not None
        assert vc.offset == 40.0
        assert vc.preutterance == 160.0  # 元音尾 = 200 - 40
        assert vc.cutoff == -(270.0 - 40.0)
        assert vc.overlap == 160.0
        assert vc.constraint_errors() == []

    def test_vc_fractional_vowel_region_generates(self):
        # 元音区 0.5 采样：仍生成（边界 0 与 1 之间的分数值不可被跳过）
        u = Timing(0.0, 199.5, -200.0, 0.0, 0.0)
        v = Timing(210.0, 60.0, -180.0, 0.0, 0.0)
        vc = u.vc_timing(v, 0.5, 0.5)
        assert vc is not None
        assert vc.preutterance == 0.25
        assert vc.constraint_errors() == []

    def test_vc_fractional_next_consonant_generates(self):
        # 下一辅音区 0.5 采样：仍生成
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)
        v = Timing(210.0, 0.5, -180.0, 0.0, 0.0)
        vc = u.vc_timing(v, 0.5, 0.5)
        assert vc is not None
        assert vc.consonant == 110.5  # 270.5 - 100 → 下一元音起点 210.5
        assert vc.constraint_errors() == []

    def test_vc_window_zero_with_zero_pre_none(self):
        # window == 0 且 pre == 0：退化窗口，不生成
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)  # 元音尾至 200
        v = Timing(150.0, 50.0, -100.0, 0.0, 0.0)  # 下一元音起点恰为 200
        assert u.vc_timing(v, 0.0, 0.0) is None

    def test_vc_window_unit_fraction_generates(self):
        # 窗口恰为 1.0 采样：仍生成
        u = Timing(0.0, 199.0, -200.0, 0.0, 0.0)  # 元音区 1.0
        v = Timing(190.0, 10.5, -100.0, 0.0, 0.0)  # 下一元音起点 200.5
        vc = u.vc_timing(v, 0.5, 0.5)
        assert vc is not None
        assert vc.preutterance == 0.5  # 1.0 * 0.5
        assert vc.consonant == 1.0  # 窗口 = 200.5 - 199.5
        assert vc.cutoff == -1.0
        assert vc.constraint_errors() == []

    def test_vc_pre_equal_window_generates(self):
        # pre == window（下一元音起点恰为当前窗口末端）：合法边界，仍生成
        u = Timing(0.0, 0.0, -200.0, 0.0, 0.0)  # pre = 100
        v = Timing(150.0, 50.0, -100.0, 0.0, 0.0)  # 下一元音起点恰为 200
        vc = u.vc_timing(v, 0.5, 0.5)
        assert vc is not None
        assert vc.offset == 100.0
        assert vc.consonant == 100.0  # window == pre == 100
        assert vc.cutoff == -100.0
        assert vc.preutterance == 100.0
        assert vc.overlap == 50.0
        assert vc.constraint_errors() == []

    def test_vc_constraints_on_realistic_pair(self):
        # 中文 demo 的 ni → hao 相邻对（44100 Hz）
        u = Timing(2205.0, 11025.0, -35280.0, 4410.0, 4410.0)
        v = Timing(35280.0, 11025.0, -39690.0, 4410.0, 4410.0)
        vc = u.vc_timing(v, 0.5, 0.5)
        assert vc is not None
        assert vc.constraint_errors() == []


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
