"""批量拼字中文适配：语言识别 + presamp 短 ID 拆分 + 缺失分区（纯函数层）。"""

from __future__ import annotations

from src.batch_combine_dialog import (
    _zh_format_group_label,
    detect_bank_language,
    split_pinyin_cv,
    zh_partition_missing,
    zh_required_units,
)


class TestDetectBankLanguage:
    def test_kana_bank_is_ja(self):
        assert detect_bank_language(["か", "き", "く"]) == "ja"
        assert detect_bank_language(["か", "さ", "た", "な"]) == "ja"

    def test_pinyin_bank_is_zh(self):
        assert detect_bank_language(["hao", "ni", "ma"]) == "zh"
        assert detect_bank_language(["a", "yi", "zhi"]) == "zh"

    def test_empty_bank_defaults_zh(self):
        assert detect_bank_language([]) == "zh"

    def test_mixed_with_kana_prefers_zh_by_majority(self):
        # 三色あやか_CVVCHN 式混合标注：标准拼音过半 → zh
        assert detect_bank_language(["hao", "ni", "ma", "か", "き"]) == "zh"

    def test_mixed_with_kana_majority_is_ja(self):
        assert detect_bank_language(["hao", "か", "き", "く", "け"]) == "ja"


class TestSplitPinyinCv:
    """presamp 短 ID 拆分：与交付 presamp.ini / zh-cvv 音素器同源。"""

    def test_standard_syllable(self):
        assert split_pinyin_cv("hao") == ("h", "ao")
        assert split_pinyin_cv("shang") == ("sh", "ang")
        assert split_pinyin_cv("yue") == ("v", "e0")
        assert split_pinyin_cv("zhi") == ("zh", "ir")
        assert split_pinyin_cv("zi") == ("z", "i0")

    def test_semivowel_ids(self):
        assert split_pinyin_cv("lia") == ("ly", "a")
        assert split_pinyin_cv("hua") == ("hw", "a")
        assert split_pinyin_cv("wen") == ("w", "en")
        assert split_pinyin_cv("nv") == ("n", "v")

    def test_zero_initial(self):
        # 零声母：声母侧为 None → 无法 crossfade 拼接，必须落入跳过清单
        assert split_pinyin_cv("ang") == (None, "ang")
        assert split_pinyin_cv("a") == (None, "a")
        assert split_pinyin_cv("ou") == (None, "ou")

    def test_unenumerated(self):
        # presamp 未枚举（UTAU 标准拼写不收录）：两侧 None
        assert split_pinyin_cv("lve") == (None, None)
        assert split_pinyin_cv("yo") == (None, None)
        assert split_pinyin_cv("cei") == (None, None)
        assert split_pinyin_cv("chua") == (None, None)
        assert split_pinyin_cv("lo") == (None, None)
        assert split_pinyin_cv("nou") == (None, None)
        assert split_pinyin_cv("rua") == (None, None)


class TestZhPartitionMissing:
    """缺失分区：两侧无选项的音节绝不进入「可拼接」（否则总览永远待配置）。"""

    def test_partition_mixed(self):
        combinable, skipped = zh_partition_missing(["jiong", "juan", "eng", "lve", "cei", "hao"])
        assert [s for s, _c, _v in combinable] == ["jiong", "juan", "hao"]
        # eng：标准模板 [VOWEL] eng 行不含裸 eng（枚举外），与 lve/cei 同为
        # 「韵母未枚举」；ang/ou 这类枚举过的零声母才是「零声母」
        assert skipped == [
            ("eng", "韵母未枚举（presamp 无此组）"),
            ("lve", "韵母未枚举（presamp 无此组）"),
            ("cei", "韵母未枚举（presamp 无此组）"),
        ]

    def test_partition_all_unenumerated(self):
        combinable, skipped = zh_partition_missing(
            ["cei", "chua", "lo", "lve", "nou", "nve", "rua", "yo"]
        )
        assert combinable == []
        assert len(skipped) == 8
        assert all(reason == "韵母未枚举（presamp 无此组）" for _s, reason in skipped)

    def test_partition_zero_initial_reason(self):
        # ang/ou 在 [VOWEL] 已枚举（零声母）；eng 未枚举自身 → 韵母组缺失
        _combinable, skipped = zh_partition_missing(["ang", "ou", "eng"])
        assert skipped == [
            ("ang", "零声母（需原版录音）"),
            ("ou", "零声母（需原版录音）"),
            ("eng", "韵母未枚举（presamp 无此组）"),
        ]

    def test_partition_subsets_full_unit_set(self):
        missing = [s for s in zh_required_units() if s in {"eng", "lve", "nve", "jiong"}]
        combinable, skipped = zh_partition_missing(missing)
        assert [s for s, _c, _v in combinable] == ["jiong"]
        assert len(skipped) == 3


class TestZhRequiredUnits:
    def test_full_set(self):
        units = zh_required_units()
        assert len(units) == 410
        assert units == sorted(units)
        for s in ("a", "zhuang", "yue", "nv", "lve"):
            assert s in units

    def test_no_duplicates(self):
        assert len(set(zh_required_units())) == 410


class TestZhGroupLabel:
    def test_plain_label(self):
        assert _zh_format_group_label("hao", 3) == "  hao      (3)"
