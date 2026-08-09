"""Golden 测试：固定 fixture 的编译产物必须与检入的期望值逐字节一致。

重新生成：python tests/golden/generate_golden.py（生成后必须人工核对数值再提交）。
"""

from __future__ import annotations

from pathlib import Path

from fixtures.builder import build_demo_project

from jrh.core.compile_engine import compile_project, write_build
from jrh.core.project import JRHProject

GOLDEN_DATA = Path(__file__).resolve().parent / "data"


def _compile_to(tmp_path: Path) -> Path:
    proj_path = build_demo_project(tmp_path)
    proj = JRHProject.open(proj_path)
    out = proj_path / "builds" / "openutau-jrh"
    write_build(proj, compile_project(proj), out)
    return out


class TestGoldenOutputs:
    def test_oto_ini_byte_identical(self, tmp_path):
        out = _compile_to(tmp_path)
        got = (out / "oto.ini").read_bytes()
        expected = (GOLDEN_DATA / "oto.ini").read_bytes()
        assert got == expected

    def test_build_report_byte_identical(self, tmp_path):
        out = _compile_to(tmp_path)
        got = (out / "build-report.json").read_bytes()
        expected = (GOLDEN_DATA / "build-report.json").read_bytes()
        assert got == expected

    def test_alias_map_byte_identical(self, tmp_path):
        out = _compile_to(tmp_path)
        got = (out / "alias-map.json").read_bytes()
        expected = (GOLDEN_DATA / "alias-map.json").read_bytes()
        assert got == expected

    def test_wav_content(self, tmp_path):
        """原句 WAV 内容（int16 采样）与素材切片一致（逐字节级确定性）。"""
        from fixtures.wavs import read_wav_samples

        proj_path = build_demo_project(tmp_path)
        proj = JRHProject.open(proj_path)
        out = proj_path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        asset_samples = {
            aid: read_wav_samples(proj_path / proj.get_asset(aid).file)
            for aid in sorted(proj.assets)
        }
        for sent in proj.sentences_sorted():
            exported = read_wav_samples(out / f"sentence_{sent.sentence_id:03d}.wav")
            assert exported == asset_samples[sent.asset_id][sent.start_sample : sent.end_sample]

    def test_golden_data_complete(self):
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            assert (GOLDEN_DATA / name).exists(), f"缺少 golden 数据: {name}"
