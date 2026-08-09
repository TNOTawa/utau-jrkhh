"""Clean-environment QA：在全新 venv 中安装并执行完整工作流。

场景（JRH_SPEC §10 要求）：
clean env → install → create JRH → import fixture → edit → analyze → sort →
compile → validate → simulate phonemizer → destroy derived build → rebuild →
compare output；重复执行结果一致。

用法：python tools/qa_clean_env.py [--keep-venv]
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(AttributeError, ValueError):
            reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, errors="replace", encoding="utf-8", env=e
    )


def dir_sha256(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode("utf-8"))
            h.update(p.read_bytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-venv", action="store_true")
    args = ap.parse_args()

    steps: list[dict] = []
    tmp = Path(tempfile.mkdtemp(prefix="jrh_clean_env_"))
    venv = tmp / ".venv"

    def step(name: str, fn) -> bool:
        t0 = time.time()
        try:
            ok = fn()
            print(f"[{'通过' if ok else '失败'}] {name} ({time.time() - t0:.1f}s)", flush=True)
            steps.append({"name": name, "ok": ok})
            return ok
        except Exception as e:  # noqa: BLE001
            print(f"[失败] {name}: {e}", flush=True)
            steps.append({"name": name, "ok": False, "error": str(e)})
            return False

    def ok(proc: subprocess.CompletedProcess, what: str = "") -> bool:
        if proc.returncode != 0:
            print(f"  stderr: {proc.stderr.strip()[-300:]}", flush=True)
            return False
        return True

    # 1. clean venv
    def s_create_venv():
        p = run([PYTHON, "-m", "venv", str(venv)], ROOT)
        return ok(p, "venv")

    # 2. install
    def s_install():
        py = venv / "Scripts" / "python.exe"
        p = run([str(py), "-m", "pip", "install", "--upgrade", "pip"], ROOT)
        if not ok(p):
            return False
        p = run([str(py), "-m", "pip", "install", "-e", "."], ROOT)
        if not ok(p):
            return False
        p = run(
            [
                str(py),
                "-m",
                "pip",
                "install",
                "numpy",
                "soundfile",
                "pytest",
                "pytest-cov",
                "hypothesis",
                "ruff",
                "mypy",
            ],
            ROOT,
        )
        return ok(p)

    py = venv / "Scripts" / "python.exe"
    jrh = [str(py), "-m", "jrh"]

    # 3. 完整工作流（在临时目录）
    work = tmp / "work"
    work.mkdir()
    proj = work / "vb.jrh"
    scenario: dict = {}

    def s_create():
        p = run(jrh + ["init", str(proj)], work)
        return ok(p)

    def s_import():
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "tests"))
        from fixtures.wavs import write_sine_wav  # type: ignore[import-not-found]

        write_sine_wav(work / "src.wav", 44100, 3.0)
        write_sine_wav(work / "src2.wav", 48000, 1.0, 9000, 550.0)
        p = run(jrh + ["asset-add", str(proj), str(work / "src.wav")], work)
        if not ok(p):
            return False
        p = run(jrh + ["asset-add", str(proj), str(work / "src2.wav")], work)
        return ok(p)

    def s_edit():
        steps_cfg = [
            ("sentence-create", [str(proj), "asset-001", "--start", "0", "--end", "88200"]),
            (
                "unit-create",
                [
                    str(proj),
                    "1",
                    "--label",
                    "ni",
                    "--offset",
                    "2205",
                    "--consonant",
                    "11025",
                    "--cutoff",
                    "-35280",
                    "--preutterance",
                    "4410",
                    "--overlap",
                    "4410",
                ],
            ),
            (
                "unit-create",
                [
                    str(proj),
                    "1",
                    "--label",
                    "hao",
                    "--offset",
                    "35280",
                    "--consonant",
                    "11025",
                    "--cutoff",
                    "-39690",
                    "--preutterance",
                    "4410",
                    "--overlap",
                    "4410",
                ],
            ),
            ("sentence-create", [str(proj), "asset-001", "--start", "88200", "--end", "132300"]),
            (
                "unit-create",
                [
                    str(proj),
                    "2",
                    "--label",
                    "wo",
                    "--offset",
                    "2205",
                    "--consonant",
                    "11025",
                    "--cutoff",
                    "-26460",
                    "--preutterance",
                    "4410",
                    "--overlap",
                    "4410",
                ],
            ),
            (
                "unit-create",
                [
                    str(proj),
                    "2",
                    "--label",
                    "hao",
                    "--offset",
                    "24255",
                    "--consonant",
                    "11025",
                    "--cutoff",
                    "-17640",
                    "--preutterance",
                    "4410",
                    "--overlap",
                    "4410",
                ],
            ),
        ]
        for name, args in steps_cfg:
            p = run(jrh + [name] + args, work)
            if not ok(p, name):
                return False
        p = run(
            jrh + ["sentence-create", str(proj), "asset-002", "--start", "0", "--end", "48000"],
            work,
        )
        if not ok(p):
            return False
        p = run(
            jrh
            + [
                "unit-create",
                str(proj),
                "3",
                "--label",
                "hao",
                "--offset",
                "2400",
                "--consonant",
                "9600",
                "--cutoff",
                "-28800",
                "--preutterance",
                "4800",
                "--overlap",
                "4800",
            ],
            work,
        )
        return ok(p)

    def s_analyze():
        p = run(jrh + ["analyze", str(proj)], work)
        return ok(p)

    def s_sort():
        p = run(jrh + ["group", str(proj), "hao", "--manual", "3:1,1:2,2:2"], work)
        return ok(p)

    def s_freeze():
        p = run(jrh + ["freeze", str(proj)], work)
        return ok(p)

    def s_validate():
        p = run(jrh + ["validate", str(proj)], work)
        return ok(p)

    def s_compile():
        p = run(jrh + ["compile", str(proj)], work)
        if not ok(p):
            return False
        build = proj / "builds" / "openutau-jrh"
        scenario["build_sha"] = dir_sha256(build)
        report = json.loads((build / "build-report.json").read_text(encoding="utf-8"))
        scenario["report"] = report
        return report["summary"]["conflicts"] == 0

    def s_phonemize():
        p = run(jrh + ["--format", "json", "phonemize", str(proj), "ni", "hao"], work)
        if not ok(p):
            return False
        data = json.loads(p.stdout)
        levels = [t["level"] for t in data["targets"]]
        return levels == ["full", "continuous"]

    def s_rebuild_identical():
        build = proj / "builds" / "openutau-jrh"
        shutil.rmtree(build)
        p = run(jrh + ["compile", str(proj)], work)
        if not ok(p):
            return False
        sha2 = dir_sha256(build)
        same = sha2 == scenario["build_sha"]
        if not same:
            print(f"  重建产物不一致: {scenario['build_sha']} vs {sha2}", flush=True)
        return same

    def s_repeat_compile():
        p = run(jrh + ["compile", str(proj), "--clean"], work)
        if not ok(p):
            return False
        sha3 = dir_sha256(proj / "builds" / "openutau-jrh")
        return sha3 == scenario["build_sha"]

    def s_corrupt_handling():
        """主动构造损坏输入，验证显式报错。"""
        units = proj / "data" / "units.json"
        data = json.loads(units.read_text(encoding="utf-8"))
        data["units"][0]["timing"]["preutterance"] = 10**9
        units.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        p = run(jrh + ["validate", str(proj)], work)
        if p.returncode != 3:
            print(f"  损坏数据未报错（退出码 {p.returncode}）", flush=True)
            return False
        p = run(jrh + ["compile", str(proj), "--dry-run"], work)
        return p.returncode == 3

    def s_pip_check():
        p = run([str(py), "-m", "pip", "check"], venv)
        return ok(p)

    def s_full_qa():
        p = run([str(py), "qa.py", "--quick"], ROOT)
        return ok(p)

    checks = [
        ("创建干净 venv", s_create_venv),
        ("安装项目与依赖", s_install),
        ("创建 JRH 项目", s_create),
        ("导入素材 fixture", s_import),
        ("编辑句子与单元", s_edit),
        ("时长/RMS 分析", s_analyze),
        ("人工候选排序", s_sort),
        ("冻结编号", s_freeze),
        ("验证", s_validate),
        ("编译（记录产物哈希）", s_compile),
        ("phonemizer 模拟", s_phonemize),
        ("销毁 build 后重建（逐字节一致）", s_rebuild_identical),
        ("重复编译一致", s_repeat_compile),
        ("损坏输入显式报错", s_corrupt_handling),
        ("干净环境 pip check", s_pip_check),
        ("干净环境完整 QA（--quick）", s_full_qa),
    ]
    for name, fn in checks:
        step(name, fn)

    report = {
        "passed": all(s.get("ok") for s in steps),
        "steps": steps,
        "repeat_sha": scenario.get("build_sha"),
    }
    (ROOT / "clean-env-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not args.keep_venv:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"clean-env QA 报告: clean-env-report.json（{'通过' if report['passed'] else '失败'}）")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
