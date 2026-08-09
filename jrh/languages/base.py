"""语言包接口定义。核心不判断单位（hao/ko/HH）的语言学意义。"""

from __future__ import annotations

from typing import Protocol


class LanguagePack(Protocol):
    """语言包接口（JRH_SPEC §7）。"""

    name: str
    unit_system: str

    def lyric_to_units(self, lyric: str) -> list[str]:
        """文本 → 录音单位列表。无法转换时必须抛异常（不得静默忽略）。"""

    def final_vowel(self, unit: str) -> str | None:
        """韵母/可延续元音（用于前元音匹配）；无则返回 None。"""

    def initial_consonant(self, unit: str) -> str | None:
        """起音辅音；纯元音返回 None。"""

    def substitutes(self, unit: str) -> list[str]:
        """语言包允许的有序近似替代单位（无则空列表）。"""

    def validate_unit(self, unit: str) -> bool:
        """该字符串是否为合法录音单位。"""
