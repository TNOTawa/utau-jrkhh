"""人力V助手（JinrikiHelper）bank → JRH 母版导入器。

输入：bank 目录（meta.json + slices/*.wav + textgrid/*.TextGrid）。
可选：现有传统音源 oto.ini —— 提供「原参数原样保留」与「组内优先级人工排序」。

语言（按 meta.json 的 language 自动分发）：
- japanese/ja：jrh.ja-romaji；切片按「段_序号」（-\\d+_\\d+$）分组，同段拼接成句
- chinese/zh ：jrh.zh-pinyin；每切片独立成句（DJUTAU 实测：切片按词/停顿切，
  跨切片无协同发音，VC 只产切片内）

输出（JRH 母版）：
- Asset = 单切片组：切片文件原样复制（assets/{stem}.wav，供导出「定向已有文件」）；
  多切片段：按序号拼接（assets/segment_{seg:03d}.wav）
- Sentence = 一组；Unit = TextGrid 音素映射出的拍/音节
- Unit timing 优先取原版 oto 条目五参数原样（毫秒→采样点，无损往返）；
  无对应条目的按区间估计（consonant=辅音段时长，preutterance=consonant，
  overlap=0.3×preutterance；中文零声母 consonant=min(30ms, 元音首音素×0.2)，
  由 mfa_zh 的 consonant_end 表达）
- candidate_groups 人工排序 = 原版 oto 组内顺序（拼字产物/无单位别名除外，逐条报告）
"""

from __future__ import annotations

import hashlib
import re
import shutil
import wave
from pathlib import Path
from typing import Any

from ..core.errors import DataError, InvalidInputError
from ..core.model import Asset, Timing
from ..core.project import JRHProject
from ..core.util import read_json_strict, write_json
from ..formats.oto_ini import OtoLine, read_oto
from ..languages import get_pack
from . import mfa_ja, mfa_zh
from .mfa_ja import Mora
from .textgrid import read_textgrid

_SLICE_KEY_RE = re.compile(r"-(\d+)_(\d+)$")
_BASE_ALIAS_RE = re.compile(r"^(.*?)(\d+)$")

_LANG_SPECS: dict[str, dict] = {
    "japanese": {"pack": "jrh.ja-romaji", "mfa": mfa_ja, "group": "segment"},
    "chinese": {"pack": "jrh.zh-pinyin", "mfa": mfa_zh, "group": "per_slice"},
}


def _resolve_language(language: str | None) -> dict:
    if language in ("japanese", "ja"):
        return _LANG_SPECS["japanese"]
    if language in ("chinese", "zh"):
        return _LANG_SPECS["chinese"]
    raise InvalidInputError(f"不支持的语言（meta.language={language!r}，支持 japanese/chinese）")


def _slice_key(stem: str, language: str) -> tuple[Any, int] | None:
    """切片 stem → (组键, 组内序号)。日语按「段_序号」；中文每切片独立成组。"""
    if language in ("japanese", "ja"):
        m = _SLICE_KEY_RE.search(stem)
        if not m:
            return None
        return int(m.group(1)), int(m.group(2))
    return (stem, 0)


def _base_alias(alias: str) -> str:
    m = _BASE_ALIAS_RE.match(alias)
    return m.group(1) if m else alias


def _entry_label(pack: Any, alias: str) -> str | None:
    """原版别名 → 语言包单位；无法映射返回 None（如裸辅音 k、乱码）。"""
    try:
        units = pack.lyric_to_units(alias)
    except InvalidInputError:
        units = []
    if len(units) == 1:
        return units[0]
    if pack.validate_unit(alias):
        return alias
    return None


