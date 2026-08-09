"""OpenUtau 适配层：只做结果转换，不包含任何候选搜索逻辑。

Phoneme 结构对应 OpenUtau Phonemizer 输出契约：
- phoneme: 音源中的 oto alias（必须是编译产物里存在的别名）
- position_ms: 相对音符起点的位置（负值 = 音符起点之前，如 $T 过渡）
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.selection import SelectionResult


@dataclass
class Phoneme:
    phoneme: str
    position_ms: float

    def to_dict(self) -> dict:
        return {"phoneme": self.phoneme, "position_ms": self.position_ms}


def to_phonemes(result: SelectionResult) -> list[Phoneme]:
    """把选择结果转换为 OpenUtau Phoneme 列表（缺音 → 空列表）。"""
    return [Phoneme(p.alias, p.position_ms) for p in result.phonemes]
