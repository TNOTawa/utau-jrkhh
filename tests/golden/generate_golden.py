"""Golden 数据生成器：从演示项目编译并写出期望产物。

运行：python tests/golden/generate_golden.py
生成后必须人工核对数值（见 test_golden.py 与手工抽查），再提交。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TESTS = ROOT / "tests"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

GOLDEN_DATA = Path(__file__).resolve().parent / "data"


def main() -> None:
    import tempfile

    from fixtures.builder import build_demo_project

    from jrh.core.compile_engine import compile_project, write_build
    from jrh.core.project import JRHProject

    if GOLDEN_DATA.exists():
        shutil.rmtree(GOLDEN_DATA)
    GOLDEN_DATA.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as td:
        proj_path = build_demo_project(Path(td))
        proj = JRHProject.open(proj_path)
        result = compile_project(proj)
        tmp_out = Path(td) / "build"
        write_build(proj, result, tmp_out)
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            shutil.copy2(tmp_out / name, GOLDEN_DATA / name)
    print(f"golden 数据已生成到 {GOLDEN_DATA}")


if __name__ == "__main__":
    main()
