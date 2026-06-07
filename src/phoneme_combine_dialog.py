import os
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import List, Optional, Tuple

import customtkinter as ctk
import numpy as np
import soundfile as sf

from .audio_player import AudioPlayer
from .draggable_list import _get_cjk_font, DraggableListbox
from .oto_parser import OtoBank, OtoEntry, get_base_phoneme, hiragana_to_romaji
from .waveform_display import WaveformDisplay

# ── 日语罗马音辅音（按长度降序，保证最长优先匹配） ───────────────
_JAPANESE_CONSONANTS_DESC = [
    # 2字母辅音
    "ch", "sh", "ts",
    "ny", "ky", "gy", "py", "by", "my", "ry", "hy",
    "kw", "sw", "tw", "dw", "nw", "mw", "rw", "gw", "zw", "bw", "pw",
    "wh",
    # 单字母辅音
    "k", "g", "s", "z", "t", "d", "n", "h", "b", "p", "m", "r", "w", "y", "f", "j",
]

# 扩展音素辅音降级映射：找不到组合辅音分组时回退到单辅音
_CONSONANT_FALLBACK = {
    "pw": "p", "kw": "k", "sw": "s", "tw": "t", "dw": "d",
    "nw": "n", "mw": "m", "rw": "r", "gw": "g", "zw": "z", "bw": "b",
    "wh": "w",
    "ny": "n", "ky": "k", "gy": "g", "py": "p", "by": "b",
    "my": "m", "ry": "r", "hy": "h",
    "sh": "s", "ch": "t", "ts": "t",
}

# ── 罗马音 → 平假名（常见 CV 映射） ────────────────────────────
_ROMAJI_TO_HIRAGANA = {
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "sa": "さ", "shi": "し", "su": "す", "se": "せ", "so": "そ",
    "ta": "た", "chi": "ち", "tsu": "つ", "te": "て", "to": "と",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "fu": "ふ", "he": "へ", "ho": "ほ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "wa": "わ", "wo": "を", "n": "ん",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "za": "ざ", "ji": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "da": "だ", "di": "ぢ", "du": "づ", "de": "で", "do": "ど",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "kya": "きゃ", "kyu": "きゅ", "kyo": "きょ",
    "sha": "しゃ", "shu": "しゅ", "sho": "しょ",
    "cha": "ちゃ", "chu": "ちゅ", "cho": "ちょ",
    "nya": "にゃ", "nyu": "にゅ", "nyo": "にょ",
    "hya": "ひゃ", "hyu": "ひゅ", "hyo": "ひょ",
    "mya": "みゃ", "myu": "みゅ", "myo": "みょ",
    "rya": "りゃ", "ryu": "りゅ", "ryo": "りょ",
    "gya": "ぎゃ", "gyu": "ぎゅ", "gyo": "ぎょ",
    "ja": "じゃ", "ju": "じゅ", "jo": "じょ",
    "bya": "びゃ", "byu": "びゅ", "byo": "びょ",
    "pya": "ぴゃ", "pyu": "ぴゅ", "pyo": "ぴょ",
    # 外来语 / 扩展音素
    "ye": "いぇ", "kye": "きぇ", "she": "しぇ", "che": "ちぇ",
    "nye": "にぇ", "hye": "ひぇ", "mye": "みぇ", "rye": "りぇ",
    "gye": "ぎぇ", "je": "じぇ", "bye": "びぇ", "pye": "ぴぇ",
    "wha": "うぁ", "wi": "うぃ", "we": "うぇ", "who": "うぉ",
    "kwa": "くぁ", "kwi": "くぃ", "kwe": "くぇ", "kwo": "くぉ",
    "swa": "すぁ", "swi": "すぃ", "swe": "すぇ", "swo": "すぉ",
    "tsa": "つぁ", "tsi": "つぃ", "tse": "つぇ", "tso": "つぉ",
    "nwa": "ぬぁ", "nwi": "ぬぃ", "nwe": "ぬぇ", "nwo": "ぬぉ",
    "fa": "ふぁ", "fi": "ふぃ", "fe": "ふぇ", "fo": "ふぉ",
    "mwa": "むぁ", "mwi": "むぃ", "mwe": "むぇ", "mwo": "むぉ",
    "rwa": "るぁ", "rwi": "るぃ", "rwe": "るぇ", "rwo": "るぉ",
    "gwa": "ぐぁ", "gwi": "ぐぃ", "gwe": "ぐぇ", "gwo": "ぐぉ",
    "zwa": "ずぁ", "zwi": "ずぃ", "zwe": "ずぇ", "zwo": "ずぉ",
    "bwa": "ぶぁ", "bwi": "ぶぃ", "bwe": "ぶぇ", "bwo": "ぶぉ",
    "pwa": "ぷぁ", "pwi": "ぷぃ", "pwe": "ぷぇ", "pwo": "ぷぉ",
    "ti": "てぃ", "di": "でぃ", "tu": "てゅ", "du": "でゅ",
    "twu": "とぅ", "dwu": "どぅ",
}


