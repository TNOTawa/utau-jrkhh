"""人力V助手 bank → JRH 母版导入端到端测试（合成夹具）。"""

from __future__ import annotations

import pytest
from fixtures.henki_bank import build_henki_bank

from jrh.core.errors import InvalidInputError
from jrh.core.project import JRHProject
from jrh.importers.henki import import_henki_bank

SR = 44100


@pytest.fixture()
def henki_dirs(tmp_path):
    return build_henki_bank(tmp_path)


class TestHenkiImport:
    def test_sentences_and_units(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        report = import_henki_bank(
            henki_dirs["bank_dir"], out, oto_ini=henki_dirs["oto_dir"] / "oto.ini"
        )
        proj = JRHProject.open(out)
        assert report["segments"] == 2
        assert report["units_total"] == 6
        assert [u.label for u in proj.units_in_sentence(1)] == ["ka", "ta", "n"]
        assert [u.label for u in proj.units_in_sentence(2)] == ["su", "xtsu", "ka"]
        assert proj.manifest["language_pack"] == "jrh.ja-romaji"
        assert proj.manifest["import_source"]["kind"] == "henki"

    def test_original_params_preserved(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        import_henki_bank(henki_dirs["bank_dir"], out, oto_ini=henki_dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        # ka@1:1 ← 原版 song-001_0000.wav=ka,0,100,-300,100,30（ms 原样）
        ms = proj.get_unit(1, 1).timing.to_ms(SR)
        assert ms == {
            "offset": 0.0,
            "consonant": 100.0,
            "cutoff": -300.0,
            "preutterance": 100.0,
            "overlap": 30.0,
        }
        # ka@2:3 ← song-002_0000.wav=ka,280,120,-120,120,36
        ms = proj.get_unit(2, 3).timing.to_ms(SR)
        assert ms["offset"] == 280.0 and ms["cutoff"] == -120.0
        assert ms["preutterance"] == 120.0 and ms["overlap"] == 36.0

    def test_estimated_params_for_unmatched_mora(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        import_henki_bank(henki_dirs["bank_dir"], out, oto_ini=henki_dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        # xtsu@2:2：促音持阻段 [0.28,0.36)，无原版条目 → 估计（consonant=全长，overlap=0.3×）
        ms = proj.get_unit(2, 2).timing.to_ms(SR)
        assert ms == {
            "offset": 280.0,
            "consonant": 80.0,
            "cutoff": -80.0,
            "preutterance": 80.0,
            "overlap": 24.0,
        }

    def test_priority_manual_order_preserved(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        import_henki_bank(henki_dirs["bank_dir"], out, oto_ini=henki_dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        # 原版文件里 ka 组顺序 = [song-002（→2:3）, song-001（→1:1）]，倒置以验证保留
        assert proj.candidate_groups.mode("ka") == "manual"
        assert proj.candidate_groups.ordered_unit_ids("ka") == ["2:3", "1:1"]
        assert proj.candidate_groups.ordered_unit_ids("su") == ["2:1"]

    def test_report_matching(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        report = import_henki_bank(
            henki_dirs["bank_dir"], out, oto_ini=henki_dirs["oto_dir"] / "oto.ini"
        )
        assert report["matched_entries"] == 5
        reasons = {u["alias"]: u["reason"] for u in report["unmatched_entries"]}
        assert reasons == {"き": "非切片 wav（拼字产物等）"}
        assert (out / "import-report.json").exists()

    def test_dry_run_writes_nothing(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        report = import_henki_bank(
            henki_dirs["bank_dir"], out, oto_ini=henki_dirs["oto_dir"] / "oto.ini", dry_run=True
        )
        assert report["dry_run"] is True and report["output"] is None
        assert report["units_total"] == 6
        assert not out.exists()

    def test_unsupported_language_rejected(self, henki_dirs, tmp_path):
        (henki_dirs["bank_dir"] / "meta.json").write_text(
            '{"language": "korean"}\n', encoding="utf-8"
        )
        with pytest.raises(InvalidInputError, match="不支持的语言"):
            import_henki_bank(henki_dirs["bank_dir"], tmp_path / "p.jrh")

    def test_chinese_language_accepted(self, henki_dirs, tmp_path):
        # 中文 bank 用同一夹具结构验证语言分发（音素表为日语时中文音素会告警，
        # 但分发与项目创建路径一致——完整中文夹具见 test_henki_import_zh.py）
        (henki_dirs["bank_dir"] / "meta.json").write_text(
            '{"language": "chinese"}\n', encoding="utf-8"
        )
        report = import_henki_bank(henki_dirs["bank_dir"], tmp_path / "p.jrh", dry_run=True)
        assert report["language"] == "chinese"

    def test_output_dir_must_be_empty(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        out.mkdir()
        (out / "x.txt").write_text("x", encoding="utf-8")
        with pytest.raises(InvalidInputError, match="非空"):
            import_henki_bank(henki_dirs["bank_dir"], out)

    def test_without_oto_ini_still_imports(self, henki_dirs, tmp_path):
        out = tmp_path / "p.jrh"
        report = import_henki_bank(henki_dirs["bank_dir"], out)
        proj = JRHProject.open(out)
        assert report["entries_total"] == 0
        assert report["units_total"] == 6
        assert proj.candidate_groups.mode("ka") == "auto"
        # 无原版参数 → 全部区间估计
        ms = proj.get_unit(1, 1).timing.to_ms(SR)
        assert ms["consonant"] == 100.0  # k 段 [0,0.1)
        assert ms["cutoff"] == -300.0
