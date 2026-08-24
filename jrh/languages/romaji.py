"""日语（ja）罗马音语言包。

单位：Hepburn 式罗马音（逐假名一拍单位，如 こんにちは → ko n ni chi ha）。
假名表沿用现有 `src/oto_parser.py` 的数据（同一仓库 MIT 许可）。
近似替代：v0.1 为空（保守，不做跨音近似）。
"""

from __future__ import annotations

from ..core.errors import InvalidInputError

PACK_NAME = "jrh.ja-romaji"
UNIT_SYSTEM = "romaji-hepburn"

# 平假名 → 罗马音（2 字符组合优先；数据复制自 src/oto_parser.py）
_HIRAGANA_TO_ROMAJI: dict[str, str] = {
    "あ": "a",
    "い": "i",
    "う": "u",
    "え": "e",
    "お": "o",
    "か": "ka",
    "き": "ki",
    "く": "ku",
    "け": "ke",
    "こ": "ko",
    "さ": "sa",
    "し": "shi",
    "す": "su",
    "せ": "se",
    "そ": "so",
    "た": "ta",
    "ち": "chi",
    "つ": "tsu",
    "て": "te",
    "と": "to",
    "な": "na",
    "に": "ni",
    "ぬ": "nu",
    "ね": "ne",
    "の": "no",
    "は": "ha",
    "ひ": "hi",
    "ふ": "fu",
    "へ": "he",
    "ほ": "ho",
    "ま": "ma",
    "み": "mi",
    "む": "mu",
    "め": "me",
    "も": "mo",
    "や": "ya",
    "ゆ": "yu",
    "よ": "yo",
    "ら": "ra",
    "り": "ri",
    "る": "ru",
    "れ": "re",
    "ろ": "ro",
    "わ": "wa",
    "を": "wo",
    "ん": "n",
    "が": "ga",
    "ぎ": "gi",
    "ぐ": "gu",
    "げ": "ge",
    "ご": "go",
    "ざ": "za",
    "じ": "ji",
    "ず": "zu",
    "ぜ": "ze",
    "ぞ": "zo",
    "だ": "da",
    "ぢ": "ji",
    "づ": "zu",
    "で": "de",
    "ど": "do",
    "ば": "ba",
    "び": "bi",
    "ぶ": "bu",
    "べ": "be",
    "ぼ": "bo",
    "ぱ": "pa",
    "ぴ": "pi",
    "ぷ": "pu",
    "ぺ": "pe",
    "ぽ": "po",
    "きゃ": "kya",
    "きゅ": "kyu",
    "きょ": "kyo",
    "しゃ": "sha",
    "しゅ": "shu",
    "しょ": "sho",
    "ちゃ": "cha",
    "ちゅ": "chu",
    "ちょ": "cho",
    "にゃ": "nya",
    "にゅ": "nyu",
    "にょ": "nyo",
    "ひゃ": "hya",
    "ひゅ": "hyu",
    "ひょ": "hyo",
    "みゃ": "mya",
    "みゅ": "myu",
    "みょ": "myo",
    "りゃ": "rya",
    "りゅ": "ryu",
    "りょ": "ryo",
    "ぎゃ": "gya",
    "ぎゅ": "gyu",
    "ぎょ": "gyo",
    "じゃ": "ja",
    "じゅ": "ju",
    "じょ": "jo",
    "びゃ": "bya",
    "びゅ": "byu",
    "びょ": "byo",
    "ぴゃ": "pya",
    "ぴゅ": "pyu",
    "ぴょ": "pyo",
    "っ": "xtsu",
    "ゃ": "xya",
    "ゅ": "xyu",
    "ょ": "xyo",
    "ぁ": "xa",
    "ぃ": "xi",
    "ぅ": "xu",
    "ぇ": "xe",
    "ぉ": "xo",
    "いぇ": "ye",
    "きぇ": "kye",
    "しぇ": "she",
    "ちぇ": "che",
    "にぇ": "nye",
    "ひぇ": "hye",
    "みぇ": "mye",
    "りぇ": "rye",
    "ぎぇ": "gye",
    "じぇ": "je",
    "びぇ": "bye",
    "ぴぇ": "pye",
    "うぁ": "wha",
    "うぃ": "wi",
    "うぇ": "we",
    "うぉ": "who",
    "くぁ": "kwa",
    "くぃ": "kwi",
    "くぇ": "kwe",
    "くぉ": "kwo",
    "すぁ": "swa",
    "すぃ": "swi",
    "すぇ": "swe",
    "すぉ": "swo",
    "つぁ": "tsa",
    "つぃ": "tsi",
    "つぇ": "tse",
    "つぉ": "tso",
    "ぬぁ": "nwa",
    "ぬぃ": "nwi",
    "ぬぇ": "nwe",
    "ぬぉ": "nwo",
    "ふぁ": "fa",
    "ふぃ": "fi",
    "ふぇ": "fe",
    "ふぉ": "fo",
    "むぁ": "mwa",
    "むぃ": "mwi",
    "むぇ": "mwe",
    "むぉ": "mwo",
    "るぁ": "rwa",
    "るぃ": "rwi",
    "るぇ": "rwe",
    "るぉ": "rwo",
    "ぐぁ": "gwa",
    "ぐぃ": "gwi",
    "ぐぇ": "gwe",
    "ぐぉ": "gwo",
    "ずぁ": "zwa",
    "ずぃ": "zwi",
    "ずぇ": "zwe",
    "ずぉ": "zwo",
    "ぶぁ": "bwa",
    "ぶぃ": "bwi",
    "ぶぇ": "bwe",
    "ぶぉ": "bwo",
    "ぷぁ": "pwa",
    "ぷぃ": "pwi",
    "ぷぇ": "pwe",
    "ぷぉ": "pwo",
    "てぃ": "ti",
    "でぃ": "di",
    "てゅ": "tu",
    "でゅ": "du",
    "とぅ": "twu",
    "どぅ": "dwu",
}

