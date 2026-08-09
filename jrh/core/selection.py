"""候选选择引擎（与 OpenUtau 解耦的 Core 服务）。

回退层级（JRH_SPEC §6.1）：
L1 continuous → L2 full → L3 split($T+$B) → L4 body → L5 substitute → L6 missing。
同层排序（§6.2）：原素材连续性 > 当前字人工排序 > 统计辅助 > 永久编号。
禁用候选永不选中；人工排序不被重分析覆盖；同一输入永远同一结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..languages.base import LanguagePack
from . import analysis as analysis_mod
from .compile_engine import (
    CompileConfig,
    _display_labels,
    _five_part_alias,
)
from .errors import InvalidInputError
from .model import Unit
from .project import JRHProject

LEVELS = ("continuous", "full", "split", "body", "substitute", "missing")
_DEGRADED_LEVELS = frozenset({"split", "body", "substitute"})


@dataclass
class PhonemeAlias:
    alias: str
    position_ms: float
    kind: str  # "full" | "transition" | "body"

    def to_dict(self) -> dict:
        return {"phoneme": self.alias, "position_ms": self.position_ms, "kind": self.kind}


@dataclass
class SelectionResult:
    index: int
    label: str
    level: str
    unit_coord: str | None
    phonemes: list[PhonemeAlias] = field(default_factory=list)
    explanation: dict[str, object] = field(default_factory=dict)

    @property
    def degraded(self) -> bool:
        return self.level in _DEGRADED_LEVELS

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "label": self.label,
            "level": self.level,
            "unit": self.unit_coord,
            "degraded": self.degraded,
            "phonemes": [p.to_dict() for p in self.phonemes],
            "explanation": self.explanation,
        }


def _gap_ms(project: JRHProject, a: Unit, b: Unit) -> float:
    """a 窗口结束到 b 窗口开始的间隔（毫秒）。"""
    sent = project.get_sentence(a.sentence_id)
    return (b.timing.offset - a.timing.window_end()) * 1000.0 / sent.sample_rate


def _leading_vowel(project: JRHProject, u: Unit) -> str | None:
    """u 的实际前元音：句内前一单元的韵母；句首为 None。"""
    units = project.units_in_sentence(u.sentence_id)
    pos = {x.unit_id: x for x in units}
    ids = sorted(pos)
    idx = ids.index(u.unit_id)
    if idx == 0:
        return None
    return project.pack.final_vowel(pos[ids[idx - 1]].label)


def _order_rank(project: JRHProject, u: Unit) -> int:
    """候选在其自身 label 分组有效顺序中的位置（确定性）。"""
    order = analysis_mod.effective_group_order(project, u.label)
    try:
        return order.index(u.coordinate())
    except ValueError:
        return len(order)  # 理论上不会发生（有效顺序包含全部启用单元）


def _candidates(project: JRHProject, label: str) -> list[Unit]:
    return [u for u in project.units_by_label(label) if u.enabled]


def _sort_by_tiebreak(
    project: JRHProject,
    units: list[Unit],
    prev_unit: Unit | None,
) -> list[Unit]:
    scored = []
    for u in units:
        bonus = 0 if (prev_unit is not None and u.sentence_id == prev_unit.sentence_id) else 1
        scored.append((bonus, _order_rank(project, u), u.sentence_id, u.unit_id, u))
    scored.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return [t[4] for t in scored]


def select_sequence(
    project: JRHProject,
    targets: list[str],
    config: CompileConfig | None = None,
) -> list[SelectionResult]:
    """对目标单位序列执行确定性选择。

    targets 为录音单位（label）序列；句首/句尾边界由序列位置决定。
    """
    config = config or CompileConfig()
    if not targets:
        return []
    results: list[SelectionResult] = []
    for i, label in enumerate(targets):
        if not label:
            raise InvalidInputError(f"目标序列第 {i} 项为空")
        prev_label = targets[i - 1] if i > 0 else None
        prev_result = results[i - 1] if i > 0 else None
        prev_unit = None
        if prev_result is not None and prev_result.level != "missing" and prev_result.unit_coord:
            s, u = prev_result.unit_coord.split(":")
            prev_unit = project.get_unit(int(s), int(u))
        results.append(_select_one(project, i, label, prev_label, prev_unit, config))
    return results


def _select_one(
    project: JRHProject,
    index: int,
    label: str,
    prev_label: str | None,
    prev_unit: Unit | None,
    config: CompileConfig,
) -> SelectionResult:
    pack: LanguagePack = project.pack
    target_leading = pack.final_vowel(prev_label) if prev_label is not None else None
    target_initial = pack.initial_consonant(label)
    all_label_units = _candidates(project, label)

    counts: dict[str, int] = dict.fromkeys(LEVELS, 0)

    # L1 原素材连续
    l1: list[Unit] = []
    if prev_unit is not None:
        nxt = project.next_unit_in_sentence(prev_unit.sentence_id, prev_unit.unit_id)
        if nxt is not None and nxt.enabled and nxt.label == label:
            gap = _gap_ms(project, prev_unit, nxt)
            if gap <= config.continuity_max_gap_ms:
                l1 = [nxt]
    counts["continuous"] = len(l1)
    if l1 and prev_unit is not None:
        u = l1[0]
        return _make_result(
            project,
            index,
            label,
            "continuous",
            u,
            config,
            counts,
            prev_unit,
            reasons=[
                f"命中 continuous：与上一选中 {prev_unit.coordinate()} 同句连续"
                f"（时间间隔 {_gap_ms(project, prev_unit, u):.1f} ms）"
            ],
        )

    # L2 完整原音（前元音 + 当前字）
    l2 = [u for u in all_label_units if _leading_vowel(project, u) == target_leading]
    counts["full"] = len(l2)
    if l2:
        chosen = _sort_by_tiebreak(project, l2, prev_unit)[0]
        reason = (
            f"命中 full：前元音 {target_leading!r} 与当前字 {label} 的完整原音"
            if target_leading is not None
            else "命中 full：句首型完整原音（无前元音）"
        )
        return _make_result(
            project, index, label, "full", chosen, config, counts, prev_unit, reasons=[reason]
        )

    # L3 过渡片段 + 当前字主体
    t_cands = [
        u
        for u in project.units_sorted()
        if u.enabled
        and u.timing.consonant > 0
        and pack.initial_consonant(u.label) == target_initial
        and _leading_vowel(project, u) == target_leading
    ]
    b_cands = all_label_units
    counts["split"] = min(len(t_cands), len(b_cands))
    if t_cands and b_cands:
        t_best = _sort_by_tiebreak(project, t_cands, prev_unit)[0]
        b_best = _sort_by_tiebreak(project, b_cands, prev_unit)[0]
        return _make_result(
            project,
            index,
            label,
            "split",
            b_best,
            config,
            counts,
            prev_unit,
            transition_unit=t_best,
            reasons=[
                f"命中 split：无 {target_leading!r}→{label} 完整原音，"
                f"改用过渡 {t_best.coordinate()}($T) + 主体 {b_best.coordinate()}($B)"
            ],
        )

    # L4 当前字主体
    counts["body"] = len(b_cands)
    if b_cands:
        chosen = _sort_by_tiebreak(project, b_cands, prev_unit)[0]
        return _make_result(
            project,
            index,
            label,
            "body",
            chosen,
            config,
            counts,
            prev_unit,
            reasons=["命中 body：退化为当前字主体（CV 级）"],
        )

    # L5 语言包近似替代
    for alt in pack.substitutes(label):
        sub_units = _candidates(project, alt)
        if sub_units:
            counts["substitute"] = len(sub_units)
            chosen = _sort_by_tiebreak(project, sub_units, prev_unit)[0]
            return _make_result(
                project,
                index,
                label,
                "substitute",
                chosen,
                config,
                counts,
                prev_unit,
                substituted=alt,
                reasons=[f"命中 substitute：无 {label}，使用语言包替代 {alt}"],
            )

    # L6 缺音
    return _make_result(
        project,
        index,
        label,
        "missing",
        None,
        config,
        counts,
        prev_unit,
        reasons=[f"缺音：音源中不存在 {label}（替代候选也为空）"],
    )


def _make_result(
    project: JRHProject,
    index: int,
    label: str,
    level: str,
    unit: Unit | None,
    config: CompileConfig,
    counts: dict[str, int],
    prev_unit: Unit | None,
    reasons: list[str],
    transition_unit: Unit | None = None,
    substituted: str | None = None,
) -> SelectionResult:
    phonemes: list[PhonemeAlias] = []
    sources: list[str] = []
    if unit is not None:
        prev, cur, nxt = _display_labels(project, unit.sentence_id, unit.unit_id)
        full_alias = _five_part_alias(
            project, unit.unit_id, unit.sentence_id, prev, cur, nxt, config
        )
        if level in ("continuous", "full"):
            phonemes.append(PhonemeAlias(full_alias, 0.0, "full"))
        elif level == "split":
            assert transition_unit is not None
            sent = project.get_sentence(transition_unit.sentence_id)
            t_ms = transition_unit.timing.consonant * 1000.0 / sent.sample_rate
            t_prev, t_cur, t_nxt = _display_labels(
                project, transition_unit.sentence_id, transition_unit.unit_id
            )
            t_full = _five_part_alias(
                project,
                transition_unit.unit_id,
                transition_unit.sentence_id,
                t_prev,
                t_cur,
                t_nxt,
                config,
            )
            phonemes.append(PhonemeAlias(t_full + config.suffix_transition, -t_ms, "transition"))
            phonemes.append(PhonemeAlias(full_alias + config.suffix_body, 0.0, "body"))
            sources.append(transition_unit.coordinate())
        else:  # body / substitute
            phonemes.append(PhonemeAlias(full_alias + config.suffix_body, 0.0, "body"))
        sources.append(unit.coordinate())
    rejected = _rejected_explanation(project, unit, prev_unit)
    explanation: dict[str, object] = {
        "level": level,
        "degraded": level in _DEGRADED_LEVELS,
        "candidates": counts,
        "unit": unit.coordinate() if unit else None,
        "substituted_label": substituted,
        "reasons": reasons,
        "rejected": rejected,
        "sources": sorted(set(sources)),
    }
    return SelectionResult(
        index=index,
        label=label,
        level=level,
        unit_coord=unit.coordinate() if unit else None,
        phonemes=phonemes,
        explanation=explanation,
    )


def _rejected_explanation(
    project: JRHProject,
    chosen: Unit | None,
    prev_unit: Unit | None,
) -> list[dict[str, str]]:
    """落选候选说明（确定性）：同 label 启用候选按有效顺序的前若干名。"""
    if chosen is None:
        return []
    order = analysis_mod.effective_group_order(project, chosen.label)
    try:
        chosen_rank = order.index(chosen.coordinate())
    except ValueError:
        return []
    out: list[dict[str, str]] = []
    for rank, coord in enumerate(order):
        if rank == chosen_rank:
            continue
        if rank > chosen_rank and len(out) >= 5:
            break
        out.append(
            {
                "unit": coord,
                "reason": f"有效顺序第 {rank + 1} 位（tie-break: 排序落后于选中项 {chosen.coordinate()}）",
            }
        )
        if len(out) >= 5:
            break
    return out
