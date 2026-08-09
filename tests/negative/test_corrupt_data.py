"""负例测试：损坏输入必须产生显式错误，绝不静默。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jrh.core.errors import DataError, InvalidInputError, NotFoundError
from jrh.core.project import JRHProject
from jrh.core.util import write_json


def corrupt_units(proj_path: Path, mutate) -> None:
    p = proj_path / "data" / "units.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    mutate(data)
    write_json(p, data)


class TestCorruptManifest:
    @pytest.mark.parametrize(
        "content",
        [
            "not json at all",
            "{}",
            '{"format": "WRONG"}',
            '{"format": "JRH", "schema_version": "0.0.0"}',
            '{"format": "JRH", "schema_version": "0.1.0", "state": "banana"}',
            '{"format": "JRH", "schema_version": "0.1.0", "language_pack": "nope"}',
        ],
    )
    def test_open_rejects(self, tmp_path, content):
        from jrh.core.errors import JRHError

        d = tmp_path / "p"
        d.mkdir()
        (d / "manifest.json").write_text(content, encoding="utf-8")
        with pytest.raises(JRHError):
            JRHProject.open(d)

    def test_missing_data_files(self, tmp_path):
        from jrh.core.project import JRHProject

        p = JRHProject.create(tmp_path / "p")
        (p.path / "data" / "units.json").unlink()
        with pytest.raises(NotFoundError):
            JRHProject.open(tmp_path / "p")


class TestCorruptUnits:
    def test_nan_timing(self, demo_project):
        def mutate(data):
            data["units"][0]["timing"]["offset"] = float("nan")

        corrupt_units(demo_project, mutate)
        with pytest.raises(InvalidInputError):
            JRHProject.open(demo_project)

    def test_wrong_type_timing(self, demo_project):
        def mutate(data):
            data["units"][0]["timing"]["cutoff"] = "abc"

        corrupt_units(demo_project, mutate)
        with pytest.raises(InvalidInputError):
            JRHProject.open(demo_project)

    def test_missing_label(self, demo_project):
        def mutate(data):
            del data["units"][0]["label"]

        corrupt_units(demo_project, mutate)
        with pytest.raises(InvalidInputError):
            JRHProject.open(demo_project)

    def test_negative_unit_id(self, demo_project):
        def mutate(data):
            data["units"][0]["unit_id"] = -3

        corrupt_units(demo_project, mutate)
        with pytest.raises(InvalidInputError):
            JRHProject.open(demo_project)

    def test_duplicate_coordinates(self, demo_project):
        def mutate(data):
            u = dict(data["units"][0])
            data["units"].append(u)

        corrupt_units(demo_project, mutate)
        with pytest.raises(DataError, match="重复"):
            JRHProject.open(demo_project)


class TestCorruptSentences:
    def test_sentence_missing_asset_ref(self, demo_project):
        from jrh.core.validate import validate_project

        s = demo_project / "data" / "sentences.json"
        data = json.loads(s.read_text(encoding="utf-8"))
        data["sentences"][0]["asset_id"] = "ghost"
        write_json(s, data)
        proj = JRHProject.open(demo_project)
        result = validate_project(proj)
        assert any(i.code == "sentence.asset_ref" for i in result.errors())

    def test_zero_length_sentence(self, demo_project):
        from jrh.core.validate import validate_project

        s = demo_project / "data" / "sentences.json"
        data = json.loads(s.read_text(encoding="utf-8"))
        data["sentences"][0]["end_sample"] = data["sentences"][0]["start_sample"]
        write_json(s, data)
        proj = JRHProject.open(demo_project)
        result = validate_project(proj)
        assert any(i.code == "sentence.range" for i in result.errors())

    def test_overlapping_sentences_allowed_and_validated(self, demo_project):
        """重叠句不视为损坏（合法场景），但单元窗口越界仍被捕获。"""
        from jrh.core.validate import validate_project

        s = demo_project / "data" / "sentences.json"
        data = json.loads(s.read_text(encoding="utf-8"))
        data["sentences"][1]["start_sample"] = data["sentences"][0]["end_sample"] - 100
        write_json(s, data)
        proj = JRHProject.open(demo_project)
        result = validate_project(proj)
        # 边界被拉小后，句 2 的单元窗口可能越界 → unit.range 错误
        assert not result.has_errors() or any(i.code == "unit.range" for i in result.errors())


class TestCorruptGroups:
    def test_bad_mode_rejected_on_open(self, demo_project):
        """mode 非法在打开时即失败（fail fast）。"""
        g = demo_project / "data" / "candidate_groups.json"
        data = json.loads(g.read_text(encoding="utf-8"))
        data["groups"]["hao"]["mode"] = "banana"
        write_json(g, data)
        with pytest.raises(InvalidInputError, match="mode"):
            JRHProject.open(demo_project)


class TestCorruptAnalysis:
    def test_analysis_inf_value_rejected(self, demo_project):
        """analysis 含非有限数值（inf）在打开时拒绝。"""
        corrupt_units(
            demo_project,
            lambda data: data["units"][0]["analysis"].update({"rms_dbfs": float("inf")}),
        )
        with pytest.raises(InvalidInputError, match="非有限"):
            JRHProject.open(demo_project)


class TestAliasSafety:
    def test_forbidden_label_chars_rejected_in_compile(self, demo_project):
        from jrh.core.compile_engine import compile_project
        from jrh.core.errors import ValidationError

        proj = JRHProject.open(demo_project)
        proj.update_unit(1, 1, label="ni=hao")
        with pytest.raises(ValidationError, match="验证"):
            compile_project(proj)

    def test_rest_marker_collision_with_label(self, demo_project):
        """label 不能含 $（派生命名空间保留）。"""
        from jrh.core.validate import validate_label_charset

        assert validate_label_charset("hao$T") is not None


class TestIntegrity:
    def test_missing_build_wav(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        (out / "sentence_001.wav").unlink()
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_wav_missing" for i in result.errors())

    def test_duplicate_alias_in_oto(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        # 手工复制一行制造重复别名
        text = (out / "oto.ini").read_text(encoding="utf-8")
        first = text.splitlines()[0]
        (out / "oto.ini").write_text(text + first + "\n", encoding="utf-8")
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_duplicate_alias" for i in result.errors())

    def test_truncated_build(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        (out / "oto.ini").unlink()
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_partial" for i in result.errors())


class TestBrokenAudio:
    def test_not_an_audio_file(self, tmp_path):
        from jrh.core.errors import MissingDependencyError

        # 写入非音频内容
        bad = tmp_path / "bad.bin"
        bad.write_bytes(b"\x00" * 100)
        from jrh.audio.probe import probe_audio_file

        with pytest.raises(MissingDependencyError, match="无法读取"):
            probe_audio_file(bad)
