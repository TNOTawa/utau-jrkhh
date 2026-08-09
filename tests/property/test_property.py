"""Property-based 测试（hypothesis）：序列化 round-trip、排序稳定性、公式恒等。"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from jrh.core.analysis import auto_suggest_order, effective_group_order
from jrh.core.ids import format_coordinate, parse_coordinate
from jrh.core.model import Timing
from jrh.formats.oto_ini import fmt_ms

# ── ID 坐标 ──────────────────────────────────────────────────────


@given(s=st.integers(min_value=1, max_value=10**6), u=st.integers(min_value=1, max_value=10**6))
def test_coordinate_roundtrip(s, u):
    assert parse_coordinate(format_coordinate(s, u)) == (s, u)


# ── Timing 公式恒等（策略生成满足有效性约束的合法 Timing）─────


@st.composite
def valid_timing(draw):
    """满足 0 ≤ overlap ≤ preutterance ≤ |cutoff|、0 ≤ consonant ≤ |cutoff|。"""
    dur = draw(st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    pre = draw(st.floats(min_value=0.0, max_value=dur, allow_nan=False, allow_infinity=False))
    cons = draw(st.floats(min_value=0.0, max_value=dur, allow_nan=False, allow_infinity=False))
    ovl = draw(st.floats(min_value=0.0, max_value=pre, allow_nan=False, allow_infinity=False))
    off = draw(st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    return Timing(off, cons, -dur, pre, ovl)


@given(valid_timing())
@settings(max_examples=200)
def test_timing_serialization_roundtrip(t: Timing):
    assert Timing.from_dict(t.to_dict()) == t


@given(valid_timing())
@settings(max_examples=200)
def test_body_timing_cutoff_never_positive(t: Timing):
    b = t.body_timing()
    assert b.cutoff <= 0
    assert b.offset == t.offset + t.preutterance
    # 浮点误差内：主体窗口终点 == 完整窗口终点
    assert abs(b.window_end() - t.window_end()) < 1e-6 * max(1.0, abs(t.window_end()))


@given(valid_timing())
@settings(max_examples=200)
def test_transition_region_inside_window(t: Timing):
    tr = t.transition_timing()
    if tr is not None:
        assert tr.offset >= t.offset
        assert tr.window_end() <= t.window_end()
        assert tr.window_end() == t.offset + t.consonant


@given(
    offset=st.floats(min_value=0, max_value=1e6, allow_nan=False),
    dur=st.floats(min_value=0.001, max_value=1e6, allow_nan=False),
    preutterance=st.floats(min_value=0, max_value=1e6, allow_nan=False),
    sr=st.integers(min_value=1, max_value=192000),
)
@settings(max_examples=200)
def test_ms_conversion_deterministic(offset, dur, preutterance, sr):
    t = Timing(offset, 0.0, -dur, min(preutterance, dur), 0.0)
    ms1 = t.to_ms(sr)
    ms2 = t.to_ms(sr)
    assert ms1 == ms2
    assert all(abs(v) < 1e10 for v in ms1.values())


@given(v=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False))
def test_fmt_ms_deterministic_and_stable(v):
    s1 = fmt_ms(v)
    s2 = fmt_ms(v)
    assert s1 == s2
    # 输出必须是 oto.ini 安全字符
    assert "," not in s1 and "=" not in s1


# ── 排序稳定性（需项目；用 demo fixture 构造）──────────────────


def test_auto_order_is_stable_under_reload(tmp_path):
    from fixtures.builder import build_demo_project

    p = build_demo_project(tmp_path)
    from jrh.core.project import JRHProject

    proj1 = JRHProject.open(p)
    order1 = auto_suggest_order(proj1, "hao")
    proj1.save()
    proj2 = JRHProject.open(p)
    order2 = auto_suggest_order(proj2, "hao")
    assert order1 == order2
    assert order1 == sorted(set(order1), key=order1.index)  # 无重复


def test_effective_order_contains_all_enabled(tmp_path):
    from fixtures.builder import build_demo_project

    p = build_demo_project(tmp_path)
    from jrh.core.project import JRHProject

    proj = JRHProject.open(p)
    enabled = {u.coordinate() for u in proj.units_by_label("hao") if u.enabled}
    assert set(effective_group_order(proj, "hao")) == enabled
