"""Golden 数据生成器：从演示项目编译并写出期望产物。

运行：python tests/golden/generate_golden.py
- data/         默认编译（zh demo，cvvc 关；与历史行为一致）
- data_cvvc/    CVVC 编译（ja demo，cvvc 开，含 VC 条目）
- data_zh_cvvc/ CVVC 编译（zh demo，cvvc 开，presamp 短 ID VC 条目）
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
GOLDEN_CVVC_DATA = Path(__file__).resolve().parent / "data_cvvc"
GOLDEN_ZH_CVVC_DATA = Path(__file__).resolve().parent / "data_zh_cvvc"


def main() -> None:
    import tempfile

    from fixtures.builder import build_demo_project, build_ja_demo_project

    from jrh.core.compile_engine import CompileConfig, compile_project, write_build
    from jrh.core.project import JRHProject

    for data_dir in (GOLDEN_DATA, GOLDEN_CVVC_DATA, GOLDEN_ZH_CVVC_DATA):
        if data_dir.exists():
            shutil.rmtree(data_dir)
        data_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as td:
        proj_path = build_demo_project(Path(td))
        proj = JRHProject.open(proj_path)
        result = compile_project(proj)
        tmp_out = Path(td) / "build"
        write_build(proj, result, tmp_out)
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            shutil.copy2(tmp_out / name, GOLDEN_DATA / name)

        ja_path = build_ja_demo_project(Path(td))
        ja = JRHProject.open(ja_path)
        ja_result = compile_project(ja, CompileConfig(cvvc=True))
        ja_out = Path(td) / "build_cvvc"
        write_build(ja, ja_result, ja_out)
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            shutil.copy2(ja_out / name, GOLDEN_CVVC_DATA / name)

        zh_path = build_demo_project(Path(td))
        zh = JRHProject.open(zh_path)
        zh_result = compile_project(zh, CompileConfig(cvvc=True))
        zh_out = Path(td) / "build_zh_cvvc"
        write_build(zh, zh_result, zh_out)
        for name in ("oto.ini", "build-report.json", "alias-map.json"):
            shutil.copy2(zh_out / name, GOLDEN_ZH_CVVC_DATA / name)
    print(f"golden 数据已生成到 {GOLDEN_DATA}、{GOLDEN_CVVC_DATA} 与 {GOLDEN_ZH_CVVC_DATA}")


if __name__ == "__main__":
    main()
