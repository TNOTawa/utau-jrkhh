"""VC 补充导出单元测试：无差别保证（原版逐字节 + VC 纯增量）。"""

from __future__ import annotations

import pytest
from fixtures.henki_bank import build_henki_bank

from jrh.core.errors import InvalidInputError
from jrh.core.project import JRHProject
from jrh.exporters.vc_supplement import export_vc_supplement
from jrh.importers.henki import import_henki_bank


@pytest.fixture()
def imported(tmp_path):
    dirs = build_henki_bank(tmp_path)
    out = tmp_path / "p.jrh"
    import_henki_bank(dirs["bank_dir"], out, oto_ini=dirs["oto_dir"] / "oto.ini")
    return dirs, JRHProject.open(out)


class TestVcSupplement:
    def test_original_lines_byte_identical(self, imported, tmp_path):
        dirs, proj = imported
        out = tmp_path / "cvvc"
        report = export_vc_supplement(proj, out)
        orig = (dirs["oto_dir"] / "oto.ini").read_bytes()
        data = (out / "oto.ini").read_bytes()
        assert data[: len(orig)] == orig  # 非 VC 部分逐字节原样（含注释行）
        tail = data[len(orig) :].decode("ascii")
        assert "=a t," in tail
        assert "=a n," in tail
        assert "=u k," in tail  # 促音借位：su→xtsu→ka 归一为 u k
        assert report["vc_entries"] == 3
        assert report["original_entries"] == 6

    def test_wavs_copied(self, imported, tmp_path):
        dirs, proj = imported
        out = tmp_path / "cvvc"
        export_vc_supplement(proj, out)
        assert (out / "song-001_0000.wav").exists()  # 原版 wav 原样拷贝
        assert (out / "Cき.wav").exists()
        assert (
            out / "segment_001.wav"
        ).exists()  # 多切片句：句 wav = 合并资产（整资产句定向已有文件）
        assert (
            out / "song-002_0000.wav"
        ).exists()  # 单切片句：句 wav = 切片原文件（与原版同源，零重复）

    def test_rejects_project_without_import_source(self, tmp_path):
        from fixtures.builder import build_demo_project

        proj_path = build_demo_project(tmp_path)
        proj = JRHProject.open(proj_path)
        with pytest.raises(InvalidInputError, match="henki"):
            export_vc_supplement(proj, tmp_path / "cvvc")

    def test_report_deterministic(self, imported, tmp_path):
        _dirs, proj = imported
        r1 = export_vc_supplement(proj, tmp_path / "c1")
        r2 = export_vc_supplement(proj, tmp_path / "c2")
        assert {k: v for k, v in r1.items() if k != "output"} == {
            k: v for k, v in r2.items() if k != "output"
        }
        assert r1["vc_aliases"] == ["a n", "a t", "u k"]


