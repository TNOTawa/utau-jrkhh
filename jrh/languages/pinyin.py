"""普通话（zh-CN）无声调拼音语言包。

音节表：标准普通话 410 音节（无声调，`v` 表示 ü），
经 pinyin-data 交叉核对（2026-08-07）。
"""

from __future__ import annotations

import re

from ..core.errors import InvalidInputError
from .presamp import consonant_id_of, vowel_id_of

PACK_NAME = "jrh.zh-pinyin"
UNIT_SYSTEM = "pinyin-toneless"

# 标准 410 音节（无声调；ü 记作 v）
_SYLLABLES = frozenset(
    [
        "a",
        "ai",
        "an",
        "ang",
        "ao",
        "e",
        "ei",
        "en",
        "eng",
        "er",
        "o",
        "ou",
        "ba",
        "bai",
        "ban",
        "bang",
        "bao",
        "bei",
        "ben",
        "beng",
        "bi",
        "bian",
        "biao",
        "bie",
        "bin",
        "bing",
        "bo",
        "bu",
        "pa",
        "pai",
        "pan",
        "pang",
        "pao",
        "pei",
        "pen",
        "peng",
        "pi",
        "pian",
        "piao",
        "pie",
        "pin",
        "ping",
        "po",
        "pou",
        "pu",
        "ma",
        "mai",
        "man",
        "mang",
        "mao",
        "me",
        "mei",
        "men",
        "meng",
        "mi",
        "mian",
        "miao",
        "mie",
        "min",
        "ming",
        "miu",
        "mo",
        "mou",
        "mu",
        "fa",
        "fan",
        "fang",
        "fei",
        "fen",
        "feng",
        "fo",
        "fou",
        "fu",
        "da",
        "dai",
        "dan",
        "dang",
        "dao",
        "de",
        "dei",
        "den",
        "deng",
        "di",
        "dian",
        "diao",
        "die",
        "ding",
        "diu",
        "dong",
        "dou",
        "du",
        "duan",
        "dui",
        "dun",
        "duo",
        "ta",
        "tai",
        "tan",
        "tang",
        "tao",
        "te",
        "teng",
        "ti",
        "tian",
        "tiao",
        "tie",
        "ting",
        "tong",
        "tou",
        "tu",
        "tuan",
        "tui",
        "tun",
        "tuo",
        "na",
        "nai",
        "nan",
        "nang",
        "nao",
        "ne",
        "nei",
        "nen",
        "neng",
        "ni",
        "nian",
        "niang",
        "niao",
        "nie",
        "nin",
        "ning",
        "niu",
        "nong",
        "nou",
        "nu",
        "nuan",
        "nuo",
        "nv",
        "nve",
        "la",
        "lai",
        "lan",
        "lang",
        "lao",
        "le",
        "lei",
        "leng",
        "li",
        "lia",
        "lian",
        "liang",
        "liao",
        "lie",
        "lin",
        "ling",
        "liu",
        "lo",
        "long",
        "lou",
        "lu",
        "luan",
        "lun",
        "luo",
        "lv",
        "lve",
        "ga",
        "gai",
        "gan",
        "gang",
        "gao",
        "ge",
        "gei",
        "gen",
        "geng",
        "gong",
        "gou",
        "gu",
        "gua",
        "guai",
        "guan",
        "guang",
        "gui",
        "gun",
        "guo",
        "ka",
        "kai",
        "kan",
        "kang",
        "kao",
        "ke",
        "kei",
        "ken",
        "keng",
        "kong",
        "kou",
        "ku",
        "kua",
        "kuai",
        "kuan",
        "kuang",
        "kui",
        "kun",
        "kuo",
        "ha",
        "hai",
        "han",
        "hang",
        "hao",
        "he",
        "hei",
        "hen",
        "heng",
        "hong",
        "hou",
        "hu",
        "hua",
        "huai",
        "huan",
        "huang",
        "hui",
        "hun",
        "huo",
        "ji",
        "jia",
        "jian",
        "jiang",
        "jiao",
        "jie",
        "jin",
        "jing",
        "jiong",
        "jiu",
        "ju",
        "juan",
        "jue",
        "jun",
        "qi",
        "qia",
        "qian",
        "qiang",
        "qiao",
        "qie",
        "qin",
        "qing",
        "qiong",
        "qiu",
        "qu",
        "quan",
        "que",
        "qun",
        "xi",
        "xia",
        "xian",
        "xiang",
        "xiao",
        "xie",
        "xin",
        "xing",
        "xiong",
        "xiu",
        "xu",
        "xuan",
        "xue",
        "xun",
        "zha",
        "zhai",
        "zhan",
        "zhang",
        "zhao",
        "zhe",
        "zhei",
        "zhen",
        "zheng",
        "zhi",
        "zhong",
        "zhou",
        "zhu",
        "zhua",
        "zhuai",
        "zhuan",
        "zhuang",
        "zhui",
        "zhun",
        "zhuo",
        "cha",
        "chai",
        "chan",
        "chang",
        "chao",
        "che",
        "chen",
        "cheng",
        "chi",
        "chong",
        "chou",
        "chu",
        "chua",
        "chuai",
        "chuan",
        "chuang",
        "chui",
        "chun",
        "chuo",
        "sha",
        "shai",
        "shan",
        "shang",
        "shao",
        "she",
        "shei",
        "shen",
        "sheng",
        "shi",
        "shou",
        "shu",
        "shua",
        "shuai",
        "shuan",
        "shuang",
        "shui",
        "shun",
        "shuo",
        "ran",
        "rang",
        "rao",
        "re",
        "ren",
        "reng",
        "ri",
        "rong",
        "rou",
        "ru",
        "rua",
        "ruan",
        "rui",
        "run",
        "ruo",
        "za",
        "zai",
        "zan",
        "zang",
        "zao",
        "ze",
        "zei",
        "zen",
        "zeng",
        "zi",
        "zong",
        "zou",
        "zu",
        "zuan",
        "zui",
        "zun",
        "zuo",
        "ca",
        "cai",
        "can",
        "cang",
        "cao",
        "ce",
        "cei",
        "cen",
        "ceng",
        "ci",
        "cong",
        "cou",
        "cu",
        "cuan",
        "cui",
        "cun",
        "cuo",
        "sa",
        "sai",
        "san",
        "sang",
        "sao",
        "se",
        "sen",
        "seng",
        "si",
        "song",
        "sou",
        "su",
        "suan",
        "sui",
        "sun",
        "suo",
        "ya",
        "yan",
        "yang",
        "yao",
        "ye",
        "yi",
        "yin",
        "ying",
        "yo",
        "yong",
        "you",
        "yu",
        "yuan",
        "yue",
        "yun",
        "wa",
        "wai",
        "wan",
        "wang",
        "wei",
        "wen",
        "weng",
        "wo",
        "wu",
    ]
)

