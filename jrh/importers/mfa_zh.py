"""MFA mandarin_china_mfa 音素 → jrh.zh-pinyin 音节映射。

规则移植自参考插件 utau_oto_export.py 的生效路径（_extract_cv_pairs 中文分支 +
_syllable_to_pinyin + CHINESE_* 映射表），并按 DJUTAU bank 全量实测（459 TextGrid、
99 种音素符号、4005 个音节）迭代修正。实测标注精度：非法音节 3/4005（0.07%）。

实测关键规则（勿回退，均以真实数据为准）：
- 声调剥离：˥˦˧˨˩ 组合标记 + ˇˊˋ¯ + 清化环 ̥
- 介音 j/w/ɥ 是独立音素，不作声母；ʔ 是声母（时长真实）兼词首元音边界标记
- MFA 把介音吸收进声母：tɕ/ɕ + 非 i/y 元音 = j 介音（家/结/见/就/先，tɕ+ow=就 jiu）；
  tɕʷ/ɕʷ = 虚拟 ɥ（决 jue、雪 xue）；xʷ/kʷ/tʷ = 虚拟 w（花/国/多，同化 u 不插，
  工 = kʷ+u+ŋ → gong）；pʷ 同化 {u,o}（不/波）；pʲ/mʲ/nʲ/tʲ/ʎ/ɲ = 虚拟 j
  （连 lian、片 pian，同化 i 不插）；ɲ+y = 鼻化零声母（语 yu），n+y = nü（nv）
- 元音 y 后接 a/ɛ/e/ə = ɥ 介音形态（全 = tɕʰ y a n → quan）；y+i/u 不吞并（绿一 lv yi）
- 复韵母是单音素（aj/aw/ej/ow）；韵尾只有鼻音：ŋ 恒为韵尾（无 ŋ 声母）；
  n 仅接在能构成鼻韵母的元音后（a/ə/e/ɛ/i/y）且与元音同词（防「可能」→ kon）
- o+ŋ = eng（能/成/朋/正），u+ŋ = ong（中/工/动）；裸 o 多音映射：卷舌/舌根/
  齿龈塞音后 [ɤ]→e（这/可/热/得/特），n 后 [a]→a（那 = n+o），唇音 + 多余 w + o
  → 去 w（末 = m+w+o → mo、伯 = p+w+o → bo）
- 裸 ʐ̩→ri（日）、裸 z̩→zi（自）；成音节 z̩/ʐ̩ 随声母（zi/ci/si、zhi/chi/shi/ri）
- 儿化 ɻ/ɚ → er 独立音节（JRH 约定，不并入前音节）
- 零声母（无 ʔ）：consonant_end = 起点 + min(30ms, 元音首音素×0.2)
  （参考插件 L978-980；有原版条目的 Unit 以原版参数优先）
- spn/sil/<unk> 跳过；孤辅音/孤介音/无元音丢弃并告警（不污染母版 label）

接口与 mfa_ja.py 对齐：Phone / Mora / phones_to_moras(phones, word_ranges=None)。
纯 stdlib；与 jrh/core 无依赖（导入器专用）。
"""

from __future__ import annotations

from dataclasses import dataclass

_TONE_MARKS = "˥˦˧˨˩ˇˊˋ¯̥"

# 中文辅音集合（参考插件 CHINESE_CONSONANTS + DJUTAU 实测：xʷ ʎ pʲ mʲ nʲ tʷ tɕʷ ɕʷ）
_CONSONANT_SET = frozenset(
    {
        "p",
        "pʰ",
        "pʲ",
        "pʷ",
        "b",
        "m",
        "mʲ",
        "f",
        "t",
        "tʰ",
        "tʲ",
        "tʷ",
        "d",
        "n",
        "nʲ",
        "l",
        "ʎ",
        "k",
        "kʰ",
        "kʷ",
        "ɡ",
        "g",
        "ŋ",
        "x",
        "xʷ",
        "h",
        "tɕ",
        "tɕʰ",
        "tɕʷ",
        "dʑ",
        "ɕ",
        "ɕʷ",
        "ʑ",
        "ts",
        "tsʰ",
        "dz",
        "s",
        "z",
        "ʈʂ",
        "ʈʂʰ",
        "ɖʐ",
        "ʂ",
        "ʐ",
        "ɲ",
        "j",
        "w",
        "ɥ",
        "ʔ",
    }
)

