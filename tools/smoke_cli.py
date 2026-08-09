"""CLI 冒烟测试：逐一调用全部子命令，验证退出码与基本输出。"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(AttributeError, ValueError):
            reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [PYTHON, "-m", "jrh", *args],
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        env=env,
        cwd=str(cwd),
    )


def main() -> int:
    failures: list[str] = []
    td = Path(tempfile.mkdtemp(prefix="jrh_smoke_"))
    try:
        _smoke(td, failures)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    if failures:
        print("CLI smoke 失败：")
        for f in failures:
            print("  -", f)
        return 1
    print("CLI smoke 全部通过")
    return 0


def _smoke(td: Path, failures: list[str]) -> None:
    proj = td / "vb.jrh"

    def check(
        name: str, proc: subprocess.CompletedProcess, expect_rc: int = 0, must_contain: str = ""
    ) -> None:
        if proc.returncode != expect_rc:
            failures.append(
                f"{name}: 退出码 {proc.returncode} ≠ {expect_rc}（{proc.stderr.strip()[-200:]}）"
            )
        elif must_contain and must_contain not in proc.stdout:
            failures.append(f"{name}: 输出缺少 {must_contain!r}")

    r = run("init", str(proj))
    check("init", r)
    r = run("info", str(proj))
    check("info", r, must_contain="draft")
    r = run("language-pack")
    check("language-pack", r, must_contain="jrh.zh-pinyin")

    # 生成素材
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    from fixtures.wavs import write_sine_wav  # type: ignore[import-not-found]

    wav = write_sine_wav(td / "src.wav", 44100, 1.0)

    r = run("asset-add", str(proj), str(wav))
    check("asset-add", r)
    r = run("asset-list", str(proj))
    check("asset-list", r)
    r = run("asset-info", str(proj), "asset-001")
    check("asset-info", r)

    r = run("sentence-create", str(proj), "asset-001", "--start", "0", "--end", "44100")
    check("sentence-create", r)
    for label, off, cons, cut, pre, ovl in [
        ("ni", 0, 4410, -22050, 4410, 4410),
        ("hao", 22050, 4410, -22050, 4410, 4410),
    ]:
        r = run(
            "unit-create",
            str(proj),
            "1",
            "--label",
            label,
            "--offset",
            str(off),
            "--consonant",
            str(cons),
            "--cutoff",
            str(cut),
            "--preutterance",
            str(pre),
            "--overlap",
            str(ovl),
        )
        check(f"unit-create {label}", r)
    r = run("unit-list", str(proj))
    check("unit-list", r)
    r = run("unit-update", str(proj), "1:2", "--label", "gao")
    check("unit-update", r)
    r = run("group", str(proj), "ni", "--show")
    check("group-show", r)
    r = run("group", str(proj), "ni", "--manual", "1:1")
    check("group-manual", r)
    r = run("group", str(proj), "ni", "--auto")
    check("group-auto", r)

    r = run("analyze", str(proj), "--no-rms")
    check("analyze", r)

    r = run("validate", str(proj))
    check("validate", r)
    r = run("integrity", str(proj))
    check("integrity", r)

    r = run("compile", str(proj), "--dry-run")
    check("compile-dry-run", r)
    r = run("compile", str(proj))
    check("compile", r)
    r = run("compile", str(proj), "--clean")
    check("compile-clean", r)

    r = run("--format", "json", "select", str(proj), "ni", "gao")
    check("select", r)
    if r.returncode == 0:
        data = json.loads(r.stdout)
        if data["missing_count"] != 0:
            failures.append("select: 意外缺音")

    r = run("--format", "json", "phonemize", str(proj), "ni", "gao")
    check("phonemize", r)
    r = run("phonemize", str(proj), "zzz", "--strict")
    check("phonemize-strict", r, expect_rc=4)

    r = run("freeze", str(proj))
    check("freeze", r)
    r = run("freeze", str(proj))
    check("freeze-twice", r, expect_rc=1)

    r = run("sentence-split", str(proj), "1", "--at", "22050")
    check("sentence-split", r)
    r = run("sentence-merge", str(proj), "1", "2")
    check("sentence-merge", r)
    r = run("sentence-list", str(proj))
    check("sentence-list", r)
    r = run("sentence-update", str(proj), "1", "--end", "44100")
    check("sentence-update", r)
    r = run("unit-delete", str(proj), "1:1")
    check("unit-delete", r)
    r = run("sentence-delete", str(proj), "1", "--cascade")
    check("sentence-delete", r)

    r = run("unit-renumber", str(proj))
    check("unit-renumber", r, expect_rc=1)  # 冻结后禁止

    # 错误路径
    r = run("frobnicate")
    check("unknown-command", r, expect_rc=2)
    r = run("info", str(td / "missing.jrh"))
    check("missing-project", r, expect_rc=1)


if __name__ == "__main__":
    sys.exit(main())
