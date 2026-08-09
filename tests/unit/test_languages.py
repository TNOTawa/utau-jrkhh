"""语言包单元测试。"""

from __future__ import annotations

import pytest

from jrh.core.errors import InvalidInputError
from jrh.languages import get_pack, list_packs
from jrh.languages.pinyin import PinyinPack
from jrh.languages.romaji import RomajiPack


class TestPinyinPack:
    def setup_method(self):
        self.pack = PinyinPack()

    def test_syllable_count_and_content(self):
        # 标准 410 音节
        from jrh.languages.pinyin import _SYLLABLES

        assert len(_SYLLABLES) == 410
        for s in ("a", "ni", "hao", "zhuang", "lve", "nv", "wu", "yi", "er"):
            assert self.pack.validate_unit(s)

    def test_final_vowel(self):
        assert self.pack.final_vowel("hao") == "ao"
        assert self.pack.final_vowel("ni") == "i"
        assert self.pack.final_vowel("ya") == "a"
        assert self.pack.final_vowel("wu") == "u"
        assert self.pack.final_vowel("zhuang") == "ua"
        assert self.pack.final_vowel("a") == "a"

    def test_initial_consonant(self):
        assert self.pack.initial_consonant("hao") == "h"
        assert self.pack.initial_consonant("zhuang") == "zh"
        assert self.pack.initial_consonant("a") is None
        assert self.pack.initial_consonant("ya") == "y"
        assert self.pack.initial_consonant("wo") == "w"

    def test_substitutes_same_final(self):
        subs = self.pack.substitutes("hao")
        assert "hao" not in subs
        assert all(self.pack.final_vowel(s) == "ao" for s in subs)
        assert subs == sorted(subs)

    def test_lyric_to_units_greedy(self):
        assert self.pack.lyric_to_units("nihao") == ["ni", "hao"]
        assert self.pack.lyric_to_units("xian") == ["xian"]

    def test_lyric_to_units_cjk(self):
        assert self.pack.lyric_to_units("你好") == ["ni", "hao"]
        assert self.pack.lyric_to_units("你好啊") == ["ni", "hao", "a"]

    def test_lyric_to_units_unknown_char(self):
        with pytest.raises(InvalidInputError, match="未收录"):
            self.pack.lyric_to_units("齉")

    def test_lyric_to_units_unsegmentable(self):
        with pytest.raises(InvalidInputError, match="切分"):
            self.pack.lyric_to_units("nihaozz")

    def test_lyric_empty(self):
        with pytest.raises(InvalidInputError):
            self.pack.lyric_to_units("  ")


class TestRomajiPack:
    def setup_method(self):
        self.pack = RomajiPack()

    def test_lyric_to_units_mora(self):
        assert self.pack.lyric_to_units("こんにちは") == ["ko", "n", "ni", "chi", "ha"]
        assert self.pack.lyric_to_units("きゃ") == ["kya"]

    def test_katakana_normalized(self):
        assert self.pack.lyric_to_units("コンニチハ") == ["ko", "n", "ni", "chi", "ha"]

    def test_unsupported_chars(self):
        with pytest.raises(InvalidInputError):
            self.pack.lyric_to_units("アー")

    def test_final_vowel(self):
        assert self.pack.final_vowel("ko") == "o"
        assert self.pack.final_vowel("n") is None
        assert self.pack.final_vowel("a") == "a"

    def test_initial_consonant(self):
        assert self.pack.initial_consonant("ko") == "k"
        assert self.pack.initial_consonant("tsu") == "ts"
        assert self.pack.initial_consonant("a") is None
        assert self.pack.initial_consonant("n") is None

    def test_no_substitutes(self):
        assert self.pack.substitutes("ko") == []

    def test_validate_unit(self):
        assert self.pack.validate_unit("ko")
        assert not self.pack.validate_unit("xy")


class TestRegistry:
    def test_get_pack(self):
        assert get_pack("jrh.zh-pinyin").name == "jrh.zh-pinyin"
        assert get_pack("jrh.ja-romaji").name == "jrh.ja-romaji"

    def test_unknown_pack(self):
        with pytest.raises(InvalidInputError, match="未知语言包"):
            get_pack("nope")

    def test_list_packs_sorted(self):
        names = [p["name"] for p in list_packs()]
        assert names == sorted(names)
        assert "jrh.zh-pinyin" in names
