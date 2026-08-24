"""轻量 AST 变异测试工具（JRH 核心公式模块）。

对指定模块逐个注入变异（运算符/比较/常量/条件反转），
用该模块的目标测试集在隔离副本中验证是否被杀死。

用法：python tools/mutate.py [--module jrh/core/model.py ...] [--gate-kill-rate 90]
"""

from __future__ import annotations

import ast
import contextlib
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeAlias

for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(AttributeError, ValueError):
            reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# 模块 → 目标测试文件（验证该模块行为的 oracle）
TARGETS: dict[str, list[str]] = {
    "jrh/core/model.py": [
        "tests/unit/test_timing.py",
        "tests/property/test_property.py",
        "tests/unit/test_project.py",
        "tests/unit/test_validate.py",
        "tests/unit/test_boundaries.py",
    ],
    "jrh/core/compile_engine.py": [
        "tests/golden/test_golden.py",
        "tests/unit/test_alias_identity.py",
        "tests/integration/test_lifecycle.py",
        "tests/integration/test_determinism.py",
        "tests/unit/test_validate.py",
        "tests/unit/test_boundaries.py",
        "tests/unit/test_vc_compile.py",
    ],
    "jrh/core/analysis.py": [
        "tests/unit/test_analysis.py",
        "tests/unit/test_selection.py",
        "tests/unit/test_validate.py",
        "tests/unit/test_boundaries.py",
    ],
    "jrh/core/selection.py": [
        "tests/unit/test_selection.py",
        "tests/integration/test_determinism.py",
        "tests/integration/test_lifecycle.py",
        "tests/unit/test_analysis.py",
        "tests/unit/test_boundaries.py",
    ],
    "jrh/formats/oto_ini.py": [
        "tests/unit/test_oto_format.py",
        "tests/unit/test_boundaries.py",
    ],
}

# 关键操作符变异：+↔-、*↔/、<↔<=、>↔>=、==↔!=、<↔>
_COMPARISON_PAIRS = [
    (ast.Lt, ast.LtE),
    (ast.LtE, ast.Lt),
    (ast.Gt, ast.GtE),
    (ast.GtE, ast.Gt),
    (ast.Eq, ast.NotEq),
    (ast.NotEq, ast.Eq),
    (ast.Lt, ast.Gt),
]
_BINOP_PAIRS = [(ast.Add, ast.Sub), (ast.Sub, ast.Add), (ast.Mult, ast.Div), (ast.Div, ast.Mult)]

_MAX_MUTANTS_PER_MODULE = 60

MutantFactory: TypeAlias = Callable[..., ast.AST]
Mutant: TypeAlias = tuple[tuple[int, int, type], MutantFactory]

# 等价变异白名单：(模块, 描述前缀, 理由)。
# 这些变异不改变任何可观测行为（已验证），不计入门禁。
EQUIVALENT_WHITELIST: list[tuple[str, str, str]] = [
    (
        "jrh/core/compile_engine.py",
        "const 0→1 L33",
        "等价：_KIND_RANK 数值变化后，别名字典序仍给出相同条目顺序",
    ),
    (
        "jrh/core/compile_engine.py",
        "const 1→0 L33",
        "等价：见上（full 与 transition 同秩时按别名排序，顺序不变）",
    ),
    (
        "jrh/core/compile_engine.py",
        "const 2→3 L33",
        "等价：见上（body 与 cv 同秩时按别名排序，顺序不变）",
    ),
    (
        "jrh/core/compile_engine.py",
        "const 4→5 L33",
        "等价：vc 已为最大秩，+1 后与其他 kind 的相对顺序不变",
    ),
    ("jrh/core/compile_engine.py", "const 9→10 L255", "等价：kind 只取已知五值，fallback 永不触发"),
    (
        "jrh/core/compile_engine.py",
        "const 1→0 L298",
        "等价：组序回退值永不可达（辅音侧必为启用单元，其坐标必在 effective_group_order 中）",
    ),
    (
        "jrh/core/compile_engine.py",
        "const 30→31 L298",
        "等价：见上（回退仅防御性，永不触发）",
    ),
    (
        "jrh/core/compile_engine.py",
        "binop Sub→Add L302",
        "等价：起点偏移到 nxt 只多检查辅助拍（跳过）或 nxt 自身——(nxt,nxt) 自配对经 vc_timing 恒 None"
        "（窗口≤0）；真实 (U,V) 由 (U,辅助拍) 配对的向前借位产出，输出不变",
    ),
    (
        "jrh/core/compile_engine.py",
        "const 1→0 L302",
        "等价：range 停止/步进 -1→0 使向前借位漏检 j=0 或空转，但 (U,辅助拍) 配对的向后借位"
        "已产出同一归一化对（镜像补偿），输出不变",
    ),
    (
        "jrh/core/analysis.py",
        "const 0→1 L90",
        "等价：per_asset count 缺失时 0 与 1 都 < 10，均回退全局统计",
    ),
    ("jrh/core/analysis.py", "compare LtE→Lt L111", "等价：单单元分组两条路径输出相同"),
    ("jrh/core/analysis.py", "const 1→0 L111", "等价：见上"),
    (
        "jrh/core/analysis.py",
        "const 0.0→1 L126",
        "等价：缺失 RMS 的占位 z 只用于同层比较，双方同为占位时按编号排序",
    ),
    (
        "jrh/core/analysis.py",
        "compare Gt→GtE L128",
        "边界约定：z == 2.5 在浮点下不可达（0.6745 系数），两者行为等价",
    ),
    ("jrh/core/analysis.py", "compare Gt→GtE L129", "边界约定：见上"),
    (
        "jrh/core/model.py",
        "const 0→1 L63",
        "等价：Sentence 的 max_unit_id_ever 默认值从不被使用（构造与 from_dict 均显式传值）",
    ),
    (
        "jrh/core/model.py",
        "bool True→False L258",
        "等价：Unit.enabled 默认值从不被使用（构造与 from_dict 均显式传值）",
    ),
    (
        "jrh/formats/oto_ini.py",
        "const 3→4 L19",
        "等价：后续 .3f 格式化强制三位小数，round 位数变化不可观测",
    ),
    ("jrh/formats/oto_ini.py", "compare Lt→LtE L20", "等价：三位小数取整后 |v| == 1e-9 不可达"),
]