# 中文元音集合（参考插件 CHINESE_VOWELS + aj）
_VOWEL_SET = frozenset(
    {
        "a",
        "o",
        "e",
        "i",
        "u",
        "y",
        "ü",
        "ə",
        "ɛ",
        "ɔ",
        "ɤ",
        "ɨ",
        "ʅ",
        "ʉ",
        "aj",
        "aw",
        "ej",
        "ow",
        "z̩",
        "ʐ̩",
        "ɻ",
        "ɚ",
    }
)
_VOWEL_STARTS = ("a", "o", "e", "i", "u", "y", "ü", "ə", "ɛ", "ɔ", "ɤ", "ɨ", "ʅ", "ʉ", "ɻ", "ɚ")

_CHINESE_MEDIALS = frozenset({"j", "w", "ɥ"})
# 实测：MFA 的复韵母是单音素（aj/aw/ej/ow），韵尾只有鼻音 n/ŋ
_CHINESE_CODAS = frozenset({"n", "ŋ"})
_SKIP_MARKS = frozenset({"", "SP", "AP", "<unk>", "spn", "sil"})

# 声母 → 拼音声母（参考插件 CHINESE_CONSONANT_TO_PINYIN + 实测扩展）
_CONSONANT_TO_PINYIN: dict[str, str] = {
    "p": "b",
    "pʰ": "p",
    "pʲ": "p",
    "pʷ": "b",
    "b": "b",
    "m": "m",
    "mʲ": "m",
    "f": "f",
    "t": "d",
    "tʰ": "t",
    "tʲ": "d",
    "tʷ": "d",
    "d": "d",
    "n": "n",
    "nʲ": "n",
    "l": "l",
    "ʎ": "l",
    "k": "g",
    "kʰ": "k",
    "kʷ": "g",
    "ɡ": "g",
    "g": "g",
    "x": "h",
    "xʷ": "h",
    "h": "h",
    "tɕ": "j",
    "tɕʰ": "q",
    "tɕʷ": "j",
    "dʑ": "j",
    "ɕ": "x",
    "ɕʷ": "x",
    "ʑ": "x",
    "ts": "z",
    "tsʰ": "c",
    "dz": "z",
    "s": "s",
    "z": "z",
    "ʈʂ": "zh",
    "ʈʂʰ": "ch",
    "ɖʐ": "zh",
    "ʂ": "sh",
    "ʐ": "r",
    "ɲ": "n",
    "ŋ": "",
    "j": "",
    "w": "",
    "ɥ": "",
    "ʔ": "",
}

# 腭化声母：基声母 + 虚拟 j 介音（同化元音 i 除外）
_PALATAL_CONS = {"pʲ", "mʲ", "nʲ", "tʲ", "ʎ", "ɲ"}
# 唇化声母：基声母 + 虚拟 w 介音（同化元音 u 除外；pʷ 另含 o）
_LABIAL_CONS = {"xʷ", "kʷ", "pʷ", "tʷ"}

# 元音 → 拼音韵母（参考插件 CHINESE_VOWEL_TO_PINYIN）
_VOWEL_TO_PINYIN: dict[str, str] = {
    "a": "a",
    "o": "o",
    "e": "e",
    "i": "i",
    "u": "u",
    "y": "v",
    "ü": "v",
    "ə": "e",
    "ɛ": "e",
    "ɔ": "o",
    "ɤ": "e",
    "ɨ": "i",
    "ʅ": "i",
    "ʉ": "u",
    "aj": "ai",
    "aw": "ao",
    "ej": "ei",
    "ow": "ou",
    "ai": "ai",
    "ao": "ao",
    "ei": "ei",
    "ou": "ou",
    "ja": "ia",
    "je": "ie",
    "jɛ": "ie",
    "jao": "iao",
    "jow": "iu",
    "ju": "iu",
    "ia": "ia",
    "ie": "ie",
    "iao": "iao",
    "iu": "iu",
    "wa": "ua",
    "wo": "uo",
    "wɔ": "uo",
    "wej": "ui",
    "waj": "uai",
    "ua": "ua",
    "uo": "uo",
    "ui": "ui",
    "uai": "uai",
    "ɥe": "ve",
    "ɥɛ": "ve",
    "ve": "ve",
    "an": "an",
    "en": "en",
    "ang": "ang",
    "eng": "eng",
    "ong": "ong",
    "in": "in",
    "ing": "ing",
    "ian": "ian",
    "iang": "iang",
    "iong": "iong",
    "uan": "uan",
    "un": "un",
    "uang": "uang",
    "ueng": "ueng",
    "van": "van",
    "vn": "vn",
    "z̩": "i",
    "ʐ̩": "i",
    "ɻ": "er",
    "ɚ": "er",
}


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
    """辅音区终点（相对该音节区间；None = 无辅音。零声母音节为
    xmin + min(30ms, 元音首音素×0.2) 的虚拟起点标记）。"""


