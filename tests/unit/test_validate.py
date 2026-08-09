"""validate / integrity 语义校验单元测试。"""

from __future__ import annotations

import pytest

from jrh.core.errors import ConflictError
from jrh.core.model import Timing
from jrh.core.project import JRHProject
from jrh.core.validate import validate_label_charset, validate_project


class TestLabelCharset:
    @pytest.mark.parametrize(
        "ok",
        ["hao", "ni", "AH0", "tS", "@", "zhuang", "A.B", "x_y", "a#b", "x{}y", "lve"],
    )
    def test_ok(self, ok):
        assert validate_label_charset(ok) is None

    @pytest.mark.parametrize(
        "bad",
        ["", "a b", "a,b", "a=b", "a;b", 'a"b', "a'b", "a\\b", "a/b", "a-b", "a\nb", "$T", "a\tb"],
    )
    def test_bad(self, bad):
        assert validate_label_charset(bad) is not None


class TestValidateProject:
    def test_demo_valid(self, demo_project):
        proj = JRHProject.open(demo_project)
        result = validate_project(proj)
        assert not result.has_errors(), result.to_dict()

    def test_invalid_timing_constraint(self, demo_project):
        """绕过 API 直接写坏数据：preutterance > |cutoff|。"""
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        units = []
        for u in proj.units_sorted():
            d = u.to_dict()
            if (u.sentence_id, u.unit_id) == (1, 2):
                d["timing"]["preutterance"] = 50000.0
            units.append(d)
        write_json(proj.path / "data" / "units.json", {"units": units})
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)
        assert result.has_errors()
        assert any(i.code == "unit.timing" for i in result.errors())

    def test_bad_label_charset(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.update_unit(1, 2, label="hao-ma")
        result = validate_project(proj)
        assert any(i.code == "unit.label_charset" for i in result.errors())

    def test_unknown_label_warning(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.update_unit(1, 2, label="zzzz")
        result = validate_project(proj)
        assert any(i.code == "unit.label_unknown" for i in result.issues)
        assert not result.has_errors()

    def test_group_ref_missing_unit(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.group_set_manual("hao", ["1:2", "9:9"])
        result = validate_project(proj)
        assert any(i.code == "group.ref" for i in result.errors())

    def test_group_duplicate_coord(self, demo_project):
        """绕过 API 直接写坏数据：人工顺序重复坐标。"""
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        groups = proj.candidate_groups.to_dict()
        groups["groups"]["hao"] = {"mode": "manual", "ordered_unit_ids": ["1:2", "1:2"]}
        write_json(proj.path / "data" / "candidate_groups.json", groups)
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)
        assert any(i.code == "group.order" for i in result.errors())

    def test_window_out_of_sentence(self, demo_project):
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        units = []
        for u in proj.units_sorted():
            d = u.to_dict()
            if (u.sentence_id, u.unit_id) == (1, 3):
                d["timing"]["offset"] = 80000.0  # 80000+17640=97640 > 88200
            units.append(d)
        write_json(proj.path / "data" / "units.json", {"units": units})
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)
        assert any(i.code == "unit.range" for i in result.errors())

    def test_asset_hash_mismatch(self, demo_project):
        proj = JRHProject.open(demo_project)
        asset = proj.get_asset("asset-001")
        asset.sha256 = "f" * 64
        proj.save()
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)
        assert any(i.code == "asset.hash_mismatch" for i in result.errors())

    def test_asset_missing_file(self, demo_project):
        proj = JRHProject.open(demo_project)
        (proj.path / "assets" / "src1.wav").unlink()
        result = validate_project(proj)
        assert any(i.code == "asset.missing" for i in result.errors())

    def test_sentence_out_of_asset(self, demo_project):
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        sentences = [proj.get_sentence(s).to_dict() for s in sorted(proj.sentences)]
        sentences[1]["end_sample"] = 999999
        write_json(proj.path / "data" / "sentences.json", {"sentences": sentences})
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)
        assert any(i.code == "sentence.range" for i in result.errors())

    def test_stale_analysis_warning(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.create_sentence("asset-001", 0, 1000)
        proj.create_unit(4, "a", Timing(0, 0, -500, 0, 0))  # 新增单元未分析
        proj.save()
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)
        assert any(i.code == "analysis.stale" for i in result.issues)
        assert not result.has_errors()


class TestValidateCompileGate:
    def test_compile_rejects_invalid_project(self, demo_project):
        from jrh.core.compile_engine import compile_project
        from jrh.core.errors import ValidationError

        proj = JRHProject.open(demo_project)
        proj.update_unit(1, 2, label="bad label")
        with pytest.raises(ValidationError):
            compile_project(proj)

    def test_compile_conflict_raises(self, demo_project):
        from jrh.core.compile_engine import compile_project

        proj = JRHProject.open(demo_project)
        # 构造 CV 别名冲突：label=\"hao1\" 的单元与 hao 组第 2 名 CV 别名 \"hao1\" 冲突
        proj.update_unit(1, 1, label="hao1")  # 1:1 ni → hao1
        with pytest.raises(ConflictError, match="别名冲突"):
            compile_project(proj)
