"""Determinism 不变量测试：同输入 ⇒ 逐字节相同输出。"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from jrh.core.compile_engine import compile_project, write_build
from jrh.core.project import JRHProject
from jrh.core.selection import select_sequence


def _dir_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(root))
            h.update(rel.encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def _project_dict(proj: JRHProject) -> dict:
    return {
        "sentences": [s.to_dict() for s in proj.sentences_sorted()],
        "units": [u.to_dict() for u in proj.units_sorted()],
        "groups": proj.candidate_groups.to_dict(),
    }


class TestCompileDeterminism:
    def test_repeat_compile_identical(self, demo_project):
        proj = JRHProject.open(demo_project)
        r1 = compile_project(proj)
        r2 = compile_project(proj)
        assert [e.to_dict() for e in r1.entries] == [e.to_dict() for e in r2.entries]
        assert r1.report_dict(proj) == r2.report_dict(proj)

    def test_clean_rebuild_byte_identical(self, demo_project):
        """删除 build 目录后重建，产物逐字节一致。"""
        proj = JRHProject.open(demo_project)
        out1 = proj.path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out1)
        sha1 = _dir_sha256(out1)

        shutil.rmtree(out1)
        proj2 = JRHProject.open(demo_project)
        out2 = proj2.path / "builds" / "openutau-jrh"
        write_build(proj2, compile_project(proj2), out2)
        sha2 = _dir_sha256(out2)
        assert sha1 == sha2

    def test_json_files_sorted_keys(self, demo_project):
        import json

        proj = JRHProject.open(demo_project)
        proj.save()
        for name in ("manifest.json", "data/units.json", "data/sentences.json"):
            obj = json.loads((proj.path / name).read_text(encoding="utf-8"))
            text = (proj.path / name).read_text(encoding="utf-8")
            assert text == json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


class TestSelectionDeterminism:
    def test_same_input_same_result(self, demo_project):
        proj = JRHProject.open(demo_project)
        targets = ["wo", "hao", "ma", "zzz", "a"]
        a = [r.to_dict() for r in select_sequence(proj, targets)]
        b = [r.to_dict() for r in select_sequence(proj, targets)]
        assert a == b

    def test_selection_after_reload_same(self, demo_project):
        proj = JRHProject.open(demo_project)
        before = [r.to_dict() for r in select_sequence(proj, ["ni", "hao", "a"])]
        proj.save()
        proj2 = JRHProject.open(demo_project)
        after = [r.to_dict() for r in select_sequence(proj2, ["ni", "hao", "a"])]
        assert before == after


class TestSaveDeterminism:
    def test_save_is_idempotent(self, demo_project):
        proj = JRHProject.open(demo_project)
        proj.save()
        files1 = {p.name: p.read_bytes() for p in (proj.path / "data").glob("*.json")}
        proj.save()
        files2 = {p.name: p.read_bytes() for p in (proj.path / "data").glob("*.json")}
        assert files1 == files2

    def test_project_dict_roundtrip(self, demo_project):
        proj = JRHProject.open(demo_project)
        d1 = _project_dict(proj)
        proj.save()
        proj2 = JRHProject.open(demo_project)
        assert _project_dict(proj2) == d1
