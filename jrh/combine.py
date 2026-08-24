"""母版侧自动拼字（jrh combine）：补全缺失 CV 音节。

缺失集合 = 语言包全部音节（410）− 母版已有 label（任一 Unit 即视为覆盖）。
对每个缺失音节：
- presamp 短 ID（韵母 ID / 声母 ID）来自内置 presamp.ini（单一事实来源）；
  任一侧未枚举（如 yo）→ 跳过并报告（与 OpenUtau 侧回退行为一致）
- 辅音源 = 同声母 ID 的启用 Unit（辅音区非空），元音源 = 同韵母 ID 的启用 Unit
  （元音区非空）；同 label 组内按有效组序 rank0（= 原版组序第一名）为代表，
  跨 label 统计选择：辅音源取时长最接近代表组中位数，元音源取时长最长
  （并列取坐标小者，确定性）
- 源组完全缺失时按模糊近似组回退（sh~s、zh~z、ch~c、l~n~r、f~h；前鼻/后鼻
  an~ang、en~eng~ong、in~ing），报告逐条标注 fuzzy
- --config 可覆盖任意音节的源（坐标）或跳过
- 合成 = jrh/audio/combine.combine_cv（RMS 匹配 + 余弦 S-curve crossfade）；
  timing = offset 0 / consonant=辅音源时长 / cutoff=−总时长 / preutterance=辅音源时长
  / overlap=辅音源时长×0.5
- 产物：每音节一个 Asset（assets/C{音节}.wav）+ 独立 Sentence + 单 Unit
  （拼字音节互不连续，独立成句符合 JRH 层级；冻结项目拒绝执行）
"""

from __future__ import annotations

import hashlib
import statistics
from pathlib import Path
from typing import Any

from .core.analysis import (
    _ANOMALY_Z_THRESHOLD,
    _robust_z,
    _stats_for,
    rms_dbfs_to_float,
    unit_duration_ms,
)
from .core.errors import FrozenError, InvalidInputError
from .core.ids import parse_coordinate
from .core.model import Asset, Timing, Unit
from .core.project import JRHProject
from .core.util import read_json_strict, write_json
from .languages.pinyin import PACK_NAME, all_units
from .languages.presamp import consonant_id_of, vowel_id_of

_FUZZY_CONSONANT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("sh", "s"),
    ("zh", "z"),
    ("ch", "c"),
    ("l", "n", "r"),
    ("f", "h"),
)
_FUZZY_VOWEL_GROUPS: tuple[tuple[str, ...], ...] = (
    ("an", "ang"),
    ("en", "eng", "ong"),
    ("in", "ing"),
)

_OVERLAP_RATIO = 0.5


def _fuzzy_alts(groups: tuple[tuple[str, ...], ...]) -> dict[str, tuple[str, ...]]:
    alts: dict[str, tuple[str, ...]] = {}
    for group in groups:
        for i, member in enumerate(group):
            alts[member] = tuple(group[:i] + group[i + 1 :])
    return alts


_FUZZY_CONS_ALTS = _fuzzy_alts(_FUZZY_CONSONANT_GROUPS)
_FUZZY_VOWEL_ALTS = _fuzzy_alts(_FUZZY_VOWEL_GROUPS)


def _auto_score(project: JRHProject, unit: Unit, summary) -> tuple:
    """复刻 analysis.auto_suggest_order 的排序元组（min 取第一项 = 组序 rank0）。"""
    sent = project.get_sentence(unit.sentence_id)
    dur = unit_duration_ms(unit, sent.sample_rate)
    dur_stats = _stats_for(summary, sent.asset_id, "duration_ms")
    rms_raw = rms_dbfs_to_float(unit.analysis.get("rms_dbfs"))
    rms_stats = _stats_for(summary, sent.asset_id, "rms_dbfs")
    z_dur = _robust_z(dur, dur_stats)
    if rms_raw is not None:
        z_rms = _robust_z(rms_raw, rms_stats)
        has_rms = 0
    else:
        z_rms = 0.0
        has_rms = 1
    anomalous = abs(z_dur) > _ANOMALY_Z_THRESHOLD or (
        rms_raw is not None and abs(z_rms) > _ANOMALY_Z_THRESHOLD
    )
    return (
        (1 if anomalous else 0),
        abs(z_dur),
        has_rms,
        abs(z_rms),
        unit.sentence_id,
        unit.unit_id,
    )