def _romaji_to_hiragana(text: str) -> str:
    """将罗马音（小写）转换为平假名；无法转换的字符原样保留。"""
    result = []
    i = 0
    text = text.lower()
    while i < len(text):
        matched = False
        for length in (3, 2, 1):
            if i + length <= len(text):
                chunk = text[i : i + length]
                if chunk in _ROMAJI_TO_HIRAGANA:
                    result.append(_ROMAJI_TO_HIRAGANA[chunk])
                    i += length
                    matched = True
                    break
        if not matched:
            result.append(text[i])
            i += 1
    return "".join(result)


def split_japanese_cv(text: str) -> Tuple[Optional[str], Optional[str]]:
    """将别名拆分为日语辅音+元音；返回 (consonant, vowel)。"""
    romaji = hiragana_to_romaji(text).lower().strip()
    for c in _JAPANESE_CONSONANTS_DESC:
        if romaji.startswith(c):
            v = romaji[len(c) :]
            return c, v if v else None
    return None, romaji if romaji else None


def _get_cv_of_base(base: str) -> Tuple[Optional[str], Optional[str]]:
    """获取分组的辅音/元音拆分。"""
    return split_japanese_cv(base)


# ── list.txt 完整音素表（平假名 + 罗马音）──────────────────────
ALL_REQUIRED_PHONEMES = [
    # 清音
    ("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"),
    ("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"),
    ("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so"),
    ("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"), ("と", "to"),
    ("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no"),
    ("は", "ha"), ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho"),
    ("ま", "ma"), ("み", "mi"), ("む", "mu"), ("め", "me"), ("も", "mo"),
    ("や", "ya"), ("ゆ", "yu"), ("よ", "yo"),
    ("ら", "ra"), ("り", "ri"), ("る", "ru"), ("れ", "re"), ("ろ", "ro"),
    ("わ", "wa"), ("を", "wo"), ("ん", "n"),
    # 浊音
    ("が", "ga"), ("ぎ", "gi"), ("ぐ", "gu"), ("げ", "ge"), ("ご", "go"),
    ("ざ", "za"), ("じ", "ji"), ("ず", "zu"), ("ぜ", "ze"), ("ぞ", "zo"),
    ("だ", "da"), ("で", "de"), ("ど", "do"),
    ("ば", "ba"), ("び", "bi"), ("ぶ", "bu"), ("べ", "be"), ("ぼ", "bo"),
    # 半浊音
    ("ぱ", "pa"), ("ぴ", "pi"), ("ぷ", "pu"), ("ぺ", "pe"), ("ぽ", "po"),
    # 拗音
    ("きゃ", "kya"), ("きゅ", "kyu"), ("きょ", "kyo"),
    ("しゃ", "sha"), ("しゅ", "shu"), ("しょ", "sho"),
    ("ちゃ", "cha"), ("ちゅ", "chu"), ("ちょ", "cho"),
    ("にゃ", "nya"), ("にゅ", "nyu"), ("にょ", "nyo"),
    ("ひゃ", "hya"), ("ひゅ", "hyu"), ("ひょ", "hyo"),
    ("みゃ", "mya"), ("みゅ", "myu"), ("みょ", "myo"),
    ("りゃ", "rya"), ("りゅ", "ryu"), ("りょ", "ryo"),
    ("ぎゃ", "gya"), ("ぎゅ", "gyu"), ("ぎょ", "gyo"),
    ("じゃ", "ja"), ("じゅ", "ju"), ("じょ", "jo"),
    ("びゃ", "bya"), ("びゅ", "byu"), ("びょ", "byo"),
    ("ぴゃ", "pya"), ("ぴゅ", "pyu"), ("ぴょ", "pyo"),
    # 扩展音素
    ("いぇ", "ye"), ("きぇ", "kye"), ("しぇ", "she"), ("ちぇ", "che"),
    ("にぇ", "nye"), ("ひぇ", "hye"), ("みぇ", "mye"), ("りぇ", "rye"),
    ("ぎぇ", "gye"), ("じぇ", "je"), ("びぇ", "bye"), ("ぴぇ", "pye"),
    ("うぁ", "wha"), ("うぃ", "wi"), ("うぇ", "we"), ("うぉ", "who"),
    ("くぁ", "kwa"), ("くぃ", "kwi"), ("くぇ", "kwe"), ("くぉ", "kwo"),
    ("すぁ", "swa"), ("すぃ", "swi"), ("すぇ", "swe"), ("すぉ", "swo"),
    ("つぁ", "tsa"), ("つぃ", "tsi"), ("つぇ", "tse"), ("つぉ", "tso"),
    ("ぬぁ", "nwa"), ("ぬぃ", "nwi"), ("ぬぇ", "nwe"), ("ぬぉ", "nwo"),
    ("ふぁ", "fa"), ("ふぃ", "fi"), ("ふぇ", "fe"), ("ふぉ", "fo"),
    ("むぁ", "mwa"), ("むぃ", "mwi"), ("むぇ", "mwe"), ("むぉ", "mwo"),
    ("るぁ", "rwa"), ("るぃ", "rwi"), ("るぇ", "rwe"), ("るぉ", "rwo"),
    ("ぐぁ", "gwa"), ("ぐぃ", "gwi"), ("ぐぇ", "gwe"), ("ぐぉ", "gwo"),
    ("ずぁ", "zwa"), ("ずぃ", "zwi"), ("ずぇ", "zwe"), ("ずぉ", "zwo"),
    ("ぶぁ", "bwa"), ("ぶぃ", "bwi"), ("ぶぇ", "bwe"), ("ぶぉ", "bwo"),
    ("ぷぁ", "pwa"), ("ぷぃ", "pwi"), ("ぷぇ", "pwe"), ("ぷぉ", "pwo"),
    ("てぃ", "ti"), ("でぃ", "di"), ("てゅ", "tu"), ("でゅ", "du"),
    ("とぅ", "twu"), ("どぅ", "dwu"),
]


