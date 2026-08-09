"""pytest 共享夹具。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))

# 变异测试隔离：设置 JRH_TEST_PACKAGE_ROOT 时加载变异包副本（最高优先级），
# 此时真实 jrh 不应进入 sys.path（变异工具用中性 cwd + PYTHONPATH 提供包）。
mutant_root = os.environ.get("JRH_TEST_PACKAGE_ROOT")
if mutant_root:
    sys.path.insert(0, mutant_root)
else:
    sys.path.insert(0, str(ROOT))

from fixtures.builder import (  # noqa: E402
    build_demo_project,
)


@pytest.fixture()
def demo_project(tmp_path: Path):
    """标准演示项目（含音频）。"""
    return build_demo_project(tmp_path)


@pytest.fixture()
def demo_project_frozen(tmp_path: Path):
    """冻结的标准演示项目。"""
    return build_demo_project(tmp_path, freeze=True)


@pytest.fixture()
def demo_project_noaudio(tmp_path: Path):
    """无真实音频文件的演示项目（文件缺失场景）。"""
    return build_demo_project(tmp_path, with_audio=False)
