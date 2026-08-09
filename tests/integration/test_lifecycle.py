"""集成测试：完整生命周期 + Source Timeline 追溯链。"""

from __future__ import annotations

import json

from fixtures.wavs import read_wav_samples

from jrh.core.compile_engine import compile_project, sentence_wav_name, write_build
from jrh.core.project import JRHProject
from jrh.core.validate import validate_project
from jrh.formats.oto_ini import read_oto


class TestFullLifecycle:
    def test_init_to_compile(self, demo_project):
        proj = JRHProject.open(demo_project)
        assert not validate_project(proj).has_errors()

        proj.freeze()
        proj2 = JRHProject.open(demo_project)
        assert proj2.frozen

        result = compile_project(proj2)
        out = proj2.path / "builds" / "openutau-jrh"
        write_build(proj2, result, out)

        # 产物齐全
        assert (out / "oto.ini").exists()
        assert (out / "alias-map.json").exists()
        assert (out / "build-report.json").exists()
        for sent in proj2.sentences_sorted():
            assert (out / sentence_wav_name(sent.sentence_id)).exists()

        # oto 条目数与 report 一致
        oto = read_oto(out / "oto.ini")
        report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
        assert len(oto) == report["summary"]["aliases_total"]

        # alias-map 反查全部有效
        amap = json.loads((out / "alias-map.json").read_text(encoding="utf-8"))
        assert set(amap) == {line.alias for line in oto}

    def test_analyze_with_rms(self, demo_project):
        from jrh.audio.rms import unit_rms_dbfs

        proj = JRHProject.open(demo_project)
        u = proj.get_unit(1, 1)
        rms = unit_rms_dbfs(proj, u)
        assert rms is not None
        # 12000 振幅正弦 → rms ≈ 12000/√2 ≈ 8485 → ≈ -11.7 dBFS
        assert abs(rms - (-11.7)) < 0.3

    def test_analyze_missing_file_returns_none(self, demo_project):
        proj = JRHProject.open(demo_project)
        (proj.path / "assets" / "src1.wav").unlink()
        from jrh.audio.rms import unit_rms_dbfs

        assert unit_rms_dbfs(proj, proj.get_unit(1, 1)) is None


class TestSourceTimeline:
    """Source Timeline 不变量：Unit → Asset 时间轴追溯链。"""

    def test_unit_to_asset_position(self, demo_project):
        proj = JRHProject.open(demo_project)
        u = proj.get_unit(1, 2)
        sent = proj.get_sentence(1)
        asset = proj.get_asset("asset-001")
        # 单元窗口在 asset 时间轴上的绝对位置
        abs_start = sent.start_sample + u.timing.offset
        abs_end = sent.start_sample + u.timing.window_end()
        assert abs_start == 35280
        assert abs_end == 74970
        assert 0 <= abs_start < abs_end <= asset.num_samples

    def test_build_alias_backtrace(self, demo_project):
        proj = JRHProject.open(demo_project)
        result = compile_project(proj)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, result, out)
        amap = json.loads((out / "alias-map.json").read_text(encoding="utf-8"))
        for _alias, info in amap.items():
            s, u = info["sentence_id"], info["unit_id"]
            unit = proj.get_unit(s, u)  # 反查成功
            sent = proj.get_sentence(s)
            # 产物中的 WAV = 句子切片
            assert info["wav"] == sentence_wav_name(s)
            assert proj.get_asset(sent.asset_id).id == sent.asset_id
            # 来源单元确实指向该 asset
            assert unit.label == info["source_label"]

    def test_exported_wav_is_asset_slice(self, demo_project):
        """导出原句 WAV 内容 = 各自 asset 对应采样区间（独立 stdlib 验证路径）。"""
        proj = JRHProject.open(demo_project)
        result = compile_project(proj)
        out = proj.path / "builds" / "openutau-jrh"
        write_build(proj, result, out)
        asset_samples = {
            aid: read_wav_samples(proj.path / proj.get_asset(aid).file)
            for aid in sorted(proj.assets)
        }
        for sent in proj.sentences_sorted():
            exported = read_wav_samples(out / sentence_wav_name(sent.sentence_id))
            expected = asset_samples[sent.asset_id][sent.start_sample : sent.end_sample]
            assert exported == expected, f"sentence {sent.sentence_id} 切片不一致"

    def test_different_sample_rates(self, demo_project):
        """asset-001(44100) 与 asset-002(48000) 并存且各自换算正确。"""
        proj = JRHProject.open(demo_project)
        result = compile_project(proj)
        ms = {e.alias: e.params for e in result.entries}
        # 48000 Hz 的 3:1：offset 2400 → 50ms
        assert ms["3-1-R-hao-jiu"]["offset"] == 50.0
        # 44100 Hz 的 1:1：offset 2205 → 50ms
        assert ms["1-1-R-ni-hao"]["offset"] == 50.0
