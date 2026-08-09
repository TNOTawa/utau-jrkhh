"""覆盖率补充测试：针对 coverage 缺失行（error paths / 分支）。

这些路径大多是异常分支，用负例/边界输入触发，不降低门禁。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures.builder import build_demo_project

from jrh.core.errors import DataError, InvalidInputError, NotFoundError
from jrh.core.model import (
    AnalysisSummary,
    CandidateGroups,
    Sentence,
    Timing,
    Unit,
)
from jrh.core.project import JRHProject
from jrh.core.util import expect_dict, expect_list, read_json_strict
from jrh.formats.oto_ini import OtoLine, fmt_ms, read_oto

# ── util.py：原子写/JSON 错误路径 ────────────────────────────────


class TestUtilErrors:
    def test_read_json_strict_missing(self, tmp_path):
        with pytest.raises(NotFoundError):
            read_json_strict(tmp_path / "nope.json")

    def test_read_json_strict_invalid_utf8(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_bytes(b"\xff\xfe\x00broken")
        with pytest.raises(DataError, match="损坏"):
            read_json_strict(p)

    def test_read_json_strict_not_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(DataError, match="损坏"):
            read_json_strict(p)

    def test_expect_dict_list(self):
        assert expect_dict({"a": 1}, "x") == {"a": 1}
        assert expect_list([1], "x") == [1]
        with pytest.raises(DataError, match="结构错误"):
            expect_dict([1], "x")
        with pytest.raises(DataError, match="结构错误"):
            expect_list({"a": 1}, "x")

    def test_atomic_write_text_to_invalid_parent(self, tmp_path):
        """父目录是文件时原子写失败路径。"""
        from jrh.core.util import atomic_write_bytes, atomic_write_text

        f = tmp_path / "afile"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(OSError):
            atomic_write_text(f / "sub" / "y.txt", "data")
        with pytest.raises(OSError):
            atomic_write_bytes(f / "sub" / "y.bin", b"data")

    def test_atomic_write_success_paths(self, tmp_path):
        from jrh.core.util import atomic_write_bytes, atomic_write_text

        atomic_write_text(tmp_path / "a.txt", "héllo\n")
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "héllo\n"
        atomic_write_bytes(tmp_path / "a.bin", b"\x00\x01")
        assert (tmp_path / "a.bin").read_bytes() == b"\x00\x01"

    def test_atomic_write_cleanup_on_failure(self, tmp_path, monkeypatch):
        """os.replace 失败时清理临时文件并重新抛出（两变体）。"""
        from jrh.core.util import atomic_write_bytes, atomic_write_text

        def failing_replace(src, dst):
            raise OSError("boom")

        monkeypatch.setattr("os.replace", failing_replace)
        for writer in (atomic_write_text, atomic_write_bytes):
            with pytest.raises(OSError, match="boom"):
                writer(tmp_path / "x.out", "data" if writer is atomic_write_text else b"data")
        assert list(tmp_path.iterdir()) == []  # 临时文件已清理

    def test_read_json_strict_os_error(self, tmp_path, monkeypatch):
        """读取权限/IO 错误路径。"""
        p = tmp_path / "locked.json"
        p.write_text("{}", encoding="utf-8")

        def boom(*a, **k):
            raise OSError("denied")

        monkeypatch.setattr(Path, "read_bytes", boom)
        with pytest.raises(DataError, match="无法读取"):
            read_json_strict(p)


# ── model.py：from_dict 错误分支与边界 ───────────────────────────


class TestModelFromDictErrors:
    def test_sentence_missing_fields(self):
        with pytest.raises(InvalidInputError):
            Sentence.from_dict({"sentence_id": 1})  # 缺 asset_id 等

    def test_sentence_bad_segmentation(self):
        d = {
            "sentence_id": 1,
            "asset_id": "a1",
            "sample_rate": 44100,
            "start_sample": 0,
            "end_sample": 100,
            "segmentation": "oops",
        }
        with pytest.raises(InvalidInputError):
            Sentence.from_dict(d)

    def test_unit_timing_not_dict(self):
        d = {"sentence_id": 1, "unit_id": 1, "label": "hao", "timing": "oops"}
        with pytest.raises(InvalidInputError):
            Unit.from_dict(d)

    def test_unit_bad_enabled(self):
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
            "enabled": "yes",
        }
        with pytest.raises(InvalidInputError):
            Unit.from_dict(d)

    def test_unit_analysis_not_dict(self):
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
            "analysis": [1, 2],
        }
        with pytest.raises(InvalidInputError):
            Unit.from_dict(d)

    def test_timing_bool_value_rejected(self):
        with pytest.raises(InvalidInputError):
            Timing.from_dict(
                {"offset": True, "consonant": 1, "cutoff": -1, "preutterance": 0, "overlap": 0}
            )

    def test_timing_missing_field(self):
        with pytest.raises(InvalidInputError):
            Timing.from_dict({"offset": 0, "consonant": 0, "cutoff": -1})

    def test_candidate_groups_bad_structure(self):
        with pytest.raises(InvalidInputError):
            CandidateGroups.from_dict({"groups": "oops"})
        with pytest.raises(InvalidInputError):
            CandidateGroups.from_dict({"groups": {"hao": "oops"}})
        with pytest.raises(InvalidInputError):
            CandidateGroups.from_dict({"groups": {"hao": {"mode": "x"}}})
        with pytest.raises(InvalidInputError):
            CandidateGroups.from_dict(
                {"groups": {"hao": {"mode": "manual", "ordered_unit_ids": [1, 2]}}}
            )

    def test_candidate_groups_duplicate_manual(self):
        g = CandidateGroups()
        with pytest.raises(InvalidInputError, match="重复"):
            g.set_manual("hao", ["1:1", "1:1"])

    def test_analysis_summary_bad(self):
        with pytest.raises(InvalidInputError):
            AnalysisSummary.from_dict({"global": "x", "per_asset": {}})
        with pytest.raises(InvalidInputError):
            AnalysisSummary.from_dict({"global": {}, "per_asset": {}, "revision": -1})

    def test_asset_from_dict_errors(self):
        from jrh.core.model import Asset

        with pytest.raises(InvalidInputError):
            Asset.from_dict({"id": "a1"})  # 缺字段
        with pytest.raises(InvalidInputError):
            Asset.from_dict(
                {
                    "id": "a1",
                    "file": "x",
                    "kind": "audio",
                    "sha256": "s",
                    "sample_rate": "x",
                    "num_samples": 1,
                    "duration_seconds": 1.0,
                }
            )


# ── project.py：错误路径与边界 ───────────────────────────────────


class TestProjectErrors:
    def test_duplicate_asset_rejected(self, tmp_path):
        from jrh.core.model import Asset

        proj = JRHProject.create(tmp_path / "p")
        a = Asset(
            id="a1",
            file="x",
            kind="audio",
            sha256="s",
            sample_rate=44100,
            num_samples=100,
            duration_seconds=1.0,
        )
        proj.add_asset(a)
        with pytest.raises(InvalidInputError, match="已存在"):
            proj.add_asset(a)

    def test_asset_bad_info_rejected(self, tmp_path):
        from jrh.core.model import Asset

        proj = JRHProject.create(tmp_path / "p")
        with pytest.raises(InvalidInputError, match="信息非法"):
            proj.add_asset(
                Asset(
                    id="a1",
                    file="x",
                    kind="audio",
                    sha256="s",
                    sample_rate=0,
                    num_samples=100,
                    duration_seconds=1.0,
                )
            )

    def test_sentence_bounds_non_int(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        with pytest.raises(InvalidInputError, match="整数"):
            proj.create_sentence("a1", 0.5, 100)

    def test_update_sentence_shrinks_below_unit_window(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(1, "hao", Timing(0, 0, -90000, 0, 0))
        with pytest.raises(InvalidInputError, match="窗口超出句子范围"):
            proj.update_sentence(1, end_sample=50000)

    def test_update_unit_empty_label(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(1, "hao", Timing(0, 0, -1000, 0, 0))
        with pytest.raises(InvalidInputError, match="label"):
            proj.update_unit(1, 1, label="")

    def test_update_unit_bad_enabled(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(1, "hao", Timing(0, 0, -1000, 0, 0))
        with pytest.raises(InvalidInputError, match="布尔"):
            proj.update_unit(1, 1, enabled="x")  # type: ignore[arg-type]

    def test_set_analysis_bad_value(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(1, "hao", Timing(0, 0, -1000, 0, 0))
        with pytest.raises(InvalidInputError):
            proj.set_unit_analysis(1, 1, {"rms_dbfs": float("inf")})

    def test_group_manual_bad_coord(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        with pytest.raises(InvalidInputError, match="坐标"):
            proj.group_set_manual("hao", ["not-a-coord"])

    def test_remove_asset_unreferenced_ok(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.remove_asset("a1")
        assert "a1" not in proj.assets

    def test_next_unit_missing(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100000)
        proj.create_unit(1, "hao", Timing(0, 0, -1000, 0, 0))
        with pytest.raises(NotFoundError):
            proj.next_unit_in_sentence(1, 99)

    def test_get_unit_missing(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        with pytest.raises(NotFoundError):
            proj.get_unit(1, 1)

    def test_get_sentence_missing(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        with pytest.raises(NotFoundError):
            proj.get_sentence(9)

    def test_merge_same_sentence(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 0, 100)
        with pytest.raises(InvalidInputError, match="两个不同"):
            proj.merge_sentences(1, 1)

    def test_split_requires_valid_sentence(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        with pytest.raises(NotFoundError):
            proj.split_sentence(99, 100)

    def test_create_unit_on_missing_sentence(self, tmp_path):
        proj = JRHProject.create(tmp_path / "p")
        with pytest.raises(NotFoundError):
            proj.create_unit(99, "hao", Timing(0, 0, -100, 0, 0))

    def test_unit_merge_timing_shift(self, tmp_path):
        """合并时较晚句子的单元 offset 平移。"""
        proj = JRHProject.create(tmp_path / "p")
        proj.add_asset(_asset())
        proj.create_sentence("a1", 50000, 100000)  # 句1 晚
        proj.create_unit(1, "hao", Timing(100, 0, -1000, 0, 0))
        proj.create_sentence("a1", 0, 50000)  # 句2 早
        proj.create_unit(2, "ni", Timing(0, 0, -1000, 0, 0))
        proj.merge_sentences(1, 2)  # 保留 1
        units = proj.units_in_sentence(1)
        by_label = {u.label: u for u in units}
        assert by_label["hao"].timing.offset == 100 - 50000  # 晚句平移


# ── validate.py：未覆盖分支 ──────────────────────────────────────


class TestValidateBranches:
    def _inmem_project(
        self, demo_project, mutate_units=None, mutate_sents=None, mutate_groups=None
    ):
        """绕过 open() 的严格校验，直接构造内存项目以覆盖 validate 防御分支。"""
        from jrh.core.ids import IdAllocator, IdCounters
        from jrh.core.model import CandidateGroups

        proj = JRHProject.open(demo_project)
        units = dict(proj.units)
        sents = dict(proj.sentences)
        groups = CandidateGroups.from_dict(proj.candidate_groups.to_dict())
        if mutate_units:
            mutate_units(units)
        if mutate_sents:
            mutate_sents(sents)
        if mutate_groups:
            mutate_groups(groups)
        return JRHProject(
            path=proj.path,
            manifest=dict(proj.manifest),
            assets=dict(proj.assets),
            sentences=sents,
            units=units,
            groups=groups,
            analysis_summary=proj.analysis_summary,
            pack=proj.pack,
            allocator=IdAllocator(IdCounters.from_dict(proj.manifest["id_counters"])),
        )

    def test_validate_label_charset_control_char(self):
        from jrh.core.validate import validate_label_charset

        assert validate_label_charset("a\x01b") is not None

    def test_validate_group_unknown_label_warning(self, demo_project):
        from jrh.core.util import write_json
        from jrh.core.validate import validate_project

        proj = JRHProject.open(demo_project)
        groups = proj.candidate_groups.to_dict()
        groups["groups"]["zzz"] = {"mode": "auto", "ordered_unit_ids": []}
        write_json(proj.path / "data" / "candidate_groups.json", groups)
        proj2 = JRHProject.open(demo_project)
        result = validate_project(proj2)
        assert any(i.code == "group.unknown_label" for i in result.issues)

    def test_validate_group_bad_order_type(self, demo_project):
        """ordered_unit_ids 非数组在打开时即失败（fail fast）。"""
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        groups = proj.candidate_groups.to_dict()
        groups["groups"]["hao"]["ordered_unit_ids"] = "not-a-list"
        write_json(proj.path / "data" / "candidate_groups.json", groups)
        with pytest.raises(InvalidInputError, match="ordered_unit_ids"):
            JRHProject.open(demo_project)

    def test_validate_asset_id_key_mismatch(self, demo_project):
        """防御分支：asset 字典键与 id 不一致。"""
        from jrh.core.validate import validate_project

        base = JRHProject.open(demo_project)
        assets = dict(base.assets)
        asset = assets.pop("asset-001")
        assets["ghost-key"] = asset  # 键 ≠ id
        proj = JRHProject(
            path=base.path,
            manifest=dict(base.manifest),
            assets=assets,
            sentences=base.sentences,
            units=base.units,
            groups=base.candidate_groups,
            analysis_summary=base.analysis_summary,
            pack=base.pack,
            allocator=base._allocator,  # noqa: SLF001
        )
        result = validate_project(proj)
        assert any(i.code == "asset.id" for i in result.errors())

    def test_validate_duplicate_unit_id_in_sentence(self, demo_project):
        """防御分支：句内重复 unit_id（绕过 open 的坐标唯一性检查）。"""
        from jrh.core.validate import validate_project

        base = JRHProject.open(demo_project)
        units = dict(base.units)
        dup = units[(1, 1)]
        units[(1, 1)] = dup
        units[(1, 9)] = dup  # 不同坐标、同一 unit_id 内容
        proj = JRHProject(
            path=base.path,
            manifest=dict(base.manifest),
            assets=base.assets,
            sentences=base.sentences,
            units=units,
            groups=base.candidate_groups,
            analysis_summary=base.analysis_summary,
            pack=base.pack,
            allocator=base._allocator,  # noqa: SLF001
        )
        result = validate_project(proj)
        assert any(i.code == "sentence.duplicate_unit" for i in result.errors())

    def test_validate_negative_max_unit_id_ever(self, demo_project):
        """防御分支：max_unit_id_ever 为负。"""
        from jrh.core.validate import validate_project

        proj = self._inmem_project(
            demo_project,
            mutate_sents=lambda s: s[1].__setattr__("max_unit_id_ever", -5),
        )
        result = validate_project(proj)
        assert any(i.code == "sentence.max_unit_id_ever" for i in result.errors())

    def test_validate_counter_lower_than_ids(self, demo_project):
        """防御分支：max_unit_id_ever 小于现有编号。"""
        from jrh.core.validate import validate_project

        proj = self._inmem_project(
            demo_project,
            mutate_sents=lambda s: s[1].__setattr__("max_unit_id_ever", 1),
        )
        result = validate_project(proj)
        assert any(i.code == "sentence.max_unit_id_ever" for i in result.errors())

    def test_validate_frozen_counter_inconsistency(self, tmp_path):
        """防御分支：冻结状态计数器不一致。"""
        from jrh.core.validate import validate_project

        p = build_demo_project(tmp_path, freeze=True)
        base = JRHProject.open(p)
        base._allocator.counters.max_sentence_id_ever = 1  # noqa: SLF001
        result = validate_project(base)
        assert any(i.code == "frozen.counters" for i in result.errors())

    def test_validate_label_charset_dollar(self):
        from jrh.core.validate import validate_label_charset

        assert validate_label_charset("a$b") is not None

    def test_validate_result_serialization(self, demo_project):
        """ValidationResult/Issue 的序列化方法（CLI JSON 输出路径）。"""
        from jrh.core.validate import validate_project

        proj = JRHProject.open(demo_project)
        result = validate_project(proj)
        d = result.to_dict()
        assert d["valid"] is True
        assert d["error_count"] == 0
        assert result.errors() == []
        assert result.error_count() == 0
        result.add("warning", "test.code", "loc", "msg")
        assert any(i.code == "test.code" for i in result.issues)
        assert result.to_dict()["warning_count"] == 1

    def test_validate_manifest_branches(self, demo_project):
        """manifest 各非法分支（内存构造）。"""
        from jrh.core.validate import validate_project

        base = JRHProject.open(demo_project)
        for key, value in [
            ("format", "NOPE"),
            ("schema_version", "9.9.9"),
            ("state", "banana"),
            ("language_pack", "no-such-pack"),
        ]:
            manifest = dict(base.manifest)
            manifest[key] = value
            proj = JRHProject(
                path=base.path,
                manifest=manifest,
                assets=base.assets,
                sentences=base.sentences,
                units=base.units,
                groups=base.candidate_groups,
                analysis_summary=base.analysis_summary,
                pack=base.pack,
                allocator=base._allocator,  # noqa: SLF001
            )
            result = validate_project(proj)
            assert result.has_errors(), key

    def test_validate_asset_branches(self, demo_project):
        """asset 非法分支（内存构造）。"""
        from jrh.core.validate import validate_project

        base = JRHProject.open(demo_project)
        assets = dict(base.assets)
        bad = assets["asset-001"]
        for field, value in [("sample_rate", 0), ("num_samples", 0), ("file", "")]:
            a = bad.__class__(
                id=bad.id,
                file=bad.file,
                kind=bad.kind,
                sha256=bad.sha256,
                sample_rate=bad.sample_rate,
                num_samples=bad.num_samples,
                duration_seconds=bad.duration_seconds,
            )
            setattr(a, field, value)
            assets2 = dict(assets)
            assets2["asset-001"] = a
            proj = JRHProject(
                path=base.path,
                manifest=dict(base.manifest),
                assets=assets2,
                sentences=base.sentences,
                units=base.units,
                groups=base.candidate_groups,
                analysis_summary=base.analysis_summary,
                pack=base.pack,
                allocator=base._allocator,  # noqa: SLF001
            )
            result = validate_project(proj)
            assert result.has_errors(), field

    def test_validate_sentence_range_branch(self, demo_project):
        """句范围非法分支（内存构造，绕过 open 校验）。"""
        from jrh.core.validate import validate_project

        proj = self._inmem_project(
            demo_project,
            mutate_sents=lambda s: s[2].__setattr__("end_sample", 10),
        )
        result = validate_project(proj)
        assert any(i.code == "sentence.range" for i in result.errors())

    def test_validate_unit_ref_and_analysis_branches(self, demo_project):
        """unit 引用缺失与 analysis 类型非法分支。"""
        from jrh.core.validate import validate_project

        proj = self._inmem_project(
            demo_project,
            mutate_units=lambda u: u[(1, 1)].__setattr__("sentence_id", 99),
        )
        result = validate_project(proj)
        assert any(i.code == "unit.sentence_ref" for i in result.errors())

        proj2 = self._inmem_project(
            demo_project,
            mutate_units=lambda u: u[(1, 1)].analysis.update({"duration_ms": "x"}),
        )
        result2 = validate_project(proj2)
        assert any(i.code == "unit.analysis" for i in result2.errors())

    def test_validate_group_mode_and_order_branches(self, demo_project):
        """group.mode / group.order / group.mismatch 防御分支。"""
        from jrh.core.validate import validate_project

        proj = self._inmem_project(
            demo_project,
            mutate_groups=lambda g: g.groups.__setitem__(
                "hao", {"mode": "banana", "ordered_unit_ids": []}
            ),
        )
        result = validate_project(proj)
        assert any(i.code == "group.mode" for i in result.errors())

        proj2 = self._inmem_project(
            demo_project,
            mutate_groups=lambda g: g.groups.__setitem__(
                "hao", {"mode": "manual", "ordered_unit_ids": "oops"}
            ),
        )
        result2 = validate_project(proj2)
        assert any(i.code == "group.order" for i in result2.errors())

        proj3 = self._inmem_project(
            demo_project,
            mutate_groups=lambda g: g.groups.__setitem__(
                "hao", {"mode": "manual", "ordered_unit_ids": ["not-coord"]}
            ),
        )
        result3 = validate_project(proj3)
        assert any(i.code == "group.order" for i in result3.errors())

        proj4 = self._inmem_project(
            demo_project,
            mutate_groups=lambda g: g.groups.__setitem__(
                "hao", {"mode": "manual", "ordered_unit_ids": ["2:1"]}
            ),
        )
        result4 = validate_project(proj4)
        assert any(i.code == "group.mismatch" for i in result4.issues)

    def test_validate_sha256_os_error(self, demo_project, monkeypatch):
        """_sha256_file 的 OSError 回退路径。"""
        from jrh.core.validate import _sha256_file, validate_project

        proj = JRHProject.open(demo_project)
        p = proj.path / proj.get_asset("asset-001").file

        def boom(*a, **k):
            raise OSError("denied")

        monkeypatch.setattr("builtins.open", boom)
        assert _sha256_file(p) is None
        # validate 中哈希失败不产生新错误（回退为无哈希比较）
        monkeypatch.undo()
        result = validate_project(proj)
        assert not result.has_errors()


# ── integrity.py：构建产物一致性分支 ─────────────────────────────


class TestIntegrityBranches:
    def test_integrity_asset_missing_file(self, demo_project):
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        (proj.path / "assets" / "src1.wav").unlink()
        result = check_integrity(proj)
        assert any(i.code == "integrity.asset_missing" for i in result.errors())

    def test_integrity_corrupt_oto_as_directory(self, demo_project):
        """oto.ini 被目录占用：read_oto 必须显式报错而非崩溃。"""
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        (out / "oto.ini").unlink()
        (out / "oto.ini").mkdir()
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_partial" for i in result.errors())

    def test_integrity_corrupt_alias_map_as_directory(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        (out / "alias-map.json").unlink()
        (out / "alias-map.json").mkdir()
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_partial" for i in result.errors())

    def test_integrity_corrupt_report_as_directory(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        (out / "build-report.json").unlink()
        (out / "build-report.json").mkdir()
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_partial" for i in result.errors())

    def test_integrity_bad_alias_map(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        write_json(out / "alias-map.json", {"bad-entry": "not-a-dict"})
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_alias_map" for i in result.errors())

    def test_integrity_alias_map_refs_missing_unit(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        amap = {
            "1-1-R-ni-hao": {
                "sentence_id": 99,
                "unit_id": 99,
                "kind": "full",
                "wav": "sentence_001.wav",
                "params": {},
            }
        }
        write_json(out / "alias-map.json", amap)
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_alias_map" for i in result.errors())

    def test_integrity_alias_map_alias_not_in_oto(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        amap = {
            "ghost-alias": {
                "sentence_id": 1,
                "unit_id": 1,
                "kind": "full",
                "wav": "sentence_001.wav",
                "params": {},
            }
        }
        write_json(out / "alias-map.json", amap)
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_alias_map" for i in result.errors())

    def test_integrity_bad_report(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        write_json(out / "build-report.json", {"not": "a report"})
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_report" for i in result.errors())

    def test_integrity_report_count_mismatch(self, demo_project):
        from jrh.core.compile_engine import compile_project, write_build
        from jrh.core.integrity import check_integrity
        from jrh.core.util import write_json

        proj = JRHProject.open(demo_project)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        report = {
            "summary": {"aliases_total": 999},
            "target": "openutau-jrh",
        }
        write_json(out / "build-report.json", report)
        result = check_integrity(proj)
        assert any(i.code == "integrity.build_report" for i in result.errors())

    def test_integrity_asset_ok_info(self, demo_project):
        from jrh.core.integrity import check_integrity

        proj = JRHProject.open(demo_project)
        result = check_integrity(proj)
        assert any(i.code == "integrity.asset_ok" for i in result.issues)


# ── oto_ini.py：编码回退与边界 ───────────────────────────────────


class TestOtoEncodingFallback:
    def test_fmt_ms_trailing_zero_strip(self):
        assert fmt_ms(85.600) == "85.6"
        assert fmt_ms(0.005) == "0.005"

    def test_detect_encoding_utf8_valid(self, tmp_path):
        p = tmp_path / "oto.ini"
        p.write_text("x.wav=a,1,2,-3,4,5\n", encoding="utf-8")
        assert read_oto(p)[0].alias == "a"

    def test_detect_encoding_utf8_cjk_preferred(self, tmp_path):
        """合法 UTF-8 优先于 shift_jis（0xE4 0xBD 0xA0 会被 shift_jis 误读）。"""
        p = tmp_path / "oto.ini"
        p.write_text("x.wav=你,1,2,-3,4,5\n", encoding="utf-8")
        assert read_oto(p)[0].alias == "你"

    def test_detect_encoding_gbk(self, tmp_path):
        """0x81 0xFD 仅 gbk 可解码（utf-8/shift_jis/cp932 均失败）→ 回退 gbk。"""
        expected = bytes([0x81, 0xFD]).decode("gbk")
        p = tmp_path / "oto.ini"
        p.write_bytes(b"x.wav=\x81\xfd,1,2,-3,4,5\n")
        assert read_oto(p)[0].alias == expected

    def test_line_too_short_ignored(self, tmp_path):
        p = tmp_path / "oto.ini"
        p.write_text("x.wav=partial,1,2\n", encoding="utf-8")
        assert read_oto(p) == []

    def test_oto_line_roundtrip_format(self):
        line = OtoLine("s.wav", "alias", 1.0, 2.0, -3.0, 4.0, 5.0)
        assert line.to_line() == "s.wav=alias,1,2,-3,4,5"


def _asset():
    from jrh.core.model import Asset

    return Asset(
        id="a1",
        file="assets/x.wav",
        kind="audio",
        sha256="0" * 64,
        sample_rate=44100,
        num_samples=200000,
        duration_seconds=4.5,
    )