def _strip_tone(phone: str) -> str:
    result = phone
    for mark in _TONE_MARKS:
        result = result.replace(mark, "")
    return result


def _is_vowel(lab: str) -> bool:
    if lab in _VOWEL_SET:
        return True
    if lab.startswith(_VOWEL_STARTS):
        return True
    return "z̩" in lab or "ʐ̩" in lab


def _plain_final(v: str, cd: str | None) -> str:
    """无介音韵母（v 为原始音素；DJUTAU 实测：o+ŋ→eng、u+ŋ→ong、y+n→vn）。"""
    if cd == "ŋ":
        if v == "o":
            return "eng"  # 实测：能/成/朋/正 = o+ŋ（MFA 的 eng）
        if v == "u":
            return "ong"  # 实测：中/工/动 = u+ŋ（MFA 的 ong）
        return _VOWEL_TO_PINYIN[v] + "ng"
    if cd == "n":
        if v == "y":
            return "vn"
        return _VOWEL_TO_PINYIN[v] + "n"
    if cd:
        return _VOWEL_TO_PINYIN[v] + cd
    return _VOWEL_TO_PINYIN[v]


def _j_final(v: str, cd: str | None) -> str:
    """j 介音（i 行韵母；v 为原始音素）。实测修正：
    - 同化元音 i → i/in/ing（京/今/机）
    - ɛ/e + n → ian（眼/见/先/年/连），ə + n → in（因）
    - ə + ŋ → ing（英），o + ŋ → iong（用）
    - ow → iu（就/六/有），aw → iao（教/聊/要）
    """
    if v == "i":
        return _plain_final("i", cd)
    if cd == "n":
        return "in" if v == "ə" else "ian"
    if cd == "ŋ":
        if v == "ə":
            return "ing"
        if v == "o":
            return "iong"
        if v == "u":
            return "iong"  # 用 = j+u+ŋ [jʊŋ]
        return "iang" if v == "a" else "i" + _VOWEL_TO_PINYIN[v] + "ng"
    if cd:
        return "i" + _VOWEL_TO_PINYIN[v] + cd
    if v == "a":
        return "ia"
    if v in ("e", "ɛ", "ə"):
        return "ie"
    if v == "aw":
        return "iao"
    if v == "ow":
        return "iu"
    return "i" + _VOWEL_TO_PINYIN[v]


def _w_final(v: str, cd: str | None) -> str:
    """w 介音（u 行韵母；v 为原始音素）。含同化元音 u（工/呼）的修正。"""
    if v == "u":
        return _plain_final("u", cd)  # u / ong（工 kʷ+u+ŋ）
    if cd == "n":
        return "uan" if v == "a" else "un"
    if cd == "ŋ":
        if v == "a":
            return "uang"
        return "ueng"  # 翁 w+ə+ŋ
    if cd:
        return "u" + _VOWEL_TO_PINYIN[v] + cd
    if v == "a":
        return "ua"
    if v == "o":
        return "uo"
    if v == "ej":
        return "ui"
    if v == "aj":
        return "uai"
    return "u" + _VOWEL_TO_PINYIN[v]


def _y_final(v: str, cd: str | None) -> str:
    """ɥ 介音（ü 行韵母；v 为原始音素）。实测：a/ɛ+n→van（元/卷），ə/y+n→vn（云/晕），
    u+ŋ→iong（用 = ɥ+u+ŋ [jʊŋ]）。"""
    if v == "y":
        return _plain_final("y", cd)  # v / vn（语/晕）
    if cd == "ŋ" and v == "u":
        return "iong"
    if cd == "n":
        return "van" if v in ("a", "ɛ") else "vn"
    if cd:
        return "v" + _VOWEL_TO_PINYIN[v] + cd
    if v in ("e", "ɛ", "ə"):
        return "ve"
    return "v" + _VOWEL_TO_PINYIN[v]


