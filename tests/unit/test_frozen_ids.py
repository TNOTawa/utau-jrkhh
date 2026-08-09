"""Permanent Coordinate 不变量专项测试（JRH_SPEC §10）。

冻结后：修改文字/发音/边界/重分析不改编号；删除编号不复用；新增不改变既有坐标。
"""

from __future__ import annotations

from jrh.core.model import Timing
from jrh.core.project import JRHProject


class TestFrozenIdInvariants:
    def test_edit_label_keeps_ids(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        before = {u.coordinate() for u in proj.units_sorted()}
        proj.update_unit(1, 2, label="gao")
        proj.save()
        proj2 = JRHProject.open(demo_project_frozen)
        after = {u.coordinate() for u in proj2.units_sorted()}
        assert before == after
        assert proj2.get_unit(1, 2).label == "gao"

    def test_edit_timing_keeps_ids(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        proj.update_unit(1, 2, timing=Timing(30000, 100, -20000, 100, 100))
        proj.save()
        proj2 = JRHProject.open(demo_project_frozen)
        assert set(proj2.units.keys()) == set(proj.units.keys())
        assert proj2.get_unit(1, 2).timing.offset == 30000

    def test_edit_boundaries_keeps_ids(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        ids_before = {u.coordinate() for u in proj.units_sorted()}
        proj.update_sentence(1, start_sample=0, end_sample=90000)
        proj.save()
        proj2 = JRHProject.open(demo_project_frozen)
        assert {u.coordinate() for u in proj2.units_sorted()} == ids_before

    def test_reanalysis_keeps_ids(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        ids_before = {u.coordinate() for u in proj.units_sorted()}
        from jrh.core import analysis as analysis_mod

        for u in proj.units_sorted():
            proj.set_unit_analysis(
                u.sentence_id,
                u.unit_id,
                {
                    "duration_ms": 1.0,
                    "rms_dbfs": -30.0,
                },
            )
        proj.set_analysis_summary(analysis_mod.build_summary(proj))
        proj.save()
        proj2 = JRHProject.open(demo_project_frozen)
        assert {u.coordinate() for u in proj2.units_sorted()} == ids_before

    def test_deleted_id_never_reused(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        proj.delete_unit(1, 2)
        proj.save()
        proj2 = JRHProject.open(demo_project_frozen)
        u = proj2.create_unit(1, "hao", Timing(0, 100, -500, 0, 0))
        assert u.unit_id != 2  # 已删除编号不复用
        proj2.save()
        proj3 = JRHProject.open(demo_project_frozen)
        assert (1, 2) not in proj3.units
        assert proj3.get_unit(1, u.unit_id).label == "hao"

    def test_new_units_do_not_change_existing(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        before = {u.coordinate(): (u.label, u.timing.to_dict()) for u in proj.units_sorted()}
        s = proj.create_sentence("asset-001", 0, 5000)
        proj.create_unit(s.sentence_id, "ni", Timing(0, 100, -1000, 0, 0))
        proj.save()
        proj2 = JRHProject.open(demo_project_frozen)
        after = {
            u.coordinate(): (u.label, u.timing.to_dict())
            for u in proj2.units_sorted()
            if u.sentence_id != s.sentence_id
        }
        assert before == after

    def test_deleted_sentence_id_not_reused(self, demo_project_frozen):
        proj = JRHProject.open(demo_project_frozen)
        proj.delete_sentence(2, cascade=True)
        s = proj.create_sentence("asset-001", 0, 5000)
        assert s.sentence_id != 2