def import_henki_bank(
    bank_dir: str | Path,
    out_dir: str | Path,
    oto_ini: str | Path | None = None,
    dry_run: bool = False,
) -> dict:
    """执行导入。返回确定性报告 dict（非 dry_run 时另写 import-report.json）。"""
    bank = Path(bank_dir)
    out = Path(out_dir)

    meta = read_json_strict(bank / "meta.json", "meta.json")
    language = meta.get("language")
    spec = _resolve_language(language)
    pack = get_pack(spec["pack"])
    mfa_mod = spec["mfa"]
    phones_to_moras = mfa_mod.phones_to_moras

    # ── 1. 收集切片（按语言分组策略） ──────────────────────────
    slice_files: dict[tuple[Any, int], Path] = {}
    stray: list[str] = []
    for p in sorted((bank / "slices").glob("*.wav")):
        key = _slice_key(p.stem, language)
        if key is None:
            stray.append(p.name)
        else:
            slice_files[key] = p
    segments: dict[Any, list[tuple[int, Path]]] = {}
    for (seg, idx), p in sorted(slice_files.items()):
        segments.setdefault(seg, []).append((idx, p))

    # ── 2. 解析每切片的 wav 信息 + TextGrid → 拍序列 ──────────
    slice_plans: dict[tuple[Any, int], dict] = {}
    skipped_slices: list[str] = []
    warnings: list[str] = []
    phones_total = 0
    moras_total = 0
    for (seg, idx), wav_path in sorted(slice_files.items()):
        tg_path = bank / "textgrid" / f"{wav_path.stem}.TextGrid"
        if not tg_path.exists():
            skipped_slices.append(wav_path.stem)
            continue
        with wave.open(str(wav_path), "rb") as w:
            rate, frames = w.getframerate(), w.getnframes()
            channels, sampwidth = w.getnchannels(), w.getsampwidth()
        grid = read_textgrid(tg_path)
        phones = [
            mfa_mod.Phone(iv.text, iv.xmin, iv.xmax)
            for iv in grid.tier("phones")
            if iv.text.strip()  # 空文本音素为对齐填充，跳过
        ]
        if spec["group"] == "per_slice":
            # 中文：words 层词区间用于韵尾同词约束（防「可能」→ kon 类跨词吞并）
            word_ranges = [(iv.xmin, iv.xmax) for iv in grid.tier("words") if iv.text.strip()]
            moras, warns = phones_to_moras(phones, word_ranges=word_ranges)
        else:
            moras, warns = phones_to_moras(phones)
        phones_total += len(phones)
        moras_total += len(moras)
        for wmsg in warns:
            warnings.append(f"{wav_path.stem}: {wmsg}")
        slice_plans[(seg, idx)] = {
            "seg": seg,
            "idx": idx,
            "wav": wav_path,
            "rate": rate,
            "frames": frames,
            "channels": channels,
            "sampwidth": sampwidth,
            "moras": moras,
        }

    # ── 3. 原版 oto.ini：分组（保序）与匹配 ──────────────────
    # 无可用切片（缺 TextGrid）的段整段跳过
    usable_segments = {
        seg: items
        for seg, items in sorted(segments.items())
        if any(slice_plans.get((seg, i)) is not None for i, _ in items)
    }
    empty_segments = sorted(set(segments) - set(usable_segments))

    entries: list[OtoLine] = []
    if oto_ini is not None:
        oto_path = Path(oto_ini)
        if not oto_path.exists():
            raise DataError(f"原版 oto.ini 不存在: {oto_path}")
        entries = read_oto(oto_path)

    unmatched: list[dict] = []
    # 组 → 有序条目（文件序）；base 顺序按首次出现
    group_order: dict[str, list[OtoLine]] = {}
    for e in entries:
        group_order.setdefault(_base_alias(e.alias), []).append(e)

    # 单元计划：每段按 (idx, 拍起点) 顺序 → 单元描述
    unit_plans: dict[Any, list[dict]] = {}
    for seg in sorted(usable_segments):
        plan: list[dict] = []
        for idx, _ in sorted(usable_segments[seg]):
            sp = slice_plans.get((seg, idx))
            if sp is None:
                continue
            for m in sp["moras"]:
                plan.append(
                    {
                        "seg": seg,
                        "idx": idx,
                        "mora": m,
                        "entry": None,  # 匹配到的原版条目（timing 来源）
                    }
                )
        unit_plans[seg] = plan

    # 匹配：同切片、同 label、窗口重叠 ≥ 50%×较短者，贪心最大重叠、一对一
    matched_count = 0
    for e in entries:
        wav_stem = Path(e.wav).stem
        key = _slice_key(wav_stem, language)
        if key is None or key not in slice_files:
            unmatched.append({"alias": e.alias, "wav": e.wav, "reason": "非切片 wav（拼字产物等）"})
            continue
        sp = slice_plans.get(key)
        if sp is None:
            unmatched.append({"alias": e.alias, "wav": e.wav, "reason": "切片缺失 TextGrid"})
            continue
        label = _entry_label(pack, _base_alias(e.alias))
        if label is None:
            unmatched.append({"alias": e.alias, "wav": e.wav, "reason": "别名无语言包单位"})
            continue
        entry_start = e.offset_ms / 1000.0
        entry_end = entry_start + abs(e.cutoff_ms) / 1000.0
        seg = key[0]
        best: dict | None = None
        best_overlap = 0.0
        for up in unit_plans[seg]:
            cand_mora: Mora = up["mora"]
            if up["idx"] != key[1] or up["entry"] is not None or cand_mora.romaji != label:
                continue
            overlap = min(entry_end, cand_mora.xmax) - max(entry_start, cand_mora.xmin)
            shorter = min(entry_end - entry_start, cand_mora.xmax - cand_mora.xmin)
            if shorter <= 0 or overlap < 0.5 * shorter:
                continue
            if overlap > best_overlap:
                best, best_overlap = up, overlap
        if best is None:
            unmatched.append(
                {"alias": e.alias, "wav": e.wav, "reason": "切片内无对应单元（窗口重叠不足）"}
            )
            continue
        best["entry"] = e
        matched_count += 1

    # ── 4. 建项目（非 dry_run） ───────────────────────────────
    if dry_run:
        return _report(
            meta,
            bank,
            usable_segments,
            empty_segments,
            slice_files,
            skipped_slices,
            stray,
            warnings,
            phones_total,
            moras_total,
            entries,
            unmatched,
            matched_count,
            group_order,
            unit_plans,
            out=None,
        )

    if out.exists() and any(out.iterdir()):
        raise InvalidInputError(f"输出目录非空: {out}（请换新目录）")
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)

    proj = JRHProject.create(out, spec["pack"])

    # 合并段 wav + Asset + Sentence + Units
    units_of_seg: dict[Any, list[Any]] = {}
    asset_index = 0
    for seg in sorted(usable_segments):
        asset_index += 1
        asset_id = f"seg-{asset_index:03d}"
        items = sorted(segments[seg])
        if len(items) == 1:
            # 单切片组：资产 = 切片文件原样复制（供导出「定向已有文件」，避免重复音频）
            _idx, wav_path = items[0]
            merged_name = f"{wav_path.stem}.wav"
            merged_path = out / "assets" / merged_name
            shutil.copy2(wav_path, merged_path)
            with wave.open(str(merged_path), "rb") as mw:
                channels = mw.getnchannels()
                sampwidth = mw.getsampwidth()
                rate = mw.getframerate()
                total_frames = mw.getnframes()
        else:
            merged_name = f"segment_{asset_index:03d}.wav"
            merged_path = out / "assets" / merged_name
            total_frames = 0
            rate = 0
            channels = sampwidth = 1
            with wave.open(str(merged_path), "wb") as mw:
                first = True
                for _idx, wav_path in items:
                    with wave.open(str(wav_path), "rb") as sw:
                        params = (sw.getnchannels(), sw.getsampwidth(), sw.getframerate())
                        nframes = sw.getnframes()
                        frames_data = sw.readframes(nframes)
                    if first:
                        channels, sampwidth, rate = params
                        mw.setnchannels(channels)
                        mw.setsampwidth(sampwidth)
                        mw.setframerate(rate)
                        first = False
                    elif params != (channels, sampwidth, rate):
                        raise InvalidInputError(f"段 {seg} 内切片格式不一致: {wav_path.name}")
                    mw.writeframes(frames_data)
                    total_frames += nframes
        sha = hashlib.sha256(merged_path.read_bytes()).hexdigest()
        proj.add_asset(
            Asset(
                id=asset_id,
                file=f"assets/{merged_name}",
                kind="audio",
                sha256=sha,
                sample_rate=rate,
                num_samples=total_frames,
                duration_seconds=total_frames / rate,
            )
        )
        sent = proj.create_sentence(asset_id, 0, total_frames)

        # 计算每切片在段内的采样偏移（含缺 TextGrid 的切片——其音频仍在段内）
        slice_offsets: dict[int, float] = {}
        acc = 0
        for idx, _ in sorted(segments[seg]):
            slice_offsets[idx] = acc
            with wave.open(str(slice_files[(seg, idx)]), "rb") as w:
                acc += w.getnframes()

        created: list[Any] = []
        for up in unit_plans[seg]:
            sp = slice_plans[(seg, up["idx"])]
            r = sp["rate"]
            slice_off = slice_offsets[up["idx"]]
            unit_mora: Mora = up["mora"]
            timing = _timing_from_entry(up["entry"], r, slice_off, unit_mora)
            if timing is not None:
                limit = slice_off + sp["frames"]
                if timing.window_end() > limit + 0.5:
                    timing = None  # 条目窗口真越出切片 → 改用区间估计
                elif timing.window_end() > limit:
                    timing = _clamp_window(timing, limit)  # 毫秒→采样点浮点噪声
            if timing is None:
                timing = _estimated_timing(unit_mora, r, slice_off)
            # 统一钳制到切片边界（估计 timing 的 TextGrid 浮点噪声可达 >0.5 采样点）
            limit = slice_off + sp["frames"]
            if timing.window_end() > limit + 1e-6:
                if timing.offset < limit - 1e-6:
                    timing = _clamp_window(timing, limit)
                else:
                    warnings.append(
                        f"{sp['wav'].stem}: 单元区间完全在切片外，跳过（{unit_mora.romaji}）"
                    )
                    continue
            unit = proj.create_unit(sent.sentence_id, up["mora"].romaji, timing)
            created.append((up, unit))
        units_of_seg[seg] = created

    # ── 5. 优先级：原版组序 → candidate_groups 人工排序 ──────
    coord_of_entry: dict[int, str] = {}  # id(entry) → 坐标
    for _seg, created in sorted(units_of_seg.items()):
        for up, unit in created:
            if up["entry"] is not None:
                coord_of_entry[id(up["entry"])] = unit.coordinate()

    label_orders: dict[str, list[str]] = {}
    for base, group in group_order.items():
        label = _entry_label(pack, base)
        if label is None:
            continue
        coords = [coord_of_entry[id(e)] for e in group if id(e) in coord_of_entry]
        if coords:
            merged = label_orders.setdefault(label, [])
            for c in coords:
                if c not in merged:
                    merged.append(c)
    for label, coords in sorted(label_orders.items()):
        proj.group_set_manual(label, coords)

    proj.manifest["import_source"] = {
        "kind": "henki",
        "language": language,
        "bank_dir": str(bank),
        "oto_ini": str(Path(oto_ini)) if oto_ini is not None else None,
        "oto_dir": str(Path(oto_ini).parent) if oto_ini is not None else None,
        "segments": len(usable_segments),
        "slices_used": len(slice_plans),
    }
    proj.save()

    report = _report(
        meta,
        bank,
        usable_segments,
        empty_segments,
        slice_files,
        skipped_slices,
        stray,
        warnings,
        phones_total,
        moras_total,
        entries,
        unmatched,
        matched_count,
        group_order,
        unit_plans,
        out=out,
    )
    write_json(out / "import-report.json", report)
    return report