class MutantCollector(ast.NodeVisitor):
    """收集所有可变异点：返回 (描述, (位置, 替换函数)) 列表。

    位置 = (lineno, col_offset, 节点类型)，保证每次在全新解析的树上
    都能定位（变异之间互不污染）。
    """

    def __init__(self):
        self.mutants: list[tuple[str, Mutant]] = []

    def _record(self, desc: str, node: ast.AST, repl_factory: MutantFactory) -> None:
        pos = (getattr(node, "lineno", -1), getattr(node, "col_offset", -1), type(node))
        self.mutants.append((desc, (pos, repl_factory)))

    def visit_Compare(self, node: ast.Compare) -> None:  # noqa: N802
        for pair in _COMPARISON_PAIRS:
            src, dst = pair
            if isinstance(node.ops[0], src):

                def factory(n=node, r=None, d=dst):  # type: ignore[misc]
                    new = copy.deepcopy(n)
                    new.ops = [d()]
                    return new

                self._record(f"compare {src.__name__}→{dst.__name__} L{node.lineno}", node, factory)
                break
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:  # noqa: N802
        for src, dst in _BINOP_PAIRS:
            if isinstance(node.op, src):

                def factory(n=node, r=None, d=dst):  # type: ignore[misc]
                    new = copy.deepcopy(n)
                    new.op = d()
                    return new

                self._record(f"binop {src.__name__}→{dst.__name__} L{node.lineno}", node, factory)
                break
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, bool):

            def factory(n=node, r=None, d=None):  # type: ignore[misc]
                new = copy.deepcopy(n)
                new.value = not n.value
                return new

            self._record(f"bool {node.value}→{not node.value} L{node.lineno}", node, factory)
        elif isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            v = node.value
            repl = 1 if v == 0 else (0 if v == 1 else v + 1)

            def factory(n=node, r=None, d=None):  # type: ignore[misc]
                # repl 来自闭包绑定（保持与其它 factory 相同签名）
                new = copy.deepcopy(n)
                new.value = repl
                return new

            self._record(f"const {v}→{repl} L{node.lineno}", node, factory)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        def factory(n=node, r=None):  # type: ignore[misc]
            new = copy.deepcopy(n)
            new.test = ast.UnaryOp(op=ast.Not(), operand=copy.deepcopy(n.test))
            ast.fix_missing_locations(new)
            return new

        self._record(f"if-invert L{node.lineno}", node, factory)
        self.generic_visit(node)


def collect_mutants(source: str) -> list[tuple[str, Mutant]]:
    tree = ast.parse(source)
    c = MutantCollector()
    c.visit(tree)
    return c.mutants[:_MAX_MUTANTS_PER_MODULE]


def apply_mutant(source: str, mutant: Mutant) -> str:
    """在全新解析的树上按 (lineno, col_offset, type) 定位并应用变异。"""
    pos, factory = mutant
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (getattr(node, "lineno", None), getattr(node, "col_offset", None), type(node)) == pos:
            for parent in ast.walk(tree):
                for field, value in ast.iter_fields(parent):
                    if value is node:
                        setattr(parent, field, factory())
                        return ast.unparse(tree)
                    if isinstance(value, list):
                        for i, item in enumerate(value):
                            if item is node:
                                value[i] = factory()
                                return ast.unparse(tree)
            raise RuntimeError("mutant 节点已定位但无法替换")
    raise RuntimeError("mutant 节点未找到")


