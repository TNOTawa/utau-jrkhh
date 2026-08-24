"""MFA japanese_mfa 音素 → jrh.ja-romaji 拍单位（罗马音）映射。

规则按 bank/shiqi17 实际数据核实（39 个 TextGrid 的音素全集与上下文序列）：
- 清化高元音 ɨ/ɨː：腭音（ɕ tɕ c ɲ ç）后读 i，其余读 u；长音拆两拍
- 清化元音 i̥→i、ɯ̥→u；长元音 aː/iː/ɯː/eː/oː 拆两拍（均分区间）
- 促音 kː/tː：持阻段独立成「促音拍」xtsu，除阻并入后接 CV（辅音时长按 0 估计）
- ん：ɴ/ɰ̃ → n（全段辅音）
- 腭化辅音 c/mʲ/bʲ/ɾʲ/ɡʲ：+i 为基表行，+其他元音插入 y（ki/kya/kyo…）
- spn 跳过；词尾孤辅音丢弃并告警；未知映射丢弃并告警（不污染母版 label）

纯 stdlib；与 jrh/core 无依赖（导入器专用）。
"""

from __future__ import annotations

from dataclasses import dataclass

# 基表：辅音 → {元音: 罗马音拍}（Hepburn）
_BASE: dict[str, dict[str, str]] = {
    "k": {"a": "ka", "i": "ki", "u": "ku", "e": "ke", "o": "ko"},
    "s": {"a": "sa", "i": "shi", "u": "su", "e": "se", "o": "so"},
    "t": {"a": "ta", "i": "chi", "u": "tsu", "e": "te", "o": "to"},
    "n": {"a": "na", "i": "ni", "u": "nu", "e": "ne", "o": "no"},
    "h": {"a": "ha", "i": "hi", "u": "fu", "e": "he", "o": "ho"},
    "m": {"a": "ma", "i": "mi", "u": "mu", "e": "me", "o": "mo"},
    "ɾ": {"a": "ra", "i": "ri", "u": "ru", "e": "re", "o": "ro"},
    "ɡ": {"a": "ga", "i": "gi", "u": "gu", "e": "ge", "o": "go"},
    "z": {"a": "za", "i": "ji", "u": "zu", "e": "ze", "o": "zo"},
    "d": {"a": "da", "i": "ji", "u": "zu", "e": "de", "o": "do"},
    "b": {"a": "ba", "i": "bi", "u": "bu", "e": "be", "o": "bo"},
    "p": {"a": "pa", "i": "pi", "u": "pu", "e": "pe", "o": "po"},
    "ɕ": {"a": "sha", "i": "shi", "u": "shu", "e": "she", "o": "sho"},
    "tɕ": {"a": "cha", "i": "chi", "u": "chu", "e": "che", "o": "cho"},
    "ts": {"u": "tsu"},
    "dz": {"a": "za", "i": "ji", "u": "zu", "e": "ze", "o": "zo"},
    "ɸ": {"a": "fa", "i": "fi", "u": "fu", "e": "fe", "o": "fo"},
    "ç": {"a": "hya", "i": "hi", "u": "hyu", "e": "hye", "o": "hyo"},
    "ɲ": {"a": "nya", "i": "ni", "u": "nyu", "e": "nye", "o": "nyo"},
    "w": {"a": "wa"},
    "j": {"a": "ya", "u": "yu", "e": "ye", "o": "yo"},
}

# 腭化辅音 → (基表音素键, 罗马音基字母)（+i 取基表行；+其他元音插入 y）
_PALATAL_BASE = {
    "c": ("k", "k"),
    "mʲ": ("m", "m"),
    "bʲ": ("b", "b"),
    "ɾʲ": ("ɾ", "r"),
    "ɡʲ": ("ɡ", "g"),
}

# MFA 音素层的元音符号 → 罗马音字母（注意 u 的音素符号是 ɯ）
_PHONE_VOWELS = frozenset("aiɯeo")
_VOWEL_ROMANJI = {"a": "a", "i": "i", "ɯ": "u", "e": "e", "o": "o"}
_LONG_VOWELS = {"aː": "a", "iː": "i", "ɯː": "u", "eː": "e", "oː": "o"}
_DEVOICED_VOWELS = {"i̥": "i", "ɯ̥": "u"}
# 清化高元音 ɨ 的读音按前接音素判定（腭音后为 i，否则 u）
_PALATAL_CONTEXT = frozenset({"ɕ", "tɕ", "c", "ɲ", "ç"})


@dataclass
class Phone:
    phone: str
    xmin: float
    xmax: float


@dataclass
class Mora:
    romaji: str
    xmin: float
    xmax: float
    consonant_end: float | None = None
    """辅音区终点（相对该拍区间；None = 纯元音拍，consonant 估计为 0）。"""


def _base_mora(consonant: str, vowel: str) -> str | None:
    if consonant in _PALATAL_BASE:
        base_phone, base_romaji = _PALATAL_BASE[consonant]
        if vowel == "i":
            return _BASE[base_phone]["i"]
        return f"{base_romaji}y{vowel}"
    row = _BASE.get(consonant)
    if row is None:
        return None
    return row.get(vowel)


