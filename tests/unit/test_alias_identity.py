"""Alias Identity 不变量测试：身份只用永久坐标 s:u，不解析后三项。"""

from __future__ import annotations

from jrh.core.compile_engine import (
    CompileConfig,
    _display_labels,
    _five_part_alias,
    compile_project,
)
from jrh.core.project import JRHProject


def test_identity_not_affected_by_trailing_three(tmp_path):
    """修改 label（后三项变化）不改变单元身份与查找。"""
    from fixtures.builder import build_demo_project

    p = build_demo_project(tmp_path)
    proj = JRHProject.open(p)
    proj.update_unit(1, 2, label="gao")  # 1:2 hao → gao
    proj.save()
    proj2 = JRHProject.open(p)
    u = proj2.get_unit(1, 2)  # 身份定位仍然有效
    assert u.label == "gao"


def test_compile_uses_coordinates_not_alias_parsing(demo_project):
    """编译产物反查不依赖五段式别名解析。"""
    proj = JRHProject.open(demo_project)
    result = compile_project(proj)
    by_alias = {e.alias: e for e in result.entries}
    full = by_alias["1-2-ni-hao-a"]
    assert (full.sentence_id, full.unit_id) == (1, 2)


def test_display_labels_boundaries(demo_project):
    proj = JRHProject.open(demo_project)
    prev, cur, nxt = _display_labels(proj, 1, 1)
    assert (prev, cur, nxt) == (None, "ni", "hao")
    prev, cur, nxt = _display_labels(proj, 1, 3)
    assert (prev, cur, nxt) == ("hao", "a", None)


def test_five_part_alias_uses_rest_marker(demo_project):
    proj = JRHProject.open(demo_project)
    cfg = CompileConfig()
    prev, cur, nxt = _display_labels(proj, 1, 1)
    alias = _five_part_alias(proj, 1, 1, prev, cur, nxt, cfg)
    assert alias == "1-1-R-ni-hao"
