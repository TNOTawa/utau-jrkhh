"""母版侧自动拼字（jrh combine）单元测试。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fixtures.wavs import write_sine_wav

from jrh.combine import combine_phonemes
from jrh.core.errors import FrozenError, InvalidInputError, JRHError
from jrh.core.model import Asset, Timing
from jrh.core.project import JRHProject

SR = 44100


def _make_project(root: Path, with_audio: bool = True) -> Path:
    """组合源项目：qi×2（人工排序 1:2 在前）、qing、yan、xian、sa、ba。"""
    proj_path = root / "cb.jrh"
    proj = JRHProject.create(proj_path, "jrh.zh-pinyin")
    assets_dir = proj_path / "assets"
    wav = write_sine_wav(assets_dir / "src.wav", SR, 4.0)
    if with_audio:
        from jrh.audio.probe import probe_audio_file

        info = probe_audio_file(wav)
        proj.add_asset(
            Asset(
                id="a1",
                file="assets/src.wav",
                kind="audio",
                sha256=hashlib.sha256(wav.read_bytes()).hexdigest(),
                sample_rate=int(info["sample_rate"]),
                num_samples=int(info["num_samples"]),
                duration_seconds=float(info["duration_seconds"]),
            )
        )
    else:
        proj.add_asset(
            Asset(
                id="a1",
                file="assets/src.wav",
                kind="audio",
                sha256="0" * 64,
                sample_rate=SR,
                num_samples=SR * 4,
                duration_seconds=4.0,
            )
        )
    proj.create_sentence("a1", 0, SR * 4)
    proj.create_unit(1, "qi", Timing(0, 2205, -17640, 2205, 1102))  # 0.4s
    proj.create_unit(1, "qi", Timing(SR, 2205, -22050, 2205, 1102))  # 0.5s
    proj.create_unit(1, "qing", Timing(SR * 2, 2205, -22050, 2205, 1102))
    proj.create_unit(1, "yan", Timing(SR * 3, 2205, -17640, 2205, 1102))
    proj.create_unit(1, "xian", Timing(SR * 3 + 17640 + 100, 2205, -22050, 2205, 1102))
    proj.create_sentence("a1", 0, SR * 4)
    proj.create_unit(2, "sa", Timing(0, 2205, -17640, 2205, 1102))
    proj.create_unit(2, "ba", Timing(SR, 2205, -17640, 2205, 1102))
    proj.group_set_manual("qi", ["1:2", "1:1"])
    proj.save()
    return proj_path


def _plan(report, label):
    return next(p for p in report["combined"] if p["label"] == label)


class TestCombinePlan:
    def test_missing_set_and_sources(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        report = combine_phonemes(proj, dry_run=True)
        assert report["existing_labels"] == 6
        assert report["missing_total"] == 410 - 6
        qian = _plan(report, "qian")
        # 辅音源：qi 组 rank0 = 1:2（人工排序）；跨 label 统计中位数 → 1:2
        assert qian["consonant_source"] == "1:2"
        # 元音源：en0 组内最长 = xian（0.5s > yan 0.4s）
        assert qian["vowel_source"] == "1:5"
        assert not qian["consonant_fuzzy"] and not qian["vowel_fuzzy"]

    def test_unenumerated_skipped(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        report = combine_phonemes(proj, dry_run=True)
        skipped = {s["label"]: s["reason"] for s in report["skipped"]}
        for label in ("yo", "lo", "den", "nou", "rua", "cei", "lve", "nve", "chua"):
            assert skipped[label] == "presamp 未枚举"

    def test_no_source_skipped(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        report = combine_phonemes(proj, dry_run=True)
        skipped = {s["label"]: s["reason"] for s in report["skipped"]}
        assert skipped["zha"] == "无辅音源（zh）"

    def test_fuzzy_fallback(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        report = combine_phonemes(proj, dry_run=True)
        sha = _plan(report, "sha")
        assert sha["consonant_source"] == "2:1"  # 模糊回退：sh→s → sa
        assert sha["consonant_fuzzy"] is True

    def test_config_override_and_skip(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        cfg = tmp_path / "cfg.json"
        cfg.write_text(
            json.dumps(
                {"sources": {"qian": {"consonant": "1:1", "vowel": "1:4"}}, "skip": ["qia"]}
            ),
            encoding="utf-8",
        )
        report = combine_phonemes(proj, config_path=cfg, dry_run=True)
        qian = _plan(report, "qian")
        assert qian["consonant_source"] == "1:1"
        assert qian["vowel_source"] == "1:4"
        skipped = {s["label"]: s["reason"] for s in report["skipped"]}
        assert skipped["qia"] == "config 跳过"

    def test_config_invalid_coordinate(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"sources": {"qian": {"consonant": "nope"}}}), encoding="utf-8")
        with pytest.raises(JRHError):
            combine_phonemes(proj, config_path=cfg, dry_run=True)

    def test_frozen_refused(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        proj.freeze()
        with pytest.raises(FrozenError, match="冻结"):
            combine_phonemes(proj, dry_run=True)

    def test_non_pinyin_pack_refused(self, tmp_path):
        from fixtures.builder import build_ja_demo_project

        proj = JRHProject.open(build_ja_demo_project(tmp_path))
        with pytest.raises(InvalidInputError, match="jrh.zh-pinyin"):
            combine_phonemes(proj, dry_run=True)

    def test_dry_run_writes_nothing(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        report = combine_phonemes(proj, dry_run=True)
        assert report["dry_run"] is True
        assert not (tmp_path / "cb.jrh" / "assets" / "Cqian.wav").exists()


class TestCombineRun:
    def test_full_run_creates_units_and_assets(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        report = combine_phonemes(proj)
        assert report["dry_run"] is False
        assert any(p["label"] == "qian" for p in report["combined"])
        qian = _plan(report, "qian")
        s, u = (int(x) for x in qian["unit"].split(":"))
        unit = proj.get_unit(s, u)
        assert unit.label == "qian"
        asset = proj.get_asset(proj.get_sentence(s).asset_id)
        assert asset.file == "assets/Cqian.wav"
        assert (proj.path / asset.file).exists()
        # timing 公式：consonant/|cutoff|/preutterance/overlap 与源一致
        ms = unit.timing.to_ms(SR)
        assert ms["consonant"] == 50.0
        assert ms["preutterance"] == 50.0
        assert ms["overlap"] == 25.0
        assert ms["cutoff"] < -300  # 拼接总长 > 300ms
        assert ms["offset"] == 0.0
        assert (proj.path / "combine-report.json").exists()

    def test_second_run_idempotent(self, tmp_path):
        proj = JRHProject.open(_make_project(tmp_path))
        first = combine_phonemes(proj)
        second = combine_phonemes(proj)
        assert second["combined"] == []
        assert {p["label"] for p in first["combined"]}.isdisjoint(
            {p["label"] for p in second["combined"]}
        )

    def test_deterministic(self, tmp_path):
        r1 = combine_phonemes(JRHProject.open(_make_project(tmp_path / "a")))
        r2 = combine_phonemes(JRHProject.open(_make_project(tmp_path / "b")))
        assert r1 == r2
