"""合成人力V助手 bank 夹具（测试共用，确定性）。

结构：
- 段 1（song-001）：切片 0000（0.5s）+ 0001（0.5s），44.1kHz
- 段 2（song-002）：切片 0000（0.4s）
- TextGrid phones：
  - 001_0000: k [0,0.1) a [0.1,0.3) spn [0.3,0.5)   → ka
  - 001_0001: t [0,0.08) a [0.08,0.25) ɴ [0.25,0.4) "" [0.4,0.5)  → ta, n
  - 002_0000: s [0,0.12) ɨ [0.12,0.28) kː [0.28,0.36) a [0.36,0.4) → su, xtsu, ka
- 原版 oto.ini（song-*.wav + 拼字 Cき.wav；ka 组顺序故意倒置以测优先级保留）：
  ka@song-002_0000, ka@song-001_0000（文件里 002 在前）
"""

from __future__ import annotations

from pathlib import Path

from fixtures.wavs import write_sine_wav

TEXTGRIDS: dict[str, list[tuple[str, float, float]]] = {
    "song-001_0000": [
        ("k", 0.0, 0.1),
        ("a", 0.1, 0.3),
        ("spn", 0.3, 0.5),
    ],
    "song-001_0001": [
        ("t", 0.0, 0.08),
        ("a", 0.08, 0.25),
        ("ɴ", 0.25, 0.4),
        ("", 0.4, 0.5),
    ],
    "song-002_0000": [
        ("s", 0.0, 0.12),
        ("ɨ", 0.12, 0.28),
        ("kː", 0.28, 0.36),
        ("a", 0.36, 0.4),
    ],
}

# 原版 oto.ini 文本（条目顺序即优先级；ka 组故意倒序）
OTO_TEXT = """# 原版音源 oto.ini（含注释行，验证逐字节保留）
song-002_0000.wav=ka,280.0,120.0,-120.0,120.0,36.0
song-001_0000.wav=ka,0.0,100.0,-300.0,100.0,30.0
song-001_0001.wav=ta,80.0,80.0,-170.0,80.0,24.0
song-001_0001.wav=n,250.0,150.0,-150.0,150.0,45.0
song-002_0000.wav=su,0.0,120.0,-280.0,120.0,36.0
Cき.wav=き,0.0,40.0,-200.0,40.0,12.0
"""


def _tg_text(name: str, intervals: list[tuple[str, float, float]]) -> str:
    lines = [
        'File type = "ooTextFile"',
        'Object class = "TextGrid"',
        "",
        "xmin = 0",
        f"xmax = {intervals[-1][2]}",
        "tiers? <exists>",
        "size = 2",
        "item []:",
        "    item [1]:",
        '        class = "IntervalTier"',
        '        name = "words"',
        "        xmin = 0",
        f"        xmax = {intervals[-1][2]}",
        "        intervals: size = 1",
        "        intervals [1]:",
        "            xmin = 0.0",
        f"            xmax = {intervals[-1][2]}",
        '            text = "dummy"',
        "    item [2]:",
        '        class = "IntervalTier"',
        '        name = "phones"',
        "        xmin = 0",
        f"        xmax = {intervals[-1][2]}",
        f"        intervals: size = {len(intervals)}",
    ]
    for i, (text, xmin, xmax) in enumerate(intervals, start=1):
        lines.append(f"        intervals [{i}]:")
        lines.append(f"            xmin = {xmin}")
        lines.append(f"            xmax = {xmax}")
        lines.append(f'            text = "{text}"')
    return "\n".join(lines) + "\n"


def build_henki_bank(root: Path) -> dict[str, Path]:
    """构造 bank 目录 + 原版音源目录，返回 {bank_dir, oto_dir}。"""
    root = Path(root)
    bank_dir = root / "bank" / "henki_bank"
    oto_dir = root / "original_bank"
    (bank_dir / "slices").mkdir(parents=True)
    (bank_dir / "textgrid").mkdir(parents=True)
    oto_dir.mkdir(parents=True)

    (bank_dir / "meta.json").write_text(
        '{"source_name": "fixture", "language": "japanese"}\n', encoding="utf-8"
    )

    durations = {"song-001_0000": 0.5, "song-001_0001": 0.5, "song-002_0000": 0.4}
    for name, seconds in durations.items():
        write_sine_wav(bank_dir / "slices" / f"{name}.wav", 44100, seconds, 8000, 440.0)
        (bank_dir / "slices" / f"{name}.lab").write_text("", encoding="utf-8")
        (bank_dir / "textgrid" / f"{name}.TextGrid").write_text(
            _tg_text(name, TEXTGRIDS[name]), encoding="utf-8"
        )
        # 原版音源目录里的同名 wav（导出时原样拷贝用）
        write_sine_wav(oto_dir / f"{name}.wav", 44100, seconds, 8000, 440.0)

    # 拼字产物（原版目录才有）
    write_sine_wav(oto_dir / "Cき.wav", 44100, 0.2, 8000, 440.0)
    (oto_dir / "oto.ini").write_text(OTO_TEXT, encoding="utf-8")
    (oto_dir / "character.txt").write_text("name=fixture\n", encoding="utf-8")
    return {"bank_dir": bank_dir, "oto_dir": oto_dir}
