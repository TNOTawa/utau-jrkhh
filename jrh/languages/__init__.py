"""语言包注册表。"""

from __future__ import annotations

from ..core.errors import InvalidInputError
from .base import LanguagePack
from .pinyin import PinyinPack
from .romaji import RomajiPack

_PACKS: dict[str, LanguagePack] = {
    PinyinPack.name: PinyinPack(),
    RomajiPack.name: RomajiPack(),
}


def get_pack(name: str) -> LanguagePack:
    pack = _PACKS.get(name)
    if pack is None:
        raise InvalidInputError(f"未知语言包: {name!r}（可用: {', '.join(sorted(_PACKS))}）")
    return pack


def list_packs() -> list:
    return [
        {"name": p.name, "unit_system": p.unit_system}
        for p in sorted(_PACKS.values(), key=lambda p: p.name)
    ]
