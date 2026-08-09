"""编译引擎：JRH 母版 → openutau-jrh 运行目标。

派生规则（JRH_SPEC §5，唯一权威公式）：
- FULL      原样五参数
- TRANSITION $T：[offset, offset+consonant]（consonant>0 时生成）
- BODY       $B：[offset+preutterance, offset+|cutoff|]
- CV         与 $B 同区域，命名按候选分组顺序（label, label1, ...）
- 不生成 ENDING。
冲突（重复 alias）⇒ 编译失败，不写任何产物。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..formats.oto_ini import OtoLine, write_oto
from .analysis import effective_group_order
from .errors import ConflictError, ValidationError
from .project import JRHProject
from .util import write_json
from .validate import validate_project

TARGET = "openutau-jrh"
SCHEMA = "0.1.0"

# oto.ini 内条目排序：FULL → TRANSITION → BODY → CV
_KIND_RANK = {"full": 0, "transition": 1, "body": 2, "cv": 3}


@dataclass
class CompileConfig:
    target: str = TARGET
    suffix_transition: str = "$T"
    suffix_body: str = "$B"
    rest_marker: str = "R"
    continuity_max_gap_ms: float = 100.0
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "suffix_transition": self.suffix_transition,
            "suffix_body": self.suffix_body,
            "rest_marker": self.rest_marker,
            "continuity_max_gap_ms": self.continuity_max_gap_ms,
            "dry_run": self.dry_run,
        }


@dataclass
class CompiledEntry:
    alias: str
    sentence_id: int
    unit_id: int
    kind: str
    wav: str
    params: dict[str, float]
    source_label: str = ""

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "sentence_id": self.sentence_id,
            "unit_id": self.unit_id,
            "kind": self.kind,
            "wav": self.wav,
            "params": self.params,
            "source_label": self.source_label,
        }


@dataclass
class BuildResult:
    config: CompileConfig
    entries: list[CompiledEntry] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)
    degraded: list[dict[str, Any]] = field(default_factory=list)
    unrepresentable: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    def report_dict(self, project: JRHProject) -> dict:
        summary = {
            "aliases_total": len(self.entries),
            "full": sum(1 for e in self.entries if e.kind == "full"),
            "transition": sum(1 for e in self.entries if e.kind == "transition"),
            "body": sum(1 for e in self.entries if e.kind == "body"),
            "cv": sum(1 for e in self.entries if e.kind == "cv"),
            "conflicts": len(self.conflicts),
            "missing": len(self.missing),
            "degraded": len(self.degraded),
        }
        return {
            "target": self.config.target,
            "schema": SCHEMA,
            "project": {
                "language_pack": project.manifest.get("language_pack"),
                "frozen": project.frozen,
            },
            "config": self.config.to_dict(),
            "summary": summary,
            "entries": [e.to_dict() for e in self.entries],
            "conflicts": self.conflicts,
            "missing": self.missing,
            "degraded": self.degraded,
            "unrepresentable": self.unrepresentable,
        }


def sentence_wav_name(sentence_id: int) -> str:
    return f"sentence_{sentence_id:03d}.wav"


def _five_part_alias(
    project: JRHProject,
    unit_id: int,
    sentence_id: int,
    prev_label: str | None,
    cur_label: str,
    next_label: str | None,
    config: CompileConfig,
) -> str:
    rest = config.rest_marker
    prev = prev_label if prev_label is not None else rest
    nxt = next_label if next_label is not None else rest
    return f"{sentence_id}-{unit_id}-{prev}-{cur_label}-{nxt}"


def _display_labels(project: JRHProject, sentence_id: int, unit_id: int):
    """句内相邻单元的显示 label；边界为 None。"""
    units = project.units_in_sentence(sentence_id)
    pos = {u.unit_id: u for u in units}
    u = pos.get(unit_id)
    if u is None:
        return None, None, None
    ids = sorted(pos)
    idx = ids.index(unit_id)
    prev = pos[ids[idx - 1]].label if idx > 0 else None
    nxt = pos[ids[idx + 1]].label if idx + 1 < len(ids) else None
    return prev, u.label, nxt


def compile_project(
    project: JRHProject,
    config: CompileConfig | None = None,
    validate_first: bool = True,
) -> BuildResult:
    """执行编译（纯计算，不写文件）。冲突 ⇒ ConflictError。"""
    config = config or CompileConfig()
    if validate_first:
        vres = validate_project(project)
        if vres.has_errors():
            raise ValidationError("项目未通过验证，无法编译：" + _first_errors(vres.errors(), 5))
    result = BuildResult(config=config)
    seen_aliases: dict[str, list[str]] = {}

    for sent in project.sentences_sorted():
        wav = sentence_wav_name(sent.sentence_id)
        for u in project.units_in_sentence(sent.sentence_id):
            if not u.enabled:
                continue  # 禁用单元不产生任何别名
            prev, cur, nxt = _display_labels(project, sent.sentence_id, u.unit_id)
            full_alias = _five_part_alias(
                project, u.unit_id, sent.sentence_id, prev, cur, nxt, config
            )
            params = u.timing.to_ms(sent.sample_rate)
            result.entries.append(
                CompiledEntry(full_alias, sent.sentence_id, u.unit_id, "full", wav, params, u.label)
            )
            _register(seen_aliases, full_alias, u.coordinate(), result)
            t = u.timing.transition_timing()
            if t is not None:
                t_alias = full_alias + config.suffix_transition
                result.entries.append(
                    CompiledEntry(
                        t_alias,
                        sent.sentence_id,
                        u.unit_id,
                        "transition",
                        wav,
                        t.to_ms(sent.sample_rate),
                        u.label,
                    )
                )
                _register(seen_aliases, t_alias, u.coordinate(), result)
            b = u.timing.body_timing()
            b_alias = full_alias + config.suffix_body
            result.entries.append(
                CompiledEntry(
                    b_alias,
                    sent.sentence_id,
                    u.unit_id,
                    "body",
                    wav,
                    b.to_ms(sent.sample_rate),
                    u.label,
                )
            )
            _register(seen_aliases, b_alias, u.coordinate(), result)

    # CV 搜索别名：按候选分组有效顺序命名
    for label in sorted({u.label for u in project.units.values()}):
        order = effective_group_order(project, label)
        for rank, coord in enumerate(order):
            s, u = _coord_to_unit(project, coord)
            cv_alias = label if rank == 0 else f"{label}{rank}"
            b = u.timing.body_timing()
            sent = project.get_sentence(s)
            wav = sentence_wav_name(s)
            result.entries.append(
                CompiledEntry(
                    cv_alias,
                    s,
                    u.unit_id,
                    "cv",
                    wav,
                    b.to_ms(sent.sample_rate),
                    u.label,
                )
            )
            _register(seen_aliases, cv_alias, u.coordinate(), result)

    result.entries.sort(
        key=lambda e: (
            e.sentence_id,
            e.unit_id,
            _KIND_RANK.get(e.kind, 9),
            e.alias,
        )
    )
    result.conflicts = sorted(
        [
            {"alias": a, "sources": sorted(set(srcs))}
            for a, srcs in seen_aliases.items()
            if len(srcs) > 1
        ],
        key=lambda c: c["alias"],
    )
    if result.conflicts:
        detail = "; ".join(f"{c['alias']} <- {', '.join(c['sources'])}" for c in result.conflicts)
        raise ConflictError(f"别名冲突，编译失败（不写产物）: {detail}")
    return result


def _coord_to_unit(project: JRHProject, coord: str):
    from .ids import parse_coordinate

    s, u = parse_coordinate(coord)
    return s, project.get_unit(s, u)


def _register(seen: dict[str, list[str]], alias: str, coord: str, result: BuildResult) -> None:
    seen.setdefault(alias, []).append(coord)


def _first_errors(issues, n: int) -> str:
    msgs = [f"{i.location}: {i.message}" for i in issues[:n]]
    if len(issues) > n:
        msgs.append(f"…（共 {len(issues)} 个错误）")
    return "；".join(msgs)


def write_build(
    project: JRHProject,
    result: BuildResult,
    out_dir: Path,
    export_audio: bool = True,
) -> Path:
    """写出编译产物（原句 WAV + oto.ini + alias-map.json + build-report.json）。

    - 冲突在 compile_project 已抛错；本函数假设 result 无冲突。
    - export_audio=False 时跳过 WAV 写出（report 仍生成）。
    - 返回 build 目录。
    """
    out_dir = Path(out_dir)
    if export_audio:
        from ..audio.export import export_sentence_wavs

        export_sentence_wavs(project, out_dir)
    oto_lines: list[OtoLine] = []
    alias_map: dict[str, dict] = {}
    for e in result.entries:
        oto_lines.append(
            OtoLine(
                wav=e.wav,
                alias=e.alias,
                offset_ms=e.params["offset"],
                consonant_ms=e.params["consonant"],
                cutoff_ms=e.params["cutoff"],
                preutterance_ms=e.params["preutterance"],
                overlap_ms=e.params["overlap"],
            )
        )
        alias_map[e.alias] = {
            "sentence_id": e.sentence_id,
            "unit_id": e.unit_id,
            "kind": e.kind,
            "wav": e.wav,
            "params": e.params,
            "source_label": e.source_label,
        }
    write_oto(out_dir / "oto.ini", oto_lines)
    write_json(out_dir / "alias-map.json", alias_map)
    write_json(out_dir / "build-report.json", result.report_dict(project))
    return out_dir