class TestVcSupplementZh:
    """中文导出：presamp.ini 交付 + 派生 CV 追加 + 基线逐字节。"""

    @pytest.fixture()
    def zh_imported(self, tmp_path):
        from fixtures.henki_bank_zh import OTO_TEXT_STRIPPED, build_henki_bank_zh

        dirs = build_henki_bank_zh(tmp_path, oto_text=OTO_TEXT_STRIPPED)
        out = tmp_path / "p.jrh"
        import_henki_bank(dirs["bank_dir"], out, oto_ini=dirs["oto_dir"] / "oto.ini")
        return dirs, JRHProject.open(out)

    def test_presamp_ini_written_byte_exact(self, zh_imported, tmp_path):
        _dirs, proj = zh_imported
        out = tmp_path / "cvvc"
        report = export_vc_supplement(proj, out)
        from jrh.languages.presamp import PRESAMP_INI_TEXT

        assert report["presamp_ini"] is True
        assert (out / "presamp.ini").read_bytes() == PRESAMP_INI_TEXT.encode("ascii")

    def test_derived_cv_appended_for_missing_base(self, zh_imported, tmp_path):
        dirs, proj = zh_imported
        out = tmp_path / "cvvc"
        report = export_vc_supplement(proj, out)
        orig = (dirs["oto_dir"] / "oto.ini").read_bytes()
        data = (out / "oto.ini").read_bytes()
        assert data[: len(orig)] == orig  # 基线逐字节保真
        tail = data[len(orig) :].decode("ascii")
        # yi 在剥离版中被剔除 → 派生 CV 追加（wav = 资产原名，定向已有文件）
        assert "qfcy_0004.wav=yi," in tail
        assert "=e n," in tail and "=ou sh," in tail  # VC 短 ID 别名（ke→neng、jiu→shi）
        assert report["appended_cv_entries"] == 1
        assert report["appended_cv_aliases"] == ["yi"]
        # 已存在的 base（a/ke/neng/jiu/shi/kan）不追加派生行
        assert report["vc_entries"] == 2
        assert report["vc_aliases"] == ["e n", "ou sh"]

    def test_space_alias_rejected(self, tmp_path):
        from fixtures.henki_bank_zh import OTO_TEXT, build_henki_bank_zh

        dirs = build_henki_bank_zh(tmp_path, oto_text=OTO_TEXT)  # 含 VC 行 a sh
        out = tmp_path / "p.jrh"
        import_henki_bank(dirs["bank_dir"], out, oto_ini=dirs["oto_dir"] / "oto.ini")
        proj = JRHProject.open(out)
        from jrh.core.errors import DataError

        with pytest.raises(DataError, match="空格"):
            export_vc_supplement(proj, tmp_path / "cvvc")


class TestVcSupplementSubstitution:
    """substitutions：缺失 label → 复用已有来源别名追加（纯增量，默认关闭）。"""

    @pytest.fixture()
    def zh_imported(self, tmp_path):
        from fixtures.henki_bank_zh import OTO_TEXT_STRIPPED, build_henki_bank_zh

        dirs = build_henki_bank_zh(tmp_path, oto_text=OTO_TEXT_STRIPPED)
        out = tmp_path / "p.jrh"
        import_henki_bank(dirs["bank_dir"], out, oto_ini=dirs["oto_dir"] / "oto.ini")
        return dirs, JRHProject.open(out)

    def test_substitution_appends_reusing_source(self, zh_imported, tmp_path):
        dirs, proj = zh_imported
        out = tmp_path / "cvvc"
        report = export_vc_supplement(proj, out, substitutions={"zui": "kan"})
        orig = (dirs["oto_dir"] / "oto.ini").read_bytes()
        data = (out / "oto.ini").read_bytes()
        assert data[: len(orig)] == orig  # 基线逐字节保真
        tail = data[len(orig) :].decode("ascii")
        # kan = qfcy_0005.wav=kan,0,80,-450,80,24 → zui 复用其 wav+参数
        assert "qfcy_0005.wav=zui,0,80,-450,80,24" in tail
        assert report["substituted_entries"] == 1
        assert report["substituted_aliases"] == ["zui"]
        assert (out / "qfcy_0005.wav").exists()

    def test_substitution_target_conflict(self, zh_imported, tmp_path):
        from jrh.core.errors import DataError

        _dirs, proj = zh_imported
        with pytest.raises(DataError, match="已存在"):
            export_vc_supplement(proj, tmp_path / "c", substitutions={"kan": "kan"})

    def test_substitution_unknown_source(self, zh_imported, tmp_path):
        from jrh.core.errors import DataError

        _dirs, proj = zh_imported
        with pytest.raises(DataError, match="来源别名不存在"):
            export_vc_supplement(proj, tmp_path / "c", substitutions={"zui": "zyx"})

    def test_default_no_substitution_unchanged(self, zh_imported, tmp_path):
        _dirs, proj = zh_imported
        r1 = export_vc_supplement(proj, tmp_path / "c1")
        r2 = export_vc_supplement(proj, tmp_path / "c2", substitutions=None)
        assert r1["substituted_entries"] == 0
        assert r1["substituted_aliases"] == []
        assert {k: v for k, v in r1.items() if k != "output"} == {
            k: v for k, v in r2.items() if k != "output"
        }
