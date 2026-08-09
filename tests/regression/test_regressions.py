"""回归测试：QA 阶段发现并修复的 bug 固化。

规则：任何 QA 发现的问题先加回归测试，再修复，再全量回归。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.builder import build_demo_project

from jrh.core.errors import InvalidInputError
from jrh.core.model import Timing
from jrh.core.project import JRHProject


class TestRegressionAliasNameError:
    """REG-1: 五段式别名生成曾引用不存在的变量 cur（NameError）。"""

    def test_five_part_alias_generates(self, demo_project):
        from jrh.core.compile_engine import compile_project

        proj = JRHProject.open(demo_project)
        result = compile_project(proj)
        aliases = {e.alias for e in result.entries}
        assert "1-2-ni-hao-a" in aliases
        assert "1-1-R-ni-hao" in aliases


class TestRegressionRenumberCoordinates:
    """REG-2: 重排句号后单元坐标曾悬空（键未重映射）。"""

    def test_renumber_remaps_unit_keys(self, tmp_path):
        from jrh.core.model import Asset

        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(
            Asset(
                id="a1",
                file="x.wav",
                kind="audio",
                sha256="0" * 64,
                sample_rate=44100,
                num_samples=10000,
                duration_seconds=1.0,
            )
        )
        proj.create_sentence("a1", 0, 1000)
        proj.create_unit(1, "hao", Timing(0, 0, -500, 0, 0))
        proj.create_sentence("a1", 2000, 3000)
        proj.create_unit(2, "ni", Timing(0, 0, -500, 0, 0))
        proj.delete_sentence(1, cascade=True)
        proj.renumber_sentences()
        proj.save()
        proj2 = JRHProject.open(tmp_path / "p")
        # 句号 2 → 1 后，其单元坐标必须映射到新句号
        assert list(proj2.sentences.keys()) == [1]
        assert (1, 1) in proj2.units
        assert proj2.get_unit(1, 1).label == "ni"


class TestRegressionMergeTimingShift:
    """REG-3: 合并句子时较晚句的单元 offset 未按句起点差平移。"""

    def test_merge_shifts_later_sentence_offsets(self, tmp_path):
        from jrh.core.model import Asset

        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(
            Asset(
                id="a1",
                file="x.wav",
                kind="audio",
                sha256="0" * 64,
                sample_rate=44100,
                num_samples=10000,
                duration_seconds=1.0,
            )
        )
        proj.create_sentence("a1", 0, 4000)
        proj.create_unit(1, "ni", Timing(100, 0, -1000, 0, 0))
        proj.create_sentence("a1", 4000, 9000)
        proj.create_unit(2, "hao", Timing(200, 0, -1000, 0, 0))
        proj.merge_sentences(1, 2)
        units = proj.units_in_sentence(1)
        by_label = {u.label: u for u in units}
        # 晚句(4000)单元 offset 平移 -4000
        assert by_label["hao"].timing.offset == 200 - 4000
        assert by_label["ni"].timing.offset == 100


class TestRegressionValidateCrashOnMissingSentence:
    """REG-4: validate 曾因句子引用缺失在 build_summary 处崩溃。"""

    def test_validate_reports_missing_sentence_ref(self, demo_project):
        from jrh.core.util import write_json
        from jrh.core.validate import validate_project

        proj = JRHProject.open(demo_project)
        sents = [s.to_dict() for s in proj.sentences_sorted() if s.sentence_id != 3]
        write_json(proj.path / "data" / "sentences.json", {"sentences": sents})
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)  # 不得崩溃
        assert any(i.code == "unit.sentence_ref" for i in result.errors())


class TestRegressionNonFiniteAnalysis:
    """REG-5: analysis 含 inf/NaN 曾被静默接受。"""

    def test_inf_analysis_rejected_on_open(self, demo_project):
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        units = [u.to_dict() for u in proj.units_sorted()]
        units[0]["analysis"]["rms_dbfs"] = float("inf")
        write_json(proj.path / "data" / "units.json", {"units": units})
        with pytest.raises(InvalidInputError, match="非有限"):
            JRHProject.open(demo_project)


class TestRegressionIntegrityDirectoryAttack:
    """REG-6: integrity 曾因产物文件被目录占用而崩溃。"""

    def test_integrity_handles_directory_oto(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        (out / "oto.ini").unlink()
        (out / "oto.ini").mkdir()
        result = check_integrity(proj)  # 不得崩溃
        assert any(i.code == "integrity.build_partial" for i in result.errors())


class TestRegressionGoldenStability:
    """REG-7: 编译产物必须与 golden 逐字节一致（编译规则回归）。"""

    def test_golden_still_matches(self, tmp_path):
        from jrh.core.compile_engine import compile_project, write_build

        p = build_demo_project(tmp_path)
        proj = JRHProject.open(p)
        out = p / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        golden = Path(__file__).resolve().parent.parent / "golden" / "data"
        assert (out / "oto.ini").read_bytes() == (golden / "oto.ini").read_bytes()
        assert (out / "build-report.json").read_bytes() == (
            golden / "build-report.json"
        ).read_bytes()
