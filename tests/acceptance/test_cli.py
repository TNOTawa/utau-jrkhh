"""CLI 验收测试：真实子进程运行，校验 stdout/JSON 与退出码。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

ENV = dict(os.environ)
ENV["PYTHONIOENCODING"] = "utf-8"
ENV["PYTHONUTF8"] = "1"


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "jrh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ENV,
        cwd=cwd or ROOT,
    )


def json_out(res: subprocess.CompletedProcess) -> dict:
    return json.loads(res.stdout)


@pytest.fixture()
def proj(tmp_path: Path) -> Path:
    p = tmp_path / "vb.jrh"
    res = run_cli("init", str(p))
    assert res.returncode == 0, res.stderr
    return p


@pytest.fixture()
def full_proj(tmp_path: Path) -> Path:
    """含音频的完整项目（等价 demo）。"""
    from fixtures.builder import build_demo_project

    return build_demo_project(tmp_path)


class TestInitAndInfo:
    def test_init_creates_manifest(self, proj):
        assert (proj / "manifest.json").exists()
        res = run_cli("info", str(proj))
        assert res.returncode == 0
        assert "jrh.zh-pinyin" in res.stdout

    def test_init_json(self, proj):
        res = run_cli("--format", "json", "info", str(proj))
        data = json_out(res)
        assert data["state"] == "draft"
        assert data["counts"] == {"assets": 0, "sentences": 0, "units": 0}

    def test_init_unknown_pack(self, tmp_path):
        res = run_cli("init", str(tmp_path / "x.jrh"), "--language-pack", "nope")
        assert res.returncode == 1
        assert "未知语言包" in res.stderr

    def test_open_missing(self, tmp_path):
        res = run_cli("info", str(tmp_path / "nope"))
        assert res.returncode == 1


class TestAssetCLI:
    def test_asset_add_list_info(self, proj, tmp_path):
        from fixtures.wavs import write_sine_wav

        wav = write_sine_wav(tmp_path / "src.wav", 44100, 1.0)
        r = run_cli("asset-add", str(proj), str(wav))
        assert r.returncode == 0, r.stderr
        assert "asset-001" in r.stdout
        r = run_cli("asset-list", str(proj))
        assert "asset-001" in r.stdout
        r = run_cli("asset-info", str(proj), "asset-001")
        r = run_cli("--format", "json", "asset-info", str(proj), "asset-001")
        assert json_out(r)["sample_rate"] == 44100

    def test_asset_add_missing_file(self, proj, tmp_path):
        r = run_cli("asset-add", str(proj), str(tmp_path / "nope.wav"))
        assert r.returncode == 1

    def test_asset_remove_referenced(self, full_proj):
        r = run_cli("asset-remove", str(full_proj), "asset-001")
        assert r.returncode == 1
        assert "引用" in r.stderr


class TestSentenceUnitCLI:
    def test_full_flow(self, proj):
        from fixtures.wavs import write_sine_wav

        # 需要 asset
        wav = write_sine_wav(Path(os.environ.get("TEMP", ".")) / "cli_src.wav", 44100, 1.0)
        run_cli("asset-add", str(proj), str(wav))
        r = run_cli("sentence-create", str(proj), "asset-001", "--start", "0", "--end", "10000")
        assert r.returncode == 0, r.stderr
        assert "'sentence_id': 1" in r.stdout
        r = run_cli(
            "unit-create",
            str(proj),
            "1",
            "--label",
            "hao",
            "--offset",
            "0",
            "--consonant",
            "100",
            "--cutoff",
            "-500",
            "--preutterance",
            "0",
            "--overlap",
            "0",
        )
        assert r.returncode == 0, r.stderr
        r = run_cli("unit-list", str(proj))
        assert "1:1" in r.stdout
        r = run_cli("unit-update", str(proj), "1:1", "--disabled")
        assert r.returncode == 0
        r = run_cli("--format", "json", "unit-list", str(proj))
        assert json_out(r)["units"][0]["enabled"] is False

    def test_unit_create_bad_cutoff(self, proj, tmp_path):
        from fixtures.wavs import write_sine_wav

        wav = write_sine_wav(tmp_path / "s.wav", 44100, 1.0)
        run_cli("asset-add", str(proj), str(wav))
        run_cli("sentence-create", str(proj), "asset-001", "--start", "0", "--end", "10000")
        r = run_cli("unit-create", str(proj), "1", "--label", "hao", "--cutoff", "500")
        assert r.returncode == 1
        assert "cutoff" in r.stderr

    def test_bad_coordinate_usage(self, proj):
        r = run_cli("unit-delete", str(proj), "abc")
        assert r.returncode == 1
        assert "坐标" in r.stderr


class TestGroupAnalyzeValidate:
    def test_group_manual_show(self, full_proj):
        r = run_cli("group", str(full_proj), "hao", "--manual", "3:1,1:2,2:2")
        assert r.returncode == 0
        r = run_cli("group", str(full_proj), "hao", "--show")
        assert "3:1, 1:2, 2:2" in r.stdout
        r = run_cli("group", str(full_proj), "hao", "--auto")
        assert r.returncode == 0

    def test_analyze(self, full_proj):
        r = run_cli("analyze", str(full_proj), "--no-rms")
        assert r.returncode == 0
        assert "8" in r.stdout
        r = run_cli("--format", "json", "analyze", str(full_proj))
        data = json_out(r)
        assert data["analyzed"] == 8
        assert data["rms_computed"] == 8

    def test_validate_ok_and_bad(self, full_proj, tmp_path):
        r = run_cli("validate", str(full_proj))
        assert r.returncode == 0
        # 破坏后
        units_file = full_proj / "data" / "units.json"
        data = json.loads(units_file.read_text(encoding="utf-8"))
        data["units"][0]["timing"]["preutterance"] = 10**9
        units_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        r = run_cli("validate", str(full_proj))
        assert r.returncode == 3
        assert "unit.timing" in r.stdout

    def test_integrity_detects_hash_change(self, full_proj):
        (full_proj / "assets" / "src1.wav").write_bytes(b"corrupted")
        r = run_cli("integrity", str(full_proj))
        assert r.returncode == 3
        assert "哈希不符" in r.stdout


class TestCompileCLI:
    def test_compile_and_reports(self, full_proj):
        r = run_cli("compile", str(full_proj))
        assert r.returncode == 0, r.stderr
        out = full_proj / "builds" / "openutau-jrh"
        assert (out / "oto.ini").exists()
        report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
        assert report["summary"]["conflicts"] == 0
        assert report["summary"]["full"] == 8

    def test_compile_dry_run_writes_nothing(self, full_proj):
        r = run_cli("compile", str(full_proj), "--dry-run")
        assert r.returncode == 0
        assert not (full_proj / "builds").exists()

    def test_compile_clean_rebuild(self, full_proj):
        run_cli("compile", str(full_proj))
        out = full_proj / "builds" / "openutau-jrh"
        before = (out / "oto.ini").read_bytes()
        r = run_cli("compile", str(full_proj), "--clean")
        assert r.returncode == 0
        assert (out / "oto.ini").read_bytes() == before

    def test_compile_conflict_exit_3(self, full_proj):
        # 制造 CV 别名冲突：hao 组第二名 "hao1" 与 label "hao1" 冲突
        run_cli("unit-update", str(full_proj), "1:1", "--label", "hao1")
        r = run_cli("compile", str(full_proj), "--dry-run")
        assert r.returncode == 3
        assert "别名冲突" in r.stderr

    def test_compile_invalid_project_exit_3(self, full_proj):
        run_cli("unit-update", str(full_proj), "1:1", "--label", "bad label")
        r = run_cli("compile", str(full_proj), "--dry-run")
        assert r.returncode == 3

    def test_compile_cvvc_flag(self, tmp_path):
        from fixtures.builder import build_ja_demo_project

        ja = build_ja_demo_project(tmp_path)
        r = run_cli("compile", str(ja), "--cvvc")
        assert r.returncode == 0, r.stderr
        out = ja / "builds" / "openutau-jrh"
        oto = (out / "oto.ini").read_text(encoding="utf-8")
        assert "=a t," in oto
        assert "=a t1," in oto
        assert "=o n," in oto
        report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
        assert report["summary"]["vc"] == 6
        assert report["config"]["cvvc"] is True
        assert "VC 6" in r.stdout

    def test_compile_cvvc_dry_run_json(self, tmp_path):
        from fixtures.builder import build_ja_demo_project

        ja = build_ja_demo_project(tmp_path)
        r = run_cli("--format", "json", "compile", str(ja), "--cvvc", "--dry-run")
        assert r.returncode == 0, r.stderr
        data = json_out(r)
        assert data["summary"]["vc"] == 6
        vcs = [e for e in data["entries"] if e["kind"] == "vc"]
        assert [e["alias"] for e in vcs] == ["a t", "o n", "i ch", "i h", "a k", "a t1"]
        assert all(e["wav"] == f"sentence_{e['sentence_id']:03d}.wav" for e in vcs)

    def test_compile_default_no_vc(self, tmp_path):
        from fixtures.builder import build_ja_demo_project

        ja = build_ja_demo_project(tmp_path)
        r = run_cli("compile", str(ja))
        assert r.returncode == 0, r.stderr
        out = ja / "builds" / "openutau-jrh"
        oto = (out / "oto.ini").read_text(encoding="utf-8")
        assert "=a t," not in oto
        report = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
        assert "vc" not in report["summary"]


class TestImportExportCLI:
    def _bank(self, tmp_path):
        from fixtures.henki_bank import build_henki_bank

        return build_henki_bank(tmp_path)

    def test_import_henki_and_export_vc(self, tmp_path):
        dirs = self._bank(tmp_path)
        proj = tmp_path / "p.jrh"
        r = run_cli(
            "import-henki",
            str(dirs["bank_dir"]),
            "--out",
            str(proj),
            "--oto",
            str(dirs["oto_dir"] / "oto.ini"),
        )
        assert r.returncode == 0, r.stderr
        assert (proj / "manifest.json").exists()
        assert "6 单元" in r.stdout
        cvvc = tmp_path / "cvvc"
        r = run_cli("export-vc", str(proj), "--out", str(cvvc))
        assert r.returncode == 0, r.stderr
        orig = (dirs["oto_dir"] / "oto.ini").read_bytes()
        data = (cvvc / "oto.ini").read_bytes()
        assert data[: len(orig)] == orig
        assert "=a t," in data[len(orig) :].decode("ascii")

    def test_import_henki_dry_run_json(self, tmp_path):
        dirs = self._bank(tmp_path)
        r = run_cli(
            "--format",
            "json",
            "import-henki",
            str(dirs["bank_dir"]),
            "--out",
            str(tmp_path / "p.jrh"),
            "--dry-run",
        )
        assert r.returncode == 0, r.stderr
        data = json_out(r)
        assert data["dry_run"] is True
        assert data["units_total"] == 6
        assert not (tmp_path / "p.jrh").exists()

    def test_import_henki_unsupported_language_rejected(self, tmp_path):
        dirs = self._bank(tmp_path)
        (dirs["bank_dir"] / "meta.json").write_text('{"language": "korean"}\n', encoding="utf-8")
        r = run_cli("import-henki", str(dirs["bank_dir"]), "--out", str(tmp_path / "p.jrh"))
        assert r.returncode == 1
        assert "不支持的语言" in r.stderr

    def test_import_henki_chinese(self, tmp_path):
        from fixtures.henki_bank_zh import build_henki_bank_zh

        dirs = build_henki_bank_zh(tmp_path)
        proj = tmp_path / "p.jrh"
        r = run_cli(
            "import-henki",
            str(dirs["bank_dir"]),
            "--out",
            str(proj),
            "--oto",
            str(dirs["oto_dir"] / "oto.ini"),
        )
        assert r.returncode == 0, r.stderr
        assert "8 单元" in r.stdout
        r = run_cli("--format", "json", "info", str(proj))
        data = json_out(r)
        assert data["language_pack"] == "jrh.zh-pinyin"

    def test_export_vc_requires_henki_project(self, tmp_path):
        from fixtures.builder import build_demo_project

        proj = build_demo_project(tmp_path)
        r = run_cli("export-vc", str(proj), "--out", str(tmp_path / "cvvc"))
        assert r.returncode == 1


class TestCombineCLI:
    def _project(self, tmp_path):
        from tests.unit.test_combine import _make_project  # noqa: PLC0415

        return _make_project(tmp_path)

    def test_combine_dry_run(self, tmp_path):
        proj = self._project(tmp_path)
        r = run_cli("--format", "json", "combine", str(proj), "--dry-run")
        assert r.returncode == 0, r.stderr
        data = json_out(r)
        assert data["dry_run"] is True
        assert data["missing_total"] == 410 - 6

    def test_combine_full_run(self, tmp_path):
        proj = self._project(tmp_path)
        r = run_cli("combine", str(proj))
        assert r.returncode == 0, r.stderr
        assert "合成" in r.stdout
        assert (proj / "combine-report.json").exists()


class TestSelectPhonemizeCLI:
    def test_select_json(self, full_proj):
        r = run_cli("--format", "json", "select", str(full_proj), "ni", "hao", "a")
        assert r.returncode == 0
        data = json_out(r)
        levels = [t["level"] for t in data["targets"]]
        assert levels == ["full", "continuous", "continuous"]
        assert data["missing_count"] == 0

    def test_phonemize_output(self, full_proj):
        r = run_cli("--format", "json", "phonemize", str(full_proj), "ni", "hao", "a")
        data = json_out(r)
        t1 = data["targets"][0]
        assert t1["phonemes"][0]["phoneme"] == "1-1-R-ni-hao"
        assert t1["phonemes"][0]["position_ms"] == 0.0

    def test_phonemize_strict_missing(self, full_proj):
        r = run_cli("phonemize", str(full_proj), "zzz", "--strict")
        assert r.returncode == 4
        r = run_cli("phonemize", str(full_proj), "zzz")
        assert r.returncode == 0  # 非 strict 正常退出

    def test_phonemize_after_freeze(self, full_proj):
        run_cli("freeze", str(full_proj))
        r = run_cli("--format", "json", "phonemize", str(full_proj), "ni", "hao")
        assert r.returncode == 0
        assert json_out(r)["targets"][1]["unit"] == "1:2"


class TestFreezeCLI:
    def test_freeze_one_way(self, full_proj):
        r = run_cli("freeze", str(full_proj))
        assert r.returncode == 0
        r = run_cli("freeze", str(full_proj))
        assert r.returncode == 1
        assert "冻结" in r.stderr

    def test_frozen_renumber_rejected(self, full_proj):
        run_cli("freeze", str(full_proj))
        r = run_cli("unit-renumber", str(full_proj))
        assert r.returncode == 1
        assert "冻结" in r.stderr


class TestUsageErrors:
    def test_unknown_command(self):
        r = run_cli("frobnicate")
        assert r.returncode == 2

    def test_missing_required_arg(self, tmp_path):
        r = run_cli("unit-create", str(tmp_path / "x"))
        assert r.returncode == 2

    def test_language_pack_list(self):
        r = run_cli("language-pack")
        assert r.returncode == 0
        assert "jrh.zh-pinyin" in r.stdout
