"""CVVC 的 VC 条目编译单元测试（JRH_SPEC §5 VC 派生）。

日语 fixture（tests/fixtures/builder.py::build_ja_demo_project）覆盖：
- 促音借位 + 归一化去重（あって 两侧都借到 a→te，只产一条 "a t"）
- ん 全辅音拍作 C 侧（"o n"）
- 同对多样本编号（"a t" / "a t1"，按辅音侧有效组序）
- 零声母/元音拍/句尾不生成
"""

from __future__ import annotations

import pytest

from jrh.core.compile_engine import CompileConfig, compile_project
from jrh.core.errors import InvalidInputError
from jrh.core.model import Timing
from jrh.core.project import JRHProject

# (alias, sentence_id, unit_id, params_ms) —— 与冒烟验证的手算值一致
EXPECTED_VC = [
    (
        "a t",
        1,
        3,
        {
            "offset": 226.757,
            "consonant": 634.921,
            "cutoff": -634.921,
            "preutterance": 226.757,
            "overlap": 113.379,
        },
    ),
    (
        "o n",
        2,
        2,
        {
            "offset": 340.136,
            "consonant": 521.542,
            "cutoff": -521.542,
            "preutterance": 204.082,
            "overlap": 102.041,
        },
    ),
    (
        "i ch",
        2,
        4,
        {
            "offset": 1190.476,
            "consonant": 306.122,
            "cutoff": -306.122,
            "preutterance": 170.068,
            "overlap": 85.034,
        },
    ),
    (
        "i h",
        2,
        5,
        {
            "offset": 1587.302,
            "consonant": 226.757,
            "cutoff": -226.757,
            "preutterance": 90.703,
            "overlap": 45.351,
        },
    ),
    (
        "a k",
        3,
        2,
        {
            "offset": 340.136,
            "consonant": 340.136,
            "cutoff": -340.136,
            "preutterance": 204.082,
            "overlap": 102.041,
        },
    ),
    (
        "a t1",
        4,
        2,
        {
            "offset": 340.136,
            "consonant": 385.488,
            "cutoff": -385.488,
            "preutterance": 204.082,
            "overlap": 102.041,
        },
    ),
]


def _vc(project_path):
    proj = JRHProject.open(project_path)
    result = compile_project(proj, CompileConfig(cvvc=True))
    entries = [e for e in result.entries if e.kind == "vc"]
    return entries, result, proj


class TestJaVcCompile:
    def test_exact_vc_entries(self, ja_demo_project):
        entries, _res, _proj = _vc(ja_demo_project)
        got = [(e.alias, e.sentence_id, e.unit_id, e.params) for e in entries]
        assert got == [t[:4] for t in EXPECTED_VC]

    def test_vc_source_labels(self, ja_demo_project):
        entries, _res, _proj = _vc(ja_demo_project)
        assert [e.source_label for e in entries] == ["te", "n", "chi", "ha", "ka", "te"]

    def test_vc_reuses_sentence_wav(self, ja_demo_project):
        entries, _res, _proj = _vc(ja_demo_project)
        for e in entries:
            assert e.wav == f"sentence_{e.sentence_id:03d}.wav"

    def test_default_compile_has_no_vc(self, ja_demo_project):
        proj = JRHProject.open(ja_demo_project)
        result = compile_project(proj)
        assert not any(e.kind == "vc" for e in result.entries)
        report = result.report_dict(proj)
        assert "vc" not in report["summary"]
        assert "cvvc" not in report["config"]

    def test_report_summary_vc(self, ja_demo_project):
        entries, result, proj = _vc(ja_demo_project)
        report = result.report_dict(proj)
        assert report["summary"]["vc"] == len(EXPECTED_VC)
        assert report["summary"]["aliases_total"] == len(result.entries)
        assert report["config"]["cvvc"] is True
        assert report["config"]["vc_offset_ratio"] == 0.5
        assert report["config"]["vc_overlap_ratio"] == 0.5

    def test_ratios_configurable(self, ja_demo_project):
        proj = JRHProject.open(ja_demo_project)
        result = compile_project(
            proj, CompileConfig(cvvc=True, vc_offset_ratio=0.4, vc_overlap_ratio=0.6)
        )
        a_t = next(e for e in result.entries if e.alias == "a t")
        # pre = 20000*0.4 = 8000；offset = 20000-8000 = 12000；
        # window = 38000-12000 = 26000；overlap = 8000*0.6 = 4800
        assert a_t.params == {
            "offset": 272.109,
            "consonant": 589.569,
            "cutoff": -589.569,
            "preutterance": 181.406,
            "overlap": 108.844,
        }

    def test_invalid_ratio_rejected(self, ja_demo_project):
        proj = JRHProject.open(ja_demo_project)
        with pytest.raises(InvalidInputError):
            compile_project(proj, CompileConfig(cvvc=True, vc_offset_ratio=1.5))

    def test_disabled_consonant_unit_blocks_pair(self, ja_demo_project):
        proj = JRHProject.open(ja_demo_project)
        proj.update_unit(1, 3, enabled=False)  # 禁用 S1 的 te
        result = compile_project(proj, CompileConfig(cvvc=True))
        vcs = [e for e in result.entries if e.kind == "vc"]
        assert not any(e.sentence_id == 1 for e in vcs)  # S1 不再产 VC
        a_t = [e for e in vcs if e.alias == "a t"]
        assert len(a_t) == 1 and a_t[0].sentence_id == 4 and a_t[0].unit_id == 2

    def test_disabled_vowel_unit_blocks_pair(self, ja_demo_project):
        proj = JRHProject.open(ja_demo_project)
        proj.update_unit(1, 1, enabled=False)  # 禁用 S1 的 a
        result = compile_project(proj, CompileConfig(cvvc=True))
        vcs = [e for e in result.entries if e.kind == "vc"]
        assert not any(e.sentence_id == 1 for e in vcs)

    def test_zero_onset_and_ending_no_vc(self, ja_demo_project):
        # S5 おえ（零声母 e）与 S2 句尾 ha 均不生成（EXPECTED_VC 已隐式覆盖）
        entries, _res, _proj = _vc(ja_demo_project)
        aliases = {e.alias for e in entries}
        assert not any(a.startswith("e ") for a in aliases)  # e 为 V 侧的 VC 不存在
        assert "o e" not in aliases  # おえ 未产 VC
        assert "a h" not in aliases  # 句尾 ha：无 ENDING

    def test_determinism(self, ja_demo_project):
        e1, r1, _p1 = _vc(ja_demo_project)
        e2, r2, _p2 = _vc(ja_demo_project)
        assert [(e.alias, e.sentence_id, e.unit_id, e.params) for e in e1] == [
            (e.alias, e.sentence_id, e.unit_id, e.params) for e in e2
        ]
        assert r1.report_dict(_p1) == r2.report_dict(_p2)

    def test_frozen_project_supported(self, ja_demo_project):
        proj = JRHProject.open(ja_demo_project)
        proj.freeze()
        result = compile_project(proj, CompileConfig(cvvc=True))
        assert sum(1 for e in result.entries if e.kind == "vc") == len(EXPECTED_VC)