def run_oracle(target_tests: list[str], mutant_root: Path, workdir: Path) -> bool:
    """在隔离包上运行目标测试；返回 True = 变异被杀死。

    隔离要点：中性 cwd（真实 jrh 不在路径上）+ PYTHONPATH 指向变异包
    + conftest 在设置 JRH_TEST_PACKAGE_ROOT 时不插入真实 ROOT。
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(mutant_root.parent)
    env["JRH_TEST_PACKAGE_ROOT"] = str(mutant_root)
    neutral = workdir / ".mutant_workdir"
    neutral.mkdir(exist_ok=True)
    abs_tests = [str((workdir / t).resolve()) for t in target_tests]
    cmd = [
        PYTHON,
        "-m",
        "pytest",
        *abs_tests,
        "-q",
        "--tb=line",
        "-p",
        "no:cacheprovider",
        "--no-header",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(neutral),
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
        env=env,
    )
    return proc.returncode != 0


def run_module(
    module: Path, target_tests: list[str], workdir: Path, gate_kill_rate: float
) -> dict[str, Any]:
    module = ROOT / module  # 相对 → 绝对
    source = module.read_text(encoding="utf-8")
    mutants = collect_mutants(source)
    if not mutants:
        return {"module": str(module), "mutants": 0, "skipped": True}
    killed = 0
    survivors: list[dict] = []
    whitelisted: list[dict] = []
    for desc, mutant in mutants:
        with tempfile.TemporaryDirectory(prefix="jrh_mut_") as td:
            mutant_root = Path(td) / "jrh"
            shutil.copytree(ROOT / "jrh", mutant_root)
            target = mutant_root / module.relative_to(ROOT / "jrh")
            target.write_text(apply_mutant(source, mutant), encoding="utf-8")
            if run_oracle(target_tests, mutant_root, workdir):
                killed += 1
            else:
                entry: dict[str, Any] = {"desc": desc, "module": str(module)}
                wl = _match_whitelist(str(module.relative_to(ROOT)).replace("\\", "/"), desc)
                if wl is not None:
                    entry["whitelisted"] = True
                    entry["justification"] = wl
                    whitelisted.append(entry)
                else:
                    survivors.append(entry)
    total = len(mutants)
    # 有效变异 = 总数 - 等价白名单（白名单不计入门禁）
    effective = total - len(whitelisted)
    rate = killed / effective if effective else 1.0
    return {
        "module": str(module),
        "mutants": total,
        "killed": killed,
        "survived": total - killed,
        "whitelisted": whitelisted,
        "kill_rate": round(rate, 3),
        "gate": round(gate_kill_rate, 3),
        "passed": rate >= gate_kill_rate,
        "survivors": survivors,
    }


def _match_whitelist(module: str, desc: str) -> str | None:
    for m, prefix, reason in EQUIVALENT_WHITELIST:
        if m == module and desc.startswith(prefix):
            return reason
    return None


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="JRH 核心模块变异测试")
    ap.add_argument(
        "--module", action="append", default=None, help="指定模块（相对仓库根），默认全部"
    )
    ap.add_argument("--gate-kill-rate", type=float, default=0.9, help="杀灭率门禁（默认 0.9）")
    args = ap.parse_args()

    modules = [Path(m) for m in (args.module or list(TARGETS))]
    results = []
    for module in modules:
        key = module.as_posix()
        if key not in TARGETS:
            print(f"[skip] 未配置目标测试: {module}")
            continue
        res = run_module(module, TARGETS[key], ROOT, args.gate_kill_rate)
        results.append(res)
        m = res
        status = "OK" if m.get("passed") else "FAIL"
        print(
            f"[{status}] {m['module']}: {m['killed']}/{m['mutants']} 杀死 "
            f"(杀灭率 {m['kill_rate']:.1%} ≥ 门禁 {m['gate']:.1%})"
        )
        for s in m.get("survivors", []):
            print(f"    surviving mutant: {s['desc']}")
        for s in m.get("whitelisted", []):
            print(f"    [等价白名单] {s['desc']}: {s['justification']}")

    report = {
        "gate_kill_rate": args.gate_kill_rate,
        "modules": results,
        "passed": all(r.get("passed", True) for r in results),
        "total_mutants": sum(r.get("mutants", 0) for r in results),
        "total_killed": sum(r.get("killed", 0) for r in results),
    }
    (ROOT / "mutation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"变异测试报告: mutation-report.json（共 {report['total_mutants']} 个变异）")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
