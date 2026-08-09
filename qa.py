"""QA 质量门：单一入口，本地与 CI 使用同一命令。

用法：python qa.py [--quick] [--skip-mutation] [--skip-coverage]

步骤（任一失败即非零退出）：
1. 构建/语法（compileall）
2. 格式（ruff format --check）
3. lint（ruff check）
4. typecheck（mypy）
5. 全量测试（pytest：unit/integration/acceptance/golden/negative/property/regression）
6. 覆盖率门禁（jrh.core 行 ≥90%、关键模块 branch ≥80%）
7. 变异测试（tools/mutate.py，门禁 90%）
8. 依赖检查（pip check；pip-audit 可用时执行）
9. 构建（pip install -e .）
10. CLI smoke 测试（全部子命令）
11. 输出 qa-report.json

--quick：跳过变异与覆盖率（开发期加速）。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(AttributeError, ValueError):
            reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable

# 覆盖率门禁：jrh/core 与 jrh/formats 行覆盖率下限；关键模块 branch 下限
CORE_LINE_GATE = 90.0
CRITICAL_BRANCH_GATE = 80.0
CRITICAL_MODULES = (
    "jrh/core/model.py",
    "jrh/core/analysis.py",
    "jrh/core/selection.py",
    "jrh/core/compile_engine.py",
    "jrh/formats/oto_ini.py",
)

STEPS: list[dict] = []


def run_step(name: str, cmd: list[str], cwd: Path = ROOT, env=None) -> bool:
    print(f"\n=== {name} ===", flush=True)
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env or dict(os.environ),
    )
    ok = proc.returncode == 0
    dt = time.time() - t0
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    tail = (out + "\n" + err).strip().splitlines()[-12:]
    for line in tail:
        print("  " + line, flush=True)
    print(f"  → {'通过' if ok else '失败'} ({dt:.1f}s)", flush=True)
    STEPS.append({"name": name, "ok": ok, "seconds": round(dt, 1), "exit_code": proc.returncode})
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="JRH QA 质量门")
    ap.add_argument("--quick", action="store_true", help="跳过变异与覆盖率")
    ap.add_argument("--skip-mutation", action="store_true")
    ap.add_argument("--skip-coverage", action="store_true")
    args = ap.parse_args()

    ok = True

    # 1. 构建/语法
    ok &= run_step(
        "构建/语法 (compileall)",
        [PYTHON, "-m", "compileall", "-q", "jrh", "tools", "tests", "qa.py"],
    )

    # 2. 格式
    ok &= run_step(
        "格式 (ruff format --check)",
        [PYTHON, "-m", "ruff", "format", "--check", "jrh", "tools", "tests", "qa.py"],
    )

    # 3. lint
    ok &= run_step(
        "lint (ruff check)", [PYTHON, "-m", "ruff", "check", "jrh", "tools", "tests", "qa.py"]
    )

    # 4. typecheck
    ok &= run_step("typecheck (mypy)", [PYTHON, "-m", "mypy", "jrh", "tools", "qa.py"])

    # 5. 全量测试
    ok &= run_step(
        "全量测试 (pytest)", [PYTHON, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"]
    )

    # 6. 覆盖率门禁
    if not args.skip_coverage and not args.quick:
        ok &= run_step(
            "覆盖率 (pytest --cov)",
            [
                PYTHON,
                "-m",
                "pytest",
                "tests",
                "-q",
                "-p",
                "no:cacheprovider",
                "--cov=jrh",
                "--cov-report=json:coverage-report.json",
                "--cov-report=term-missing:skip-covered",
            ],
        )
        ok &= check_coverage()
    else:
        print("\n=== 覆盖率（跳过） ===")
        STEPS.append({"name": "覆盖率", "ok": True, "skipped": True})

    # 7. 变异测试
    if not args.skip_mutation and not args.quick:
        ok &= run_step(
            "变异测试 (tools/mutate.py)", [PYTHON, "tools/mutate.py", "--gate-kill-rate", "0.9"]
        )
    else:
        print("\n=== 变异测试（跳过） ===")
        STEPS.append({"name": "变异测试", "ok": True, "skipped": True})

    # 8. 依赖检查（pip check；仅当涉及本项目依赖时判失败，环境历史垃圾只记警告）
    pip_check_ok, pip_check_notes = run_pip_check()
    ok &= pip_check_ok
    pip_audit = shutil.which("pip-audit")
    if pip_audit:
        ok &= run_step("安全审计 (pip-audit)", [pip_audit, "--format=json"])

    # 9. 构建（可安装）
    ok &= run_step("构建 (pip install -e .)", [PYTHON, "-m", "pip", "install", "-e", "."])

    # 10. CLI smoke
    ok &= run_step("CLI smoke", [PYTHON, "tools/smoke_cli.py"])

    # 11. 架构纯净（core 不依赖第三方）—— 由 pytest 的 test_core_purity 覆盖

    report = {
        "passed": ok,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": STEPS,
    }
    (ROOT / "qa-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failed = [s["name"] for s in STEPS if not s.get("ok")]
    if failed:
        print(f"\nQA 失败步骤: {failed}")
    else:
        print("\nQA 全部通过")
    return 0 if ok else 1


def run_pip_check() -> tuple[bool, list[str]]:
    """pip check：只有涉及本项目（utau-jrkhh-core）或开发依赖的冲突才判失败。"""
    print("\n=== 依赖检查 (pip check) ===", flush=True)
    proc = subprocess.run(
        [PYTHON, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    notes: list[str] = []
    if proc.returncode == 0:
        print("  → 通过", flush=True)
        STEPS.append({"name": "依赖检查", "ok": True})
        return True, notes
    own_fail = False
    for line in (proc.stdout or "").splitlines():
        if line.strip():
            print("  " + line, flush=True)
        low = line.lower()
        if "utau-jrkhh-core" in low or any(
            d in low for d in ("pytest", "hypothesis", "ruff", "mypy", "mutmut", "coverage")
        ):
            own_fail = True
            notes.append(line)
    if not own_fail:
        print("  → 警告：环境存在无关的历史依赖冲突（不影响本项目），不计入门禁", flush=True)
    STEPS.append({"name": "依赖检查", "ok": not own_fail, "notes": notes})
    return not own_fail, notes


def check_coverage() -> bool:
    """解析 coverage-report.json 并执行门禁。"""
    path = ROOT / "coverage-report.json"
    if not path.exists():
        print("  coverage-report.json 缺失")
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files", {})
    core_bad: list[str] = []
    branch_bad: list[str] = []
    core_line_sum = 0
    core_line_num = 0
    for name, info in sorted(files.items()):
        norm = name.replace("\\", "/")
        if not (norm.startswith("jrh/core/") or norm.startswith("jrh/formats/")):
            continue
        line_rate = info["summary"]["percent_covered"]
        core_line_sum += info["summary"]["covered_lines"]
        core_line_num += info["summary"]["num_statements"]
        if line_rate < CORE_LINE_GATE:
            core_bad.append(f"{norm}: {line_rate:.1f}%")
        if norm in CRITICAL_MODULES:
            num_branches = info["summary"].get("num_branches", 0)
            if num_branches:
                br_rate = info["summary"]["covered_branches"] / num_branches * 100
                if br_rate < CRITICAL_BRANCH_GATE:
                    branch_bad.append(f"{name}: branch {br_rate:.1f}%")
    overall = core_line_sum / core_line_num * 100 if core_line_num else 0.0
    print(f"  jrh.core/formats 行覆盖率: {overall:.1f}% (门禁 {CORE_LINE_GATE:.0f}%)")
    for bad in core_bad:
        print(f"    [行覆盖率不足] {bad}")
    for bad in branch_bad:
        print(f"    [branch 覆盖率不足] {bad}")
    ok = overall >= CORE_LINE_GATE and not core_bad and not branch_bad
    STEPS.append(
        {
            "name": "覆盖率门禁",
            "ok": ok,
            "core_line_percent": round(overall, 1),
            "core_line_gate": CORE_LINE_GATE,
            "branch_gate": CRITICAL_BRANCH_GATE,
        }
    )
    return ok


if __name__ == "__main__":
    sys.exit(main())