def combine_audio_entries(left: OtoEntry, right: OtoEntry,
                         output_path: Path, folder: Optional[Path],
                         parent=None) -> Optional[float]:
    """拼接两段音频并保存到 output_path；返回总时长(ms)或 None。"""
    if folder is None:
        return None
    left_wav = folder / left.wav_filename
    right_wav = folder / right.wav_filename
    if not left_wav.exists() or not right_wav.exists():
        return None

    try:
        c_audio, c_sr = sf.read(str(left_wav))
        v_audio, v_sr = sf.read(str(right_wav))
    except Exception as e:
        if parent is not None:
            messagebox.showwarning("读取音频失败", str(e), parent=parent)
        return None

    if c_audio.ndim > 1:
        c_audio = c_audio[:, 0]
    if v_audio.ndim > 1:
        v_audio = v_audio[:, 0]
    if c_sr != v_sr:
        if parent is not None:
            messagebox.showwarning(
                "采样率不一致",
                f"辅音源 {c_sr} Hz 与 元音源 {v_sr} Hz 不匹配", parent=parent)
        return None

    sr = c_sr
    c_start = int(left.offset / 1000 * sr)
    c_end = int((left.offset + left.consonant) / 1000 * sr)
    c_segment = c_audio[c_start:c_end]

    v_start = int((right.offset + right.consonant) / 1000 * sr)
    v_end = int((right.offset + abs(right.cutoff)) / 1000 * sr)
    v_segment = v_audio[v_start:v_end]

    if len(c_segment) == 0 or len(v_segment) == 0:
        if parent is not None:
            messagebox.showwarning("片段为空", "选中的音频片段为空", parent=parent)
        return None

    combined = _enhanced_crossfade(c_segment, v_segment, sr)
    sf.write(str(output_path), combined, sr)
    return len(combined) / sr * 1000.0


