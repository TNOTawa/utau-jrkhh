"""数据完整性检查：文件存在、哈希、引用、编译产物一致性。

与 validate 的区别：本命令检查「物理层」（磁盘文件），validate 检查「语义层」。
"""

from __future__ import annotations

from pathlib import Path

from ..formats.oto_ini import read_oto
from .errors import DataError
from .model import unit_key
from .project import JRHProject
from .util import read_json_strict
from .validate import ValidationResult, validate_project

_BUILD_TARGETS = ("openutau-jrh",)


def check_integrity(project: JRHProject) -> ValidationResult:
    res = validate_project(project)

    # 物理文件与哈希
    for aid in sorted(project.assets):
        asset = project.assets[aid]
        p = project.path / asset.file
        if not p.exists():
            res.add("error", "integrity.asset_missing", f"asset:{aid}", f"文件不存在: {p}")
            continue
        from ..audio.probe import sha256_file

        sha = sha256_file(p)
        if asset.sha256 and sha != asset.sha256:
            res.add(
                "error",
                "integrity.asset_hash",
                f"asset:{aid}",
                f"哈希不符（记录 {asset.sha256}，实际 {sha}）",
            )
        else:
            res.add("info", "integrity.asset_ok", f"asset:{aid}", "文件存在且哈希一致")

    # 编译产物一致性（存在时）
    for target in _BUILD_TARGETS:
        build_dir = project.path / "builds" / target
        if not build_dir.exists():
            continue
        _check_build(project, build_dir, res)

    return res


def _check_build(project: JRHProject, build_dir: Path, res: ValidationResult) -> None:
    oto_path = build_dir / "oto.ini"
    amap_path = build_dir / "alias-map.json"
    report_path = build_dir / "build-report.json"
    if not oto_path.exists():
        res.add("error", "integrity.build_partial", str(build_dir), "缺少 oto.ini")
        return
    try:
        oto_lines = read_oto(oto_path)
    except DataError as e:
        res.add("error", "integrity.build_partial", str(oto_path), str(e))
        return
    oto_aliases = [line.alias for line in oto_lines]
    if len(set(oto_aliases)) != len(oto_aliases):
        res.add(
            "error",
            "integrity.build_duplicate_alias",
            str(oto_path),
            "oto.ini 存在重复别名（违反编译不变量）",
        )

    if amap_path.exists():
        try:
            amap = read_json_strict(amap_path)
        except DataError as e:
            res.add("error", "integrity.build_partial", str(amap_path), str(e))
            amap = None
        if isinstance(amap, dict):
            for alias, info in sorted(amap.items()):
                if not isinstance(info, dict):
                    res.add(
                        "error",
                        "integrity.build_alias_map",
                        str(amap_path),
                        f"alias-map 条目非法: {alias}",
                    )
                    continue
                if alias not in set(oto_aliases):
                    res.add(
                        "error",
                        "integrity.build_alias_map",
                        str(amap_path),
                        f"alias-map 中的别名不在 oto.ini: {alias}",
                    )
                s = info.get("sentence_id")
                u = info.get("unit_id")
                if (
                    not isinstance(s, int)
                    or not isinstance(u, int)
                    or unit_key(s, u) not in project.units
                ):
                    res.add(
                        "error",
                        "integrity.build_alias_map",
                        str(amap_path),
                        f"alias {alias} 引用的来源单元不存在: {s}:{u}",
                    )
        else:
            res.add("error", "integrity.build_alias_map", str(amap_path), "alias-map.json 结构错误")

    if report_path.exists():
        try:
            report = read_json_strict(report_path)
        except DataError as e:
            res.add("error", "integrity.build_partial", str(report_path), str(e))
            return
        if isinstance(report, dict) and "summary" in report:
            summary = report["summary"]
            n = summary.get("aliases_total", -1)
            if n != len(oto_aliases):
                res.add(
                    "error",
                    "integrity.build_report",
                    str(report_path),
                    f"report 条目数 {n} ≠ oto.ini 实际条目 {len(oto_aliases)}",
                )
        else:
            res.add(
                "error", "integrity.build_report", str(report_path), "build-report.json 结构错误"
            )

    # 原句 WAV 存在性
    wavs = {line.wav for line in oto_lines}
    for w in sorted(wavs):
        if not (build_dir / w).exists():
            res.add("error", "integrity.build_wav_missing", str(build_dir), f"原句 WAV 不存在: {w}")
