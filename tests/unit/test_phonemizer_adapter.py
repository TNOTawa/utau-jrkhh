"""OpenUtau 适配层测试：只做转换，不包含选择逻辑。"""

from __future__ import annotations

import inspect

from jrh.core.project import JRHProject
from jrh.core.selection import select_sequence
from jrh.phonemizer.adapters import Phoneme, to_phonemes


def test_to_phonemes_full(demo_project):
    proj = JRHProject.open(demo_project)
    r = select_sequence(proj, ["ni"])[0]
    ph = to_phonemes(r)
    assert ph == [Phoneme("1-1-R-ni-hao", 0.0)]
    assert ph[0].to_dict() == {"phoneme": "1-1-R-ni-hao", "position_ms": 0.0}


def test_to_phonemes_split(tmp_path):
    from fixtures.builder import build_split_project

    from jrh.core.project import JRHProject

    proj = JRHProject.open(build_split_project(tmp_path))
    r = select_sequence(proj, ["ni", "hao"])[1]
    ph = to_phonemes(r)
    assert len(ph) == 2
    assert ph[0].position_ms < 0 and ph[1].position_ms == 0.0
    assert ph[0].phoneme.endswith("$T") and ph[1].phoneme.endswith("$B")


def test_to_phonemes_missing_empty(demo_project):
    proj = JRHProject.open(demo_project)
    r = select_sequence(proj, ["zzz"])[0]
    assert to_phonemes(r) == []


def test_adapter_has_no_selection_logic():
    """适配层必须是薄转换：源码中不得出现层级关键词/候选搜索。"""
    from pathlib import Path

    path = Path(inspect.getfile(to_phonemes)).parent / "adapters.py"
    src = path.read_text(encoding="utf-8")
    for banned in ("continuous", "substitute", "candidates", "leading_vowel"):
        assert banned not in src, f"适配层不应包含选择逻辑关键词: {banned}"