def _syllable_to_pinyin(c: str | None, m: str | None, v: str, cd: str | None) -> str | None:
    """(声母, 介音, 元音, 韵尾) → 无声调拼音音节（参考 _syllable_to_pinyin，实测修正）。"""
    # 裸舌尖/卷舌元音：日 ri、自 zi（r/z 被 MFA 吸收进元音符号）
    if c is None and cd is None:
        if v == "ʐ̩":
            return "ri"
        if v == "z̩":
            return "zi"
    v_py = _VOWEL_TO_PINYIN.get(v)
    if v_py is None:
        return None
    c_py = _CONSONANT_TO_PINYIN.get(c or "", "")
    # 实测（DJUTAU 词典形态）：裸 o（无韵尾、无介音）的多音映射——
    # 卷舌/舌根/齿龈塞音后为 [ɤ]→e（这/可/热/得/特），n 后为 [a]→a（那 = n+o）
    if m is None and cd is None and v == "o":
        if c_py in ("zh", "ch", "sh", "r", "g", "k", "h", "d", "t"):
            v = "ə"
            v_py = "e"
        elif c_py == "n":
            v = "a"
            v_py = "a"
    # 实测：唇音 + 多余 w + o（末 = m+w+o、伯 = p+w+o）→ 去 w 得 mo/bo
    if c_py in ("b", "p", "m", "f") and m == "w" and v == "o" and cd is None:
        m = None
    if m == "j":
        final = _j_final(v, cd)
    elif m == "w":
        final = _w_final(v, cd)
    elif m == "ɥ":
        final = _y_final(v, cd)
    else:
        final = _plain_final(v, cd)

    if not c_py:
        # 零声母：加 y/w/yu
        if final.startswith("i"):
            if final == "i":
                return "yi"
            if final in ("in", "ing"):
                return "y" + final
            if final in ("iu", "iou"):
                return "you"  # 有 yǒu（修正参考实现 iu→yu 的错误）
            return "y" + final[1:]
        if final.startswith("u"):
            if final == "u":
                return "wu"
            if final == "un":
                return "wen"
            if final in ("ui", "uei"):
                return "wei"  # 为 wèi（修正参考实现 ui→wi 的错误）
            if final in ("ueng", "ong"):
                return "weng"
            return "w" + final[1:]
        if final.startswith("v"):
            if final == "v":
                return "yu"
            return "yu" + final[1:]
        return final

    if c_py in ("j", "q", "x"):
        if final.startswith("v"):
            return c_py + "u" + final[1:]
        return c_py + final
    if c_py in ("n", "l"):
        return c_py + final
    if final.startswith("v"):
        return c_py + "u" + final[1:]
    return c_py + final


