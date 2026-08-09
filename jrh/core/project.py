"""JRHProject：加载/保存/冻结/CRUD —— 唯一的项目状态修改入口。

不变量（JRH_SPEC §3、§10）：
- 冻结后编号只增不改、不复用；
- 修改文字/发音/边界/分析不改变编号；
- 句内单元编号不复用（每句维护 max_unit_id_ever）。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ..languages import get_pack
from ..languages.base import LanguagePack
from .errors import (
    DataError,
    FrozenError,
    InvalidInputError,
    NotFoundError,
)
from .ids import IdAllocator, IdCounters, format_coordinate
from .model import (
    AnalysisSummary,
    Asset,
    CandidateGroups,
    Sentence,
    Timing,
    Unit,
    unit_key,
)
from .util import read_json_strict, write_json

SCHEMA_VERSION = "0.1.0"
_FORMAT = "JRH"


class JRHProject:
    def __init__(
        self,
        path: Path,
        manifest: dict[str, Any],
        assets: dict[str, Asset],
        sentences: dict[int, Sentence],
        units: dict[tuple, Unit],
        groups: CandidateGroups,
        analysis_summary: AnalysisSummary | None,
        pack: LanguagePack,
        allocator: IdAllocator,
    ):
        self.path = Path(path)
        self.manifest = manifest
        self.assets = assets
        self.sentences = sentences
        self.units = units
        self.candidate_groups = groups
        self.analysis_summary = analysis_summary
        self.pack = pack
        self._allocator = allocator

    # ── 创建 / 打开 ────────────────────────────────────────────────

    @classmethod
    def create(cls, path, language_pack: str = "jrh.zh-pinyin") -> JRHProject:
        pack = get_pack(language_pack)
        p = Path(path)
        manifest: dict[str, Any] = {
            "format": _FORMAT,
            "schema_version": SCHEMA_VERSION,
            "generator": {"name": "utau-jrkhh", "version": "0.1.0"},
            "state": "draft",
            "language_pack": pack.name,
            "id_counters": {"max_sentence_id_ever": 0, "max_unit_id_ever": 0},
            "capabilities": ["source-timeline", "context-units", "candidate-groups"],
        }
        proj = cls(
            path=p,
            manifest=manifest,
            assets={},
            sentences={},
            units={},
            groups=CandidateGroups(),
            analysis_summary=None,
            pack=pack,
            allocator=IdAllocator(IdCounters.from_dict(manifest["id_counters"])),
        )
        proj.save()
        return proj

    @classmethod
    def open(cls, path) -> JRHProject:
        p = Path(path)
        if not (p / "manifest.json").exists():
            raise NotFoundError(f"不是 JRH 项目（缺少 manifest.json）: {p}")
        manifest = read_json_strict(p / "manifest.json", "manifest.json")
        if not isinstance(manifest, dict):
            raise DataError("manifest.json 结构错误：应为对象")
        if manifest.get("format") != _FORMAT:
            raise DataError(f"不是 JRH 项目（format={manifest.get('format')!r}）")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise DataError(
                f"不支持的 JRH schema 版本 {manifest.get('schema_version')!r}"
                f"（当前支持 {SCHEMA_VERSION}；迁移指南为 FUTURE）"
            )
        state = manifest.get("state", "draft")
        if state not in ("draft", "frozen"):
            raise DataError(f"manifest.state 非法: {state!r}")
        counters = IdCounters.from_dict(manifest.get("id_counters", {}))
        # 语言包先行解析：未知语言包在读取数据文件前即失败
        pack = get_pack(manifest.get("language_pack", ""))

        assets: dict[str, Asset] = {}
        assets_raw = read_json_strict(p / "data" / "assets.json", "data/assets.json")
        for a in assets_raw.get("assets", []):
            if not isinstance(a, dict):
                raise DataError("data/assets.json 条目必须是对象")
            asset = Asset.from_dict(a)
            if asset.id in assets:
                raise DataError(f"重复的 asset id: {asset.id}")
            assets[asset.id] = asset

        sentences: dict[int, Sentence] = {}
        sent_raw = read_json_strict(p / "data" / "sentences.json", "data/sentences.json")
        for s in sent_raw.get("sentences", []):
            if not isinstance(s, dict):
                raise DataError("data/sentences.json 条目必须是对象")
            sent = Sentence.from_dict(s)
            if sent.sentence_id in sentences:
                raise DataError(f"重复的 sentence_id: {sent.sentence_id}")
            sentences[sent.sentence_id] = sent

        units: dict[tuple, Unit] = {}
        units_raw = read_json_strict(p / "data" / "units.json", "data/units.json")
        for u in units_raw.get("units", []):
            if not isinstance(u, dict):
                raise DataError("data/units.json 条目必须是对象")
            unit = Unit.from_dict(u)
            key = unit_key(unit.sentence_id, unit.unit_id)
            if key in units:
                raise DataError(f"重复的单元坐标: {unit.coordinate()}")
            units[key] = unit

        groups_path = p / "data" / "candidate_groups.json"
        groups = (
            CandidateGroups.from_dict(read_json_strict(groups_path))
            if groups_path.exists()
            else CandidateGroups()
        )

        summary_path = p / "data" / "analysis.json"
        summary = (
            AnalysisSummary.from_dict(read_json_strict(summary_path))
            if summary_path.exists()
            else None
        )

        proj = cls(
            path=p,
            manifest=manifest,
            assets=assets,
            sentences=sentences,
            units=units,
            groups=groups,
            analysis_summary=summary,
            pack=pack,
            allocator=IdAllocator(counters),
        )
        proj._sync_counters()
        return proj

    # ── 状态 ───────────────────────────────────────────────────────

    @property
    def frozen(self) -> bool:
        return self.manifest.get("state") == "frozen"

    def _check_mutable_identity(self, what: str) -> None:
        """冻结后禁止重排编号的操作。"""
        if self.frozen:
            raise FrozenError(f"项目已冻结，禁止 {what}（冻结后编号只增不改、不复用）")

    def _sync_counters(self) -> None:
        """计数器不得低于现有最大编号（防御手工损坏的数据）。"""
        max_sid = max(self.sentences.keys()) if self.sentences else 0
        if self._allocator.counters.max_sentence_id_ever < max_sid:
            self._allocator.counters.max_sentence_id_ever = max_sid
        max_uid = 0
        for sent in self.sentences.values():
            if sent.max_unit_id_ever < 0:
                raise DataError(f"sentence {sent.sentence_id} max_unit_id_ever 非法")
            if sent.max_unit_id_ever > max_uid:
                max_uid = sent.max_unit_id_ever
        for _s, u in self.units:
            if u > max_uid:
                max_uid = u
        if self._allocator.counters.max_unit_id_ever < max_uid:
            self._allocator.counters.max_unit_id_ever = max_uid

    # ── 保存 ───────────────────────────────────────────────────────

    def save(self) -> None:
        manifest = dict(self.manifest)
        manifest["id_counters"] = self._allocator.counters.to_dict()
        write_json(self.path / "manifest.json", manifest)
        write_json(
            self.path / "data" / "assets.json",
            {"assets": [self.assets[i].to_dict() for i in sorted(self.assets)]},
        )
        write_json(
            self.path / "data" / "sentences.json",
            {"sentences": [self.sentences[s].to_dict() for s in sorted(self.sentences)]},
        )
        write_json(
            self.path / "data" / "units.json",
            {
                "units": [
                    self.units[k].to_dict() for k in sorted(self.units, key=lambda k: (k[0], k[1]))
                ]
            },
        )
        write_json(self.path / "data" / "candidate_groups.json", self.candidate_groups.to_dict())
        if self.analysis_summary is not None:
            write_json(self.path / "data" / "analysis.json", self.analysis_summary.to_dict())

    # ── 访问器 ─────────────────────────────────────────────────────

    def get_asset(self, asset_id: str) -> Asset:
        a = self.assets.get(asset_id)
        if a is None:
            raise NotFoundError(f"asset 不存在: {asset_id}")
        return a

    def get_sentence(self, sentence_id: int) -> Sentence:
        s = self.sentences.get(sentence_id)
        if s is None:
            raise NotFoundError(f"sentence 不存在: {sentence_id}")
        return s

    def get_unit(self, sentence_id: int, unit_id: int) -> Unit:
        u = self.units.get(unit_key(sentence_id, unit_id))
        if u is None:
            raise NotFoundError(f"unit 不存在: {format_coordinate(sentence_id, unit_id)}")
        return u

    def sentences_sorted(self) -> list[Sentence]:
        return [self.sentences[s] for s in sorted(self.sentences)]

    def units_sorted(self) -> list[Unit]:
        return [self.units[k] for k in sorted(self.units, key=lambda k: (k[0], k[1]))]

    def units_in_sentence(self, sentence_id: int) -> list[Unit]:
        return sorted(
            (u for u in self.units.values() if u.sentence_id == sentence_id),
            key=lambda u: u.unit_id,
        )

    def next_unit_in_sentence(self, sentence_id: int, unit_id: int) -> Unit | None:
        """句内时间顺序（unit_id 升序）上的下一个单元；无则 None。"""
        units = self.units_in_sentence(sentence_id)
        for idx, u in enumerate(units):
            if u.unit_id == unit_id:
                return units[idx + 1] if idx + 1 < len(units) else None
        raise NotFoundError(f"unit 不存在: {format_coordinate(sentence_id, unit_id)}")

    def units_by_label(self, label: str) -> list[Unit]:
        return sorted(
            (u for u in self.units.values() if u.label == label),
            key=lambda u: (u.sentence_id, u.unit_id),
        )

    # ── Asset 操作 ─────────────────────────────────────────────────

    def add_asset(self, asset: Asset) -> None:
        if asset.id in self.assets:
            raise InvalidInputError(f"asset id 已存在: {asset.id}")
        if asset.sample_rate <= 0 or asset.num_samples <= 0:
            raise InvalidInputError(
                f"asset {asset.id} 信息非法：sample_rate={asset.sample_rate}, num_samples={asset.num_samples}"
            )
        self.assets[asset.id] = asset

    def remove_asset(self, asset_id: str) -> None:
        refs = [s.sentence_id for s in self.sentences.values() if s.asset_id == asset_id]
        if refs:
            raise InvalidInputError(
                f"asset {asset_id} 仍被句子引用: {refs}（请先删除/移动相关句子）"
            )
        del self.assets[asset_id]

    # ── Sentence 操作 ──────────────────────────────────────────────

    def create_sentence(
        self,
        asset_id: str,
        start_sample: int,
        end_sample: int,
        sample_rate: int | None = None,
        segmentation: dict[str, Any] | None = None,
    ) -> Sentence:
        asset = self.get_asset(asset_id)
        if sample_rate is None:
            sample_rate = asset.sample_rate
        if sample_rate != asset.sample_rate:
            raise InvalidInputError(
                f"sentence 采样率 {sample_rate} 必须等于 asset 采样率 {asset.sample_rate}"
                "（重采样为 FUTURE）"
            )
        self._check_sentence_bounds(start_sample, end_sample, asset.num_samples)
        if self.frozen:
            sid = self._allocator.next_sentence_id()
        else:
            sid = max(self.sentences.keys()) + 1 if self.sentences else 1
            self._allocator.counters.max_sentence_id_ever = max(
                self._allocator.counters.max_sentence_id_ever, sid
            )
        seg = dict(segmentation) if segmentation else {}
        sent = Sentence(
            sentence_id=sid,
            asset_id=asset_id,
            sample_rate=sample_rate,
            start_sample=start_sample,
            end_sample=end_sample,
            segmentation=seg,
            max_unit_id_ever=0,
        )
        self.sentences[sid] = sent
        return sent

    @staticmethod
    def _check_sentence_bounds(start_sample: int, end_sample: int, num_samples: int) -> None:
        if not isinstance(start_sample, int) or not isinstance(end_sample, int):
            raise InvalidInputError("句边界必须是整数采样点")
        if start_sample < 0 or end_sample <= start_sample:
            raise InvalidInputError(
                f"非法句范围: [{start_sample}, {end_sample})（需 0 ≤ start < end）"
            )
        if end_sample > num_samples:
            raise InvalidInputError(
                f"句范围越界: [{start_sample}, {end_sample}) 超出 asset 长度 {num_samples}"
            )

    def update_sentence(
        self,
        sentence_id: int,
        start_sample: int | None = None,
        end_sample: int | None = None,
        segmentation: dict[str, Any] | None = None,
    ) -> Sentence:
        sent = self.get_sentence(sentence_id)
        new_start = sent.start_sample if start_sample is None else start_sample
        new_end = sent.end_sample if end_sample is None else end_sample
        asset = self.get_asset(sent.asset_id)
        self._check_sentence_bounds(new_start, new_end, asset.num_samples)
        self._check_unit_windows_inside(sentence_id, new_end - new_start, "更新句子边界")
        sent.start_sample = new_start
        sent.end_sample = new_end
        if segmentation is not None:
            sent.segmentation = dict(segmentation)
        return sent

    def delete_sentence(self, sentence_id: int, cascade: bool = False) -> None:
        self.get_sentence(sentence_id)
        units = self.units_in_sentence(sentence_id)
        if units and not cascade:
            raise InvalidInputError(
                f"sentence {sentence_id} 仍有 {len(units)} 个单元（删除会连带删除，需 --cascade）"
            )
        for u in units:
            del self.units[unit_key(u.sentence_id, u.unit_id)]
        del self.sentences[sentence_id]

    def split_sentence(self, sentence_id: int, split_sample: int) -> tuple[int, Sentence]:
        """在 split_sample 处分割句子。

        冻结规则（JRH_SPEC §3）：原句保留原句号与原单元编号；
        新片段获得新句号，单元按来源顺序取得句内新编号。
        跨越分割点的单元 → 报错（须先调整单元边界）。
        """
        sent = self.get_sentence(sentence_id)
        if not (sent.start_sample < split_sample < sent.end_sample):
            raise InvalidInputError(
                f"分割点 {split_sample} 必须在句子范围 ({sent.start_sample}, {sent.end_sample}) 内"
            )
        units = self.units_in_sentence(sentence_id)
        first = [
            u for u in units if u.timing.window_end() <= split_sample - sent.start_sample + 1e-6
        ]
        second = [u for u in units if u.timing.offset >= split_sample - sent.start_sample - 1e-6]
        straddling = [u for u in units if u not in first and u not in second]
        if straddling:
            raise InvalidInputError(
                "分割点落在单元窗口内部，请先调整单元边界: "
                + ", ".join(u.coordinate() for u in straddling)
            )
        for u in second:
            del self.units[unit_key(sentence_id, u.unit_id)]
        if self.frozen:
            new_sid = self._allocator.next_sentence_id()
        else:
            new_sid = max(self.sentences.keys()) + 1
            self._allocator.counters.max_sentence_id_ever = max(
                self._allocator.counters.max_sentence_id_ever, new_sid
            )
        seg = dict(sent.segmentation)
        seg["manually_adjusted"] = True
        new_sent = Sentence(
            sentence_id=new_sid,
            asset_id=sent.asset_id,
            sample_rate=sent.sample_rate,
            start_sample=split_sample,
            end_sample=sent.end_sample,
            segmentation=seg,
            max_unit_id_ever=0,
        )
        for u in second:
            uid = self._next_unit_id_in(new_sent)
            u2 = Unit(
                sentence_id=new_sid,
                unit_id=uid,
                label=u.label,
                timing=u.timing,
                enabled=u.enabled,
                analysis=dict(u.analysis),
            )
            new_sent.max_unit_id_ever = max(new_sent.max_unit_id_ever, uid)
            self.units[unit_key(new_sid, uid)] = u2
        sent.end_sample = split_sample
        sent.segmentation["manually_adjusted"] = True
        self.sentences[new_sid] = new_sent
        return new_sid, new_sent

    def merge_sentences(self, sentence_id_a: int, sentence_id_b: int) -> int:
        """合并两句：保留较小句号；被并入单元尽量保留原编号，冲突时按来源顺序取新号。

        时间轴规则：合并后句范围 = [min start, max end]；
        较晚句子的全部单元 timing.offset 减去两句起点差（其余参数不变）。
        """
        if sentence_id_a == sentence_id_b:
            raise InvalidInputError("合并需要两个不同的句子")
        a = self.get_sentence(sentence_id_a)
        b = self.get_sentence(sentence_id_b)
        if a.asset_id != b.asset_id:
            raise InvalidInputError("只能合并同一 asset 内的句子")
        if a.sample_rate != b.sample_rate:
            raise InvalidInputError("只能合并采样率相同的句子")
        keep_id = min(sentence_id_a, sentence_id_b)
        keep = self.get_sentence(keep_id)
        drop = self.get_sentence(max(sentence_id_a, sentence_id_b))
        if a.start_sample <= b.start_sample:
            early, late = a, b
        else:
            early, late = b, a
        shift = late.start_sample - early.start_sample
        # 收集全部单元（时间顺序：early 在前）
        all_units = list(self.units_in_sentence(early.sentence_id)) + list(
            self.units_in_sentence(late.sentence_id)
        )
        # 晚句单元先做时间轴偏移（相对各自句起点 → 相对合并后起点）
        for u in all_units:
            if u.sentence_id == late.sentence_id:
                u.timing.offset -= shift
        # 移入保留句，冲突时取新编号
        for u in all_units:
            old_key = unit_key(u.sentence_id, u.unit_id)
            new_key = unit_key(keep_id, u.unit_id)
            if old_key != new_key and new_key in self.units:
                u.unit_id = self._next_unit_id_in(keep)
            else:
                keep.max_unit_id_ever = max(keep.max_unit_id_ever, u.unit_id)
            u.sentence_id = keep_id
            self.units.pop(old_key, None)
            self.units[unit_key(keep_id, u.unit_id)] = u
        keep.start_sample = min(a.start_sample, b.start_sample)
        keep.end_sample = max(a.end_sample, b.end_sample)
        keep.segmentation["manually_adjusted"] = True
        self.sentences.pop(drop.sentence_id, None)
        return keep_id

    def renumber_sentences(self) -> None:
        """草稿期整理：按当前顺序重排句号 1..n（单元坐标随之重映射）。"""
        self._check_mutable_identity("重排句号")
        ordered = sorted(self.sentences)
        old_units = dict(self.units)
        self.units.clear()
        for new_id, old_id in enumerate(ordered, start=1):
            if new_id != old_id:
                sent = self.sentences.pop(old_id)
                sent.sentence_id = new_id
            else:
                sent = self.sentences[old_id]
            self.sentences[new_id] = sent
            for (s, u), unit in old_units.items():
                if s == old_id:
                    unit.sentence_id = new_id
                    self.units[unit_key(new_id, u)] = unit
                elif s != old_id and unit_key(s, u) not in self.units:
                    self.units[unit_key(s, u)] = unit
        self._allocator.counters.max_sentence_id_ever = len(self.sentences)

    def renumber_unit_ids(self, sentence_id: int) -> None:
        """草稿期整理：重排句内单元编号 1..n。"""
        self._check_mutable_identity("重排句内单元编号")
        sent = self.get_sentence(sentence_id)
        old_units = self.units_in_sentence(sentence_id)
        for u in old_units:
            del self.units[unit_key(sentence_id, u.unit_id)]
        for new_id, u in enumerate(old_units, start=1):
            u.unit_id = new_id
            self.units[unit_key(sentence_id, new_id)] = u
        sent.max_unit_id_ever = len(old_units)

    # ── Unit 操作 ──────────────────────────────────────────────────

    def _next_unit_id_in(self, sent: Sentence) -> int:
        """句内下一个编号：冻结/草稿均不复用已删除编号。"""
        uid = sent.max_unit_id_ever + 1
        sent.max_unit_id_ever = uid
        return uid

    def _check_unit_windows_inside(
        self, sentence_id: int, duration_samples: float, what: str
    ) -> None:
        for u in self.units_in_sentence(sentence_id):
            if u.timing.window_end() > duration_samples + 1e-6:
                raise InvalidInputError(
                    f"{what} 会使单元 {u.coordinate()} 窗口超出句子范围"
                    f"（window_end={u.timing.window_end()} > {duration_samples}）"
                )

    def create_unit(
        self,
        sentence_id: int,
        label: str,
        timing: Timing,
        enabled: bool = True,
    ) -> Unit:
        sent = self.get_sentence(sentence_id)
        if not label or not isinstance(label, str):
            raise InvalidInputError("单元 label 不能为空")
        errs = timing.constraint_errors("unit 新建")
        if errs:
            raise InvalidInputError("；".join(errs))
        if timing.window_end() > sent.duration_samples() + 1e-6:
            raise InvalidInputError(
                f"单元窗口超出句子范围（window_end={timing.window_end()} > {sent.duration_samples()}）"
            )
        uid = self._next_unit_id_in(sent)
        unit = Unit(
            sentence_id=sentence_id,
            unit_id=uid,
            label=label,
            timing=timing,
            enabled=enabled,
        )
        self.units[unit_key(sentence_id, uid)] = unit
        return unit

    def update_unit(
        self,
        sentence_id: int,
        unit_id: int,
        label: str | None = None,
        timing: Timing | None = None,
        enabled: bool | None = None,
    ) -> Unit:
        unit = self.get_unit(sentence_id, unit_id)
        if label is not None:
            if not label:
                raise InvalidInputError("单元 label 不能为空")
            unit.label = label
        if timing is not None:
            errs = timing.constraint_errors(f"unit {unit.coordinate()}")
            if errs:
                raise InvalidInputError("；".join(errs))
            sent = self.get_sentence(sentence_id)
            if timing.window_end() > sent.duration_samples() + 1e-6:
                raise InvalidInputError(
                    f"单元窗口超出句子范围（window_end={timing.window_end()} > {sent.duration_samples()}）"
                )
            unit.timing = timing
        if enabled is not None:
            if not isinstance(enabled, bool):
                raise InvalidInputError("enabled 必须是布尔值")
            unit.enabled = enabled
        return unit

    def delete_unit(self, sentence_id: int, unit_id: int) -> None:
        self.get_unit(sentence_id, unit_id)
        del self.units[unit_key(sentence_id, unit_id)]

    def set_unit_analysis(self, sentence_id: int, unit_id: int, analysis: dict[str, Any]) -> None:
        unit = self.get_unit(sentence_id, unit_id)
        if not isinstance(analysis, dict):
            raise InvalidInputError("analysis 必须是对象")
        for k, v in analysis.items():
            if v is not None and (
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            ):
                raise InvalidInputError(f"analysis.{k} 非法: {v!r}")
        unit.analysis = dict(analysis)

    # ── 候选分组 ───────────────────────────────────────────────────

    def group_set_manual(self, label: str, ordered_unit_ids: list[str]) -> None:
        from .ids import is_coordinate

        for c in ordered_unit_ids:
            if not is_coordinate(c):
                raise InvalidInputError(f"人工顺序含非法坐标: {c!r}")
        self.candidate_groups.set_manual(label, ordered_unit_ids)

    def group_set_auto(self, label: str) -> None:
        self.candidate_groups.set_auto(label)

    # ── 冻结 ───────────────────────────────────────────────────────

    def freeze(self) -> None:
        if self.frozen:
            raise FrozenError("项目已处于冻结状态")
        self._sync_counters()
        self.manifest["state"] = "frozen"
        self.save()

    # ── 分析 ───────────────────────────────────────────────────────

    def set_analysis_summary(self, summary: AnalysisSummary) -> None:
        summary.revision = (self.analysis_summary.revision if self.analysis_summary else 0) + 1
        self.analysis_summary = summary

    def analysis_summary_effective(self) -> AnalysisSummary:
        """存储的汇总缓存；缺失时按当前数据实时计算（确定性）。"""
        if self.analysis_summary is not None:
            return self.analysis_summary
        from .analysis import build_summary

        return build_summary(self)

    # ── 便捷 ───────────────────────────────────────────────────────

    def coordinate_exists(self, coordinate: str) -> bool:
        from .ids import parse_coordinate

        s, u = parse_coordinate(coordinate)
        return unit_key(s, u) in self.units
