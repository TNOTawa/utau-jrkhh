"""MFA 日语音素 → 罗马音拍映射单元测试（用例取自真实 bank 上下文序列）。"""

from __future__ import annotations

from jrh.importers.mfa_ja import Phone, phones_to_moras


def _moras(phones: list[str]) -> list[str]:
    m, _ = phones_to_moras([Phone(p, 0.0, 1.0) for p in phones])
    return [x.romaji for x in m]


class TestBasicCv:
    def test_basic_rows(self):
        assert _moras(["k", "a"]) == ["ka"]
        assert _moras(["s", "a"]) == ["sa"]
        assert _moras(["t", "a"]) == ["ta"]
        assert _moras(["n", "a"]) == ["na"]
        assert _moras(["h", "a"]) == ["ha"]
        assert _moras(["m", "a"]) == ["ma"]
        assert _moras(["ɾ", "a"]) == ["ra"]
        assert _moras(["ɡ", "a"]) == ["ga"]
        assert _moras(["z", "a"]) == ["za"]
        assert _moras(["d", "a"]) == ["da"]
        assert _moras(["b", "a"]) == ["ba"]
        assert _moras(["w", "a"]) == ["wa"]
        assert _moras(["j", "a"]) == ["ya"]

    def test_u_and_irregular_rows(self):
        assert _moras(["s", "ɯ"]) == ["su"]
        assert _moras(["t", "ɯ"]) == ["tsu"]
        assert _moras(["h", "ɯ"]) == ["fu"]
        assert _moras(["ɸ", "ɯ"]) == ["fu"]
        assert _moras(["ɕ", "i"]) == ["shi"]
        assert _moras(["tɕ", "i"]) == ["chi"]
        assert _moras(["ç", "i"]) == ["hi"]
        assert _moras(["ts", "ɯ"]) == ["tsu"]
        assert _moras(["dz", "ɯ"]) == ["zu"]
        assert _moras(["z", "i"]) == ["ji"]
        assert _moras(["d", "i"]) == ["ji"]

    def test_palatalized(self):
        assert _moras(["c", "i"]) == ["ki"]
        assert _moras(["c", "a"]) == ["kya"]
        assert _moras(["c", "o"]) == ["kyo"]
        assert _moras(["c", "oː"]) == ["kyo", "o"]  # きょー = kyo + o（长音两拍）
        assert _moras(["mʲ", "i"]) == ["mi"]
        assert _moras(["mʲ", "a"]) == ["mya"]
        assert _moras(["ɾʲ", "o"]) == ["ryo"]
        assert _moras(["bʲ", "a"]) == ["bya"]


class TestDevoicedAndHighVowel:
    def test_devoiced_vowels(self):
        assert _moras(["i̥"]) == ["i"]
        assert _moras(["ɯ̥"]) == ["u"]

    def test_high_vowel_i_after_palatals(self):
        assert _moras(["ɕ", "ɨ"]) == ["shi"]
        assert _moras(["tɕ", "ɨ"]) == ["chi"]

    def test_high_vowel_u_after_sibilants(self):
        assert _moras(["s", "ɨ"]) == ["su"]
        assert _moras(["ts", "ɨ"]) == ["tsu"]
        assert _moras(["dz", "ɨ"]) == ["zu"]
        assert _moras(["z", "ɨ"]) == ["zu"]
        assert _moras(["j", "ɨ"]) == ["yu"]

    def test_standalone_high_vowel_defaults_u(self):
        assert _moras(["ɨ"]) == ["u"]
        assert _moras(["ɨː"]) == ["u", "u"]
        assert _moras(["ɕ", "ɨː"]) == ["shi", "i"]  # しー = shi + i（长音两拍）


class TestLongVowels:
    def test_long_vowel_splits_two_beats(self):
        assert _moras(["aː"]) == ["a", "a"]
        assert _moras(["iː"]) == ["i", "i"]
        assert _moras(["ɯː"]) == ["u", "u"]
        assert _moras(["eː"]) == ["e", "e"]
        assert _moras(["oː"]) == ["o", "o"]

    def test_long_vowel_after_consonant(self):
        assert _moras(["k", "aː"]) == ["ka", "a"]


class TestNAndGeminate:
    def test_n(self):
        assert _moras(["ɴ"]) == ["n"]
        assert _moras(["ɰ̃"]) == ["n"]

    def test_geminate(self):
        assert _moras(["kː", "a"]) == ["xtsu", "ka"]
        assert _moras(["tː", "o"]) == ["xtsu", "to"]
        assert _moras(["kː", "aː"]) == ["xtsu", "ka", "a"]


class TestSequenceAndDrops:
    def test_sequence(self):
        assert _moras(["k", "a", "spn", "t", "a"]) == ["ka", "ta"]

    def test_bare_consonant_dropped_with_warning(self):
        m, warns = phones_to_moras([Phone("k", 0.0, 1.0)])
        assert m == []
        assert any("孤辅音" in w for w in warns)

    def test_unknown_mapping_dropped_with_warning(self):
        m, warns = phones_to_moras([Phone("q", 0.0, 1.0), Phone("a", 1.0, 2.0)])
        assert m == []
        assert any("未知音素映射" in w for w in warns)

    def test_spn_counted(self):
        _m, warns = phones_to_moras([Phone("spn", 0.0, 1.0)])
        assert any("spn" in w for w in warns)
