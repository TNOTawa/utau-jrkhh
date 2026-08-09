"""分析模块（时长/RMS 统计 + 自动建议排序）单元测试。"""

from __future__ import annotations

from jrh.core import analysis as analysis_mod
from jrh.core.project import JRHProject


class TestDuration:
    def test_duration_formula(self, demo_project):
        proj = JRHProject.open(demo_project)
        u = proj.get_unit(1, 1)
        assert analysis_mod.unit_duration_ms(u, 44100) == 800.0

    def test_stats(self):
        s = analysis_mod.compute_stats([100.0, 200.0, 300.0])
        assert s["median"] == 200.0
        assert s["mean"] == 200.0
        assert s["count"] == 3
        assert s["mad"] == 100.0
        assert analysis_mod.compute_stats([])["count"] == 0


class TestSummary:
    def test_build_summary(self, demo_project):
        proj = JRHProject.open(demo_project)
        s = analysis_mod.build_summary(proj)
        dur = s.global_stats["duration_ms"]
        assert dur["count"] == 8
        assert dur["median"] == 500.0
        rms = s.global_stats["rms_dbfs"]
        assert rms["count"] == 8
        pa = s.per_asset_stats["asset-001"]
        assert pa["duration_ms"]["count"] == 6

    def test_per_asset_stats_ignored_when_sparse(self, demo_project):
        """样本数 < 10 时自动排序退回全局统计。"""
        proj = JRHProject.open(demo_project)
        summary = analysis_mod.build_summary(proj)
        stats = analysis_mod._stats_for(summary, "asset-001", "duration_ms")
        assert stats is summary.global_stats["duration_ms"]  # 6 个样本 < 10


class TestAutoOrder:
    def test_single_unit_trivial(self, demo_project):
        proj = JRHProject.open(demo_project)
        assert analysis_mod.auto_suggest_order(proj, "ni") == ["1:1"]

    def test_auto_order_puts_anomaly_last(self, tmp_path):
        from jrh.core.model import Asset, Timing
        from jrh.core.project import JRHProject

        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(
            Asset(
                id="a1",
                file="x.wav",
                kind="audio",
                sha256="0" * 64,
                sample_rate=44100,
                num_samples=100000,
                duration_seconds=2.0,
            )
        )
        proj.create_sentence("a1", 0, 100000)
        # 3 个 hao：两个正常（500ms），一个异常（100ms 过短）
        proj.create_unit(1, "hao", Timing(0, 100, -22050, 0, 0))
        proj.create_unit(1, "hao", Timing(23000, 100, -22050, 0, 0))
        proj.create_unit(1, "hao", Timing(46000, 100, -4410, 0, 0))
        for coord in ("1:1", "1:2", "1:3"):
            s, u = (int(x) for x in coord.split(":"))
            proj.set_unit_analysis(s, u, {"duration_ms": 500.0, "rms_dbfs": -20.0})
        proj.set_unit_analysis(1, 3, {"duration_ms": 100.0, "rms_dbfs": -20.0})
        proj.set_analysis_summary(analysis_mod.build_summary(proj))
        order = analysis_mod.auto_suggest_order(proj, "hao")
        assert order == ["1:1", "1:2", "1:3"]  # 异常项（100ms）靠后

    def test_auto_order_missing_rms_last_within_tier(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.set_unit_analysis(2, 2, {"duration_ms": 400.0, "rms_dbfs": None})
        proj.set_analysis_summary(analysis_mod.build_summary(proj))
        order = analysis_mod.auto_suggest_order(proj, "hao")
        # 3:1 与 2:2 时长偏差同级（均为 0.6745 z）：有 RMS 的 3:1 在前
        assert order == ["3:1", "2:2", "1:2"]

    def test_auto_order_deterministic(self, demo_project):
        proj = JRHProject.open(demo_project)
        assert analysis_mod.auto_suggest_order(proj, "hao") == analysis_mod.auto_suggest_order(
            proj, "hao"
        )


class TestEffectiveOrder:
    def test_manual_effective_order(self, demo_project):
        proj = JRHProject.open(demo_project)
        order = analysis_mod.effective_group_order(proj, "hao")
        assert order == ["3:1", "1:2", "2:2"]  # 人工顺序原样

    def test_manual_unlisted_appended_by_auto(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.group_set_manual("hao", ["1:2"])  # 只列一个
        order = analysis_mod.effective_group_order(proj, "hao")
        assert order[0] == "1:2"
        assert set(order) == {"1:2", "2:2", "3:1"}

    def test_manual_order_not_overwritten_by_analysis(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.group_set_manual("hao", ["2:2", "3:1", "1:2"])
        proj.set_analysis_summary(analysis_mod.build_summary(proj))
        proj.save()
        proj2 = JRHProject.open(demo_project)
        assert proj2.candidate_groups.mode("hao") == "manual"
        order = analysis_mod.effective_group_order(proj2, "hao")
        assert order == ["2:2", "3:1", "1:2"]

    def test_restore_auto(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.group_set_auto("hao")
        assert proj.candidate_groups.mode("hao") == "auto"
        order = analysis_mod.effective_group_order(proj, "hao")
        assert order == analysis_mod.auto_suggest_order(proj, "hao")


class TestAnalysisCache:
    def test_stored_summary_preferred(self, demo_project):
        proj = JRHProject.open(demo_project)
        stored = proj.analysis_summary
        assert stored is not None
        effective = proj.analysis_summary_effective()
        assert effective is stored

    def test_live_summary_when_absent(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        s = proj.analysis_summary_effective()
        assert s.global_stats["duration_ms"]["count"] == 0
