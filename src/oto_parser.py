import collections
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PHONEME_BASE_RE = re.compile(r"^(.*?)(\d+)$")


def get_base_phoneme(alias: str) -> str:
    m = _PHONEME_BASE_RE.match(alias)
    if m:
        return m.group(1)
    return alias


@dataclass
class OtoEntry:
    wav_filename: str
    alias: str
    offset: float
    consonant: float
    cutoff: float
    preutterance: float
    overlap: float

    def to_line(self) -> str:
        return f"{self.wav_filename}={self.alias},{self.offset},{self.consonant},{self.cutoff},{self.preutterance},{self.overlap}"


class OtoBank:
    def __init__(self, folder_path: Optional[Path] = None):
        self.folder_path: Optional[Path] = folder_path
        self.entries: List[OtoEntry] = []
        self.character_name: str = ""
        self._encoding: str = "utf-8"

    def load(self, folder_path: Path):
        self.folder_path = folder_path
        self.entries.clear()
        self.character_name = ""
        self._load_character(folder_path / "character.txt")
        self._load_oto(folder_path / "oto.ini")

    def _load_character(self, path: Path):
        if not path.exists():
            return
        encoding = self._detect_encoding(path)
        with open(path, "r", encoding=encoding, errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("name="):
                    self.character_name = line[5:]
                    break

    _OTO_LINE_RE = re.compile(
        r"^(.+?)=(.+?),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)$"
    )

    @staticmethod
    def _detect_encoding(path: Path) -> str:
        raw = path.read_bytes()
        for enc in ("shift_jis", "cp932", "utf-8", "gbk"):
            try:
                raw.decode(enc)
                return enc
            except (UnicodeDecodeError, LookupError):
                continue
        return "utf-8"

    def _load_oto(self, path: Path):
        if not path.exists():
            return
        self._encoding = self._detect_encoding(path)
        text = path.read_bytes().decode(self._encoding, errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = self._OTO_LINE_RE.match(line)
            if match:
                entry = OtoEntry(
                    wav_filename=match.group(1),
                    alias=match.group(2),
                    offset=float(match.group(3)),
                    consonant=float(match.group(4)),
                    cutoff=float(match.group(5)),
                    preutterance=float(match.group(6)),
                    overlap=float(match.group(7)),
                )
                self.entries.append(entry)
        self._normalize_entries()

    def _normalize_entries(self):
        """加载后按别名编号对每组条目就地排序并重编号。"""
        group_indices = collections.defaultdict(list)
        for i, e in enumerate(self.entries):
            base = get_base_phoneme(e.alias)
            group_indices[base].append(i)

        def _sort_key(entry: OtoEntry) -> int:
            m = _PHONEME_BASE_RE.match(entry.alias)
            if m:
                return int(m.group(2))
            return 0

        for base, indices in group_indices.items():
            group_entries = [self.entries[i] for i in indices]
            group_entries.sort(key=_sort_key)
            for i, e in enumerate(group_entries):
                if i == 0:
                    e.alias = base
                else:
                    e.alias = f"{base}{i}"
            for idx, e in zip(indices, group_entries):
                self.entries[idx] = e

    def get_groups(self) -> List[Tuple[str, int]]:
        """返回 [(基础音素名, 条目数), ...]，按首次出现顺序排列"""
        seen: Dict[str, int] = {}
        order: List[str] = []
        for e in self.entries:
            base = get_base_phoneme(e.alias)
            if base not in seen:
                seen[base] = 0
                order.append(base)
            seen[base] += 1
        return [(b, seen[b]) for b in order]

    def get_group_entries(self, base_phoneme: str) -> List[OtoEntry]:
        """返回指定基础音素的所有条目，按全局顺序排列"""
        return [e for e in self.entries if get_base_phoneme(e.alias) == base_phoneme]

    def reorder_group_entry(self, base_phoneme: str, from_group_pos: int,
                            to_group_pos: int):
        """在指定组内调整条目顺序，同步更新全局列表并重编号别名"""
        base = get_base_phoneme(base_phoneme)
        group_entries = [e for e in self.entries if get_base_phoneme(e.alias) == base]
        if not group_entries:
            return
        if not (0 <= from_group_pos < len(group_entries)):
            return
        if not (0 <= to_group_pos < len(group_entries)):
            return

        entry = group_entries.pop(from_group_pos)
        group_entries.insert(to_group_pos, entry)

        for i, e in enumerate(group_entries):
            if i == 0:
                e.alias = base
            else:
                e.alias = f"{base}{i}"

        new_entries = []
        group_idx = 0
        for e in self.entries:
            if get_base_phoneme(e.alias) == base:
                new_entries.append(group_entries[group_idx])
                group_idx += 1
            else:
                new_entries.append(e)
        self.entries[:] = new_entries

    def rename_group(self, base_phoneme: str, new_base: str) -> bool:
        """将 base_phoneme 组的所有条目 alias 前缀替换为 new_base，按原顺序重编号。
        如果 new_base 已作为其他组的 base 存在，返回 False（由调用方处理合并）。"""
        base = get_base_phoneme(base_phoneme)
        new_base = get_base_phoneme(new_base)
        if base == new_base:
            return True

        existing_bases = {get_base_phoneme(e.alias) for e in self.entries}
        if new_base in existing_bases:
            return False

        for e in self.entries:
            if get_base_phoneme(e.alias) == base:
                e.alias = new_base

        group_entries = [e for e in self.entries if get_base_phoneme(e.alias) == new_base]
        for i, e in enumerate(group_entries):
            if i == 0:
                e.alias = new_base
            else:
                e.alias = f"{new_base}{i}"

        return True

    def merge_group(self, from_base: str, to_base: str):
        """将 from_base 组的所有条目 alias 改为 to_base 前缀，并重新编号 to_base 组。
        条目在全局列表中的物理顺序保持不变，只修改 alias。"""
        from_base = get_base_phoneme(from_base)
        to_base = get_base_phoneme(to_base)
        if from_base == to_base:
            return

        for e in self.entries:
            if get_base_phoneme(e.alias) == from_base:
                e.alias = to_base

        group_entries = [e for e in self.entries if get_base_phoneme(e.alias) == to_base]
        for i, e in enumerate(group_entries):
            if i == 0:
                e.alias = to_base
            else:
                e.alias = f"{to_base}{i}"

    def add_entry_to_group(self, entry: OtoEntry, base_phoneme: str):
        """将新条目插入到指定分组末尾，并重编号该分组所有别名。"""
        base = get_base_phoneme(base_phoneme)
        last_idx = -1
        for i, e in enumerate(self.entries):
            if get_base_phoneme(e.alias) == base:
                last_idx = i

        if last_idx >= 0:
            self.entries.insert(last_idx + 1, entry)
        else:
            self.entries.append(entry)

        group_entries = [e for e in self.entries if get_base_phoneme(e.alias) == base]
        for i, e in enumerate(group_entries):
            if i == 0:
                e.alias = base
            else:
                e.alias = f"{base}{i}"

        new_entries = []
        group_idx = 0
        for e in self.entries:
            if get_base_phoneme(e.alias) == base:
                new_entries.append(group_entries[group_idx])
                group_idx += 1
            else:
                new_entries.append(e)
        self.entries[:] = new_entries

    def save(self):
        if self.folder_path is None:
            return
        oto_path = self.folder_path / "oto.ini"
        with open(oto_path, "w", encoding=self._encoding) as f:
            for entry in self.entries:
                f.write(entry.to_line() + "\n")


# ── 平假名 → 罗马音 辅助 ───────────────────────────────────

_HIRAGANA_TO_ROMAJI = {
    # 清音
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "wo", "ん": "n",
    # 浊音
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    # 半浊音
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    # 拗音
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
    # 小写假名 / 促音
    "っ": "xtsu", "ゃ": "xya", "ゅ": "xyu", "ょ": "xyo",
    "ぁ": "xa", "ぃ": "xi", "ぅ": "xu", "ぇ": "xe", "ぉ": "xo",
    # 外来语 / 扩展音素
    "いぇ": "ye", "きぇ": "kye", "しぇ": "she", "ちぇ": "che",
    "にぇ": "nye", "ひぇ": "hye", "みぇ": "mye", "りぇ": "rye",
    "ぎぇ": "gye", "じぇ": "je", "びぇ": "bye", "ぴぇ": "pye",
    "うぁ": "wha", "うぃ": "wi", "うぇ": "we", "うぉ": "who",
    "くぁ": "kwa", "くぃ": "kwi", "くぇ": "kwe", "くぉ": "kwo",
    "すぁ": "swa", "すぃ": "swi", "すぇ": "swe", "すぉ": "swo",
    "つぁ": "tsa", "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso",
    "ぬぁ": "nwa", "ぬぃ": "nwi", "ぬぇ": "nwe", "ぬぉ": "nwo",
    "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo",
    "むぁ": "mwa", "むぃ": "mwi", "むぇ": "mwe", "むぉ": "mwo",
    "るぁ": "rwa", "るぃ": "rwi", "るぇ": "rwe", "るぉ": "rwo",
    "ぐぁ": "gwa", "ぐぃ": "gwi", "ぐぇ": "gwe", "ぐぉ": "gwo",
    "ずぁ": "zwa", "ずぃ": "zwi", "ずぇ": "zwe", "ずぉ": "zwo",
    "ぶぁ": "bwa", "ぶぃ": "bwi", "ぶぇ": "bwe", "ぶぉ": "bwo",
    "ぷぁ": "pwa", "ぷぃ": "pwi", "ぷぇ": "pwe", "ぷぉ": "pwo",
    "てぃ": "ti", "でぃ": "di", "てゅ": "tu", "でゅ": "du",
    "とぅ": "twu", "どぅ": "dwu",
}


def hiragana_to_romaji(text: str) -> str:
    """将平假名字符串转换为 Hepburn 式罗马音；非平假名字符原样保留。"""
    result = []
    i = 0
    while i < len(text):
        # 优先匹配 2 字符（拗音等）
        if i + 1 < len(text):
            two = text[i : i + 2]
            if two in _HIRAGANA_TO_ROMAJI:
                result.append(_HIRAGANA_TO_ROMAJI[two])
                i += 2
                continue
        ch = text[i]
        result.append(_HIRAGANA_TO_ROMAJI.get(ch, ch))
        i += 1
    return "".join(result)