def _timing_from_entry(
    entry: OtoLine | None, rate: int, slice_offset: float, m: Mora
) -> Timing | None:
    """原版条目五参数原样（毫秒→采样点）；非法/越界返回 None（改用估计）。"""
    if entry is None:
        return None
    t = Timing(
        offset=slice_offset + entry.offset_ms * rate / 1000.0,
        consonant=entry.consonant_ms * rate / 1000.0,
        cutoff=entry.cutoff_ms * rate / 1000.0,
        preutterance=entry.preutterance_ms * rate / 1000.0,
        overlap=entry.overlap_ms * rate / 1000.0,
    )
    if t.constraint_errors():
        return None
    return t


def _estimated_timing(m: Mora, rate: int, slice_offset: float) -> Timing:
    start = slice_offset + m.xmin * rate
    dur = (m.xmax - m.xmin) * rate
    cons = (m.consonant_end - m.xmin) * rate if m.consonant_end is not None else 0.0
    return Timing(
        offset=start,
        consonant=cons,
        cutoff=-dur,
        preutterance=cons,
        overlap=0.3 * cons,
    )


def _clamp_window(t: Timing, limit: float) -> Timing:
    """把窗口末端钳到切片边界（仅用于毫秒→采样点的浮点噪声修正）。"""
    dur = limit - t.offset
    pre = min(t.preutterance, dur)
    return Timing(
        offset=t.offset,
        consonant=min(t.consonant, dur),
        cutoff=-dur,
        preutterance=pre,
        overlap=min(t.overlap, pre),
    )


