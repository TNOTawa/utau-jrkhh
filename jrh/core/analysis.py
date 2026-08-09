"""时长/RMS 统计与自动建议排序（机器只做机械辅助，人工是最终权威）。

- duration_ms：由 timing 纯计算（|cutoff| * 1000 / sr），无需音频。
- rms_dbfs：主体区域 RMS（需音频；由 CLI 通过 audio 模块注入）。
- 统计：median + MAD 为主（稳健），mean/variance 保留参考。
- 自动建议排序：明显异常项靠后 → 与中位数距离 → 永久编号。
"""

from __future__ import annotations

import statistics
from typing import Any

from .errors import InvalidInputError
from .model import AnalysisSummary, Unit
from .project import JRHProject

# robust_z 异常阈值；素材局部样本不足时退回全局统计
_ANOMALY_Z_THRESHOLD = 2.5
_MIN_ASSET_SAMPLES = 10


def unit_duration_ms(unit: Unit, sample_rate: int) -> float:
    return unit.timing.window_duration() * 1000.0 / sample_rate


def rms_dbfs_to_float(value: Any) -> float | None:
    """analysis.rms_dbfs 的取值检查：None 表示未分析。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInputError(f"rms_dbfs 非法: {value!r}")
    return float(value)


def compute_stats(values: list[float]) -> dict[str, Any]:
    n = len(values)
    out: dict[str, Any] = {"count": n}
    if n == 0:
        return out
    med = statistics.median(values)
    out["median"] = med
    out["mean"] = statistics.mean(values)
    out["variance"] = statistics.variance(values) if n > 1 else 0.0
    mad = statistics.median([abs(v - med) for v in values])
    out["mad"] = mad
    return out


def build_summary(project: JRHProject) -> AnalysisSummary:
    """按全部启用单元计算全局 + 素材局部统计。"""
    global_dur: list[float] = []
    global_rms: list[float] = []
    per_asset: dict[str, dict[str, list[float]]] = {}
    for sent in project.sentences_sorted():
        per_asset.setdefault(sent.asset_id, {"duration_ms": [], "rms_dbfs": []})
    for u in project.units_sorted():
        if not u.enabled:
            continue
        unit_sent = project.sentences.get(u.sentence_id)
        if unit_sent is None:
            continue  # 句子引用缺失时跳过（validate 会单独报告）
        global_dur.append(unit_duration_ms(u, unit_sent.sample_rate))
        per_asset[unit_sent.asset_id]["duration_ms"].append(
            unit_duration_ms(u, unit_sent.sample_rate)
        )
        rms = rms_dbfs_to_float(u.analysis.get("rms_dbfs"))
        if rms is not None:
            global_rms.append(rms)
            per_asset[sent.asset_id]["rms_dbfs"].append(rms)
    return AnalysisSummary(
        revision=0,
        global_stats={
            "duration_ms": compute_stats(global_dur),
            "rms_dbfs": compute_stats(global_rms),
        },
        per_asset_stats={
            aid: {
                "duration_ms": compute_stats(stats["duration_ms"]),
                "rms_dbfs": compute_stats(stats["rms_dbfs"]),
            }
            for aid, stats in sorted(per_asset.items())
        },
    )


def _stats_for(summary: AnalysisSummary, asset_id: str, metric: str) -> dict[str, Any]:
    """素材局部统计优先；样本不足时退回全局。"""
    pa = summary.per_asset_stats.get(asset_id, {}).get(metric, {})
    if isinstance(pa, dict) and pa.get("count", 0) >= _MIN_ASSET_SAMPLES:
        return pa
    g = summary.global_stats.get(metric, {})
    return g if isinstance(g, dict) else {}


def _robust_z(value: float, stats: dict[str, Any]) -> float:
    """robust_z = 0.6745 × (x − median) / MAD；MAD=0 时用确定性替代值。"""
    median = stats.get("median")
    mad = stats.get("mad")
    if median is None:
        return 0.0
    if mad is None or mad == 0:
        return 0.0 if value == median else 10.0
    return 0.6745 * (value - median) / mad


def auto_suggest_order(project: JRHProject, label: str) -> list[str]:
    """候选分组自动建议顺序（只含启用单元；异常靠后 → 距离 → 编号）。"""
    units = [u for u in project.units_by_label(label) if u.enabled]
    units.sort(key=lambda u: (u.sentence_id, u.unit_id))
    if len(units) <= 1:
        return [u.coordinate() for u in units]
    summary = project.analysis_summary_effective()
    scored: list[tuple] = []
    for u in units:
        sent = project.get_sentence(u.sentence_id)
        dur = unit_duration_ms(u, sent.sample_rate)
        dur_stats = _stats_for(summary, sent.asset_id, "duration_ms")
        rms_raw = rms_dbfs_to_float(u.analysis.get("rms_dbfs"))
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
        scored.append(
            (
                (1 if anomalous else 0),
                abs(z_dur),
                has_rms,
                abs(z_rms),
                u.sentence_id,
                u.unit_id,
                u.coordinate(),
            )
        )
    scored.sort()
    return [c[-1] for c in scored]


def effective_group_order(project: JRHProject, label: str) -> list[str]:
    """分组有效顺序：manual 模式 = 已列条目（过滤不存在/禁用）+ 未覆盖项按自动顺序；auto = 自动建议。"""
    enabled = {u.coordinate() for u in project.units_by_label(label) if u.enabled}
    auto = auto_suggest_order(project, label)
    if project.candidate_groups.mode(label) != "manual":
        return [c for c in auto if c in enabled]
    listed = [c for c in project.candidate_groups.ordered_unit_ids(label) if c in enabled]
    listed_set = set(listed)
    rest = [c for c in auto if c in enabled and c not in listed_set]
    return listed + rest