def phones_to_moras(
    phones: list[Phone], word_ranges: list[tuple[float, float]] | None = None
) -> tuple[list[Mora], list[str]]:
    """音素序列 → 拼音音节序列（切分 + 映射）。

    word_ranges：words 层词区间（可选）。提供时，韵尾 n/ŋ 只在与元音**同词**时
    吞入（参考插件 same_word，L989；防止「可能 = kʰ+o | n+o+ŋ」被误拼为 kon）。
    返回 (moras, warnings)；spn 静默跳过并计入警告汇总。
    """

    def same_word(a: Phone, b: Phone) -> bool:
        if not word_ranges:
            return True

        def region_of(ph: Phone) -> tuple[float, float] | None:
            mid = (ph.xmin + ph.xmax) / 2.0
            for start, end in word_ranges:
                if start <= mid < end:
                    return (start, end)
            return None

        return region_of(a) == region_of(b)

    moras: list[Mora] = []
    warnings: list[str] = []
    spn_count = 0

    def skip(lab: str) -> bool:
        return lab in _SKIP_MARKS

    i = 0
    n = len(phones)
    while i < n:
        ph = phones[i]
        lab = _strip_tone(ph.phone)
        if skip(lab):
            if lab == "spn":
                spn_count += 1
            i += 1
            continue
        start = ph.xmin
        c: str | None = None
        m: str | None = None
        cons_end: float | None = None

        # 1. 声母（介音 j/w/ɥ 不作为声母——MFA 中以独立介音音素出现）
        if lab in _CONSONANT_SET and lab not in _CHINESE_MEDIALS:
            c = lab
            cons_end = ph.xmax
            i += 1
            if i >= n:
                warnings.append(f"孤辅音丢弃: {lab} @{start:.3f}s")
                continue
            ph = phones[i]
            lab = _strip_tone(ph.phone)
            if skip(lab):
                warnings.append(f"辅音后无元音丢弃: {c} @{start:.3f}s")
                continue

        # 2. 介音（独立音素）
        if lab in _CHINESE_MEDIALS:
            m = lab
            i += 1
            if i >= n:
                warnings.append(f"孤介音丢弃: {lab} @{start:.3f}s")
                continue
            ph = phones[i]
            lab = _strip_tone(ph.phone)
            if skip(lab):
                warnings.append(f"介音后无元音丢弃: {m} @{start:.3f}s")
                continue

        # 3. 元音（必须）
        if not _is_vowel(lab):
            warnings.append(f"无元音音节丢弃: {lab} @{ph.xmin:.3f}s")
            i += 1
            continue
        v = lab
        vowel_phone_dur = ph.xmax - ph.xmin
        vowel_phone = ph
        i += 1

        # 4. 韵尾：ŋ 恒为韵尾（普通话无 ŋ 声母）；n 仅在能构成鼻韵母的元音后
        #    （a/ə/e/ɛ/i/y）且同词时吞入——「可能」的 o+n、词间 n 起音不得吞并
        cd: str | None = None
        if i < n:
            nxt = phones[i]
            nxt_lab = _strip_tone(nxt.phone)
            if nxt_lab == "ŋ" or (
                nxt_lab == "n"
                and v in ("a", "ə", "e", "ɛ", "i", "y")
                and same_word(vowel_phone, nxt)
            ):
                cd = nxt_lab
                i += 1

        # 实测修正：ɲ + y（ü）= 鼻化零声母滑音（语/于），非 n 声母（女为 n+y 形态）
        if c == "ɲ" and v == "y":
            c = None

        # 元音 y 后接 ü 系元音 = 实际是 ɥ 介音形态（全 = tɕʰ y a n 等）；
        # 仅限 a/ɛ/e/ə（y+i 是「绿一」lv+yi，不得吞并）
        if v == "y" and i < n:
            nxt_lab = _strip_tone(phones[i].phone)
            if nxt_lab in ("a", "ɛ", "e", "ə"):
                m = "ɥ"
                v = nxt_lab
                i += 1
                if i < n:
                    nxt = phones[i]
                    nxt_lab = _strip_tone(nxt.phone)
                    if nxt_lab == "ŋ" or (
                        nxt_lab == "n"
                        and v in ("a", "ə", "e", "ɛ")
                        and same_word(phones[i - 1], nxt)
                    ):
                        cd = nxt_lab
                        i += 1

        # 虚拟介音（实测：MFA 把介音吸收进声母/腭化声母）——同化元音不插；
        # 已有显式介音（m 非 None）时不覆盖
        c_py_probe = _CONSONANT_TO_PINYIN.get(c or "", "")
        if m is None:
            if c in ("tɕʷ", "ɕʷ") and v != "y":
                m = "ɥ"  # 决 jue、雪 xue（先于 j/q/x 判定）
            elif c in _PALATAL_CONS and v not in ("i", "y"):
                m = "j"  # pʲ/mʲ/nʲ/tʲ/ʎ/ɲ + 非 i/y 元音 → j 介音（连 lian、片 pian；虑 lv）
            elif c_py_probe in ("j", "q", "x") and v not in ("i", "y"):
                m = "j"  # tɕ/ɕ 吸收 i 介音：家/结/见/就/先
            elif c in _LABIAL_CONS:
                if c == "pʷ":
                    if v not in ("u", "o"):
                        m = "w"  # 播 bo / 不 bu 同化；其余（罕见）加 w
                elif v != "u":
                    m = "w"  # xʷ/kʷ/tʷ：花 hua、国 guo、多 duo；呼/古/都 同化

        py = _syllable_to_pinyin(c, m, v, cd)
        if py is None:
            warnings.append(
                f"音节映射失败: {'+'.join(x for x in (c, m, v, cd) if x)} @{start:.3f}s"
            )
            continue
        end = phones[i - 1].xmax
        if c is None:
            # 零声母：虚拟辅音 = min(30ms, 元音首音素时长×0.2)（参考插件 L978-980）
            cons_end = start + min(0.030, vowel_phone_dur * 0.2)
        moras.append(Mora(py, start, end, consonant_end=cons_end))

    if spn_count:
        warnings.append(f"跳过 spn × {spn_count}")
    return moras, warnings
