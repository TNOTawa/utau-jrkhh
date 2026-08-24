"""Golden 测试：固定 fixture 的编译产物必须与检入的期望值逐字节一致。

- data/         默认编译（zh demo，cvvc 关）
- data_cvvc/    CVVC 编译（ja demo，cvvc 开，含 VC 条目）
- data_zh_cvvc/ CVVC 编译（zh demo，cvvc 开，presamp 短 ID VC 条目）
重新生成：python tests/golden/generate_golden.py（生成后必须人工核对数值再提交）。
"""

from __future__ import annotations

from pathlib import Path

from fixtures.builder import build_demo_project, build_ja_demo_project

from jrh.core.compile_engine import CompileConfig, compile_project, write_build
from jrh.core.project import JRHProject

GOLDEN_DATA = Path(__file__).resolve().parent / "data"
GOLDEN_CVVC_DATA = Path(__file__).resolve().parent / "data_cvvc"
GOLDEN_ZH_CVVC_DATA = Path(__file__).resolve().parent / "data_zh_cvvc"


def _compile_to(tmp_path: Path) -> Path:
    proj_path = build_demo_project(tmp_path)
    proj = JRHProject.open(proj_path)
    out = proj_path / "builds" / "openutau-jrh"
    write_build(proj, compile_project(proj), out)
    return out


def _compile_cvvc_to(tmp_path: Path) -> Path:
    proj_path = build_ja_demo_project(tmp_path)
    proj = JRHProject.open(proj_path)
    out = proj_path / "builds" / "openutau-jrh"
    write_build(proj, compile_project(proj, CompileConfig(cvvc=True)), out)
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
        """原句 WAV 内容与素材切片一致（逐字节级确定性）；
        整资产句定向已有文件（文件名 = 资产文件名，见 sentence_wav_name）。"""
        from fixtures.wavs import read_wav_samples

        proj_path = build_demo_project(tmp_path)
        proj = JRHProject.open(proj_path)
        out = proj_path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj), out)
        asset_samples = {
            aid: read_wav_samples(proj_path / proj.get_asset(aid).file)
            for aid in sorted(proj.assets)
        }
        from jrh.core.compile_engine import sentence_wav_name

        for sent in proj.sentences_sorted():
            exported = read_wav_samples(out / sentence_wav_name(proj, sent))
            assert exported == asset_samples[sent.asset_id][sent.start_sample : sent.end_sample]

    def test_golden_data_complete(self):
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            assert (GOLDEN_DATA / name).exists(), f"缺少 golden 数据: {name}"


class TestGoldenCvvcOutputs:
    def test_oto_ini_byte_identical(self, tmp_path):
        out = _compile_cvvc_to(tmp_path)
        got = (out / "oto.ini").read_bytes()
        expected = (GOLDEN_CVVC_DATA / "oto.ini").read_bytes()
        assert got == expected

    def test_build_report_byte_identical(self, tmp_path):
        out = _compile_cvvc_to(tmp_path)
        got = (out / "build-report.json").read_bytes()
        expected = (GOLDEN_CVVC_DATA / "build-report.json").read_bytes()
        assert got == expected

    def test_alias_map_byte_identical(self, tmp_path):
        out = _compile_cvvc_to(tmp_path)
        got = (out / "alias-map.json").read_bytes()
        expected = (GOLDEN_CVVC_DATA / "alias-map.json").read_bytes()
        assert got == expected

    def test_vc_entries_present(self, tmp_path):
        import json

        out = _compile_cvvc_to(tmp_path)
        report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
        vc = [e for e in report["entries"] if e["kind"] == "vc"]
        assert [e["alias"] for e in vc] == ["a t", "o n", "i ch", "i h", "a k", "a t1"]
        assert report["summary"]["vc"] == 6

    def test_cvvc_golden_data_complete(self):
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            assert (GOLDEN_CVVC_DATA / name).exists(), f"缺少 cvvc golden 数据: {name}"


class TestGoldenZhCvvcOutputs:
    def _compile_zh_cvvc_to(self, tmp_path: Path) -> Path:
        proj_path = build_demo_project(tmp_path)
        proj = JRHProject.open(proj_path)
        out = proj_path / "builds" / "openutau-jrh"
        write_build(proj, compile_project(proj, CompileConfig(cvvc=True)), out)
        return out

    def test_oto_ini_byte_identical(self, tmp_path):
        out = self._compile_zh_cvvc_to(tmp_path)
        assert (out / "oto.ini").read_bytes() == (GOLDEN_ZH_CVVC_DATA / "oto.ini").read_bytes()

    def test_build_report_byte_identical(self, tmp_path):
        out = self._compile_zh_cvvc_to(tmp_path)
        assert (out / "build-report.json").read_bytes() == (
            GOLDEN_ZH_CVVC_DATA / "build-report.json"
        ).read_bytes()

    def test_alias_map_byte_identical(self, tmp_path):
        out = self._compile_zh_cvvc_to(tmp_path)
        assert (out / "alias-map.json").read_bytes() == (
            GOLDEN_ZH_CVVC_DATA / "alias-map.json"
        ).read_bytes()

    def test_presamp_short_id_vc_aliases(self, tmp_path):
        import json

        out = self._compile_zh_cvvc_to(tmp_path)
        report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
        vc = [e["alias"] for e in report["entries"] if e["kind"] == "vc"]
        # ni→hao=i h、wo→hao=o h、hao→ma=ao m、hao→jiu=ao j（均与 presamp 短 ID 一致）
        assert vc == ["i h", "o h", "ao m", "ao j"]
        assert report["summary"]["vc"] == 4

    def test_zh_cvvc_golden_data_complete(self):
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            assert (GOLDEN_ZH_CVVC_DATA / name).exists(), f"缺少 zh cvvc golden 数据: {name}"