def _enhanced_crossfade(audio1: np.ndarray, audio2: np.ndarray,
                        sr: int, max_crossfade_ms: float = 30.0) -> np.ndarray:
    """
    增强版 crossfade 拼接，使过渡更流畅：
    1. 动态 crossfade 长度（较短片段的 30%，上限 30ms，下限 5ms）
    2. 全局 RMS 振幅匹配，避免音量跳变
    3. 余弦 fade（S-curve），消除线性 fade 的中间凹陷
    4. 端点 2ms fade-in / fade-out，去除边界咔哒声
    """
    if len(audio1) == 0 or len(audio2) == 0:
        return np.concatenate([audio1, audio2])

    max_cf = int(max_crossfade_ms / 1000 * sr)
    min_cf = int(5 / 1000 * sr)
    cf = int(min(len(audio1), len(audio2)) * 0.30)
    cf = max(min_cf, min(cf, max_cf))
    cf = min(cf, len(audio1) - 1, len(audio2) - 1)
    if cf < 2:
        return np.concatenate([audio1, audio2])

    # RMS 振幅匹配：对整段 audio2 施加增益，保证 crossfade 区域内外一致
    rms1 = np.sqrt(np.mean(audio1.astype(np.float64) ** 2))
    rms2 = np.sqrt(np.mean(audio2.astype(np.float64) ** 2))
    if rms2 > 1e-6 and rms1 > 1e-6:
        gain = rms1 / rms2
        gain = float(np.clip(gain, 0.5, 2.0))
        audio2 = audio2.astype(np.float64) * gain
        audio2 = audio2.astype(audio1.dtype)

    tail = audio1[-cf:]
    head = audio2[:cf]

    # 余弦 fade（S-curve），比线性更平滑
    t = np.linspace(0.0, 1.0, cf)
    fade_out = 0.5 * (1.0 + np.cos(np.pi * t))
    fade_in = 0.5 * (1.0 - np.cos(np.pi * t))

    crossfaded = tail.astype(np.float64) * fade_out + head.astype(np.float64) * fade_in
    crossfaded = crossfaded.astype(audio1.dtype)

    result = np.concatenate([audio1[:-cf], crossfaded, audio2[cf:]])

    # 端点 2ms fade-in / fade-out，去除首尾咔哒
    edge_ms = 2.0
    edge_samples = int(edge_ms / 1000 * sr)
    if edge_samples > 1 and len(result) > edge_samples * 4:
        fade_in_curve = np.linspace(0.0, 1.0, edge_samples).astype(result.dtype)
        fade_out_curve = np.linspace(1.0, 0.0, edge_samples).astype(result.dtype)
        result[:edge_samples] = result[:edge_samples] * fade_in_curve
        result[-edge_samples:] = result[-edge_samples:] * fade_out_curve

    return result


def format_group_label(base: str, count: int) -> str:
    roma = hiragana_to_romaji(base)
    if roma != base:
        return f"  {base:<6s} ({count}) {roma}"
    return f"  {base:<6s} ({count})"


