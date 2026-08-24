"""中文 henki 导入端到端测试（合成中文夹具，DJUTAU 实测形态）。"""

from __future__ import annotations

import pytest
from fixtures.henki_bank_zh import build_henki_bank_zh

from jrh.core.project import JRHProject
from jrh.importers.henki import import_henki_bank

SR = 44100


@pytest.fixture()
def zh_dirs(tmp_path):
    return build_henki_bank_zh(tmp_path)


class TestHenkiImportZh:
    def test_per_slice_sentences(self, zh_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        report = import_henki_bank(zh_dirs["bank_dir"], out, oto_ini=zh_dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        assert report["language"] == "chinese"
        assert report["segments"] == 6  # 每切片独立成句
        assert report["units_total"] == 8
        assert proj.manifest["language_pack"] == "jrh.zh-pinyin"
        assert proj.manifest["import_source"]["language"] == "chinese"
        # 句 1：啊 → a；句 2：可能 → ke, neng；句 3：就是 → jiu, shi；句 4：啊 → a；
        # 句 5：以 → yi；句 6：看 → kan
        assert [u.label for u in proj.units_in_sentence(1)] == ["a"]
        assert [u.label for u in proj.units_in_sentence(2)] == ["ke", "neng"]
        assert [u.label for u in proj.units_in_sentence(3)] == ["jiu", "shi"]
        assert [u.label for u in proj.units_in_sentence(4)] == ["a"]
        assert [u.label for u in proj.units_in_sentence(5)] == ["yi"]
        assert [u.label for u in proj.units_in_sentence(6)] == ["kan"]

    def test_single_slice_assets_named_after_slice(self, zh_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        import_henki_bank(zh_dirs["bank_dir"], out, oto_ini=zh_dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        for sent in proj.sentences_sorted():
            asset = proj.get_asset(sent.asset_id)
            # 单切片组：资产 = 切片文件（定向已有文件的前提）
            assert asset.file.endswith(".wav")
            assert asset.file != f"segment_{sent.sentence_id:03d}.wav"
            assert (proj.path / asset.file).exists()
        # 切片名原样保留
        assert {a.file for a in proj.assets.values()} == {
            "assets/qfcy_0000.wav",
            "assets/qfcy_0001.wav",
            "assets/qfcy_0002.wav",
            "assets/qfcy_0003.wav",
            "assets/qfcy_0004.wav",
            "assets/qfcy_0005.wav",
        }

    def test_params_and_unmatched(self, zh_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        report = import_henki_bank(zh_dirs["bank_dir"], out, oto_ini=zh_dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        # jiu@3:1 ← qfcy_0002.wav=jiu,0,70,-250,70,21（参数原样）
        ms = proj.get_unit(3, 1).timing.to_ms(SR)
        assert ms == {
            "offset": 0.0,
            "consonant": 70.0,
            "cutoff": -250.0,
            "preutterance": 70.0,
            "overlap": 21.0,
        }
        reasons = {(u["alias"], u["reason"]) for u in report["unmatched_entries"]}
        assert ("qian", "非切片 wav（拼字产物等）") in reasons
        assert ("a sh", "别名无语言包单位") in reasons
        assert report["matched_entries"] == 8

    def test_zero_initial_estimated_timing(self, tmp_path):
        # 无原版条目的零声母（qfcy_0004 的 yi 在剥离版中缺失）→ 虚拟 min(30, dur×0.2)
        from fixtures.henki_bank_zh import OTO_TEXT_STRIPPED, build_henki_bank_zh

        dirs = build_henki_bank_zh(tmp_path / "stripped", oto_text=OTO_TEXT_STRIPPED)
        out = tmp_path / "p.jrh"
        import_henki_bank(dirs["bank_dir"], out, oto_ini=dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        ms = proj.get_unit(5, 1).timing.to_ms(SR)
        assert ms["consonant"] == pytest.approx(min(30, 250 * 0.2), abs=0.001)
        assert ms["cutoff"] == -250.0

    def test_dry_run(self, zh_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        report = import_henki_bank(zh_dirs["bank_dir"], out, dry_run=True)
        assert report["dry_run"] is True
        assert report["units_total"] == 8
        assert report["language"] == "chinese"
        assert not out.exists()