class TestZhVcStructural:
    """中文：机制层通吃（语言包接口驱动），本阶段不承诺精度。"""

    def test_zh_cvvc_aliases(self, demo_project):
        proj = JRHProject.open(demo_project)
        result = compile_project(proj, CompileConfig(cvvc=True))
        got = {(e.alias, e.sentence_id, e.unit_id) for e in result.entries if e.kind == "vc"}
        assert got == {("i h", 1, 2), ("o h", 2, 2), ("ao m", 2, 3), ("ao j", 3, 2)}


class TestVcWalkEdges:
    """辅助拍借位的边界：句首/句尾、禁用阻断、辅助拍链去重。"""

    @staticmethod
    def _build(tmp_path, units):
        import hashlib

        from fixtures.wavs import write_sine_wav

        from jrh.core.model import Asset

        root = tmp_path / "w.jrh"
        proj = JRHProject.create(root, "jrh.ja-romaji")
        wav = write_sine_wav(root / "assets" / "x.wav", 44100, 3.0)
        proj.add_asset(
            Asset(
                id="a1",
                file="assets/x.wav",
                kind="audio",
                sha256=hashlib.sha256(wav.read_bytes()).hexdigest(),
                sample_rate=44100,
                num_samples=132300,
                duration_seconds=3.0,
            )
        )
        end = max(int(t.window_end()) for _l, t, _e in units)
        sent = proj.create_sentence("a1", 0, end)
        for label, timing, enabled in units:
            proj.create_unit(sent.sentence_id, label, timing, enabled=enabled)
        proj.save()
        return root

    def _vc_aliases(self, tmp_path, units):
        proj = JRHProject.open(self._build(tmp_path, units))
        result = compile_project(proj, CompileConfig(cvvc=True))
        return [e.alias for e in result.entries if e.kind == "vc"]

    def test_helper_at_sentence_end_no_vc(self, tmp_path):
        units = [
            ("a", Timing(0.0, 0.0, -15000.0, 0.0, 0.0), True),
            ("xtsu", Timing(15000.0, 5000.0, -5000.0, 0.0, 0.0), True),
        ]
        assert self._vc_aliases(tmp_path, units) == []

    def test_helper_at_sentence_start_no_vc(self, tmp_path):
        units = [
            ("xtsu", Timing(0.0, 5000.0, -5000.0, 0.0, 0.0), True),
            ("te", Timing(10000.0, 5000.0, -15000.0, 1000.0, 1000.0), True),
        ]
        assert self._vc_aliases(tmp_path, units) == []

    def test_disabled_helper_blocks_backward_borrow(self, tmp_path):
        units = [
            ("a", Timing(0.0, 0.0, -15000.0, 0.0, 0.0), True),
            ("xtsu", Timing(15000.0, 5000.0, -5000.0, 0.0, 0.0), False),
            ("xtsu", Timing(20000.0, 5000.0, -5000.0, 0.0, 0.0), True),
            ("te", Timing(25000.0, 5000.0, -15000.0, 1000.0, 1000.0), True),
        ]
        assert self._vc_aliases(tmp_path, units) == []

    def test_disabled_helper_blocks_forward_borrow(self, tmp_path):
        units = [
            ("a", Timing(0.0, 0.0, -15000.0, 0.0, 0.0), True),
            ("xtsu", Timing(15000.0, 5000.0, -5000.0, 0.0, 0.0), True),
            ("xtsu", Timing(20000.0, 5000.0, -5000.0, 0.0, 0.0), False),
            ("te", Timing(25000.0, 5000.0, -15000.0, 1000.0, 1000.0), True),
        ]
        assert self._vc_aliases(tmp_path, units) == []

    def test_helper_chain_dedup_single_vc(self, tmp_path):
        units = [
            ("a", Timing(0.0, 0.0, -15000.0, 0.0, 0.0), True),
            ("xtsu", Timing(15000.0, 5000.0, -5000.0, 0.0, 0.0), True),
            ("xtsu", Timing(20000.0, 5000.0, -5000.0, 0.0, 0.0), True),
            ("te", Timing(25000.0, 5000.0, -15000.0, 1000.0, 1000.0), True),
        ]
        assert self._vc_aliases(tmp_path, units) == ["a t"]
