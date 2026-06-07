import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from .audio_player import AudioPlayer
from .draggable_list import _get_cjk_font, DraggableListbox
from .oto_parser import OtoBank, OtoEntry, get_base_phoneme, hiragana_to_romaji
from .batch_combine_dialog import BatchCombineDialog
from .phoneme_combine_dialog import PhonemeCombineDialog
from .waveform_display import WaveformDisplay
from . import perf_trace


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("UTAU 式人力音源调节工具")
        self.geometry("1200x760")
        self.minsize(1000, 550)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.oto_bank = OtoBank()
        self.audio_player = AudioPlayer()
        self._current_wav_path: Optional[Path] = None
        self._current_offset: float = 0.0
        self._current_cutoff: float = 0.0
        self._current_group: str = ""
        self._group_entries: List[OtoEntry] = []

        self._build_ui()
        perf_trace.disable()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_search_bar()
        self._build_main_area()
        self._bind_global_shortcuts()

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, height=40, corner_radius=0)
        toolbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        toolbar.grid_columnconfigure(0, weight=0)
        toolbar.grid_columnconfigure(1, weight=1)
        toolbar.grid_columnconfigure(2, weight=0)
        toolbar.grid_columnconfigure(3, weight=0)

        ctk.CTkButton(toolbar, text="打开音源文件夹", width=130,
                      command=self._on_open_folder).grid(
            row=0, column=0, padx=(10, 5), pady=5)

        self._name_label = ctk.CTkLabel(
            toolbar, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self._name_label.grid(row=0, column=1, padx=10, pady=5, sticky="w")

        self._save_btn = ctk.CTkButton(toolbar, text="保存 oto.ini", width=110,
                                       command=self._on_save, state="disabled")
        self._save_btn.grid(row=0, column=2, padx=5, pady=5)

        ctk.CTkButton(toolbar, text="撤销更改", width=90,
                      fg_color="transparent", border_width=1,
                      command=self._on_undo).grid(
            row=0, column=3, padx=(5, 10), pady=5)

    def _build_search_bar(self):
        search_frame = ctk.CTkFrame(
            self, height=36, corner_radius=0, fg_color="transparent")
        search_frame.grid(row=1, column=0, columnspan=3, sticky="ew",
                          padx=10, pady=(5, 0))
        search_frame.grid_columnconfigure(0, weight=1)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._on_search())
        self._search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="搜索音素...",
            textvariable=self._search_var)
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self._count_label = ctk.CTkLabel(
            search_frame, text="", font=ctk.CTkFont(size=11),
            text_color="#888888")
        self._count_label.grid(row=0, column=1, padx=(0, 5))

        ctk.CTkButton(search_frame, text="新增拼字", width=100,
                      command=self._on_open_combine_dialog).grid(
            row=0, column=2, padx=(5, 0))

        ctk.CTkButton(search_frame, text="批量拼字", width=100,
                      command=self._on_open_batch_dialog).grid(
            row=0, column=3, padx=(5, 0))

    def _build_main_area(self):
        left_frame = ctk.CTkFrame(self, width=180)
        left_frame.grid(row=2, column=0, sticky="ns", padx=(10, 2), pady=10)
        left_frame.grid_rowconfigure(0, weight=0)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_columnconfigure(1, weight=0)
        left_frame.grid_propagate(False)

        ctk.CTkLabel(left_frame, text="音素分组",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=2,
                                      sticky="ew", padx=8, pady=(5, 2))

        list_font = _get_cjk_font(10)
        self._group_listbox = DraggableListbox(
            left_frame, draggable=False, on_select=self._on_group_select,
            bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#264f78", selectforeground="#ffffff",
            font=list_font, activestyle="none",
            exportselection=False,
            borderwidth=0, highlightthickness=0)
        self._group_listbox.grid(row=1, column=0, sticky="nsew")

        gs = ctk.CTkScrollbar(left_frame, command=self._group_listbox.yview)
        gs.grid(row=1, column=1, sticky="ns")
        self._group_listbox.configure(yscrollcommand=gs.set)

        self._group_listbox.bind("<Up>", self._on_group_key_up)
        self._group_listbox.bind("<Down>", self._on_group_key_down)
        self._group_listbox.bind("<MouseWheel>", self._on_group_wheel)
        self._group_listbox.bind("<Button-3>", self._on_group_right_click)
        self._group_listbox.focus_set()

        mid_frame = ctk.CTkFrame(self, width=260)
        mid_frame.grid(row=2, column=1, sticky="ns", padx=2, pady=10)
        mid_frame.grid_rowconfigure(0, weight=0)
        mid_frame.grid_rowconfigure(1, weight=1)
        mid_frame.grid_columnconfigure(0, weight=1)
        mid_frame.grid_columnconfigure(1, weight=0)
        mid_frame.grid_propagate(False)

        self._group_header = ctk.CTkLabel(
            mid_frame, text="样本列表",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
        self._group_header.grid(row=0, column=0, columnspan=2,
                                sticky="ew", padx=8, pady=(5, 2))

        self._entry_listbox = DraggableListbox(
            mid_frame, draggable=True,
            on_reorder=self._on_entry_reorder,
            on_select=self._on_entry_select,
            bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#264f78", selectforeground="#ffffff",
            font=list_font, activestyle="none",
            exportselection=False,
            borderwidth=0, highlightthickness=0)
        self._entry_listbox.grid(row=1, column=0, sticky="nsew")

        es = ctk.CTkScrollbar(mid_frame, command=self._entry_listbox.yview)
        es.grid(row=1, column=1, sticky="ns")
        self._entry_listbox.configure(yscrollcommand=es.set)

        self._entry_listbox.bind("<Up>", self._on_key_up)
        self._entry_listbox.bind("<Down>", self._on_key_down)
        self._entry_listbox.bind("<Delete>",
                                 lambda e: self.audio_player.stop())
        self._entry_listbox.bind("<MouseWheel>", self._on_entry_wheel)

        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=2, column=2, sticky="nsew",
                         padx=(2, 10), pady=10)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=0)
        right_frame.grid_rowconfigure(2, weight=0)
        right_frame.grid_columnconfigure(0, weight=1)

        self._waveform = WaveformDisplay(right_frame, width=550, height=320)
        self._waveform.get_widget().grid(
            row=0, column=0, sticky="nsew", padx=5, pady=(5, 2))

        self._build_player_controls(right_frame)
        self._build_detail_panel(right_frame)

    def _build_player_controls(self, parent):
        ctrl_frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=3)
        ctrl_frame.grid_columnconfigure(1, weight=1)

        self._play_btn = ctk.CTkButton(
            ctrl_frame, text="播放", width=80, command=self._on_play_stop)
        self._play_btn.grid(row=0, column=0, padx=(0, 5))

        ctk.CTkButton(ctrl_frame, text="停止", width=60,
                      fg_color="transparent", border_width=1,
                      command=self._on_stop).grid(
            row=0, column=1, padx=5, sticky="w")

    def _build_detail_panel(self, parent):
        detail_frame = ctk.CTkFrame(parent)
        detail_frame.grid(row=2, column=0, sticky="ew",
                          padx=10, pady=(2, 10))
        detail_frame.grid_columnconfigure(1, weight=1)

        labels = [
            ("别名:", "detail_alias"),
            ("WAV:", "detail_wav"),
            ("offset:", "detail_offset"),
            ("consonant:", "detail_consonant"),
            ("cutoff:", "detail_cutoff"),
            ("preutterance:", "detail_preutterance"),
            ("overlap:", "detail_overlap"),
        ]
        self._detail_labels = {}
        for i, (label_text, key) in enumerate(labels):
            ctk.CTkLabel(detail_frame, text=label_text,
                         font=ctk.CTkFont(size=10),
                         text_color="#888888").grid(
                row=i, column=0, sticky="w", padx=8, pady=1)
            val = ctk.CTkLabel(detail_frame, text="",
                               font=ctk.CTkFont(size=10,
                                                family="Consolas"))
            val.grid(row=i, column=1, sticky="w", padx=8, pady=1)
            self._detail_labels[key] = val

        self._detail_labels["detail_wav"].configure(
            wraplength=180, justify="left")

    # ── data loading ─────────────────────────────────────────

    def _load_bank(self, folder_path: Path):
        self.oto_bank.load(folder_path)
        self._groups = self.oto_bank.get_groups()
        self._current_group = ""
        self._group_entries.clear()
        self._rebuild_group_list()

        name = self.oto_bank.character_name or folder_path.name
        self._name_label.configure(
            text=f"音源: {name}  ({len(self.oto_bank.entries)} 条目)")
        self._save_btn.configure(
            state="normal" if self.oto_bank.entries else "disabled")

    def _rebuild_group_list(self):
        self._group_listbox.delete(0, tk.END)
        query = self._search_var.get().strip().lower()
        visible = 0
        total = 0
        for base, count in self._groups:
            total += 1
            if query and query not in base.lower():
                continue
            roma = hiragana_to_romaji(base)
            if roma != base:
                label = f"  {base:<6s} ({count}) {roma}"
            else:
                label = f"  {base:<6s} ({count})"
            self._group_listbox.insert(tk.END, label)
            visible += 1
        self._update_count_label(visible, total)

    def _update_count_label(self, visible: int, total: int):
        if visible < total:
            self._count_label.configure(text=f"{visible}/{total}")
        else:
            self._count_label.configure(text=f"{total} 组")

    def refresh_after_combine(self, target_base: str):
        """拼字应用后刷新主窗口列表并定位到目标分组。"""
        self._groups = self.oto_bank.get_groups()
        self._rebuild_group_list()
        self._save_btn.configure(
            state="normal" if self.oto_bank.entries else "disabled")
        idx = self._get_filtered_group_index(target_base)
        if idx >= 0:
            self._group_listbox.selection_clear(0, tk.END)
            self._group_listbox.selection_set(idx)
            self._group_listbox.see(idx)
            self._on_group_select(idx)

    def _get_group_base_by_index(self, list_index: int) -> Optional[str]:
        query = self._search_var.get().strip().lower()
        idx = 0
        for base, count in self._groups:
            if query and query not in base.lower():
                continue
            if idx == list_index:
                return base
            idx += 1
        return None

    def _get_filtered_group_index(self, base: str) -> int:
        query = self._search_var.get().strip().lower()
        idx = 0
        for b, _ in self._groups:
            if query and query not in b.lower():
                continue
            if b == base:
                return idx
            idx += 1
        return -1

    def _populate_entry_list(self, base: str):
        self._current_group = base
        self._group_entries = self.oto_bank.get_group_entries(base)
        self._entry_listbox.delete(0, tk.END)
        for i, e in enumerate(self._group_entries):
            self._entry_listbox.insert(
                tk.END,
                f"  {i:>2d}  {e.alias:<8s}  {e.wav_filename}")
        self._group_header.configure(
            text=f"样本 — {base} ({len(self._group_entries)} 条)")

    # ── event handlers ───────────────────────────────────────

    def _on_group_select(self, list_index: int):
        base = self._get_group_base_by_index(list_index)
        if base is None:
            return
        self._group_listbox.selection_clear(0, tk.END)
        self._group_listbox.selection_set(list_index)
        self._group_listbox.see(list_index)
        self._populate_entry_list(base)
        if self._group_entries:
            self._entry_listbox.selection_clear(0, tk.END)
            self._entry_listbox.selection_set(0)
            self._display_entry(0)

    def _on_group_wheel(self, event):
        selection = self._group_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if event.delta > 0:
            new_idx = max(0, idx - 1)
        else:
            new_idx = min(self._group_listbox.size() - 1, idx + 1)
        if new_idx != idx:
            self._group_listbox.selection_clear(0, tk.END)
            self._group_listbox.selection_set(new_idx)
            self._group_listbox.see(new_idx)
            self._on_group_select(new_idx)
        return "break"

    def _on_group_right_click(self, event):
        index = self._group_listbox.nearest(event.y)
        if index < 0 or index >= self._group_listbox.size():
            return "break"

        self._group_listbox.selection_clear(0, tk.END)
        self._group_listbox.selection_set(index)
        self._on_group_select(index)

        base = self._get_group_base_by_index(index)
        if base is None:
            return "break"

        menu = tk.Menu(
            self,
            tearoff=0,
            bg="#2b2b2b",
            fg="#d4d4d4",
            activebackground="#264f78",
            activeforeground="#ffffff",
            borderwidth=0,
        )
        menu.add_command(
            label="改名", command=lambda: self._open_rename_dialog(base)
        )
        menu.add_command(
            label="合并到...", command=lambda: self._open_merge_dialog(base)
        )
        menu.post(event.x_root, event.y_root)
        return "break"

    def _open_rename_dialog(self, base: str):
        from .phoneme_group_dialog import RenameGroupDialog

        RenameGroupDialog(
            self, self.oto_bank, base, on_done=self._refresh_after_group_op
        )

    def _open_merge_dialog(self, base: str):
        from .phoneme_group_dialog import MergeGroupDialog

        MergeGroupDialog(
            self, self.oto_bank, base, on_done=self._refresh_after_group_op
        )

    def _refresh_after_group_op(self):
        self._groups = self.oto_bank.get_groups()
        self._rebuild_group_list()
        self._entry_listbox.delete(0, tk.END)
        self._group_entries.clear()
        self._current_group = ""
        self._waveform.clear()
        self._save_btn.configure(
            state="normal" if self.oto_bank.entries else "disabled"
        )

    def _on_entry_select(self, list_index: int):
        self._display_entry(list_index)

    def _on_entry_reorder(self, from_idx: int, to_idx: int):
        if not self._current_group:
            return
        self.oto_bank.reorder_group_entry(
            self._current_group, from_idx, to_idx)
        self._populate_entry_list(self._current_group)
        self._entry_listbox.selection_clear(0, tk.END)
        self._entry_listbox.selection_set(to_idx)
        self._entry_listbox.see(to_idx)
        self._display_entry(to_idx)

    def _on_entry_wheel(self, event):
        if not self._current_group or not self._group_entries:
            return "break"
        selection = self._entry_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if event.delta > 0:
            new_idx = max(0, idx - 1)
        else:
            new_idx = min(len(self._group_entries) - 1, idx + 1)
        if new_idx != idx:
            self._entry_listbox.selection_clear(0, tk.END)
            self._entry_listbox.selection_set(new_idx)
            self._entry_listbox.see(new_idx)
            self._display_entry(new_idx)
        return "break"

    def _display_entry(self, group_index: int):
        if not self._group_entries:
            return
        if not (0 <= group_index < len(self._group_entries)):
            return
        t0 = perf_trace.trace("gui:_display_entry")
        entry = self._group_entries[group_index]

        self._detail_labels["detail_alias"].configure(text=entry.alias)
        self._detail_labels["detail_wav"].configure(text=entry.wav_filename)
        self._detail_labels["detail_offset"].configure(
            text=f"{entry.offset:.1f} ms")
        self._detail_labels["detail_consonant"].configure(
            text=f"{entry.consonant:.1f} ms")
        self._detail_labels["detail_cutoff"].configure(
            text=f"{entry.cutoff:.1f} ms")
        self._detail_labels["detail_preutterance"].configure(
            text=f"{entry.preutterance:.1f} ms")
        self._detail_labels["detail_overlap"].configure(
            text=f"{entry.overlap:.1f} ms")

        if self.oto_bank.folder_path:
            wav_path = self.oto_bank.folder_path / entry.wav_filename
            if wav_path.exists():
                self._current_wav_path = wav_path
                self._current_offset = entry.offset
                self._current_cutoff = entry.cutoff
                self._waveform.load_with_oto(
                    wav_path, entry.offset, entry.consonant, entry.cutoff,
                    entry.overlap, entry.preutterance)
                self.audio_player.play_segment(
                    wav_path, entry.offset, entry.cutoff)
                self._play_btn.configure(text="暂停")
            else:
                self._current_wav_path = None
                self._waveform.clear()
        else:
            self._current_wav_path = None
            self._waveform.clear()
        perf_trace.end(t0, "gui:_display_entry")

    def _on_search(self):
        self._rebuild_group_list()
        self._entry_listbox.delete(0, tk.END)
        self._group_entries.clear()
        self._current_group = ""
        self._waveform.clear()

    def _on_open_combine_dialog(self):
        if not self.oto_bank.folder_path or not self._current_group:
            messagebox.showwarning(
                "未加载音源", "请先打开音源文件夹并选择一个分组")
            return
        PhonemeCombineDialog(self, self.oto_bank, self._current_group)

    def _on_open_batch_dialog(self):
        if not self.oto_bank.folder_path:
            messagebox.showwarning(
                "未加载音源", "请先打开音源文件夹")
            return
        BatchCombineDialog(self, self.oto_bank)

    def _on_open_folder(self):
        folder = filedialog.askdirectory(title="选择音源文件夹")
        if folder:
            self._load_bank(Path(folder))

    def _on_save(self):
        if not self.oto_bank.folder_path:
            return
        self.oto_bank.save()
        messagebox.showinfo(
            "保存成功",
            f"oto.ini 已保存到:\n{self.oto_bank.folder_path / 'oto.ini'}")

    def _on_undo(self):
        if not self.oto_bank.folder_path:
            return
        self._load_bank(self.oto_bank.folder_path)
        self._entry_listbox.delete(0, tk.END)
        self._group_entries.clear()
        self._current_group = ""
        self._waveform.clear()

    def _on_play_stop(self):
        if self.audio_player.is_playing:
            self.audio_player.stop()
            self._play_btn.configure(text="播放")
        elif self._current_wav_path:
            self.audio_player.play_segment(
                self._current_wav_path,
                self._current_offset, self._current_cutoff)
            self._play_btn.configure(text="暂停")

    def _on_space_preview(self, event=None):
        if self._is_typing_widget():
            return
        self._on_play_stop()
        return "break"

    def _on_stop(self):
        self.audio_player.stop()
        self._play_btn.configure(text="播放")

    def _on_key_up(self, event):
        if not self._current_group or not self._group_entries:
            return "break"
        selection = self._entry_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx > 0:
            self.oto_bank.reorder_group_entry(
                self._current_group, idx, idx - 1)
            self._populate_entry_list(self._current_group)
            new_idx = idx - 1
            self._entry_listbox.selection_clear(0, tk.END)
            self._entry_listbox.selection_set(new_idx)
            self._entry_listbox.see(new_idx)
            self._display_entry(new_idx)
        return "break"

    def _on_key_down(self, event):
        if not self._current_group or not self._group_entries:
            return "break"
        selection = self._entry_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx < len(self._group_entries) - 1:
            self.oto_bank.reorder_group_entry(
                self._current_group, idx, idx + 1)
            self._populate_entry_list(self._current_group)
            new_idx = idx + 1
            self._entry_listbox.selection_clear(0, tk.END)
            self._entry_listbox.selection_set(new_idx)
            self._entry_listbox.see(new_idx)
            self._display_entry(new_idx)
        return "break"

    def _on_group_key_up(self, event):
        selection = self._group_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx > 0:
            self._group_listbox.selection_clear(0, tk.END)
            self._group_listbox.selection_set(idx - 1)
            self._group_listbox.see(idx - 1)
            self._on_group_select(idx - 1)
        return "break"

    def _on_group_key_down(self, event):
        selection = self._group_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx < self._group_listbox.size() - 1:
            self._group_listbox.selection_clear(0, tk.END)
            self._group_listbox.selection_set(idx + 1)
            self._group_listbox.see(idx + 1)
            self._on_group_select(idx + 1)
        return "break"

    # ── global shortcuts ─────────────────────────────────────

    def _bind_global_shortcuts(self):
        self.bind_all('<Key-q>', self._on_prev_group)
        self.bind_all('<Key-e>', self._on_next_group)
        self.bind_all('<Key-w>', self._on_zoom_in)
        self.bind_all('<Key-s>', self._on_zoom_out)
        self.bind_all('<Key-a>', self._on_pan_left)
        self.bind_all('<Key-d>', self._on_pan_right)
        self.bind_all('<Key-1>', lambda e: self._on_set_marker("offset", e))
        self.bind_all('<Key-2>', lambda e: self._on_set_marker("overlap", e))
        self.bind_all('<Key-3>', lambda e: self._on_set_marker("preutterance", e))
        self.bind_all('<Key-4>', lambda e: self._on_set_marker("consonant", e))
        self.bind_all('<Key-5>', lambda e: self._on_set_marker("cutoff", e))
        self.bind_all('<space>', self._on_space_preview)

    def _is_typing_widget(self) -> bool:
        focus = self.focus_get()
        if focus is None:
            return False
        return focus.winfo_class() in (
            'Entry', 'Text', 'TEntry', 'TCombobox', 'Spinbox')

    def _on_prev_group(self, event=None):
        if self._is_typing_widget():
            return
        selection = self._group_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx > 0:
            self._group_listbox.selection_clear(0, tk.END)
            self._group_listbox.selection_set(idx - 1)
            self._group_listbox.see(idx - 1)
            self._on_group_select(idx - 1)
        return "break"

    def _on_next_group(self, event=None):
        if self._is_typing_widget():
            return
        selection = self._group_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        if idx < self._group_listbox.size() - 1:
            self._group_listbox.selection_clear(0, tk.END)
            self._group_listbox.selection_set(idx + 1)
            self._group_listbox.see(idx + 1)
            self._on_group_select(idx + 1)
        return "break"

    def _on_zoom_in(self, event=None):
        if self._is_typing_widget():
            return
        self._waveform.zoom_in()
        return "break"

    def _on_zoom_out(self, event=None):
        if self._is_typing_widget():
            return
        self._waveform.zoom_out()
        return "break"

    def _on_pan_left(self, event=None):
        if self._is_typing_widget():
            return
        self._waveform.pan_left()
        return "break"

    def _on_pan_right(self, event=None):
        if self._is_typing_widget():
            return
        self._waveform.pan_right()
        return "break"

    def _on_set_marker(self, marker: str, event=None):
        if self._is_typing_widget():
            return
        mouse_s = self._waveform.get_mouse_time()
        if mouse_s is None:
            return "break"

        selection = self._entry_listbox.curselection()
        if not selection:
            return "break"
        idx = selection[0]
        entry = self._group_entries[idx]

        new_ms = mouse_s * 1000.0

        if marker == "offset":
            entry.offset = new_ms
        elif marker == "overlap":
            entry.overlap = new_ms - entry.offset
        elif marker == "preutterance":
            entry.preutterance = new_ms - entry.offset
        elif marker == "consonant":
            entry.consonant = max(0.0, new_ms - entry.offset)
        elif marker == "cutoff":
            length = new_ms - entry.offset
            if length <= 0:
                length = 0.1
            entry.cutoff = -length

        self._detail_labels["detail_offset"].configure(
            text=f"{entry.offset:.1f} ms")
        self._detail_labels["detail_consonant"].configure(
            text=f"{entry.consonant:.1f} ms")
        self._detail_labels["detail_cutoff"].configure(
            text=f"{entry.cutoff:.1f} ms")
        self._detail_labels["detail_preutterance"].configure(
            text=f"{entry.preutterance:.1f} ms")
        self._detail_labels["detail_overlap"].configure(
            text=f"{entry.overlap:.1f} ms")

        if self._current_wav_path and self._current_wav_path.exists():
            self._current_offset = entry.offset
            self._current_cutoff = entry.cutoff
            self._waveform.update_params(
                entry.offset, entry.consonant, entry.cutoff,
                entry.overlap, entry.preutterance)

        return "break"

    def destroy(self):
        self.audio_player.cleanup()
        super().destroy()
