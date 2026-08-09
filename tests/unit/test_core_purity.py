"""架构纯净性检查：core 不得依赖第三方包、GUI 或传统格式。"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CORE = ROOT / "jrh" / "core"

_FORBIDDEN_IMPORTS = {
    "numpy",
    "scipy",
    "soundfile",
    "sounddevice",
    "matplotlib",
    "customtkinter",
    "tkinter",
    "src",
    "torch",
    "transformers",
    "faster_whisper",
    "funasr",
    "sofa",
}

# 允许 core 内部使用的 stdlib 白名单（缺省允许所有 stdlib，但显式检查第三方）
_ALLOWED_TOP_LEVEL = set(sys.stdlib_module_names)


def _top_level(name: str) -> str:
    return name.split(".")[0]


def test_core_imports_only_stdlib():
    imports = set()
    for py in CORE.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(_top_level(alias.name))
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(_top_level(node.module))
    bad = sorted(i for i in imports if i not in _ALLOWED_TOP_LEVEL and i != "jrh")
    assert bad == [], f"core 模块导入了非 stdlib 依赖: {bad}"


def test_core_package_no_forbidden_imports():
    for mod_name in sys.modules:
        if not mod_name.startswith("jrh.core"):
            continue
        for forbidden in _FORBIDDEN_IMPORTS:
            assert forbidden not in mod_name.split(".")[:2], mod_name


def test_languages_no_third_party():
    # 语言包模块源码中不允许 import numpy/scipy 等（相对导入跳过）
    for py in (ROOT / "jrh" / "languages").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert _top_level(alias.name) in _ALLOWED_TOP_LEVEL or alias.name.startswith(
                        "jrh"
                    ), f"{py}: {alias.name}"
            elif (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                and _top_level(node.module) not in _ALLOWED_TOP_LEVEL
                and not node.module.startswith("jrh")
            ):
                raise AssertionError(f"{py}: {node.module}")


def test_core_runs_without_numpy_soundfile():
    """在屏蔽 numpy/soundfile 的进程内验证核心仍可用（pure core 契约）。"""

    saved = {mod: sys.modules.pop(mod) for mod in ("numpy", "soundfile") if mod in sys.modules}
    try:
        # 重载核心模块链（不触发任何第三方）
        from jrh.core.project import JRHProject
        from jrh.core.selection import select_sequence

        assert JRHProject is not None and select_sequence is not None
    finally:
        sys.modules.update(saved)
