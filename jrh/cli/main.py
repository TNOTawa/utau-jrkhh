"""JRH CLI：所有核心功能的命令行入口（CLI First）。

退出码（JRH_SPEC §9）：0 成功 / 1 数据或运行时错误 / 2 用法错误 / 3 验证失败 / 4 strict 缺音。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import __version__
from ..core import analysis as analysis_mod
from ..core.compile_engine import (
    CompileConfig,
    compile_project,
    write_build,
)
from ..core.errors import (
    EXIT_ERROR,
    EXIT_STRICT_MISSING,
    EXIT_USAGE,
    JRHError,
)
from ..core.integrity import check_integrity
from ..core.model import Asset, Timing
from ..core.project import JRHProject
from ..core.selection import select_sequence
from ..core.validate import validate_project
from ..languages import list_packs
from ..phonemizer.adapters import to_phonemes


def main(argv: list[str] | None = None) -> int:
    code = run_cli(argv if argv is not None else sys.argv[1:])
    sys.exit(code)


def run_cli(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else EXIT_USAGE
    if not hasattr(args, "handler"):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.handler(args)
    except JRHError as e:
        _err(f"错误[{e.category}]: {e.message}")
        return e.exit_code()
    except Exception as e:  # noqa: BLE001 —— 意外异常显式暴露，不吞
        _err(f"内部错误: {type(e).__name__}: {e}")
        return EXIT_ERROR


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _emit(args: argparse.Namespace, obj: Any) -> None:
    if args.format == "json":
        print(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(obj)


def _load(path: str) -> JRHProject:
    return JRHProject.open(Path(path))


def _add_project_arg(sp) -> None:
    sp.add_argument("project", help="JRH 项目路径")


def _add_format_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式（默认 text；机器可读用 json）",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jrh",
        description="JRH 人力音源母版格式工具（v0.1）",
    )
    p.add_argument("--version", action="version", version=f"jrh {__version__}")
    _add_format_flag(p)
    sub = p.add_subparsers(dest="command", metavar="命令")

    def cmd(name: str, help_text: str, handler: Callable) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(handler=handler)
        return sp

    # ── init ────────────────────────────────────────────────
    sp = cmd("init", "创建新 JRH 项目", _cmd_init)
    sp.add_argument("project")
    sp.add_argument("--language-pack", default="jrh.zh-pinyin", help="语言包名")
    sp.add_argument("--force", action="store_true", help="目录已存在时允许覆盖")

    # ── info / language-pack ────────────────────────────────
    sp = cmd("info", "查看项目信息（format inspection）", _cmd_info)
    _add_project_arg(sp)
    sp = cmd("language-pack", "列出可用语言包", _cmd_language_pack)

    # ── asset ───────────────────────────────────────────────
    sp = cmd("asset-add", "导入素材（复制进项目 assets/，计算 sha256）", _cmd_asset_add)
    _add_project_arg(sp)
    sp.add_argument("file", help="素材文件路径（音频）")
    sp.add_argument("--id", default=None, help="asset id（默认 asset-N）")
    sp = cmd("asset-list", "列出素材", _cmd_asset_list)
    _add_project_arg(sp)
    sp = cmd("asset-info", "查看素材详情", _cmd_asset_info)
    _add_project_arg(sp)
    sp.add_argument("asset_id")
    sp = cmd("asset-remove", "移除素材（不得被句子引用）", _cmd_asset_remove)
    _add_project_arg(sp)
    sp.add_argument("asset_id")

    # ── sentence ────────────────────────────────────────────
    sp = cmd("sentence-create", "创建句子", _cmd_sentence_create)
    _add_project_arg(sp)
    sp.add_argument("asset_id")
    sp.add_argument("--start", type=int, required=True, help="起始采样点")
    sp.add_argument("--end", type=int, required=True, help="结束采样点")
    sp.add_argument("--provider", default=None, help="分句来源（如 manual/vad）")
    sp.add_argument("--confidence", type=float, default=None)
    sp = cmd("sentence-update", "修改句子边界/分句信息", _cmd_sentence_update)
    _add_project_arg(sp)
    sp.add_argument("sentence_id", type=int)
    sp.add_argument("--start", type=int, default=None)
    sp.add_argument("--end", type=int, default=None)
    sp.add_argument("--provider", default=None)
    sp.add_argument("--confidence", type=float, default=None)
    sp = cmd("sentence-delete", "删除句子", _cmd_sentence_delete)
    _add_project_arg(sp)
    sp.add_argument("sentence_id", type=int)
    sp.add_argument("--cascade", action="store_true", help="连带删除句内单元")
    sp = cmd("sentence-split", "分割句子", _cmd_sentence_split)
    _add_project_arg(sp)
    sp.add_argument("sentence_id", type=int)
    sp.add_argument("--at", type=int, required=True, help="分割点采样点")
    sp = cmd("sentence-merge", "合并两句（保留较小句号）", _cmd_sentence_merge)
    _add_project_arg(sp)
    sp.add_argument("a", type=int)
    sp.add_argument("b", type=int)
    sp = cmd("sentence-list", "列出句子", _cmd_sentence_list)
    _add_project_arg(sp)
    sp = cmd("sentence-renumber", "草稿期重排句内单元编号 1..n", _cmd_sentence_renumber)
    _add_project_arg(sp)
    sp.add_argument("sentence_id", type=int)

    # ── unit ────────────────────────────────────────────────
    sp = cmd("unit-create", "创建单元", _cmd_unit_create)
    _add_project_arg(sp)
    sp.add_argument("sentence_id", type=int)
    sp.add_argument("--label", required=True, help="录音单位（如 hao）")
    sp.add_argument("--offset", type=float, default=0.0)
    sp.add_argument("--consonant", type=float, default=0.0)
    sp.add_argument("--cutoff", type=float, required=True, help="负值：=-窗口时长（采样点）")
    sp.add_argument("--preutterance", type=float, default=0.0)
    sp.add_argument("--overlap", type=float, default=0.0)
    sp.add_argument("--disabled", action="store_true", help="创建为禁用候选")
    sp = cmd("unit-update", "修改单元（label/原音参数/启用状态）", _cmd_unit_update)
    _add_project_arg(sp)
    sp.add_argument("coordinate", help="坐标 s:u")
    sp.add_argument("--label", default=None)
    sp.add_argument("--offset", type=float, default=None)
    sp.add_argument("--consonant", type=float, default=None)
    sp.add_argument("--cutoff", type=float, default=None)
    sp.add_argument("--preutterance", type=float, default=None)
    sp.add_argument("--overlap", type=float, default=None)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--enabled", dest="enabled", action="store_true", default=None)
    g.add_argument("--disabled", dest="enabled", action="store_false", default=None)
    sp = cmd("unit-delete", "删除单元（编号永久留空）", _cmd_unit_delete)
    _add_project_arg(sp)
    sp.add_argument("coordinate")
    sp = cmd("unit-list", "列出单元", _cmd_unit_list)
    _add_project_arg(sp)
    sp.add_argument("--sentence", type=int, default=None)
    sp.add_argument("--label", default=None)
    sp = cmd("unit-renumber", "草稿期重排全项目句号 1..n", _cmd_unit_renumber)
    _add_project_arg(sp)

    # ── group ───────────────────────────────────────────────
    sp = cmd("group", "候选分组：人工排序 / 恢复自动 / 查看", _cmd_group)
    _add_project_arg(sp)
    sp.add_argument("label")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--manual", default=None, help='人工顺序，如 "1:2,5:4"')
    g.add_argument("--auto", action="store_true", help="恢复自动排序")
    g.add_argument("--show", action="store_true", help="显示有效顺序")

    # ── analyze / validate / integrity / freeze ─────────────
    sp = cmd("analyze", "时长/RMS 分析与汇总统计", _cmd_analyze)
    _add_project_arg(sp)
    sp.add_argument("--no-rms", action="store_true", help="跳过音频 RMS（仅时长）")
    sp = cmd("validate", "JRH 验证（错误 ⇒ 退出码 3）", _cmd_validate)
    _add_project_arg(sp)
    sp = cmd("integrity", "数据完整性检查（文件/哈希/产物一致性）", _cmd_integrity)
    _add_project_arg(sp)
    sp = cmd("freeze", "冻结编号（一次性；只增不改、不复用）", _cmd_freeze)
    _add_project_arg(sp)

    # ── compile ─────────────────────────────────────────────
    sp = cmd("compile", "编译 openutau-jrh 运行目标", _cmd_compile)
    _add_project_arg(sp)
    sp.add_argument("--out", default=None, help="输出目录（默认 builds/openutau-jrh）")
    sp.add_argument("--dry-run", action="store_true", help="只计算并输出报告，不写任何文件")
    sp.add_argument("--clean", action="store_true", help="先删除旧产物再重建")
    sp.add_argument("--gap", type=float, default=100.0, help="连续性最大时间间隔 ms（默认 100）")

    # ── select / phonemize ──────────────────────────────────
    sp = cmd("select", "候选选择（逐单位输出层级与解释）", _cmd_select)
    _add_project_arg(sp)
    sp.add_argument("targets", nargs="+", help="目标单位序列，如 ni hao a")
    sp = cmd("phonemize", "phonemizer 模拟（输出实际 phoneme 别名与位置）", _cmd_phonemize)
    _add_project_arg(sp)
    sp.add_argument("targets", nargs="+", help="目标单位序列")
    sp.add_argument("--strict", action="store_true", help="存在缺音时退出码 4")

    return p


# ── 命令实现 ─────────────────────────────────────────────────────


def _cmd_init(args) -> int:
    proj = JRHProject.create(args.project, args.language_pack)
    _emit(args, {"created": str(proj.path), "language_pack": proj.pack.name, "state": "draft"})
    return 0


def _cmd_info(args) -> int:
    proj = _load(args.project)
    data = {
        "project": str(proj.path),
        "format": proj.manifest.get("format"),
        "schema_version": proj.manifest.get("schema_version"),
        "state": proj.manifest.get("state"),
        "language_pack": proj.manifest.get("language_pack"),
        "counts": {
            "assets": len(proj.assets),
            "sentences": len(proj.sentences),
            "units": len(proj.units),
        },
        "id_counters": proj._allocator.counters.to_dict(),  # noqa: SLF001
    }
    if args.format == "json":
        _emit(args, data)
    else:
        _emit(args, "\n".join(f"{k}: {v}" for k, v in data.items()))
    return 0


def _cmd_language_pack(args) -> int:
    packs = list_packs()
    _emit(
        args,
        packs
        if args.format == "json"
        else "\n".join(f"{p['name']}  ({p['unit_system']})" for p in packs),
    )
    return 0


def _cmd_asset_add(args) -> int:
    from ..audio.probe import probe_audio_file, sha256_file

    proj = _load(args.project)
    src = Path(args.file)
    if not src.exists():
        raise JRHError(f"素材文件不存在: {src}", "not-found")
    info = probe_audio_file(src)
    aid = args.id or _next_asset_id(proj)
    assets_dir = proj.path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_copy_path(assets_dir, src.name)
    shutil.copy2(src, target)
    asset = Asset(
        id=aid,
        file=str(target.relative_to(proj.path)).replace("\\", "/"),
        kind="audio",
        sha256=sha256_file(target),
        sample_rate=int(info["sample_rate"]),
        num_samples=int(info["num_samples"]),
        duration_seconds=float(info["duration_seconds"]),
    )
    proj.add_asset(asset)
    proj.save()
    _emit(
        args,
        asset.to_dict()
        if args.format == "json"
        else f"asset {aid}: {asset.file} ({asset.sample_rate} Hz, {asset.duration_seconds:.3f}s, sha256={asset.sha256[:12]}…)",
    )
    return 0


def _next_asset_id(proj: JRHProject) -> str:
    n = 1
    while f"asset-{n:03d}" in proj.assets:
        n += 1
    return f"asset-{n:03d}"


def _unique_copy_path(dir_path: Path, name: str) -> Path:
    cand = dir_path / name
    n = 1
    stem = Path(name).stem
    suffix = Path(name).suffix
    while cand.exists():
        cand = dir_path / f"{stem}_{n}{suffix}"
        n += 1
    return cand


def _cmd_asset_list(args) -> int:
    proj = _load(args.project)
    rows = [proj.assets[a].to_dict() for a in sorted(proj.assets)]
    if args.format == "json":
        _emit(args, {"assets": rows})
    else:
        _emit(args, "\n".join(f"{a['id']}: {a['file']} ({a['sample_rate']} Hz)" for a in rows))
    return 0


def _cmd_asset_info(args) -> int:
    proj = _load(args.project)
    asset = proj.get_asset(args.asset_id)
    _emit(args, asset.to_dict())
    return 0


def _cmd_asset_remove(args) -> int:
    proj = _load(args.project)
    proj.remove_asset(args.asset_id)
    proj.save()
    _emit(args, {"removed": args.asset_id})
    return 0


def _cmd_sentence_create(args) -> int:
    proj = _load(args.project)
    seg = {}
    if args.provider is not None:
        seg["provider"] = args.provider
    if args.confidence is not None:
        seg["confidence"] = args.confidence
    sent = proj.create_sentence(args.asset_id, args.start, args.end, segmentation=seg)
    proj.save()
    _emit(args, sent.to_dict())
    return 0


def _cmd_sentence_update(args) -> int:
    proj = _load(args.project)
    seg = None
    if args.provider is not None or args.confidence is not None:
        cur = proj.get_sentence(args.sentence_id).segmentation
        seg = dict(cur)
        if args.provider is not None:
            seg["provider"] = args.provider
        if args.confidence is not None:
            seg["confidence"] = args.confidence
    sent = proj.update_sentence(
        args.sentence_id,
        start_sample=args.start,
        end_sample=args.end,
        segmentation=seg,
    )
    proj.save()
    _emit(args, sent.to_dict())
    return 0


def _cmd_sentence_delete(args) -> int:
    proj = _load(args.project)
    proj.delete_sentence(args.sentence_id, cascade=args.cascade)
    proj.save()
    _emit(args, {"deleted": args.sentence_id})
    return 0


def _cmd_sentence_split(args) -> int:
    proj = _load(args.project)
    new_sid, new_sent = proj.split_sentence(args.sentence_id, args.at)
    proj.save()
    _emit(
        args,
        {
            "original": args.sentence_id,
            "new_sentence_id": new_sid,
            "new_sentence": new_sent.to_dict(),
        },
    )
    return 0


def _cmd_sentence_merge(args) -> int:
    proj = _load(args.project)
    keep = proj.merge_sentences(args.a, args.b)
    proj.save()
    _emit(args, {"kept": keep, "merged": (args.a, args.b)})
    return 0


def _cmd_sentence_list(args) -> int:
    proj = _load(args.project)
    rows = [s.to_dict() for s in proj.sentences_sorted()]
    if args.format == "json":
        _emit(args, {"sentences": rows})
    else:
        _emit(
            args,
            "\n".join(
                f"{s['sentence_id']}: asset={s['asset_id']} "
                f"[{s['start_sample']}, {s['end_sample']}) @{s['sample_rate']}Hz"
                for s in rows
            ),
        )
    return 0


def _cmd_sentence_renumber(args) -> int:
    proj = _load(args.project)
    proj.renumber_unit_ids(args.sentence_id)
    proj.save()
    _emit(args, {"renumbered": args.sentence_id})
    return 0


def _cmd_unit_create(args) -> int:
    proj = _load(args.project)
    timing = Timing(args.offset, args.consonant, args.cutoff, args.preutterance, args.overlap)
    unit = proj.create_unit(args.sentence_id, args.label, timing, enabled=not args.disabled)
    proj.save()
    _emit(args, unit.to_dict())
    return 0


def _cmd_unit_update(args) -> int:
    from ..core.ids import parse_coordinate

    proj = _load(args.project)
    s, u = parse_coordinate(args.coordinate)
    timing = None
    if any(
        x is not None
        for x in (args.offset, args.consonant, args.cutoff, args.preutterance, args.overlap)
    ):
        cur = proj.get_unit(s, u).timing
        timing = Timing(
            offset=cur.offset if args.offset is None else args.offset,
            consonant=cur.consonant if args.consonant is None else args.consonant,
            cutoff=cur.cutoff if args.cutoff is None else args.cutoff,
            preutterance=cur.preutterance if args.preutterance is None else args.preutterance,
            overlap=cur.overlap if args.overlap is None else args.overlap,
        )
    unit = proj.update_unit(s, u, label=args.label, timing=timing, enabled=args.enabled)
    proj.save()
    _emit(args, unit.to_dict())
    return 0


def _cmd_unit_delete(args) -> int:
    from ..core.ids import parse_coordinate

    proj = _load(args.project)
    s, u = parse_coordinate(args.coordinate)
    proj.delete_unit(s, u)
    proj.save()
    _emit(args, {"deleted": args.coordinate})
    return 0


def _cmd_unit_list(args) -> int:
    proj = _load(args.project)
    units = proj.units_sorted()
    if args.sentence is not None:
        units = [u for u in units if u.sentence_id == args.sentence]
    if args.label is not None:
        units = [u for u in units if u.label == args.label]
    rows = [u.to_dict() for u in units]
    if args.format == "json":
        _emit(args, {"units": rows})
    else:
        _emit(
            args,
            "\n".join(
                f"{u['sentence_id']}:{u['unit_id']}  {u['label']:<8} "
                f"{'启用' if u['enabled'] else '禁用'}  "
                f"offset={u['timing']['offset']:.1f} consonant={u['timing']['consonant']:.1f} "
                f"cutoff={u['timing']['cutoff']:.1f} preutterance={u['timing']['preutterance']:.1f} "
                f"overlap={u['timing']['overlap']:.1f}"
                for u in rows
            ),
        )
    return 0


def _cmd_unit_renumber(args) -> int:
    proj = _load(args.project)
    proj.renumber_sentences()
    proj.save()
    _emit(args, {"renumbered": "sentences"})
    return 0


def _cmd_group(args) -> int:
    proj = _load(args.project)
    if args.manual is not None:
        coords = [c.strip() for c in args.manual.split(",") if c.strip()]
        proj.group_set_manual(args.label, coords)
        proj.save()
        _emit(args, {"label": args.label, "mode": "manual", "order": coords})
        return 0
    if args.auto:
        proj.group_set_auto(args.label)
        proj.save()
        _emit(args, {"label": args.label, "mode": "auto"})
        return 0
    order = analysis_mod.effective_group_order(proj, args.label)
    data = {
        "label": args.label,
        "mode": proj.candidate_groups.mode(args.label),
        "effective_order": order,
        "manual_order": proj.candidate_groups.ordered_unit_ids(args.label),
    }
    if args.format == "json":
        _emit(args, data)
    else:
        _emit(args, f"{args.label} [{data['mode']}]: " + ", ".join(order))
    return 0


def _cmd_analyze(args) -> int:
    proj = _load(args.project)
    duration_ok = 0
    rms_ok = 0
    rms_skip = 0
    for u in proj.units_sorted():
        if not u.enabled:
            continue
        sent = proj.get_sentence(u.sentence_id)
        dur = analysis_mod.unit_duration_ms(u, sent.sample_rate)
        rms = None
        if not args.no_rms:
            from ..audio.rms import unit_rms_dbfs

            rms = unit_rms_dbfs(proj, u)
        proj.set_unit_analysis(
            u.sentence_id,
            u.unit_id,
            {
                "duration_ms": round(dur, 3),
                "rms_dbfs": round(rms, 3) if rms is not None else None,
            },
        )
        duration_ok += 1
        if rms is not None:
            rms_ok += 1
        else:
            rms_skip += 1
    summary = analysis_mod.build_summary(proj)
    proj.set_analysis_summary(summary)
    proj.save()
    data = {
        "analyzed": duration_ok,
        "rms_computed": rms_ok,
        "rms_skipped": rms_skip,
        "summary": summary.to_dict(),
    }
    if args.format == "json":
        _emit(args, data)
    else:
        _emit(
            args,
            f"分析完成：{duration_ok} 个单元（RMS {rms_ok}，跳过 {rms_skip}）\n"
            f"全局时长中位数 {summary.global_stats['duration_ms'].get('median')} ms\n"
            f"全局 RMS 中位数 {summary.global_stats['rms_dbfs'].get('median')} dBFS",
        )
    return 0


def _cmd_validate(args) -> int:
    proj = _load(args.project)
    result = validate_project(proj)
    if args.format == "json":
        _emit(args, result.to_dict())
    else:
        for i in result.issues:
            _emit(args, f"[{i.severity}] {i.code} @ {i.location}: {i.message}")
        _emit(
            args, f"错误 {result.error_count()} / 警告 {len(result.issues) - result.error_count()}"
        )
    return 0 if not result.has_errors() else 3


def _cmd_integrity(args) -> int:
    proj = _load(args.project)
    result = check_integrity(proj)
    if args.format == "json":
        _emit(args, result.to_dict())
    else:
        for i in result.issues:
            _emit(args, f"[{i.severity}] {i.code} @ {i.location}: {i.message}")
        _emit(
            args, f"错误 {result.error_count()} / 警告 {len(result.issues) - result.error_count()}"
        )
    return 0 if not result.has_errors() else 3


def _cmd_freeze(args) -> int:
    proj = _load(args.project)
    proj.freeze()
    _emit(args, {"state": "frozen"})
    return 0


def _cmd_compile(args) -> int:
    proj = _load(args.project)
    config = CompileConfig(continuity_max_gap_ms=args.gap, dry_run=args.dry_run)
    result = compile_project(proj, config)
    if not args.dry_run:
        out = Path(args.out) if args.out else proj.path / "builds" / config.target
        if args.clean and out.exists():
            shutil.rmtree(out)
        write_build(proj, result, out)
        report = result.report_dict(proj)
        report["output_dir"] = str(out)
    else:
        report = result.report_dict(proj)
        report["output_dir"] = None
    if args.format == "json":
        _emit(args, report)
    else:
        s = report["summary"]
        _emit(
            args,
            f"编译完成：{s['aliases_total']} 条别名"
            f"（FULL {s['full']} / $T {s['transition']} / $B {s['body']} / CV {s['cv']}），"
            f"冲突 {s['conflicts']}，缺音 {s['missing']}"
            + (
                f"\n输出: {report['output_dir']}"
                if report["output_dir"]
                else "\n[dry-run] 未写文件"
            ),
        )
    return 0


def _cmd_select(args) -> int:
    return _selection(args, phonemize=False)


def _cmd_phonemize(args) -> int:
    return _selection(args, phonemize=True)


def _selection(args, phonemize: bool) -> int:
    proj = _load(args.project)
    results = select_sequence(proj, args.targets)
    payload = []
    missing = 0
    for r in results:
        entry = r.to_dict()
        if phonemize:
            entry["phonemes"] = [
                {"phoneme": ph.phoneme, "position_ms": ph.position_ms} for ph in to_phonemes(r)
            ]
        payload.append(entry)
        if r.level == "missing":
            missing += 1
    data = {"targets": payload, "missing_count": missing, "phonemize": phonemize}
    if args.format == "json":
        _emit(args, data)
    else:
        for r in results:
            ph = ", ".join(p.phoneme for p in to_phonemes(r)) if phonemize else ""
            _emit(
                args, f"{r.index + 1}. {r.label:<8} → {r.level:<11} {r.unit_coord or '-':<8} {ph}"
            )
        _emit(args, f"缺音 {missing} / {len(results)}")
    if phonemize and args.strict and missing:
        return EXIT_STRICT_MISSING
    return 0
