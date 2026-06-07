import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

from .audio_player import AudioPlayer
from .draggable_list import _get_cjk_font, DraggableListbox
from .oto_parser import OtoBank, OtoEntry, get_base_phoneme, hiragana_to_romaji
from .phoneme_combine_dialog import (
    ALL_REQUIRED_PHONEMES,
    _CONSONANT_FALLBACK,
    _get_cv_of_base,
    combine_audio_entries,
    format_group_label,
    split_japanese_cv,
)
from .waveform_display import WaveformDisplay


class BatchCombineDialog(ctk.CTkToplevel):
    def __init__(self, parent, oto_bank: OtoBank):
        super().__init__(parent)
        self.parent = parent
        self.oto_bank = oto_bank

        self.title("批量拼字")
        self.geometry("1400x900")
        self.minsize(1200, 700)
        self.transient(parent)
        self.grab_set()

        self._temp_files: List[str] = []
        self._audio_player = AudioPlayer()
        self._list_font = _get_cjk_font(10)

        # 缓存所有分组
        self._all_groups = self.oto_bank.get_groups()

        # 缺失音素与类型
        self._missing: List[Tuple[str, str]] = []
        self._consonant_types: List[str] = []
        self._vowel_types: List[str] = []

        # 配置: {type: {"group_base": str, "entry_index": int}}
        self._consonant_configs: Dict[str, Dict] = {}
        self._vowel_configs: Dict[str, Dict] = {}

        # 当前选中的条目缓存（避免重复读取）
        self._current_entries: Dict[str, List[OtoEntry]] = {}

        self._build_ui()
        self._setup_defaults()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ────────────────────────────────────────────────

    def _build_ui(self):
        # 顶部信息栏
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=12, pady=(12, 6))

        self._info_label = ctk.CTkLabel(
            info_frame, text="", font=ctk.CTkFont(size=12))
        self._info_label.pack(side="left", padx=8)

        # 中间左右分栏
        mid_frame = ctk.CTkFrame(self)
        mid_frame.pack(fill="both", expand=True, padx=12, pady=6)
        mid_frame.grid_columnconfigure(0, weight=1)
        mid_frame.grid_columnconfigure(1, weight=1)
        mid_frame.grid_rowconfigure(0, weight=1)

        self._build_source_panel(mid_frame, 0, "辅音", "consonant")
        self._build_source_panel(mid_frame, 1, "元音", "vowel")

        # 底部总览与按钮
        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.pack(fill="x", padx=12, pady=(6, 12))
        bottom_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bottom_frame, text="缺失音素总览",
                     font=ctk.CTkFont(size=11, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        self._overview_text = ctk.CTkTextbox(
            bottom_frame, height=140, font=ctk.CTkFont(size=10))
        self._overview_text.grid(row=1, column=0, sticky="nsew",
                                  padx=8, pady=(0, 4))
        self._overview_text.configure(state="disabled")

        btn_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="e", padx=8, pady=(4, 8))

        ctk.CTkButton(btn_frame, text="预览当前选中", width=120,
                      command=self._on_preview_current).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="一键生成", width=120,
                      fg_color="#2b8a3e", hover_color="#237032",
                      command=self._on_generate_all).pack(
            side="left", padx=4)
        ctk.CTkButton(btn_frame, text="取消", width=100,
                      fg_color="transparent", border_width=1,
                      command=self._on_close).pack(
            side="left", padx=4)

    def _build_source_panel(self, parent, column: int, title: str, prefix: str):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=column, sticky="nsew",
                   padx=(0 if column == 0 else 6, 6 if column == 0 else 0))
        frame.grid_rowconfigure(1, weight=2)   # 类型列表
        frame.grid_rowconfigure(3, weight=2)   # 分组/样本列表行
        frame.grid_rowconfigure(4, weight=3)   # 波形
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        # 类型列表
        ctk.CTkLabel(frame, text=f"{title}类型",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=2,
                                       sticky="ew", padx=8, pady=(8, 4))

        type_lb = DraggableListbox(
            frame, draggable=False,
            on_select=getattr(self, f"_on_{prefix}_type_select"),
            bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#264f78", selectforeground="#ffffff",
            font=self._list_font, activestyle="none",
            exportselection=False, borderwidth=0, highlightthickness=0)
        type_lb.grid(row=1, column=0, columnspan=2, sticky="nsew",
                     padx=8, pady=4)
        setattr(self, f"_{prefix}_type_listbox", type_lb)

        ts = ctk.CTkScrollbar(frame, command=type_lb.yview)
        ts.grid(row=1, column=2, sticky="ns", pady=4)
        type_lb.configure(yscrollcommand=ts.set)

        type_lb.bind("<Up>", lambda e: self._handle_key_up(type_lb, getattr(self, f"_on_{prefix}_type_select")))
        type_lb.bind("<Down>", lambda e: self._handle_key_down(type_lb, getattr(self, f"_on_{prefix}_type_select")))
        type_lb.bind("<MouseWheel>", lambda e: self._handle_wheel(type_lb, e, getattr(self, f"_on_{prefix}_type_select")))

        # 分组列表（左）
        ctk.CTkLabel(frame, text="来源分组",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=2, column=0,
                                       sticky="ew", padx=8, pady=(4, 2))

        group_lb = DraggableListbox(
            frame, draggable=False,
            on_select=getattr(self, f"_on_{prefix}_group_select"),
            bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#264f78", selectforeground="#ffffff",
            font=self._list_font, activestyle="none",
            exportselection=False, borderwidth=0, highlightthickness=0)
        group_lb.grid(row=3, column=0, sticky="nsew", padx=(8, 2), pady=(2, 4))
        setattr(self, f"_{prefix}_group_listbox", group_lb)

        gs = ctk.CTkScrollbar(frame, command=group_lb.yview)
        gs.grid(row=3, column=2, sticky="ns", pady=(2, 4))
        group_lb.configure(yscrollcommand=gs.set)

        group_lb.bind("<Up>", lambda e: self._handle_key_up(group_lb, getattr(self, f"_on_{prefix}_group_select")))
        group_lb.bind("<Down>", lambda e: self._handle_key_down(group_lb, getattr(self, f"_on_{prefix}_group_select")))
        group_lb.bind("<MouseWheel>", lambda e: self._handle_wheel(group_lb, e, getattr(self, f"_on_{prefix}_group_select")))

        # 样本列表（右）
        ctk.CTkLabel(frame, text="样本",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=2, column=1,
                                       sticky="ew", padx=2, pady=(4, 2))

        entry_lb = DraggableListbox(
            frame, draggable=False,
            on_select=getattr(self, f"_on_{prefix}_entry_select"),
            bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#264f78", selectforeground="#ffffff",
            font=self._list_font, activestyle="none",
            exportselection=False, borderwidth=0, highlightthickness=0)
        entry_lb.grid(row=3, column=1, sticky="nsew", padx=(2, 8), pady=(2, 4))
        setattr(self, f"_{prefix}_entry_listbox", entry_lb)

        es = ctk.CTkScrollbar(frame, command=entry_lb.yview)
        es.grid(row=3, column=3, sticky="ns", pady=(2, 4))
        entry_lb.configure(yscrollcommand=es.set)

        entry_lb.bind("<space>", lambda e, p=prefix: self._on_play_entry(p))
        entry_lb.bind("<MouseWheel>", lambda e, p=prefix: self._handle_wheel(entry_lb, e, getattr(self, f"_on_{prefix}_entry_select")))

        # 波形预览
        wf = WaveformDisplay(frame, width=400, height=160)
        wf.get_widget().grid(row=4, column=0, columnspan=4,
                              sticky="nsew", padx=8, pady=(4, 8))
        setattr(self, f"_{prefix}_waveform", wf)

        return frame

    # ── 初始化 ─────────────────────────────────────────────────

    def _setup_defaults(self):
        self._missing = self._get_missing_phonemes()

        # 提取涉及的辅音/元音类型
        c_set = set()
        v_set = set()
        for hira, _ in self._missing:
            c, v = split_japanese_cv(hira)
            if c:
                c_set.add(c)
            if v:
                v_set.add(v)

        self._consonant_types = sorted(c_set, key=lambda x: (-len(x), x))
        self._vowel_types = sorted(v_set)

        self._update_info_label()
        self._rebuild_type_list("consonant", self._consonant_types)
        self._rebuild_type_list("vowel", self._vowel_types)
        self._refresh_overview()

    def _get_missing_phonemes(self) -> List[Tuple[str, str]]:
        existing = {base for base, _ in self._all_groups}
        return [(h, r) for h, r in ALL_REQUIRED_PHONEMES if h not in existing]

    def _update_info_label(self):
        c_count = len(self._consonant_types)
        v_count = len(self._vowel_types)
        self._info_label.configure(
            text=f"共缺失 {len(self._missing)} 个音素，"
                 f"涉及 {c_count} 种辅音 / {v_count} 种元音"
        )

    def _rebuild_type_list(self, prefix: str, types: List[str]):
        lb = getattr(self, f"_{prefix}_type_listbox")
        lb.delete(0, tk.END)
        for t in types:
            lb.insert(tk.END, f"  {t}")
        if lb.size() > 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(0)
            getattr(self, f"_on_{prefix}_type_select")(0)

    @staticmethod
    def _format_group_label(base: str, count: int) -> str:
        return format_group_label(base, count)

    # ── 候选分组 ───────────────────────────────────────────────

    def _get_consonant_candidate_groups(self, c: str) -> List[str]:
        candidates = [c]
        fb = _CONSONANT_FALLBACK.get(c)
        if fb and fb != c:
            candidates.append(fb)
        result = []
        for base, _ in self._all_groups:
            bc, _ = _get_cv_of_base(base)
            if bc in candidates:
                result.append(base)
        return result

    def _get_vowel_candidate_groups(self, v: str) -> List[str]:
        result = []
        for base, _ in self._all_groups:
            _, bv = _get_cv_of_base(base)
            if bv == v:
                result.append(base)
        return result

    @staticmethod
    def _pick_default_vowel_group(v: str, candidates: List[str]) -> Optional[str]:
        for base in candidates:
            c, vv = _get_cv_of_base(base)
            if c is None and vv == v:
                return base
        return candidates[0] if candidates else None

    # ── 事件处理 ───────────────────────────────────────────────

    def _on_consonant_type_select(self, index: int):
        if not (0 <= index < len(self._consonant_types)):
            return
        c = self._consonant_types[index]
        candidates = self._get_consonant_candidate_groups(c)
        self._rebuild_group_list("consonant", candidates, c)

    def _on_vowel_type_select(self, index: int):
        if not (0 <= index < len(self._vowel_types)):
            return
        v = self._vowel_types[index]
        candidates = self._get_vowel_candidate_groups(v)
        self._rebuild_group_list("vowel", candidates, v)

    def _rebuild_group_list(self, prefix: str, candidates: List[str], type_key: str):
        lb = getattr(self, f"_{prefix}_group_listbox")
        lb.delete(0, tk.END)
        groups: List[Tuple[str, int]] = []
        for base, count in self._all_groups:
            if base in candidates:
                groups.append((base, count))
                lb.insert(tk.END, self._format_group_label(base, count))

        cfg = getattr(self, f"_{prefix}_configs").get(type_key)

        sel = 0
        if cfg:
            for i, (base, _) in enumerate(groups):
                if base == cfg["group_base"]:
                    sel = i
                    break
        elif prefix == "vowel" and groups:
            default = self._pick_default_vowel_group(type_key, [b for b, _ in groups])
            if default:
                for i, (base, _) in enumerate(groups):
                    if base == default:
                        sel = i
                        break

        setattr(self, f"_{prefix}_current_groups", groups)

        if lb.size() > 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(sel)
            lb.see(sel)
            getattr(self, f"_on_{prefix}_group_select")(sel)

    def _on_consonant_group_select(self, index: int):
        self._on_group_selected("consonant", index)

    def _on_vowel_group_select(self, index: int):
        self._on_group_selected("vowel", index)

    def _on_group_selected(self, prefix: str, group_index: int):
        groups = getattr(self, f"_{prefix}_current_groups", [])
        if not (0 <= group_index < len(groups)):
            return
        group_base, _ = groups[group_index]
        entries = self.oto_bank.get_group_entries(group_base)
        self._current_entries[prefix] = entries

        lb = getattr(self, f"_{prefix}_entry_listbox")
        lb.delete(0, tk.END)
        for i, e in enumerate(entries):
            lb.insert(tk.END, f"  {i:>2d}  {e.alias:<8s}  {e.wav_filename}")

        # 恢复已保存的样本索引，或默认选第一个
        type_list = getattr(self, f"_{prefix}_type_listbox")
        sel = type_list.curselection()
        if sel:
            t = getattr(self, f"_{prefix}_types")[sel[0]]
            cfg = getattr(self, f"_{prefix}_configs").get(t)
            if cfg and cfg.get("group_base") == group_base:
                idx = cfg.get("entry_index", 0)
            else:
                idx = 0
            if 0 <= idx < lb.size():
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.see(idx)
                getattr(self, f"_on_{prefix}_entry_select")(idx)
            elif lb.size() > 0:
                lb.selection_clear(0, tk.END)
                lb.selection_set(0)
                getattr(self, f"_on_{prefix}_entry_select")(0)
        elif lb.size() > 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(0)
            getattr(self, f"_on_{prefix}_entry_select")(0)

    def _on_consonant_entry_select(self, index: int):
        self._save_config_and_display("consonant", index)

    def _on_vowel_entry_select(self, index: int):
        self._save_config_and_display("vowel", index)

    def _save_config_and_display(self, prefix: str, index: int):
        type_list = getattr(self, f"_{prefix}_type_listbox")
        sel = type_list.curselection()
        if not sel:
            return
        t = getattr(self, f"_{prefix}_types")[sel[0]]

        group_list = getattr(self, f"_{prefix}_group_listbox")
        g_sel = group_list.curselection()
        if not g_sel:
            return
        groups = getattr(self, f"_{prefix}_current_groups", [])
        if not (0 <= g_sel[0] < len(groups)):
            return
        group_base, _ = groups[g_sel[0]]

        entries = self._current_entries.get(prefix, [])
        if not (0 <= index < len(entries)):
            return

        getattr(self, f"_{prefix}_configs")[t] = {
            "group_base": group_base,
            "entry_index": index,
        }

        entry = entries[index]
        wf = getattr(self, f"_{prefix}_waveform")
        self._display_entry(entry, wf)
        self._refresh_overview()

    def _display_entry(self, entry: OtoEntry, waveform: WaveformDisplay):
        if not self.oto_bank.folder_path:
            waveform.clear()
            return
        wav_path = self.oto_bank.folder_path / entry.wav_filename
        if wav_path.exists():
            waveform.load_with_oto(
                wav_path, entry.offset, entry.consonant, entry.cutoff,
                entry.overlap, entry.preutterance)
            self._audio_player.play_segment(
                wav_path, entry.offset, entry.cutoff)
        else:
            waveform.clear()

    # ── 总览刷新 ───────────────────────────────────────────────

    def _refresh_overview(self):
        # 收集并排序（未就绪在前）
        items = []
        for hira, roma in self._missing:
            c, v = split_japanese_cv(hira)
            c_cfg = self._consonant_configs.get(c)
            v_cfg = self._vowel_configs.get(v)
            ready = c_cfg is not None and v_cfg is not None
            items.append((ready, hira, roma, c_cfg, v_cfg))
        items.sort(key=lambda x: x[0])  # False -> True

        self._overview_text.configure(state="normal")
        self._overview_text.delete("1.0", tk.END)

        # 配置颜色 tag（首次调用时）
        try:
            self._overview_text.tag_config("ready", foreground="#4caf50")
            self._overview_text.tag_config("pending", foreground="#f44336")
        except tk.TclError:
            pass

        for ready, hira, roma, c_cfg, v_cfg in items:
            if c_cfg:
                c_str = f"{c_cfg['group_base']}[{c_cfg['entry_index']}]"
            else:
                c_str = "待配置"

            if v_cfg:
                v_str = f"{v_cfg['group_base']}[{v_cfg['entry_index']}]"
            else:
                v_str = "待配置"

            status = "就绪" if ready else "待配置"
            line = f"{hira:<6s} ({roma:<6s}) | 辅音: {c_str:<12s} | 元音: {v_str:<12s} | {status}\n"
            tag = "ready" if ready else "pending"
            self._overview_text.insert(tk.END, line, tag)

        self._overview_text.configure(state="disabled")

    # ── 预览与生成 ─────────────────────────────────────────────

    def _on_preview_current(self):
        # 获取当前左右两栏选中的条目进行预览
        c_entry = self._get_current_entry("consonant")
        v_entry = self._get_current_entry("vowel")
        if c_entry is None or v_entry is None:
            messagebox.showwarning("未选择", "请先在左右两栏分别选择来源样本", parent=self)
            return

        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        total_ms = combine_audio_entries(
            c_entry, v_entry, Path(tmp_path),
            self.oto_bank.folder_path, parent=self)
        if total_ms is None:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return

        self._temp_files.append(tmp_path)
        self._audio_player.play_segment(Path(tmp_path), 0.0, -total_ms)

    def _get_current_entry(self, prefix: str) -> Optional[OtoEntry]:
        type_list = getattr(self, f"_{prefix}_type_listbox")
        sel = type_list.curselection()
        if not sel:
            return None
        t = getattr(self, f"_{prefix}_types")[sel[0]]
        cfg = getattr(self, f"_{prefix}_configs").get(t)
        if not cfg:
            return None
        entries = self.oto_bank.get_group_entries(cfg["group_base"])
        idx = cfg.get("entry_index", 0)
        if 0 <= idx < len(entries):
            return entries[idx]
        return None

    def _on_generate_all(self):
        if not self._missing:
            messagebox.showinfo("无需生成", "没有缺失的音素", parent=self)
            return

        # 检查配置完整性
        unconfigured = []
        for c in self._consonant_types:
            if c not in self._consonant_configs:
                unconfigured.append(f"辅音: {c}")
        for v in self._vowel_types:
            if v not in self._vowel_configs:
                unconfigured.append(f"元音: {v}")

        if unconfigured:
            messagebox.showwarning(
                "配置未完成",
                "以下类型尚未配置来源样本:\n" + "\n".join(unconfigured),
                parent=self)
            return

        folder = self.oto_bank.folder_path
        if not folder:
            return

        generated: List[str] = []
        failed: List[str] = []

        for hira, roma in self._missing:
            c, v = split_japanese_cv(hira)
            c_cfg = self._consonant_configs[c]
            v_cfg = self._vowel_configs[v]

            c_entries = self.oto_bank.get_group_entries(c_cfg["group_base"])
            v_entries = self.oto_bank.get_group_entries(v_cfg["group_base"])

            if not c_entries or not v_entries:
                failed.append(f"{hira}: 来源分组为空")
                continue

            c_idx = c_cfg.get("entry_index", 0)
            v_idx = v_cfg.get("entry_index", 0)
            if not (0 <= c_idx < len(c_entries)) or not (0 <= v_idx < len(v_entries)):
                failed.append(f"{hira}: 样本索引越界")
                continue

            c_entry = c_entries[c_idx]
            v_entry = v_entries[v_idx]

            wav_name = self._get_unique_wav_name(hira, folder)
            wav_path = folder / wav_name

            total_ms = combine_audio_entries(
                c_entry, v_entry, wav_path, folder, parent=self)
            if total_ms is None:
                failed.append(f"{hira}: 音频拼接失败")
                continue

            consonant = c_entry.consonant
            preutterance = consonant
            overlap = c_entry.overlap
            if overlap <= 0:
                overlap = consonant * 0.3

            entry = OtoEntry(
                wav_filename=wav_name,
                alias=hira,
                offset=0.0,
                consonant=round(consonant, 1),
                cutoff=round(-total_ms, 1),
                preutterance=round(preutterance, 1),
                overlap=round(overlap, 1),
            )

            self.oto_bank.add_entry_to_group(entry, hira)
            generated.append(hira)

        # 通知主窗口刷新
        if generated and hasattr(self.parent, "refresh_after_combine"):
            self.parent.refresh_after_combine(get_base_phoneme(generated[0]))

        msg = f"成功生成 {len(generated)} 个音素"
        if failed:
            msg += f"\n失败 {len(failed)} 个:\n" + "\n".join(failed[:20])
        messagebox.showinfo("批量生成完成", msg, parent=self)

    @staticmethod
    def _get_unique_wav_name(alias: str, folder: Path) -> str:
        base_name = f"C{alias}.wav"
        if not (folder / base_name).exists():
            return base_name
        i = 1
        while True:
            name = f"C{alias}_{i}.wav"
            if not (folder / name).exists():
                return name
            i += 1

    # ── 播放辅助 ───────────────────────────────────────────────

    def _on_play_entry(self, prefix: str):
        entry = self._get_current_entry(prefix)
        if entry and self.oto_bank.folder_path:
            wav = self.oto_bank.folder_path / entry.wav_filename
            if wav.exists():
                self._audio_player.play_segment(
                    wav, entry.offset, entry.cutoff)

    # ── 通用列表交互辅助 ───────────────────────────────────────

    @staticmethod
    def _handle_wheel(lb: DraggableListbox, event, callback):
        selection = lb.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        delta = -1 if event.delta > 0 else 1
        new_idx = max(0, min(lb.size() - 1, idx + delta))
        if new_idx != idx:
            lb.selection_clear(0, tk.END)
            lb.selection_set(new_idx)
            lb.see(new_idx)
            callback(new_idx)
        return "break"

    @staticmethod
    def _handle_key_up(lb: DraggableListbox, callback):
        selection = lb.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx > 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx - 1)
            lb.see(idx - 1)
            callback(idx - 1)
        return "break"

    @staticmethod
    def _handle_key_down(lb: DraggableListbox, callback):
        selection = lb.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx < lb.size() - 1:
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx + 1)
            lb.see(idx + 1)
            callback(idx + 1)
        return "break"

    # ── 关闭 ───────────────────────────────────────────────────

    def _on_close(self):
        self._audio_player.cleanup()
        for f in self._temp_files:
            try:
                os.remove(f)
            except Exception:
                pass
        self.destroy()
