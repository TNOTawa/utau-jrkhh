"""JRH 数据模型（Asset / Sentence / Unit / Timing / 候选分组 / 分析汇总）。

本模块是纯数据 + 确定性转换，无 IO、无外部依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import InvalidInputError
from .ids import format_coordinate

# ── Asset ─────────────────────────────────────────────────────────


@dataclass
class Asset:
    id: str
    file: str
    kind: str = "audio"
    sha256: str = ""
    sample_rate: int = 0
    num_samples: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "kind": self.kind,
            "sha256": self.sha256,
            "sample_rate": self.sample_rate,
            "num_samples": self.num_samples,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict, what: str = "asset") -> Asset:
        a = cls(
            id=_req_str(d, what, "id"),
            file=_req_str(d, what, "file"),
            kind=_req_str(d, what, "kind"),
            sha256=_req_str(d, what, "sha256"),
            sample_rate=_req_int(d, what, "sample_rate"),
            num_samples=_req_int(d, what, "num_samples"),
            duration_seconds=_req_float(d, what, "duration_seconds"),
        )
        return a


# ── Sentence ──────────────────────────────────────────────────────


@dataclass
class Sentence:
    sentence_id: int
    asset_id: str
    sample_rate: int
    start_sample: int
    end_sample: int
    segmentation: dict[str, Any] = field(default_factory=dict)
    max_unit_id_ever: int = 0

    def duration_seconds(self) -> float:
        return (self.end_sample - self.start_sample) / self.sample_rate

    def duration_samples(self) -> int:
        return self.end_sample - self.start_sample

    def to_dict(self) -> dict:
        seg = dict(self.segmentation)
        seg.setdefault("provider", "manual")
        seg.setdefault("confidence", None)
        seg.setdefault("original_start_sample", self.start_sample)
        seg.setdefault("original_end_sample", self.end_sample)
        seg.setdefault("manually_adjusted", False)
        return {
            "sentence_id": self.sentence_id,
            "asset_id": self.asset_id,
            "sample_rate": self.sample_rate,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "max_unit_id_ever": self.max_unit_id_ever,
            "segmentation": seg,
        }

    @classmethod
    def from_dict(cls, d: dict, what: str = "sentence") -> Sentence:
        sid = _req_int(d, what, "sentence_id")
        if sid < 1:
            raise InvalidInputError(f"{what} 的 sentence_id 必须 ≥ 1: {sid}")
        seg = d.get("segmentation")
        if seg is not None and not isinstance(seg, dict):
            raise InvalidInputError(f"{what} {sid} 的 segmentation 必须是对象")
        mue = d.get("max_unit_id_ever", 0)
        if isinstance(mue, bool) or not isinstance(mue, int) or mue < 0:
            raise InvalidInputError(f"{what} {sid} 的 max_unit_id_ever 非法: {mue!r}")
        return cls(
            sentence_id=sid,
            asset_id=_req_str(d, what, "asset_id"),
            sample_rate=_req_int(d, what, "sample_rate"),
            start_sample=_req_int(d, what, "start_sample"),
            end_sample=_req_int(d, what, "end_sample"),
            segmentation=dict(seg) if seg else {},
            max_unit_id_ever=mue,
        )


# ── Timing（唯一一套原音设定，VCV/CVVC 式五参数，单位：采样点）──


@dataclass
class Timing:
    offset: float
    consonant: float
    cutoff: float
    preutterance: float
    overlap: float

    def window_end(self) -> float:
        """窗口终点 = offset + |cutoff|（JinrikiHelper cutoff 约定）。"""
        return self.offset + abs(self.cutoff)

    def window_duration(self) -> float:
        return abs(self.cutoff)

    def body_start(self) -> float:
        """当前字主体起点 = offset + preutterance。"""
        return self.offset + self.preutterance

    def to_dict(self) -> dict:
        return {
            "offset": self.offset,
            "consonant": self.consonant,
            "cutoff": self.cutoff,
            "preutterance": self.preutterance,
            "overlap": self.overlap,
        }

    @classmethod
    def from_dict(cls, d: dict, what: str = "timing") -> Timing:
        return cls(
            offset=_req_finite_float(d, what, "offset"),
            consonant=_req_finite_float(d, what, "consonant"),
            cutoff=_req_finite_float(d, what, "cutoff"),
            preutterance=_req_finite_float(d, what, "preutterance"),
            overlap=_req_finite_float(d, what, "overlap"),
        )

    def to_ms(self, sample_rate: int) -> dict[str, float]:
        """采样点 → 毫秒（oto.ini 表示）。确定性公式，无舍入累积。"""
        return {
            "offset": _samples_to_ms(self.offset, sample_rate),
            "consonant": _samples_to_ms(self.consonant, sample_rate),
            "cutoff": _samples_to_ms(self.cutoff, sample_rate),
            "preutterance": _samples_to_ms(self.preutterance, sample_rate),
            "overlap": _samples_to_ms(self.overlap, sample_rate),
        }

    def transition_timing(self) -> Timing | None:
        """$T 过渡片段：[offset, offset+consonant]。consonant<=0 时为 None（不生成）。"""
        if self.consonant <= 0:
            return None
        return Timing(
            offset=self.offset,
            consonant=self.consonant,
            cutoff=-self.consonant,
            preutterance=0.0,
            overlap=min(self.overlap, self.consonant),
        )

    def body_timing(self) -> Timing:
        """$B 当前字主体：[offset+preutterance, offset+|cutoff|]。"""
        return Timing(
            offset=self.offset + self.preutterance,
            consonant=max(self.consonant - self.preutterance, 0.0),
            cutoff=self.cutoff + self.preutterance,
            preutterance=0.0,
            overlap=0.0,
        )

    def vc_timing(
        self, next_timing: Timing, offset_ratio: float, overlap_ratio: float
    ) -> Timing | None:
        """CVVC 的 VC 过渡片段：[当前元音后半, 下一单元元音起点)。

        - 区域 = [当前窗口末端 - 元音时长×offset_ratio, 下一单元 offset+consonant)
          （元音尾 + 下一辅音整段，不延伸到下一单元元音内部——修正参考实现的宽窗口）
        - consonant = 下一元音起点相对本 offset 的位置（= 区域全长）
        - preutterance = 元音/辅音边界相对 offset 的位置
        - 下一单元辅音不存在（consonant<=0）、元音区为空、
          或区域非正/不足以容纳 preutterance（标注重叠）时返回 None（不生成）。
        """
        if not (0.0 <= offset_ratio <= 1.0 and 0.0 <= overlap_ratio <= 1.0):
            raise InvalidInputError(
                "VC 比例参数必须在 [0,1]："
                f"offset_ratio={offset_ratio}, overlap_ratio={overlap_ratio}"
            )
        vowel_dur = self.window_duration() - self.consonant
        if vowel_dur <= 0:
            return None  # 元音区为空（如 consonant == |cutoff| 的异常标注）
        if next_timing.consonant <= 0:
            return None  # 下一单元无辅音区，不存在元音→辅音过渡
        pre = vowel_dur * offset_ratio
        offset = self.window_end() - pre
        window = next_timing.offset + next_timing.consonant - offset
        if window <= 0 or pre > window:
            return None  # 区域非正 / 不足（单元窗口重叠等异常标注）
        return Timing(
            offset=offset,
            consonant=window,
            cutoff=-window,
            preutterance=pre,
            overlap=pre * overlap_ratio,
        )

    def constraint_errors(self, what: str = "timing") -> list[str]:
        """有效性约束（JRH_SPEC §4.5）。返回错误描述列表。"""
        errs: list[str] = []
        if self.cutoff >= 0:
            errs.append(f"{what}: cutoff 必须为负值（=-窗口时长），实际 {self.cutoff}")
        dur = abs(self.cutoff)
        if dur <= 0:
            errs.append(f"{what}: 窗口时长必须 > 0（当前 cutoff={self.cutoff}）")
        if self.offset < 0:
            errs.append(f"{what}: offset 不能为负（{self.offset}）")
        if self.consonant < 0:
            errs.append(f"{what}: consonant 不能为负（{self.consonant}）")
        if self.preutterance < 0:
            errs.append(f"{what}: preutterance 不能为负（{self.preutterance}）")
        if self.overlap < 0:
            errs.append(f"{what}: overlap 不能为负（{self.overlap}）")
        if self.overlap > self.preutterance:
            errs.append(
                f"{what}: 需要 overlap ≤ preutterance（{self.overlap} > {self.preutterance}）"
            )
        if self.preutterance > dur:
            errs.append(f"{what}: 需要 preutterance ≤ |cutoff|（{self.preutterance} > {dur}）")
        if self.consonant > dur:
            errs.append(f"{what}: 需要 consonant ≤ |cutoff|（{self.consonant} > {dur}）")
        return errs


def _samples_to_ms(samples: float, sample_rate: int) -> float:
    return round(samples * 1000.0 / sample_rate, 3)


# ── Unit ───────────────────────────────────────────────────────────


@dataclass
class Unit:
    sentence_id: int
    unit_id: int
    label: str
    timing: Timing
    enabled: bool = True
    analysis: dict[str, Any] = field(default_factory=dict)

    def coordinate(self) -> str:
        return format_coordinate(self.sentence_id, self.unit_id)

    def to_dict(self) -> dict:
        return {
            "sentence_id": self.sentence_id,
            "unit_id": self.unit_id,
            "label": self.label,
            "enabled": self.enabled,
            "timing": self.timing.to_dict(),
            "analysis": dict(self.analysis),
        }

    @classmethod
    def from_dict(cls, d: dict, what: str = "unit") -> Unit:
        sid = _req_int(d, what, "sentence_id")
        uid = _req_int(d, what, "unit_id")
        if sid < 1 or uid < 1:
            raise InvalidInputError(f"{what} 的编号必须 ≥ 1: {sid}:{uid}")
        timing = Timing.from_dict(_req_dict(d, what, "timing"), what)
        enabled = d.get("enabled", True)
        if not isinstance(enabled, bool):
            raise InvalidInputError(f"{what} {sid}:{uid} 的 enabled 必须是布尔值")
        analysis = d.get("analysis")
        if analysis is None:
            analysis = {}
        if not isinstance(analysis, dict):
            raise InvalidInputError(f"{what} {sid}:{uid} 的 analysis 必须是对象")
        for k, v in analysis.items():
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                raise InvalidInputError(f"{what} {sid}:{uid} 的 analysis.{k} 类型非法")
            if v is not None and not _isfinite(v):
                raise InvalidInputError(f"{what} {sid}:{uid} 的 analysis.{k} 非有限数值")
        return cls(
            sentence_id=sid,
            unit_id=uid,
            label=_req_str(d, what, "label"),
            timing=timing,
            enabled=enabled,
            analysis=dict(analysis),
        )


# ── 候选分组状态 ─────────────────────────────────────────────────


@dataclass
class CandidateGroups:
    groups: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"groups": {k: dict(v) for k, v in sorted(self.groups.items())}}

    @classmethod
    def from_dict(cls, d: dict) -> CandidateGroups:
        raw = d.get("groups", {})
        if not isinstance(raw, dict):
            raise InvalidInputError("candidate_groups.groups 必须是对象")
        out: dict[str, dict[str, Any]] = {}
        for label, g in raw.items():
            if not isinstance(g, dict):
                raise InvalidInputError(f"候选分组 {label!r} 结构错误")
            mode = g.get("mode", "auto")
            if mode not in ("auto", "manual"):
                raise InvalidInputError(f"候选分组 {label!r} 的 mode 非法: {mode!r}")
            ordered = g.get("ordered_unit_ids", [])
            if not isinstance(ordered, list) or not all(isinstance(x, str) for x in ordered):
                raise InvalidInputError(f"候选分组 {label!r} 的 ordered_unit_ids 必须是字符串数组")
            out[label] = {"mode": mode, "ordered_unit_ids": list(ordered)}
        return cls(out)

    def mode(self, label: str) -> str:
        g = self.groups.get(label)
        return g["mode"] if g else "auto"

    def ordered_unit_ids(self, label: str) -> list[str]:
        g = self.groups.get(label)
        if not g or g["mode"] != "manual":
            return []
        return list(g.get("ordered_unit_ids", []))

    def set_manual(self, label: str, ordered_unit_ids: list[str]) -> None:
        if len(set(ordered_unit_ids)) != len(ordered_unit_ids):
            raise InvalidInputError(f"候选分组 {label!r} 的人工顺序含重复条目")
        self.groups[label] = {"mode": "manual", "ordered_unit_ids": list(ordered_unit_ids)}

    def set_auto(self, label: str) -> None:
        self.groups[label] = {"mode": "auto", "ordered_unit_ids": []}


# ── 分析汇总（可重建缓存） ───────────────────────────────────────


@dataclass
class AnalysisSummary:
    revision: int = 0
    global_stats: dict[str, dict[str, float]] = field(default_factory=dict)
    per_asset_stats: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "revision": self.revision,
            "global": self.global_stats,
            "per_asset": self.per_asset_stats,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AnalysisSummary:
        if not isinstance(d, dict):
            raise InvalidInputError("analysis.json 结构错误")
        g = d.get("global")
        pa = d.get("per_asset")
        if not isinstance(g, dict) or not isinstance(pa, dict):
            raise InvalidInputError("analysis.json 结构错误：global/per_asset 必须是对象")
        rev = d.get("revision", 0)
        if not isinstance(rev, int) or rev < 0:
            raise InvalidInputError("analysis.json revision 非法")
        return cls(revision=rev, global_stats=g, per_asset_stats=pa)


# ── 内部辅助 ──────────────────────────────────────────────────────


def _req_str(d: dict, what: str, key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str):
        raise InvalidInputError(f"{what} 缺少/非法字段 {key!r}: {v!r}")
    return v


def _req_int(d: dict, what: str, key: str) -> int:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise InvalidInputError(f"{what} 缺少/非法字段 {key!r}: {v!r}")
    return v


def _req_float(d: dict, what: str, key: str) -> float:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InvalidInputError(f"{what} 缺少/非法字段 {key!r}: {v!r}")
    return float(v)


def _req_dict(d: dict, what: str, key: str) -> dict:
    v = d.get(key)
    if not isinstance(v, dict):
        raise InvalidInputError(f"{what} 缺少/非法字段 {key!r}")
    return v


def _req_finite_float(d: dict, what: str, key: str) -> float:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not _isfinite(v):
        raise InvalidInputError(f"{what} 缺少/非法字段 {key!r}: {v!r}")
    return float(v)


def _isfinite(v: float) -> bool:
    import math

    return math.isfinite(v)


def unit_key(sentence_id: int, unit_id: int) -> tuple[int, int]:
    return (sentence_id, unit_id)