class PhonemeCombineDialog(ctk.CTkToplevel):
    def __init__(self, parent, oto_bank: OtoBank, default_group: str):
        super().__init__(parent)
        self.parent = parent
        self.oto_bank = oto_bank
        self.default_group = default_group

        self.title("新增拼字")
        self.geometry("1300x860")
        self.minsize(1100, 700)
        self.transient(parent)
        self.grab_set()

        self._temp_files: List[str] = []
        self._audio_player = AudioPlayer()
        self._list_font = _get_cjk_font(10)

        # 解析默认 CV
        self._target_consonant, self._target_vowel = split_japanese_cv(default_group)

        # 缓存所有分组
        self._all_groups = self.oto_bank.get_groups()

        # 当前选中的条目
        self._left_selected_entry: Optional[OtoEntry] = None
        self._right_selected_entry: Optional[OtoEntry] = None
        self._left_entries: List[OtoEntry] = []
        self._right_entries: List[OtoEntry] = []

        self._build_ui()
        self._setup_defaults()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ────────────────────────────────────────────────

    def _build_ui(self):
        # 顶部输入区
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(top_frame, text="目标音素:",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(
            side="left", padx=(8, 4))

        self._alias_var = tk.StringVar(value=self.default_group)
        self._alias_entry = ctk.CTkEntry(
            top_frame, textvariable=self._alias_var, width=220,
            font=ctk.CTkFont(size=12))
        self._alias_entry.pack(side="left", padx=4)
        self._alias_entry.bind("<Return>", lambda e: self._on_alias_changed())
        self._alias_entry.bind("<FocusOut>", lambda e: self._on_alias_changed())

        ctk.CTkButton(top_frame, text="平假名 ↔ 罗马音", width=140,
                      command=self._on_toggle_script).pack(
            side="left", padx=8)

        self._cv_hint = ctk.CTkLabel(
            top_frame, text="", font=ctk.CTkFont(size=11),
            text_color="#888888")
        self._cv_hint.pack(side="left", padx=8)

        ctk.CTkLabel(top_frame, text="缺少:",
                     font=ctk.CTkFont(size=12)).pack(
            side="left", padx=(20, 4))

        self._missing_var = tk.StringVar(value="无")
        self._missing_menu = ctk.CTkOptionMenu(
            top_frame, variable=self._missing_var, width=150,
            values=["无"], command=self._on_missing_selected)
        self._missing_menu.pack(side="left", padx=4)

        # 中间左右两列
        mid_frame = ctk.CTkFrame(self)
        mid_frame.pack(fill="both", expand=True, padx=12, pady=6)
        mid_frame.grid_columnconfigure(0, weight=1)
        mid_frame.grid_columnconfigure(1, weight=1)
        mid_frame.grid_rowconfigure(0, weight=1)

        self._left_frame = self._build_side_panel(
            mid_frame, 0, "辅音来源", "_left")
        self._right_frame = self._build_side_panel(
            mid_frame, 1, "元音来源", "_right")

        # 底部按钮区
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=12, pady=(6, 12))

        ctk.CTkButton(bottom_frame, text="预览最终音频", width=140,
                      command=self._on_preview).pack(
            side="left", padx=8, pady=8)
        ctk.CTkButton(bottom_frame, text="应用", width=100,
                      fg_color="#2b8a3e", hover_color="#237032",
                      command=self._on_apply).pack(
            side="right", padx=8, pady=8)
        ctk.CTkButton(bottom_frame, text="取消", width=100,
                      fg_color="transparent", border_width=1,
                      command=self._on_close).pack(
            side="right", padx=4, pady=8)

    def _build_side_panel(self, parent, column: int, title: str, prefix: str):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=column, sticky="nsew",
                   padx=(0 if column == 0 else 6, 6 if column == 0 else 0))
        frame.grid_rowconfigure(1, weight=2)
        frame.grid_rowconfigure(3, weight=2)
        frame.grid_rowconfigure(4, weight=3)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=0)

        # 分组列表
        ctk.CTkLabel(frame, text=f"{title} — 分组",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=2,
                                       sticky="ew", padx=6, pady=(6, 2))

        group_lb = DraggableListbox(
            frame, draggable=False,
            on_select=getattr(self, f"_on{prefix}_group_select"),
            bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#264f78", selectforeground="#ffffff",
            font=self._list_font, activestyle="none",
            exportselection=False, borderwidth=0, highlightthickness=0)
        group_lb.grid(row=1, column=0, sticky="nsew", padx=(6, 0))
        setattr(self, f"{prefix}_group_listbox", group_lb)

        gs = ctk.CTkScrollbar(frame, command=group_lb.yview)
        gs.grid(row=1, column=1, sticky="ns", padx=(0, 6))
        group_lb.configure(yscrollcommand=gs.set)

        group_lb.bind("<MouseWheel>", getattr(self, f"_on{prefix}_group_wheel"))
        group_lb.bind("<Up>", getattr(self, f"_on{prefix}_group_key_up"))
        group_lb.bind("<Down>", getattr(self, f"_on{prefix}_group_key_down"))

        # 样本列表
        ctk.CTkLabel(frame, text="样本",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=2, column=0, columnspan=2,
                                       sticky="ew", padx=6, pady=(4, 2))

        entry_lb = DraggableListbox(
            frame, draggable=False,
            on_select=getattr(self, f"_on{prefix}_entry_select"),
            bg="#2b2b2b", fg="#d4d4d4",
            selectbackground="#264f78", selectforeground="#ffffff",
            font=self._list_font, activestyle="none",
            exportselection=False, borderwidth=0, highlightthickness=0)
        entry_lb.grid(row=3, column=0, sticky="nsew", padx=(6, 0))
        setattr(self, f"{prefix}_entry_listbox", entry_lb)

        es = ctk.CTkScrollbar(frame, command=entry_lb.yview)
        es.grid(row=3, column=1, sticky="ns", padx=(0, 6))
        entry_lb.configure(yscrollcommand=es.set)

        entry_lb.bind("<MouseWheel>", getattr(self, f"_on{prefix}_entry_wheel"))
        entry_lb.bind("<Up>", getattr(self, f"_on{prefix}_entry_key_up"))
        entry_lb.bind("<Down>", getattr(self, f"_on{prefix}_entry_key_down"))
        entry_lb.bind("<space>", lambda e: getattr(self, f"_on{prefix}_play_current")())

        # 波形显示
        wf = WaveformDisplay(frame, width=580, height=220)
        wf.get_widget().grid(row=4, column=0, columnspan=2,
                              sticky="nsew", padx=6, pady=(4, 6))
        setattr(self, f"{prefix}_waveform", wf)

        return frame

    # ── 初始化默认值 ───────────────────────────────────────────

    def _setup_defaults(self):
        self._rebuild_left_groups()
        self._rebuild_right_groups()
        self._update_cv_hint()
        self._refresh_missing_menu()

    def _get_missing_phonemes(self) -> List[Tuple[str, str]]:
        existing = {base for base, _ in self._all_groups}
        return [(h, r) for h, r in ALL_REQUIRED_PHONEMES if h not in existing]

    def _refresh_missing_menu(self):
        missing = self._get_missing_phonemes()
        if missing:
            values = [f"{hira} ({roma})" for hira, roma in missing]
            self._missing_menu.configure(values=values, state="normal")
            self._missing_var.set(values[0])
        else:
            self._missing_menu.configure(values=["无"], state="disabled")
            self._missing_var.set("无")

    def _on_missing_selected(self, value: str):
        if value == "无":
            return
        phoneme = value.split(" ")[0]
        self._alias_var.set(phoneme)
        self._on_alias_changed()

    # ── 分组列表重建 ───────────────────────────────────────────

    def _rebuild_left_groups(self):
        lb = self._left_group_listbox
        lb.delete(0, tk.END)
        self._left_groups: List[Tuple[str, int]] = []

        candidates = [self._target_consonant]
        fb = _CONSONANT_FALLBACK.get(self._target_consonant)
        if fb:
            candidates.append(fb)

        for base, count in self._all_groups:
            c, _ = _get_cv_of_base(base)
            if c in candidates:
                self._left_groups.append((base, count))
                lb.insert(tk.END, self._format_group_label(base, count))

        # 自动选中
        sel = 0
        for i, (base, _) in enumerate(self._left_groups):
            if base == self.default_group:
                sel = i
                break
        if lb.size() > 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(sel)
            lb.see(sel)
            self._on_left_group_select(sel)

    def _rebuild_right_groups(self):
        lb = self._right_group_listbox
        lb.delete(0, tk.END)
        self._right_groups: List[Tuple[str, int]] = []
        for base, count in self._all_groups:
            _, v = _get_cv_of_base(base)
            if v == self._target_vowel:
                self._right_groups.append((base, count))
                lb.insert(tk.END, self._format_group_label(base, count))

        # 自动选中：优先纯元音，其次默认分组，否则第0个
        sel = 0
        for i, (base, _) in enumerate(self._right_groups):
            c, v = _get_cv_of_base(base)
            if c is None and v == self._target_vowel:
                sel = i
                break
        else:
            for i, (base, _) in enumerate(self._right_groups):
                if base == self.default_group:
                    sel = i
                    break

        if lb.size() > 0:
            lb.selection_clear(0, tk.END)
            lb.selection_set(sel)
            lb.see(sel)
            self._on_right_group_select(sel)

    @staticmethod
    def _format_group_label(base: str, count: int) -> str:
        return format_group_label(base, count)

    # ── 事件处理（左侧） ───────────────────────────────────────

    def _on_left_group_select(self, index: int):
        if not (0 <= index < len(self._left_groups)):
            return
        base, _ = self._left_groups[index]
        self._left_entries = self.oto_bank.get_group_entries(base)
        self._populate_entry_list(self._left_entry_listbox, self._left_entries)
        if self._left_entries:
            self._left_entry_listbox.selection_clear(0, tk.END)
            self._left_entry_listbox.selection_set(0)
            self._left_entry_listbox.see(0)
            self._on_left_entry_select(0)

    def _on_left_entry_select(self, index: int):
        if not (0 <= index < len(self._left_entries)):
            return
        entry = self._left_entries[index]
        self._left_selected_entry = entry
        self._display_entry_on_side(entry, self._left_waveform)

    def _on_left_group_wheel(self, event):
        return self._handle_wheel(self._left_group_listbox, event,
                                   self._on_left_group_select)

    def _on_left_entry_wheel(self, event):
        return self._handle_wheel(self._left_entry_listbox, event,
                                   self._on_left_entry_select)

    def _on_left_group_key_up(self, event):
        return self._handle_key_up(self._left_group_listbox, self._on_left_group_select)

    def _on_left_group_key_down(self, event):
        return self._handle_key_down(self._left_group_listbox, self._on_left_group_select)

    def _on_left_entry_key_up(self, event):
        return self._handle_key_up(self._left_entry_listbox, self._on_left_entry_select)

    def _on_left_entry_key_down(self, event):
        return self._handle_key_down(self._left_entry_listbox, self._on_left_entry_select)

    def _on_left_play_current(self):
        if self._left_selected_entry and self.oto_bank.folder_path:
            wav = self.oto_bank.folder_path / self._left_selected_entry.wav_filename
            if wav.exists():
                self._audio_player.play_segment(
                    wav, self._left_selected_entry.offset,
                    self._left_selected_entry.cutoff)

    # ── 事件处理（右侧） ───────────────────────────────────────

    def _on_right_group_select(self, index: int):
        if not (0 <= index < len(self._right_groups)):
            return
        base, _ = self._right_groups[index]
        self._right_entries = self.oto_bank.get_group_entries(base)
        self._populate_entry_list(self._right_entry_listbox, self._right_entries)
        if self._right_entries:
            self._right_entry_listbox.selection_clear(0, tk.END)
            self._right_entry_listbox.selection_set(0)
            self._right_entry_listbox.see(0)
            self._on_right_entry_select(0)

    def _on_right_entry_select(self, index: int):
        if not (0 <= index < len(self._right_entries)):
            return
        entry = self._right_entries[index]
        self._right_selected_entry = entry
        self._display_entry_on_side(entry, self._right_waveform)

    def _on_right_group_wheel(self, event):
        return self._handle_wheel(self._right_group_listbox, event,
                                   self._on_right_group_select)

    def _on_right_entry_wheel(self, event):
        return self._handle_wheel(self._right_entry_listbox, event,
                                   self._on_right_entry_select)

    def _on_right_group_key_up(self, event):
        return self._handle_key_up(self._right_group_listbox, self._on_right_group_select)

    def _on_right_group_key_down(self, event):
        return self._handle_key_down(self._right_group_listbox, self._on_right_group_select)

    def _on_right_entry_key_up(self, event):
        return self._handle_key_up(self._right_entry_listbox, self._on_right_entry_select)

    def _on_right_entry_key_down(self, event):
        return self._handle_key_down(self._right_entry_listbox, self._on_right_entry_select)

    def _on_right_play_current(self):
        if self._right_selected_entry and self.oto_bank.folder_path:
            wav = self.oto_bank.folder_path / self._right_selected_entry.wav_filename
            if wav.exists():
                self._audio_player.play_segment(
                    wav, self._right_selected_entry.offset,
                    self._right_selected_entry.cutoff)

    # ── 通用列表交互辅助 ───────────────────────────────────────

    def _populate_entry_list(self, lb: DraggableListbox, entries: List[OtoEntry]):
        lb.delete(0, tk.END)
        for i, e in enumerate(entries):
            lb.insert(tk.END, f"  {i:>2d}  {e.alias:<8s}  {e.wav_filename}")

    def _display_entry_on_side(self, entry: OtoEntry, waveform: WaveformDisplay):
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

    def _handle_wheel(self, lb: DraggableListbox, event, callback):
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

    def _handle_key_up(self, lb: DraggableListbox, callback):
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

    def _handle_key_down(self, lb: DraggableListbox, callback):
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

    def _update_cv_hint(self):
        c = self._target_consonant or "∅"
        v = self._target_vowel or "∅"
        self._cv_hint.configure(text=f"辅音: {c}  |  元音: {v}")

    # ── 输入框与转换 ───────────────────────────────────────────

    def _on_alias_changed(self):
        text = self._alias_var.get().strip()
        if not text:
            return
        self._target_consonant, self._target_vowel = split_japanese_cv(text)
        self._update_cv_hint()
        self._rebuild_left_groups()
        self._rebuild_right_groups()

    def _on_toggle_script(self):
        text = self._alias_var.get().strip()
        if not text:
            return
        # 如果包含平假名，转为罗马音；否则转为平假名
        has_hira = any("\u3040" <= ch <= "\u309f" for ch in text)
        if has_hira:
            new_text = hiragana_to_romaji(text)
        else:
            new_text = _romaji_to_hiragana(text)
        if new_text and new_text != text:
            self._alias_var.set(new_text)
            self._on_alias_changed()

    # ── 音频拼接 ───────────────────────────────────────────────

    def _combine_audio(self, left: OtoEntry, right: OtoEntry,
                       output_path: Path) -> Optional[float]:
        total_ms = combine_audio_entries(
            left, right, output_path, self.oto_bank.folder_path, parent=self)
        return total_ms

    # ── 预览 ───────────────────────────────────────────────────

    def _on_preview(self):
        if self._left_selected_entry is None or self._right_selected_entry is None:
            messagebox.showwarning("未选择", "请先选择辅音样本和元音样本", parent=self)
            return

        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        total_ms = self._combine_audio(
            self._left_selected_entry, self._right_selected_entry,
            Path(tmp_path))
        if total_ms is None:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return

        self._temp_files.append(tmp_path)
        self._audio_player.play_segment(Path(tmp_path), 0.0, -total_ms)

    # ── 应用 ───────────────────────────────────────────────────

    def _on_apply(self):
        if self._left_selected_entry is None or self._right_selected_entry is None:
            messagebox.showwarning("未选择", "请先选择辅音样本和元音样本", parent=self)
            return

        alias = self._alias_var.get().strip()
        if not alias:
            messagebox.showwarning("别名无效", "请输入目标音素别名", parent=self)
            return

        folder = self.oto_bank.folder_path
        if not folder:
            return

        # 生成唯一文件名
        wav_name = self._get_unique_wav_name(alias)
        wav_path = folder / wav_name

        total_ms = self._combine_audio(
            self._left_selected_entry, self._right_selected_entry,
            wav_path)
        if total_ms is None:
            return

        # 构建 oto 参数（沿用 JinrikiHelper 逻辑）
        consonant = self._left_selected_entry.consonant
        preutterance = consonant
        overlap = self._left_selected_entry.overlap
        if overlap <= 0:
            overlap = consonant * 0.3

        entry = OtoEntry(
            wav_filename=wav_name,
            alias=alias,
            offset=0.0,
            consonant=round(consonant, 1),
            cutoff=round(-total_ms, 1),
            preutterance=round(preutterance, 1),
            overlap=round(overlap, 1),
        )

        self.oto_bank.add_entry_to_group(entry, alias)

        # 通知主窗口刷新
        if hasattr(self.parent, "refresh_after_combine"):
            self.parent.refresh_after_combine(get_base_phoneme(alias))

        messagebox.showinfo(
            "应用成功",
            f"已生成 {wav_name} 并添加到 oto.ini\n"
            f"别名: {entry.alias}\n"
            f"请记得点击主窗口「保存 oto.ini」写入磁盘。",
            parent=self)
        self._on_close()

    def _get_unique_wav_name(self, alias: str) -> str:
        folder = self.oto_bank.folder_path
        base_name = f"C{alias}.wav"
        if not (folder / base_name).exists():
            return base_name
        i = 1
        while True:
            name = f"C{alias}_{i}.wav"
            if not (folder / name).exists():
                return name
            i += 1

    # ── 关闭 ───────────────────────────────────────────────────

    def _on_close(self):
        self._audio_player.cleanup()
        for f in self._temp_files:
            try:
                os.remove(f)
            except Exception:
                pass
        self.destroy()