# 声母表（zh/ch/sh 两字母优先；y/w 为滑音起音，UTAU 社区 CVVC 亦按声母处理）
_INITIALS = (
    "zh",
    "ch",
    "sh",
    "b",
    "p",
    "m",
    "f",
    "d",
    "t",
    "n",
    "l",
    "g",
    "k",
    "h",
    "j",
    "q",
    "x",
    "r",
    "z",
    "c",
    "s",
    "y",
    "w",
)
_VOWELS = frozenset("aoeiuv")

# 常用汉字 → 无声调拼音（常见读音；多音字取最常见一读，见 ADR/文档）
_CHAR_TABLE: dict[str, str] = {
    "你": "ni",
    "好": "hao",
    "啊": "a",
    "我": "wo",
    "是": "shi",
    "的": "de",
    "了": "le",
    "在": "zai",
    "和": "he",
    "有": "you",
    "不": "bu",
    "人": "ren",
    "大": "da",
    "中": "zhong",
    "国": "guo",
    "天": "tian",
    "上": "shang",
    "下": "xia",
    "说": "shuo",
    "话": "hua",
    "爱": "ai",
    "心": "xin",
    "想": "xiang",
    "要": "yao",
    "来": "lai",
    "去": "qu",
    "看": "kan",
    "听": "ting",
    "唱": "chang",
    "歌": "ge",
    "音": "yin",
    "乐": "yue",
    "会": "hui",
    "能": "neng",
    "没": "mei",
    "很": "hen",
    "都": "dou",
    "还": "hai",
    "就": "jiu",
    "这": "zhe",
    "那": "na",
    "什": "shen",
    "么": "me",
    "吗": "ma",
    "吧": "ba",
    "呢": "ne",
    "他": "ta",
    "她": "ta",
    "它": "ta",
    "们": "men",
    "一": "yi",
    "二": "er",
    "三": "san",
    "四": "si",
    "五": "wu",
    "六": "liu",
    "七": "qi",
    "八": "ba",
    "九": "jiu",
    "十": "shi",
    "小": "xiao",
    "学": "xue",
    "生": "sheng",
    "老": "lao",
    "师": "shi",
    "妈": "ma",
    "爸": "ba",
    "家": "jia",
    "真": "zhen",
}

