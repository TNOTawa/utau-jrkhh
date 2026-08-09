"""JRH validation：schema + 语义 + 别名安全 + 时间范围 + 冻结不变量。

- `open()` 只保证结构可解析；本模块做语义校验。
- 错误（error）⇒ 退出码 3；警告（warning）仅供参考。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..languages import get_pack
from . import analysis as analysis_mod
from .ids import format_coordinate, is_coordinate, parse_coordinate
from .model import unit_key
from .project import SCHEMA_VERSION, JRHProject

# label 允许字符集（JRH_SPEC §5.2）
_LABEL_OK_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@{}#.:_~+<>[]()%"
)
_LABEL_FORBIDDEN = set(" \t\r\n,=;\"'\\/-")


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    code: str
    location: str
    message: str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "location": self.location,
            "message": self.message,
        }


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity: str, code: str, location: str, message: str) -> None:
        self.issues.append(Issue(severity, code, location, message))

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def error_count(self) -> int:
        return len(self.errors())

    def has_errors(self) -> bool:
        return bool(self.errors())

    def to_dict(self) -> dict:
        return {
            "valid": not self.has_errors(),
            "error_count": len(self.errors()),
            "warning_count": len(self.issues) - len(self.errors()),
            "issues": [i.to_dict() for i in self.issues],
        }


def validate_label_charset(label: str) -> str | None:
    """返回违规说明；None 表示合法。"""
    if not label:
        return "label 为空"
    if "$" in label:
        return f"label {label!r} 含保留字符 $（派生别名命名空间）"
    if any(ch in _LABEL_FORBIDDEN for ch in label):
        return f"label {label!r} 含禁止字符（空白 , = ; \" ' \\ / - 等）"
    if any(ord(ch) < 32 for ch in label):
        return f"label {label!r} 含控制字符"
    if not all(ch in _LABEL_OK_CHARS for ch in label):
        return f"label {label!r} 含不在允许字符集内的字符"
    return None


def validate_project(project: JRHProject) -> ValidationResult:
    res = ValidationResult()

    # ── manifest ─────────────────────────────────────────────────
    if project.manifest.get("format") != "JRH":
        res.add("error", "manifest.format", "manifest.json", "format 必须为 JRH")
    if project.manifest.get("schema_version") != SCHEMA_VERSION:
        res.add(
            "error",
            "manifest.schema_version",
            "manifest.json",
            f"不支持的 schema_version {project.manifest.get('schema_version')!r}",
        )
    state = project.manifest.get("state")
    if state not in ("draft", "frozen"):
        res.add("error", "manifest.state", "manifest.json", f"state 非法: {state!r}")
    try:
        get_pack(project.manifest.get("language_pack", ""))
    except Exception as e:  # noqa: BLE001
        res.add("error", "manifest.language_pack", "manifest.json", str(e))

    # ── assets ───────────────────────────────────────────────────
    for aid in sorted(project.assets):
        asset = project.assets[aid]
        if asset.sample_rate <= 0:
            res.add("error", "asset.sample_rate", f"asset:{aid}", "采样率必须 > 0")
        if asset.num_samples <= 0:
            res.add("error", "asset.num_samples", f"asset:{aid}", "样本数必须 > 0")
        if not asset.file:
            res.add("error", "asset.file", f"asset:{aid}", "缺少文件路径")
        else:
            p = project.path / asset.file
            if not p.exists():
                res.add("error", "asset.missing", f"asset:{aid}", f"文件不存在: {p}")
            else:
                sha = _sha256_file(p)
                if asset.sha256 and sha and sha != asset.sha256:
                    res.add(
                        "error",
                        "asset.hash_mismatch",
                        f"asset:{aid}",
                        f"文件哈希不符（记录 {asset.sha256}，实际 {sha}）",
                    )
        if asset.id != aid:
            res.add("error", "asset.id", f"asset:{aid}", "asset id 键不一致")

    # ── sentences ────────────────────────────────────────────────
    for sid in sorted(project.sentences):
        sent = project.sentences[sid]
        sent_asset = project.assets.get(sent.asset_id)
        if sent_asset is None:
            res.add(
                "error",
                "sentence.asset_ref",
                f"sentence:{sid}",
                f"引用的 asset 不存在: {sent.asset_id}",
            )
            continue
        if sent.sample_rate != sent_asset.sample_rate:
            res.add(
                "error",
                "sentence.sample_rate",
                f"sentence:{sid}",
                f"句子采样率 {sent.sample_rate} ≠ asset {sent_asset.sample_rate}（重采样为 FUTURE）",
            )
        if sent.start_sample < 0 or sent.end_sample <= sent.start_sample:
            res.add(
                "error",
                "sentence.range",
                f"sentence:{sid}",
                f"非法范围 [{sent.start_sample}, {sent.end_sample})",
            )
        elif sent.end_sample > sent_asset.num_samples:
            res.add(
                "error",
                "sentence.range",
                f"sentence:{sid}",
                f"范围越界: [{sent.start_sample}, {sent.end_sample}) > asset 长度 {sent_asset.num_samples}",
            )
        if sent.max_unit_id_ever < 0:
            res.add(
                "error",
                "sentence.max_unit_id_ever",
                f"sentence:{sid}",
                "max_unit_id_ever 不能为负",
            )
        unit_ids = [u.unit_id for u in project.units_in_sentence(sid)]
        if len(set(unit_ids)) != len(unit_ids):
            res.add("error", "sentence.duplicate_unit", f"sentence:{sid}", "句内存在重复 unit_id")
        if unit_ids and sent.max_unit_id_ever < max(unit_ids):
            res.add(
                "error",
                "sentence.max_unit_id_ever",
                f"sentence:{sid}",
                f"max_unit_id_ever({sent.max_unit_id_ever}) 小于现有最大编号 {max(unit_ids)}",
            )

    # ── units ────────────────────────────────────────────────────
    for u in project.units_sorted():
        coord = u.coordinate()
        loc = f"unit:{coord}"
        if u.sentence_id not in project.sentences:
            res.add("error", "unit.sentence_ref", loc, "引用的句子不存在")
        label_issue = validate_label_charset(u.label)
        if label_issue:
            res.add("error", "unit.label_charset", loc, label_issue)
        elif not project.pack.validate_unit(u.label):
            res.add(
                "warning",
                "unit.label_unknown",
                loc,
                f"label {u.label!r} 不是语言包 {project.pack.name} 的合法单位",
            )
        for err in u.timing.constraint_errors(f"unit {coord}"):
            res.add("error", "unit.timing", loc, err)
        unit_sent = project.sentences.get(u.sentence_id)
        if unit_sent is not None and u.timing.window_end() > unit_sent.duration_samples() + 1e-6:
            res.add(
                "error",
                "unit.range",
                loc,
                f"窗口超出句子范围（{u.timing.window_end()} > {unit_sent.duration_samples()}）",
            )
        for metric in ("duration_ms", "rms_dbfs"):
            if metric in u.analysis:
                v = u.analysis[metric]
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                    res.add("error", "unit.analysis", loc, f"analysis.{metric} 类型非法")

    # ── candidate groups ─────────────────────────────────────────
    valid_coords = set(project.units.keys())
    for label, g in sorted(project.candidate_groups.groups.items()):
        if label not in {u.label for u in project.units.values()}:
            res.add(
                "warning",
                "group.unknown_label",
                f"group:{label}",
                f"分组 {label!r} 没有对应单元",
            )
        mode = g.get("mode")
        if mode not in ("auto", "manual"):
            res.add("error", "group.mode", f"group:{label}", f"mode 非法: {mode!r}")
        ordered = g.get("ordered_unit_ids", [])
        if not isinstance(ordered, list):
            res.add("error", "group.order", f"group:{label}", "ordered_unit_ids 必须是数组")
            continue
        seen_coords = set()
        for c in ordered:
            if not is_coordinate(c):
                res.add("error", "group.order", f"group:{label}", f"非法坐标: {c!r}")
                continue
            if c in seen_coords:
                res.add("error", "group.order", f"group:{label}", f"重复坐标: {c}")
                continue
            seen_coords.add(c)
            gs, gu = parse_coordinate(c)
            if unit_key(gs, gu) not in valid_coords:
                res.add(
                    "error",
                    "group.ref",
                    f"group:{label}",
                    f"人工顺序引用了不存在的单元: {c}",
                )
            else:
                gunit = project.units[unit_key(gs, gu)]
                if gunit.label != label:
                    res.add(
                        "warning",
                        "group.mismatch",
                        f"group:{label}",
                        f"坐标 {c} 的 label 是 {gunit.label!r} 而非 {label!r}",
                    )

    # ── frozen 不变量 ────────────────────────────────────────────
    if project.frozen:
        counters = project._allocator.counters  # noqa: SLF001
        max_sid = max(project.sentences.keys()) if project.sentences else 0
        if counters.max_sentence_id_ever < max_sid:
            res.add(
                "error",
                "frozen.counters",
                "manifest.json",
                "冻结状态计数器与现有句号不一致",
            )
        for sid in project.sentences:
            sent = project.sentences[sid]
            unit_ids = [u.unit_id for u in project.units_in_sentence(sid)]
            if unit_ids and sent.max_unit_id_ever < max(unit_ids):
                res.add(
                    "error",
                    "frozen.counters",
                    f"sentence:{sid}",
                    "冻结状态句内计数器与现有编号不一致",
                )

    # ── analysis 缓存陈旧 ────────────────────────────────────────
    if project.analysis_summary is not None:
        live = analysis_mod.build_summary(project)
        if live.global_stats.get("duration_ms", {}).get(
            "count", 0
        ) != project.analysis_summary.global_stats.get("duration_ms", {}).get("count", 0):
            res.add(
                "warning",
                "analysis.stale",
                "data/analysis.json",
                "分析缓存与当前数据不一致（请重新运行 analyze）",
            )

    # ── 重复坐标（防御） ─────────────────────────────────────────
    coords = [format_coordinate(u.sentence_id, u.unit_id) for u in project.units.values()]
    if len(coords) != len(set(coords)):
        res.add("error", "unit.duplicate_coordinate", "units.json", "存在重复坐标")

    return res


def _sha256_file(path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None
