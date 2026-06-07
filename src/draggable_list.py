import tkinter as tk
from tkinter import font as tkfont


def _get_cjk_font(size: int = 10) -> tuple:
    available = set(tkfont.families())
    for f in ("Microsoft YaHei", "Meiryo", "MS Gothic", "SimHei", "Yu Gothic UI"):
        if f in available:
            return (f, size)
    return ("TkDefaultFont", size)


class DraggableListbox(tk.Listbox):

    def __init__(self, master, on_reorder=None, on_select=None, draggable=True, **kwargs):
        super().__init__(master, **kwargs)
        self._on_reorder_callback = on_reorder
        self._on_select_callback = on_select
        self._draggable = draggable
        self._drag_start_index = -1
        self._drag_target_index = -1
        self._drag_label: tk.Toplevel | None = None

        if draggable:
            self.bind("<Button-1>", self._on_drag_start)
            self.bind("<B1-Motion>", self._on_drag_motion)
            self.bind("<ButtonRelease-1>", self._on_drag_release)
        self.bind("<<ListboxSelect>>", self._on_selection)

    def _on_selection(self, event):
        if self._on_select_callback:
            selection = self.curselection()
            if selection:
                self._on_select_callback(selection[0])

    def _on_drag_start(self, event):
        if not self._draggable:
            return
        index = self.nearest(event.y)
        if index < 0 or index >= self.size():
            self._drag_start_index = -1
            return
        self._drag_start_index = index
        self._drag_target_index = index
        self.selection_clear(0, tk.END)
        self.selection_set(index)
        self._create_drag_label(event, index)
        self.grab_set()

    def _create_drag_label(self, event, index):
        item_text = self.get(index)
        self._drag_label = tk.Toplevel(self)
        self._drag_label.overrideredirect(True)
        self._drag_label.attributes("-alpha", 0.75)
        self._drag_label.attributes("-topmost", True)
        frame = tk.Frame(self._drag_label, bg="#3a3a3a", bd=1, relief=tk.SOLID)
        frame.pack(fill=tk.BOTH, expand=True)
        font_spec = _get_cjk_font(10)
        label = tk.Label(frame, text=item_text, bg="#3a3a3a", fg="#ffffff",
                         font=font_spec, padx=8, pady=2)
        label.pack()
        x = self.winfo_rootx() + event.x + 10
        y = self.winfo_rooty() + event.y - 10
        self._drag_label.geometry(f"+{x}+{y}")

    def _on_drag_motion(self, event):
        if not self._draggable or self._drag_start_index < 0:
            return
        if self._drag_label:
            x = self.winfo_rootx() + event.x + 10
            y = self.winfo_rooty() + event.y - 10
            self._drag_label.geometry(f"+{x}+{y}")
        target = self.nearest(event.y)
        if 0 <= target < self.size() and target != self._drag_target_index:
            self._drag_target_index = target
            self.selection_clear(0, tk.END)
            self.itemconfig(target, {"bg": "#3a5a4a"})

    def _on_drag_release(self, event):
        self.grab_release()
        if self._drag_label:
            self._drag_label.destroy()
            self._drag_label = None
        if not self._draggable or self._drag_start_index < 0:
            return
        target = self.nearest(event.y)
        if target < 0 or target >= self.size():
            target = self._drag_start_index
        for i in range(self.size()):
            self.itemconfig(i, {"bg": ""})
        if target != self._drag_start_index and self._on_reorder_callback:
            self._on_reorder_callback(self._drag_start_index, target)
        self._drag_start_index = -1
        self._drag_target_index = -1