_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_MAX_UNIT_LEN = 6  # 最长音节 zhuang


def all_units() -> frozenset[str]:
    """语言包全部合法录音单位（410 音节；供拼字缺失集合等整表遍历）。"""
    return _SYLLABLES


class PinyinPack:
    name = PACK_NAME
    unit_system = UNIT_SYSTEM

    def validate_unit(self, unit: str) -> bool:
        return unit in _SYLLABLES

    def lyric_to_units(self, lyric: str) -> list[str]:
        if not isinstance(lyric, str) or not lyric.strip():
            raise InvalidInputError("歌词为空")
        out: list[str] = []
        for token in lyric.split():
            if _CJK_RE.search(token):
                out.extend(self._convert_cjk(token))
            elif token.isascii():
                out.extend(self._convert_ascii(token))
            else:
                raise InvalidInputError(f"无法转换的歌词片段: {token!r}")
        return out

    def _convert_cjk(self, token: str) -> list[str]:
        out: list[str] = []
        for ch in token:
            if ch in _CHAR_TABLE:
                out.append(_CHAR_TABLE[ch])
            elif _CJK_RE.match(ch):
                raise InvalidInputError(
                    f"常用字表未收录汉字 {ch!r}（请直接输入拼音；字符表为语言包数据，可扩展）"
                )
            else:
                raise InvalidInputError(f"歌词包含非汉字字符: {ch!r}")
        return out

    def _convert_ascii(self, token: str) -> list[str]:
        s = token.lower()
        out: list[str] = []
        i = 0
        while i < len(s):
            matched = None
            for ln in range(min(_MAX_UNIT_LEN, len(s) - i), 0, -1):
                cand = s[i : i + ln]
                if cand in _SYLLABLES:
                    matched = cand
                    break
            if matched is None:
                raise InvalidInputError(
                    f"无法将拼音串切分为合法音节: {token!r}（在位置 {i} 处失败）"
                )
            out.append(matched)
            i += len(matched)
        return out

    def final_vowel(self, unit: str) -> str | None:
        if unit not in _SYLLABLES:
            return None
        for init in _INITIALS:
            if unit.startswith(init) and len(unit) > len(init):
                rest = unit[len(init) :]
                return self._trailing_vowels(rest)
        return self._trailing_vowels(unit)

    @staticmethod
    def _trailing_vowels(rest: str) -> str | None:
        # 最后一个元音起向前的连续元音段（近似韵腹；两侧同规则，保证匹配一致）
        last = -1
        for idx, ch in enumerate(rest):
            if ch in _VOWELS:
                last = idx
        if last < 0:
            return None
        start = last
        while start > 0 and rest[start - 1] in _VOWELS:
            start -= 1
        return rest[start : last + 1]

    def initial_consonant(self, unit: str) -> str | None:
        if unit not in _SYLLABLES:
            return None
        for init in _INITIALS:
            if unit.startswith(init) and len(unit) > len(init):
                return init
        return None

    def is_helper(self, unit: str) -> bool:
        return False

    def vc_vowel(self, unit: str) -> str | None:
        """CVVC VC 元音侧 ID = presamp 韵母短 ID（an/ang/ir/i0/e0/vn…）。

        与交付的 presamp.ini 同源（presamp.vowel_id_of），保证与 OpenUtau 内置
        zh-cvv 音素器（读同一份 [VOWEL] 表）请求的别名一致；未枚举音节返回 None
        （VC 不生成，见 JRH_SPEC §5）。注意与 final_vowel（韵母近似，丢 n/ng 韵尾）
        语义不同，两者各有用途。
        """
        return vowel_id_of(unit)

    def vc_consonant(self, unit: str) -> str | None:
        """CVVC VC 辅音侧 ID = presamp 声母短 ID（含 ly/xy/hw/ny/… 组合声母、y/w）。

        与 initial_consonant（普通声母拆分）不同：li→ly、hua→hw、xue→xw 等。
        零声母/未枚举返回 None。
        """
        return consonant_id_of(unit)

    def substitutes(self, unit: str) -> list[str]:
        """近似替代：同韵母（同韵腹）的不同音节，按字典序。"""
        if unit not in _SYLLABLES:
            return []
        fv = self.final_vowel(unit)
        if not fv:
            return []
        return [s for s in sorted(_SYLLABLES) if s != unit and self.final_vowel(s) == fv]