def phones_to_moras(phones: list[Phone]) -> tuple[list[Mora], list[str]]:
    """音素序列 → 罗马音拍序列（长音/清化拆拍、促音独立拍、C+V 合并）。

    返回 (moras, warnings)；spn 静默跳过（计数并入警告汇总由调用方统计）。
    """
    moras: list[Mora] = []
    warnings: list[str] = []
    pending: tuple[str, float] | None = None  # 促音待除阻 (辅音, 持阻段终点)
    spn_count = 0

    def resolve_vowel(ph: Phone) -> str | None:
        lab = ph.phone
        if lab in _LONG_VOWELS:
            return _LONG_VOWELS[lab]
        if lab in _DEVOICED_VOWELS:
            return _DEVOICED_VOWELS[lab]
        if lab in _PHONE_VOWELS:
            return _VOWEL_ROMANJI[lab]
        return None

    def vowel_of_high(prev_phone: str) -> str:
        return "i" if prev_phone in _PALATAL_CONTEXT else "u"

    def emit_plain_vowel(ph: Phone, vowel: str) -> None:
        nonlocal pending
        if pending is not None:
            cons, cend = pending
            romaji = _base_mora(cons, vowel)
            if romaji is None:
                warnings.append(f"促音除阻映射失败: {cons}+{vowel} @{ph.xmin:.3f}s")
            else:
                moras.append(Mora(romaji, cend, ph.xmax, consonant_end=cend))
            pending = None
        else:
            moras.append(Mora(vowel, ph.xmin, ph.xmax))

    i = 0
    n = len(phones)
    while i < n:
        ph = phones[i]
        lab = ph.phone
        if lab == "spn":
            spn_count += 1
            i += 1
            continue
        if lab in ("ɴ", "ɰ̃"):
            moras.append(Mora("n", ph.xmin, ph.xmax, consonant_end=ph.xmax))
            pending = None
            i += 1
            continue
        if lab in ("kː", "tː"):
            if pending is not None:
                warnings.append(f"连续促音，前一持阻段丢弃 @{ph.xmin:.3f}s")
            moras.append(Mora("xtsu", ph.xmin, ph.xmax, consonant_end=ph.xmax))
            pending = (lab[0], ph.xmax)
            i += 1
            continue
        if lab in ("ɨ", "ɨː"):
            prev = phones[i - 1].phone if i > 0 else ""
            high_v = vowel_of_high(prev)
            if lab == "ɨː":
                mid = (ph.xmin + ph.xmax) / 2.0
                emit_plain_vowel(Phone(high_v, ph.xmin, mid), high_v)
                emit_plain_vowel(Phone(high_v, mid, ph.xmax), high_v)
            else:
                emit_plain_vowel(Phone(high_v, ph.xmin, ph.xmax), high_v)
            i += 1
            continue
        plain_v = resolve_vowel(ph)
        if plain_v is not None:
            if lab in _LONG_VOWELS:
                mid = (ph.xmin + ph.xmax) / 2.0
                emit_plain_vowel(Phone(plain_v, ph.xmin, mid), plain_v)
                emit_plain_vowel(Phone(plain_v, mid, ph.xmax), plain_v)
            else:
                emit_plain_vowel(Phone(plain_v, ph.xmin, ph.xmax), plain_v)
            i += 1
            continue
        # 辅音：与后一元音合成拍（长元音拆两拍）
        if pending is not None:
            warnings.append(f"促音持阻段后接辅音，持阻段丢弃 @{ph.xmin:.3f}s")
            pending = None
        if i + 1 < n:
            nxt = phones[i + 1]
            nxt_v = resolve_vowel(nxt)
            if nxt_v is not None:
                romaji = _base_mora(lab, nxt_v)
                if romaji is None:
                    warnings.append(f"未知音素映射: {lab}+{nxt_v} @{ph.xmin:.3f}s")
                    i += 2
                    continue
                if nxt.phone in _LONG_VOWELS:
                    mid = (nxt.xmin + nxt.xmax) / 2.0
                    moras.append(Mora(romaji, ph.xmin, mid, consonant_end=ph.xmax))
                    moras.append(Mora(nxt_v, mid, nxt.xmax))
                else:
                    moras.append(Mora(romaji, ph.xmin, nxt.xmax, consonant_end=ph.xmax))
                i += 2
                continue
            if nxt.phone in ("ɨ", "ɨː"):
                nxt_high_v = vowel_of_high(lab)
                romaji = _base_mora(lab, nxt_high_v)
                if romaji is None:
                    warnings.append(f"未知音素映射: {lab}+{nxt_high_v} @{ph.xmin:.3f}s")
                    i += 2
                    continue
                if nxt.phone == "ɨː":
                    mid = (nxt.xmin + nxt.xmax) / 2.0
                    moras.append(Mora(romaji, ph.xmin, mid, consonant_end=ph.xmax))
                    moras.append(Mora(nxt_high_v, mid, nxt.xmax))
                else:
                    moras.append(Mora(romaji, ph.xmin, nxt.xmax, consonant_end=ph.xmax))
                i += 2
                continue
        warnings.append(f"孤辅音丢弃: {lab} @{ph.xmin:.3f}s")
        i += 1
    if pending is not None:
        warnings.append("句尾促音持阻段无除阻，丢弃")
    if spn_count:
        warnings.append(f"跳过 spn × {spn_count}")
    return moras, warnings