def _report(
    meta: dict,
    bank: Path,
    usable_segments: dict,
    empty_segments: list[Any],
    slice_files: dict,
    skipped_slices: list[str],
    stray: list[str],
    warnings: list[str],
    phones_total: int,
    moras_total: int,
    entries: list[OtoLine],
    unmatched: list[dict],
    matched_count: int,
    group_order: dict[str, list[OtoLine]],
    unit_plans: dict[Any, list[dict]],
    out: Path | None,
) -> dict:
    units_total = sum(len(v) for v in unit_plans.values())
    return {
        "bank_dir": str(bank),
        "language": meta.get("language"),
        "segments": len(usable_segments),
        "segments_without_textgrid": empty_segments,
        "slices_total": len(slice_files),
        "slices_used": len(slice_files) - len(skipped_slices),
        "slices_skipped": sorted(skipped_slices),
        "stray_slice_files": sorted(stray),
        "phones_total": phones_total,
        "moras_total": moras_total,
        "units_total": units_total,
        "entries_total": len(entries),
        "matched_entries": matched_count,
        "unmatched_entries": sorted(unmatched, key=lambda d: (d["wav"], d["alias"], d["reason"])),
        "priority_groups": sorted(group_order.keys()),
        "warnings": sorted(warnings),
        "output": str(out) if out is not None else None,
        "dry_run": out is None,
    }
