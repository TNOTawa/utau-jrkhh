import tkinter as tk
from tkinter import messagebox
from typing import Callable, List, Optional, Tuple

import customtkinter as ctk

from .draggable_list import _get_cjk_font, DraggableListbox
from .oto_parser import OtoBank, get_base_phoneme, hiragana_to_romaji


class RenameGroupDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        oto_bank: OtoBank,
        base: str,
        on_done: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.oto_bank = oto_bank
        self.base = base
        self.on_done = on_done

        self.title("分组改名")
        self.geometry("360x160")
        self.minsize(300, 140)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(frame, text="新组名:", font=ctk.CTkFont(size=12)).pack(
            anchor="w"
        )

        self._var = tk.StringVar(value=self.base)
        entry = ctk.CTkEntry(
            frame, textvariable=self._var, font=ctk.CTkFont(size=12)
        )
        entry.pack(fill="x", pady=(4, 12))
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)
        entry.bind("<Return>", lambda _e: self._on_confirm())
        entry.focus_set()

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(
            btn_frame, text="确认", width=80, command=self._on_confirm
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            btn_frame,
            text="取消",
            width=80,
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).pack(side="right", padx=(0, 4))

    def _on_confirm(self):
        new_base = self._var.get().strip()
        if not new_base:
            messagebox.showwarning("名称无效", "组名不能为空", parent=self)
            return
        if new_base == self.base:
            self.destroy()
            return

        # 检查目标名是否已存在
        existing_bases = {get_base_phoneme(e.alias) for e in self.oto_bank.entries}
        if get_base_phoneme(new_base) in existing_bases:
            if messagebox.askyesno(
                "目标组已存在",
                f"组 '{new_base}' 已存在，是否将当前组合并到该组？",
                parent=self,
            ):
                self.oto_bank.merge_group(self.base, new_base)
                if self.on_done:
                    self.on_done()
                self.destroy()
            return

        self.oto_bank.rename_group(self.base, new_base)
        if self.on_done:
            self.on_done()
        self.destroy()


class MergeGroupDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        oto_bank: OtoBank,
        from_base: str,
        on_done: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.oto_bank = oto_bank
        self.from_base = from_base
        self.on_done = on_done

        self.title("合并分组")
        self.geometry("320x420")
        self.minsize(280, 360)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            frame,
            text=f"将组 '{self.from_base}' 合并到:",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        # 分组列表
        list_frame = ctk.CTkFrame(frame)
        list_frame.pack(fill="both", expand=True, pady=(0, 12))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_columnconfigure(1, weight=0)

        list_font = _get_cjk_font(10)
        self._lb = DraggableListbox(
            list_frame,
            draggable=False,
            bg="#2b2b2b",
            fg="#d4d4d4",
            selectbackground="#264f78",
            selectforeground="#ffffff",
            font=list_font,
            activestyle="none",
            exportselection=False,
            borderwidth=0,
            highlightthickness=0,
        )
        self._lb.grid(row=0, column=0, sticky="nsew")

        sb = ctk.CTkScrollbar(list_frame, command=self._lb.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._lb.configure(yscrollcommand=sb.set)

        self._lb.bind("<Double-Button-1>", lambda _e: self._on_confirm())
        self._lb.bind("<Return>", lambda _e: self._on_confirm())

        # 填充列表
        self._groups: List[Tuple[str, int]] = []
        all_groups = self.oto_bank.get_groups()
        for base, count in all_groups:
            if base == self.from_base:
                continue
            self._groups.append((base, count))
            roma = hiragana_to_romaji(base)
            if roma != base:
                label = f"  {base:<6s} ({count}) {roma}"
            else:
                label = f"  {base:<6s} ({count})"
            self._lb.insert(tk.END, label)

        if self._lb.size() > 0:
            self._lb.selection_set(0)

        # 按钮
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(
            btn_frame, text="确认", width=80, command=self._on_confirm
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            btn_frame,
            text="取消",
            width=80,
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).pack(side="right", padx=(0, 4))

    def _on_confirm(self):
        selection = self._lb.curselection()
        if not selection:
            messagebox.showwarning("未选择", "请选择一个目标分组", parent=self)
            return

        idx = selection[0]
        if not (0 <= idx < len(self._groups)):
            return

        to_base = self._groups[idx][0]
        self.oto_bank.merge_group(self.from_base, to_base)
        if self.on_done:
            self.on_done()
        self.destroy()