_ROMAAJI_SET = frozenset(_HIRAGANA_TO_ROMAJI.values())
_KATA_TO_HIRA = {chr(0x30A1 + i): chr(0x3041 + i) for i in range(0x56)}


class RomajiPack:
    name = PACK_NAME
    unit_system = UNIT_SYSTEM

    def validate_unit(self, unit: str) -> bool:
        return unit in _ROMAAJI_SET

    def lyric_to_units(self, lyric: str) -> list[str]:
        if not isinstance(lyric, str) or not lyric.strip():
            raise InvalidInputError("歌词为空")
        out: list[str] = []
        i = 0
        while i < len(lyric):
            ch = lyric[i]
            if ch in _KATA_TO_HIRA:
                ch = _KATA_TO_HIRA[ch]
            if ch in ("ー", "・", " ", "\t", "\n"):
                raise InvalidInputError(f"歌词含不支持的日语字符: {ch!r}")
            # 优先匹配 2 字符（拗音/外来语音）
            if i + 1 < len(lyric):
                two = lyric[i : i + 2]
                if two in _HIRAGANA_TO_ROMAJI:
                    out.append(_HIRAGANA_TO_ROMAJI[two])
                    i += 2
                    continue
            out.append(self._convert_one(ch))
            i += 1
        return out

    def _convert_one(self, ch: str) -> str:
        if ch in _HIRAGANA_TO_ROMAJI:
            return _HIRAGANA_TO_ROMAJI[ch]
        raise InvalidInputError(f"无法转换的假名: {ch!r}")

    def final_vowel(self, unit: str) -> str | None:
        if not unit:
            return None
        last = unit[-1]
        return last if last in "aiueo" else None

    def initial_consonant(self, unit: str) -> str | None:
        if not unit:
            return None
        i = 0
        while i < len(unit) and unit[i] not in "aiueo":
            i += 1
        if i == 0 or i >= len(unit):
            return None  # 纯元音 / 全辅音（如ん 的 "n"）没有起音辅音
        return unit[:i]

    def is_helper(self, unit: str) -> bool:
        """小假名辅助拍（っ/ゃ/ゅ/ょ/ぁ…）在罗马音中映射为 x 前缀单位。"""
        return bool(unit) and unit.startswith("x")

    def vc_vowel(self, unit: str) -> str | None:
        if self.is_helper(unit):
            return None  # 辅助拍无真实元音（如 xtsu 末字母 u 是罗马化记号）
        return self.final_vowel(unit)

    def vc_consonant(self, unit: str) -> str | None:
        if self.is_helper(unit):
            return None
        cons = self.initial_consonant(unit)
        if cons is not None:
            return cons
        # 全辅音拍（ん 的 "n"）：整体作 C 侧（日语 CVVC 惯例，如 "a n"）
        if unit and self.final_vowel(unit) is None:
            return unit
        return None

    def substitutes(self, unit: str) -> list[str]:
        return []