class _CombineIndex:
    """单次构建的索引与统计缓存（避免每音节全量扫描/重复 build_summary）。"""

    def __init__(self, project: JRHProject):
        self.project = project
        self.label_units: dict[str, list[Unit]] = {}
        for u in project.units_sorted():
            if u.enabled:
                self.label_units.setdefault(u.label, []).append(u)
        self.by_cid: dict[str, set[str]] = {}
        self.by_vid: dict[str, set[str]] = {}
        for label in self.label_units:
            cid = consonant_id_of(label)
            if cid is not None:
                self.by_cid.setdefault(cid, set()).add(label)
            vid = vowel_id_of(label)
            if vid is not None:
                self.by_vid.setdefault(vid, set()).add(label)
        self.summary = project.analysis_summary_effective()

    def candidates(self, labels: set[str], need_consonant: bool) -> dict[str, set[str]]:
        """候选按 label 分组：{label: {坐标}}。need_consonant=True 要求辅音区非空。"""
        out: dict[str, set[str]] = {}
        for label in labels:
            coords: set[str] = set()
            for u in self.label_units[label]:
                if need_consonant:
                    if u.timing.consonant <= 0:
                        continue
                elif u.timing.window_duration() - u.timing.consonant <= 0:
                    continue
                coords.add(u.coordinate())
            if coords:
                out[label] = coords
        return out

    def rank0_in(self, label: str, allowed: set[str]) -> Unit | None:
        """组内有效顺序 rank0（= 原版组序第一名；auto 时取 auto_suggest_order 第一项）。"""
        if self.project.candidate_groups.mode(label) == "manual":
            for c in self.project.candidate_groups.ordered_unit_ids(label):
                if c in allowed:
                    s, u = parse_coordinate(c)
                    return self.project.get_unit(s, u)
        cand_units = [u for u in self.label_units.get(label, []) if u.coordinate() in allowed]
        if not cand_units:
            return None
        if len(cand_units) == 1:
            return cand_units[0]
        return min(cand_units, key=lambda u: _auto_score(self.project, u, self.summary))


def _resolve_candidates(
    index: _CombineIndex,
    id_map: dict[str, set[str]],
    target_id: str,
    fuzzy_alts: dict[str, tuple[str, ...]],
    need_consonant: bool,
) -> tuple[dict[str, set[str]], bool]:
    """(候选, 是否用了模糊回退)。"""
    cands = index.candidates(id_map.get(target_id, set()), need_consonant)
    if cands:
        return cands, False
    for alt in fuzzy_alts.get(target_id, ()):
        alt_cands = index.candidates(id_map.get(alt, set()), need_consonant)
        if alt_cands:
            return alt_cands, True
    return {}, False


def _rank0_reps(index: _CombineIndex, candidates: dict[str, set[str]]) -> list[Unit]:
    """每个 label 取有效组序 rank0 为代表（候选必为启用单元，rank0 恒命中）。"""
    reps: list[Unit] = []
    for label in sorted(candidates):
        coords = candidates[label]
        unit = index.rank0_in(label, coords)
        if unit is None:  # 防御路径（不可达：候选均来自 label_units）
            s, u = parse_coordinate(min(coords))
            unit = index.project.get_unit(s, u)
        reps.append(unit)
    return reps


def _duration_ms(project: JRHProject, unit: Unit) -> float:
    sr = project.get_sentence(unit.sentence_id).sample_rate
    return unit.timing.window_duration() * 1000.0 / sr


def _pick_consonant(project: JRHProject, reps: list[Unit]) -> Unit:
    durs = [_duration_ms(project, u) for u in reps]
    med = statistics.median(durs)
    return min(reps, key=lambda u: (abs(_duration_ms(project, u) - med), u.coordinate()))


def _pick_vowel(project: JRHProject, reps: list[Unit]) -> Unit:
    return min(reps, key=lambda u: (-_duration_ms(project, u), u.coordinate()))


