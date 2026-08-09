"""边界/契约测试：针对变异测试幸存点逐项补充（Kill mutants）。

每个测试对应至少一个曾在变异测试中存活的变异点。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.builder import build_demo_project

from jrh.core import analysis as analysis_mod
from jrh.core.errors import InvalidInputError
from jrh.core.model import (
    AnalysisSummary,
    Asset,
    Sentence,
    Timing,
    Unit,
)
from jrh.core.project import JRHProject
from jrh.core.selection import select_sequence
from jrh.formats.oto_ini import OtoLine, read_oto, write_oto


def _asset():
    return Asset(
        id="a1",
        file="assets/x.wav",
        kind="audio",
        sha256="0" * 64,
        sample_rate=44100,
        num_samples=200000,
        duration_seconds=4.5,
    )


def _mk(project_path: Path):
    return JRHProject.open(project_path)


# ── model.py：dataclass 默认值 / 边界判断 ────────────────────────


class TestModelDefaults:
    def test_asset_defaults(self):
        a = Asset(id="x", file="y")
        assert a.sample_rate == 0 and a.num_samples == 0 and a.duration_seconds == 0.0

    def test_sentence_default_max_unit_id_ever(self):
        d = {
            "sentence_id": 1,
            "asset_id": "a1",
            "sample_rate": 44100,
            "start_sample": 0,
            "end_sample": 100,
        }
        assert Sentence.from_dict(d).max_unit_id_ever == 0
        assert Sentence.from_dict(d).to_dict()["segmentation"]["manually_adjusted"] is False

    def test_unit_default_enabled(self):
        d = {
            "sentence_id": 1,
            "unit_id": 1,
            "label": "hao",
            "timing": {
                "offset": 0,
                "consonant": 0,
                "cutoff": -100,
                "preutterance": 0,
                "overlap": 0,
            },
        }
        assert Unit.from_dict(d).enabled is True

    def test_sentence_duration_exact(self, demo_project):
        proj = _mk(demo_project)
        assert proj.get_sentence(1).duration_seconds() == 2.0
        assert proj.get_sentence(2).duration_seconds() == 1.0  # start ≠ 0
        assert proj.get_sentence(1).duration_samples() == 88200
        assert proj.get_sentence(2).duration_samples() == 44100


class TestModelBoundaries:
    @pytest.mark.parametrize("sid", [0, -1])
    def test_sentence_id_zero_or_negative_rejected(self, sid):
        d = {
            "sentence_id": sid,
            "asset_id": "a1",
            "sample_rate": 44100,
            "start_sample": 0,
            "end_sample": 100,
        }
        with pytest.raises(InvalidInputError):
            Sentence.from_dict(d)

    def test_max_unit_id_ever_zero_accepted(self):
        d = {
            "sentence_id": 1,
            "asset_id": "a1",
            "sample_rate": 44100,
            "start_sample": 0,
            "end_sample": 100,
            "max_unit_id_ever": 0,
        }
        assert Sentence.from_dict(d).max_unit_id_ever == 0

    def test_unit_id_zero_rejected(self):
        d = {
            "sentence_id": 1,
            "unit_id": 0,
            "label": "hao",
            "timing": {
                "offset": 0,
                "consonant": 0,
                "cutoff": -100,
                "preutterance": 0,
                "overlap": 0,
            },
        }
        with pytest.raises(InvalidInputError):
            Unit.from_dict(d)

    def test_unit_sentence_id_zero_rejected(self):
        d = {
            "sentence_id": 0,
            "unit_id": 1,
            "label": "hao",
            "timing": {
                "offset": 0,
                "consonant": 0,
                "cutoff": -100,
                "preutterance": 0,
                "overlap": 0,
            },
        }
        with pytest.raises(InvalidInputError):
            Unit.from_dict(d)

    def test_transition_generated_when_consonant_one(self):
        assert Timing(0, 1, -100, 0, 0).transition_timing() is not None

    def test_cutoff_zero_reports_negative_error(self):
        errs = Timing(0, 0, 0, 0, 0).constraint_errors()
        assert any("cutoff 必须为负值" in e for e in errs)

    def test_cutoff_half_sample_window_valid(self):
        errs = Timing(0, 0, -0.5, 0, 0).constraint_errors()
        assert errs == []

    def test_offset_zero_valid(self):
        assert Timing(0, 0, -100, 0, 0).constraint_errors() == []

    def test_preutterance_equal_window_valid(self):
        assert Timing(0, 0, -100, 100, 0).constraint_errors() == []


# ── analysis.py：统计与阈值边界 ──────────────────────────────────


class TestAnalysisBoundaries:
    def test_variance_single_value(self):
        s = analysis_mod.compute_stats([5.0])
        assert s["variance"] == 0.0

    def test_build_summary_revision_zero(self, demo_project):
        proj = _mk(demo_project)
        assert analysis_mod.build_summary(proj).revision == 0

    def test_robust_z_basics(self):
        assert analysis_mod._robust_z(1100, {"median": 1100, "mad": 100}) == 0.0
        assert analysis_mod._robust_z(1200, {"median": 1100, "mad": 100}) == 0.6745
        assert analysis_mod._robust_z(1.0, {}) == 0.0  # 无统计
        assert analysis_mod._robust_z(5.0, {"median": 1.0, "mad": 0}) == 10.0
        assert analysis_mod._robust_z(1.0, {"median": 1.0, "mad": 0}) == 0.0

    def test_per_asset_stats_used_at_exactly_ten(self):
        """count == 10（含）时使用素材局部统计。"""
        summary = AnalysisSummary(
            revision=0,
            global_stats={"duration_ms": {"count": 100, "median": 500.0, "mad": 50.0}},
            per_asset_stats={"a1": {"duration_ms": {"count": 10, "median": 100.0, "mad": 10.0}}},
        )
        stats = analysis_mod._stats_for(summary, "a1", "duration_ms")
        assert stats["median"] == 100.0

    def test_anomaly_flag_z_dur_and_z_rms_interplay(self, tmp_path):
        """z_rms ∈ (2.5, 3.5] 且 z_dur 小：异常标志改变排序（阈值边界）。"""
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 200000)
        # A: 时长 1100ms（z_dur=0），rms 使 z_rms=3.0（异常仅由 RMS 触发）
        proj.create_unit(1, "hao", Timing(0, 100, -48510, 0, 0))
        # B: 时长 1248.3ms（z_dur=1.0），rms 正常
        proj.create_unit(1, "hao", Timing(60000, 100, -55050, 0, 0))
        proj.set_unit_analysis(1, 1, {"duration_ms": 1100.0, "rms_dbfs": -15.55})
        proj.set_unit_analysis(1, 2, {"duration_ms": 1248.3, "rms_dbfs": -20.0})
        summary = AnalysisSummary(
            revision=0,
            global_stats={
                "duration_ms": {"count": 2, "median": 1100.0, "mad": 100.0},
                "rms_dbfs": {"count": 2, "median": -20.0, "mad": 1.0},
            },
            per_asset_stats={},
        )
        proj.set_analysis_summary(summary)
        order = analysis_mod.auto_suggest_order(proj, "hao")
        # 正常：1:1 异常（z_rms=3.0>2.5）靠后 → [1:2, 1:1]
        # 若阈值被改成 3.5：1:1 不再异常 → 按 z_dur → [1:1, 1:2]
        assert order == ["1:2", "1:1"]

    def test_auto_order_ignores_manual_mode(self, demo_project):
        """auto_suggest_order 只由统计决定，不受候选分组 mode 影响。"""
        proj = _mk(demo_project)
        before = analysis_mod.auto_suggest_order(proj, "hao")
        proj.group_set_manual("hao", ["1:2", "2:2", "3:1"])
        assert analysis_mod.auto_suggest_order(proj, "hao") == before
        assert before == ["2:2", "3:1", "1:2"]  # 1:2 时长偏差最大 → 最后


# ── selection.py：tie-break 与连续性边界 ─────────────────────────


class TestSelectionBoundaries:
    def test_same_sentence_bonus_in_full_level(self, tmp_path):
        """L2 两个候选时，与上一选中同句者优先（tie-break 规则 1）。

        人工顺序故意反转（[4:2, 3:2]），确保只有连续性奖励能选出 3:2。
        """
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)  # 句1: wo ni
        proj.create_unit(1, "wo", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(1, "ni", Timing(10000, 100, -9000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句2: ni hao
        proj.create_unit(2, "ni", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(2, "hao", Timing(10000, 100, -9000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句3: wo hao（3:2 与 3:1 间隔大）
        proj.create_unit(3, "wo", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(3, "hao", Timing(20000, 100, -9000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句4: wo hao
        proj.create_unit(4, "wo", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(4, "hao", Timing(10000, 100, -9000, 0, 0))
        # 禁用 1:1 与 4:1，使 "wo" 只能选 3:1
        proj.update_unit(1, 1, enabled=False)
        proj.update_unit(4, 1, enabled=False)
        # hao 人工顺序反转：4:2 在前（若连续性奖励失效，将选出 4:2）
        proj.group_set_manual("hao", ["4:2", "3:2"])
        proj.save()
        rs = select_sequence(proj, ["wo", "hao"])
        assert rs[0].unit_coord == "3:1"
        # hao：3:2 间隔 11000 采样(249ms) > 100ms → 无连续；L2 候选 3:2 与 4:2
        assert rs[1].level == "full"
        assert rs[1].unit_coord == "3:2"  # 与上一选中同句 → 优先于 4:2

    def test_continuity_gap_boundary_exact(self, tmp_path):
        """gap == 阈值（100ms）→ 连续；gap > 阈值 → 不连续。"""
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(1, "ni", Timing(0, 100, -22050, 0, 0))  # 窗口终点 22050
        proj.create_unit(1, "hao", Timing(26460, 100, -22050, 0, 0))  # 间隔 4410 = 100ms
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(2, "ni", Timing(0, 100, -22050, 0, 0))
        proj.create_unit(2, "hao", Timing(26461, 100, -22050, 0, 0))  # 间隔 4411 > 100ms
        proj.save()
        rs = select_sequence(proj, ["ni", "hao"])
        assert rs[0].unit_coord == "1:1"  # ni 组 id 序
        assert rs[1].level == "continuous"  # 恰好 == 100ms → 连续（选 1:2）
        assert rs[1].unit_coord == "1:2"

    def test_continuity_gap_over_threshold(self, tmp_path):
        """gap 超过阈值时 2:2 不连续：L2 full 命中（前元音 i 匹配 2:2 自身上下文）。"""
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(1, "ni", Timing(0, 100, -22050, 0, 0))
        proj.create_unit(1, "hao", Timing(26460, 100, -22050, 0, 0))
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(2, "ni", Timing(0, 100, -22050, 0, 0))
        proj.create_unit(2, "hao", Timing(26461, 100, -22050, 0, 0))  # 100.02ms > 100
        proj.save()
        # 强制上一选中为 2:1：禁用 1:1
        proj2 = JRHProject.open(tmp_path / "p")
        proj2.update_unit(1, 1, enabled=False)
        proj2.save()
        rs = select_sequence(JRHProject.open(tmp_path / "p"), ["ni", "hao"])
        assert rs[1].level != "continuous"
        assert rs[1].level == "full"

    def test_split_t_candidate_order_key(self, tmp_path):
        """L3 T 候选同层 tie-break：永久编号兜底（s 优先，跨句 u 交叉时稳定）。

        T 候选 2:3(hong)、2:4(huang)、3:2(huai)：同层同秩（bonus=rank=0）
        → 正常按 (s,u) 兜底选 2:3；变异排序键会选 3:2 或直接 TypeError。
        """
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)  # 句1: wo hao
        proj.create_unit(1, "wo", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(1, "hao", Timing(10000, 100, -10000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句2: ni li hong ji huang
        proj.create_unit(2, "ni", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(2, "li", Timing(10000, 100, -9000, 0, 0))
        proj.create_unit(2, "hong", Timing(20000, 4410, -10000, 0, 0))
        proj.create_unit(2, "ji", Timing(31000, 100, -9000, 0, 0))
        proj.create_unit(2, "huang", Timing(41000, 4410, -10000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句3: ni huai（3:2 huai）
        proj.create_unit(3, "ni", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(3, "huai", Timing(10000, 4410, -10000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句4: ni（4:1 作为 prev）
        proj.create_unit(4, "ni", Timing(0, 100, -9000, 0, 0))
        # 禁用 2:1 与 3:1，使 "ni" 只能选 4:1
        proj.update_unit(2, 1, enabled=False)
        proj.update_unit(3, 1, enabled=False)
        proj.save()
        rs = select_sequence(proj, ["ni", "hao"])
        assert rs[0].unit_coord == "4:1"
        assert rs[1].level == "split"
        # T 候选 2:3(hong)、2:4(huang)、3:2(huai) 同层同秩 → (s,u) 兜底 → 2:3
        assert rs[1].phonemes[0].alias.startswith("2-3-")

    def test_split_t_candidate_half_sample_consonant(self, tmp_path):
        """consonant ∈ (0, 1] 仍可作为过渡候选（变异 >1 会漏掉）。"""
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)  # 句1: wo hao
        proj.create_unit(1, "wo", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(1, "hao", Timing(10000, 100, -10000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句2: ni hong（2:2 hong consonant=0.5）
        proj.create_unit(2, "ni", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(2, "hong", Timing(10000, 0.5, -10000, 0, 0))
        proj.save()
        rs = select_sequence(proj, ["ni", "hao"])
        assert rs[1].level == "split"
        assert rs[1].phonemes[0].alias.startswith("2-2-")

    def test_candidates_counts_zero_levels(self, demo_project):
        proj = _mk(demo_project)
        r = select_sequence(proj, ["ni", "hao"])[1]
        assert r.explanation["candidates"]["full"] == 0
        assert r.explanation["candidates"]["split"] == 0

    def test_split_requires_consonant_strictly_positive(self, tmp_path):
        """consonant == 0 的单元不能充当过渡（T）候选。

        句2 的 "o"（纯元音、consonant=0、leading o）被排除后无 T 候选
        → 退化为当前字主体；若含 0 会被误当作 T 触发 split。
        """
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)  # 句1: wo hao
        proj.create_unit(1, "wo", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(1, "hao", Timing(10000, 100, -10000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句2: wo o（2:2 纯元音，consonant=0）
        proj.create_unit(2, "wo", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(2, "o", Timing(10000, 0, -9000, 0, 0))
        proj.create_sentence("a1", 0, 100000)  # 句3: hao a（3:2 leading=ao ≠ o）
        proj.create_unit(3, "hao", Timing(0, 100, -9000, 0, 0))
        proj.create_unit(3, "a", Timing(10000, 0, -9000, 0, 0))
        proj.save()
        rs = select_sequence(proj, ["wo", "a"])
        assert rs[1].level == "body"  # 无 T（consonant==0 排除）→ 退化为当前字主体
        assert rs[1].unit_coord == "3:2"


# ── compile_engine.py：验证门与错误消息 ──────────────────────────


class TestCompileGate:
    def test_compile_validation_error_message_with_many_errors(self, tmp_path):
        from jrh.core.compile_engine import compile_project
        from jrh.core.errors import ValidationError
        from jrh.core.util import write_json

        p = build_demo_project(tmp_path)
        proj = JRHProject.open(p)
        units = []
        for u in proj.units_sorted():
            d = u.to_dict()
            d["timing"]["preutterance"] = 999999.0  # 全部 8 个单元 → 8 个 timing 错误
            units.append(d)
        write_json(p / "data" / "units.json", {"units": units})
        proj2 = JRHProject.open(p)
        with pytest.raises(ValidationError) as exc:
            compile_project(proj2)
        assert "共 8 个错误" in str(exc.value)
        # 截断上限：只列出前 5 条错误（变异 5→6 会列出 6 条）
        assert str(exc.value).count("需要 preutterance") == 5

    def test_compile_error_message_no_truncation_at_five(self, tmp_path):
        """恰好 5 个错误时不应出现截断标记（变异 Gt→GtE 会误判）。"""
        from jrh.core.compile_engine import compile_project
        from jrh.core.errors import ValidationError
        from jrh.core.util import write_json

        p = build_demo_project(tmp_path)
        proj = JRHProject.open(p)
        units = []
        for u in proj.units_sorted():
            d = u.to_dict()
            # 句1 的 3 个单元 + 句2 的前 2 个单元 = 恰好 5 个错误
            if (u.sentence_id == 1 and u.unit_id <= 3) or (u.sentence_id == 2 and u.unit_id <= 2):
                d["timing"]["preutterance"] = 999999.0
            units.append(d)
        write_json(p / "data" / "units.json", {"units": units})
        proj2 = JRHProject.open(p)
        with pytest.raises(ValidationError) as exc:
            compile_project(proj2)
        assert "共" not in str(exc.value)

    def test_compile_skips_validation_when_requested(self, demo_project):
        from jrh.core.compile_engine import compile_project

        proj = _mk(demo_project)
        proj.update_unit(1, 1, label="bad label")
        result = compile_project(proj, validate_first=False)
        assert result.entries  # 显式关闭验证时仍可编译（默认开启）


# ── oto_ini.py：字段解析完整性 ───────────────────────────────────


class TestOtoFieldParsing:
    def test_all_fields_distinct_values(self, tmp_path: Path):
        lines = [
            OtoLine("s.wav", "alias", 111.0, 222.0, -333.0, 444.0, 555.0),
        ]
        p = tmp_path / "oto.ini"
        write_oto(p, lines)
        got = read_oto(p)[0]
        assert got.offset_ms == 111.0
        assert got.consonant_ms == 222.0
        assert got.cutoff_ms == -333.0
        assert got.preutterance_ms == 444.0
        assert got.overlap_ms == 555.0
