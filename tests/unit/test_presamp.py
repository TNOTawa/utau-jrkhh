"""presamp 模板与短 ID 映射单元测试。"""

from __future__ import annotations

import pytest

from jrh.core.errors import DataError
from jrh.languages.presamp import (
    CONSONANT_IDS,
    PRESAMP_INI_TEXT,
    VOWEL_IDS,
    consonant_id_of,
    load_presamp_maps,
    syllables_of_consonant,
    syllables_of_vowel,
    vowel_id_of,
)


class TestTemplateBytes:
    def test_version_and_structure(self):
        text = PRESAMP_INI_TEXT
        assert text.startswith("[VERSION]\r\n1.7\r\n")
        assert "[VOWEL]" in text and "[CONSONANT]" in text
        assert "[PRIORITY]" in text and "[ENDTYPE]" in text and "[ENDFLAG]" in text
        # 标准模板：CRLF、无 BOM、66 行、无末尾换行（与生态标准逐字节一致）
        assert "\r\n" in text
        assert not text.startswith("\ufeff")
        assert len(text.splitlines()) == 66
        assert text.endswith("1") and not text.endswith("\n")
        assert len(text.encode("ascii")) == 3920

    def test_no_duplicate_sections(self):
        bad = "[VOWEL]\na=a=a=100\n[VOWEL]\nb=b=b=100\n"
        with pytest.raises(DataError, match="重复 section"):
            load_presamp_maps(bad)

    def test_duplicate_syllable_conflict(self):
        bad = "[VOWEL]\na=a=a=100\nb=b=a=100\n"
        with pytest.raises(DataError, match="重复且 ID 冲突"):
            load_presamp_maps(bad)


class TestShortIds:
    def test_id_inventory(self):
        assert (
            tuple(
                sorted(
                    [
                        "a",
                        "ai",
                        "an",
                        "ang",
                        "ao",
                        "e",
                        "e0",
                        "ei",
                        "en",
                        "en0",
                        "eng",
                        "er",
                        "i",
                        "in",
                        "ing",
                        "i0",
                        "ir",
                        "o",
                        "ong",
                        "ou",
                        "u",
                        "v",
                        "vn",
                    ]
                )
            )
            == VOWEL_IDS
        )
        assert "ly" in CONSONANT_IDS and "hw" in CONSONANT_IDS and "xw" in CONSONANT_IDS
        assert len(CONSONANT_IDS) == 31

    @pytest.mark.parametrize(
        ("syllable", "vowel", "consonant"),
        [
            ("an", "an", None),
            ("ang", "ang", None),
            ("ao", "ao", None),
            ("er", "er", None),
            ("zhi", "ir", "zh"),
            ("zi", "i0", "z"),
            ("ye", "e0", "y"),
            ("yan", "en0", "y"),
            ("jun", "vn", "j"),
            ("li", "i", "ly"),
            ("ni", "i", "ny"),
            ("mi", "i", "my"),
            ("xi", "i", "xy"),
            ("hua", "a", "hw"),
            ("shua", "a", "shw"),
            ("suan", "an", "sw"),
            ("xue", "e0", "xw"),
            ("yu", "v", "v"),
            ("ya", "a", "y"),
            ("wu", "u", "w"),
        ],
    )
    def test_mappings(self, syllable, vowel, consonant):
        assert vowel_id_of(syllable) == vowel
        assert consonant_id_of(syllable) == consonant

    def test_unenumerated_none(self):
        for s in ("yo", "lo", "den", "nou", "rua", "cei", "lve", "nve", "chua"):
            assert vowel_id_of(s) is None and consonant_id_of(s) is None

    def test_bare_zero_initial_vowels_unenumerated(self):
        # 标准 presamp 表不含裸零声母形态（i→yi、in→yin、o→wo…）；
        # 这些音节作 VC 元音侧时 OpenUtau 同样回退 → 一致跳过
        for s in ("i", "in", "ing", "eng", "o", "u"):
            assert vowel_id_of(s) is None

    def test_group_lookup(self):
        assert syllables_of_vowel("ir") == frozenset({"zhi", "chi", "shi", "ri"})
        assert syllables_of_vowel("i0") == frozenset({"zi", "ci", "si"})
        assert syllables_of_consonant("ly") == frozenset(
            {"lia", "liang", "liao", "lie", "lian", "li", "lin", "ling", "liu"}
        )