def _parse_config(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = read_json_strict(Path(path), "combine 配置")
    if not isinstance(data, dict):
        raise InvalidInputError("combine 配置必须是对象")
    sources = data.get("sources")
    if sources is not None and not isinstance(sources, dict):
        raise InvalidInputError("combine 配置 sources 必须是对象")
    skip = data.get("skip")
    if skip is not None and not isinstance(skip, list):
        raise InvalidInputError("combine 配置 skip 必须是数组")
    if skip is not None:
        for item in skip:
            if not isinstance(item, str):
                raise InvalidInputError("combine 配置 skip 条目必须是字符串")
    return data


def combine_phonemes(
    project: JRHProject,
    config_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    """母版侧自动拼字。返回确定性报告 dict（非 dry_run 时写 import 类似报告 + 落盘母版）。"""
    if project.frozen:
        raise FrozenError("项目已冻结，禁止拼字（冻结后编号只增不改）")
    if project.pack.name != PACK_NAME:
        raise InvalidInputError(
            f"自动拼字目前仅支持 {PACK_NAME}（当前 {project.pack.name}；日语拼字扩展为 TODO）"
        )
    config = _parse_config(config_path)
    cfg_sources: dict[str, dict[str, str]] = config.get("sources") or {}
    cfg_skip: set[str] = set(config.get("skip") or [])

    existing = {u.label for u in project.units.values()}
    missing = sorted(s for s in all_units() if s not in existing)
    index = _CombineIndex(project)

    combined: list[dict] = []
    skipped: list[dict] = []

    def resolve_source(kind: str, label: str, need_consonant: bool) -> tuple[Unit, bool]:
        """返回 (源 Unit, 是否模糊)。kind ∈ {consonant, vowel}。"""
        override = cfg_sources.get(label, {}).get(kind)
        if override:
            s, u = parse_coordinate(override)
            unit = project.get_unit(s, u)
            if not unit.enabled:
                raise InvalidInputError(f"配置源未启用: {override}")
            if need_consonant and unit.timing.consonant <= 0:
                raise InvalidInputError(f"配置辅音源无辅音区: {override}")
            return unit, False
        if kind == "consonant":
            target = consonant_id_of(label)
            if target is None:
                raise LookupError(f"无辅音源（{label}）")
            cands, fuzzy = _resolve_candidates(index, index.by_cid, target, _FUZZY_CONS_ALTS, True)
            if not cands:
                raise LookupError(f"无辅音源（{target}）")
            return _pick_consonant(project, _rank0_reps(index, cands)), fuzzy
        target = vowel_id_of(label)
        if target is None:
            raise LookupError(f"无元音源（{label}）")
        cands, fuzzy = _resolve_candidates(index, index.by_vid, target, _FUZZY_VOWEL_ALTS, False)
        if not cands:
            raise LookupError(f"无元音源（{target}）")
        return _pick_vowel(project, _rank0_reps(index, cands)), fuzzy

    for label in missing:
        if label in cfg_skip:
            skipped.append({"label": label, "reason": "config 跳过"})
            continue
        if consonant_id_of(label) is None or vowel_id_of(label) is None:
            skipped.append({"label": label, "reason": "presamp 未枚举"})
            continue
        try:
            c_unit, c_fuzzy = resolve_source("consonant", label, True)
            v_unit, v_fuzzy = resolve_source("vowel", label, False)
        except LookupError as e:
            skipped.append({"label": label, "reason": str(e)})
            continue
        combined.append(
            {
                "label": label,
                "consonant_source": c_unit.coordinate(),
                "vowel_source": v_unit.coordinate(),
                "consonant_fuzzy": c_fuzzy,
                "vowel_fuzzy": v_fuzzy,
            }
        )

    combined.sort(key=lambda d: d["label"])
    skipped.sort(key=lambda d: (d["label"], d["reason"]))

    if dry_run:
        return {
            "dry_run": True,
            "existing_labels": len(existing),
            "missing_total": len(missing),
            "combined": combined,
            "skipped": skipped,
        }

    produced: list[dict] = []
    failed: list[dict] = []
    for plan in combined:
        from .audio.combine import combine_cv

        label = plan["label"]
        c_unit = project.get_unit(*parse_coordinate(plan["consonant_source"]))
        v_unit = project.get_unit(*parse_coordinate(plan["vowel_source"]))
        asset_file = f"assets/C{label}.wav"
        out_path = project.path / asset_file
        info = combine_cv(project, c_unit, v_unit, out_path)
        if info is None:
            failed.append({"label": label, "reason": "合成失败（音频缺失/采样率不一致）"})
            continue
        sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
        proj_asset = Asset(
            id=f"cb-{label}",
            file=asset_file,
            kind="audio",
            sha256=sha,
            sample_rate=info["sample_rate"],
            num_samples=info["total_samples"],
            duration_seconds=info["total_samples"] / info["sample_rate"],
        )
        if proj_asset.id in project.assets:
            raise InvalidInputError(f"asset id 已存在: {proj_asset.id}（请勿重复拼字）")
        project.add_asset(proj_asset)
        sent = project.create_sentence(proj_asset.id, 0, info["total_samples"])
        cons = c_unit.timing.consonant
        timing = Timing(
            offset=0.0,
            consonant=cons,
            cutoff=-float(info["total_samples"]),
            preutterance=cons,
            overlap=cons * _OVERLAP_RATIO,
        )
        unit = project.create_unit(sent.sentence_id, label, timing)
        produced.append(
            {
                "label": label,
                "unit": unit.coordinate(),
                "consonant_source": plan["consonant_source"],
                "vowel_source": plan["vowel_source"],
                "consonant_fuzzy": plan["consonant_fuzzy"],
                "vowel_fuzzy": plan["vowel_fuzzy"],
                "timing": timing.to_ms(info["sample_rate"]),
            }
        )

    project.save()
    report = {
        "dry_run": False,
        "existing_labels": len(existing),
        "missing_total": len(missing),
        "combined": produced,
        "skipped": skipped + sorted(failed, key=lambda d: d["label"]),
    }
    write_json(project.path / "combine-report.json", report)
    return report
