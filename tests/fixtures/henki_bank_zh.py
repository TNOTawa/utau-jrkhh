"""合成中文人力V助手 bank 夹具（测试共用，确定性）。

结构（DJUTAU 实测形态：无「段」前缀、每切片独立成句、带声调音素）。
时长取 0.25s 的整数倍（44100Hz 下帧数为精确整数，避免浮点噪声）：
- qfcy_0000（0.5s）：ʔ [0,0.1) a˥˩ [0.1,0.45) spn → a（ʔ 作声母）
- qfcy_0001（0.75s）：kʰ o | n o ŋ（可|能，分词界）→ ke, neng
- qfcy_0002（0.5s）：tɕ ow˥˩ ʂ ʐ̩˥˩（就是）→ jiu, shi
- qfcy_0003（0.5s）：a˥（零声母，无 ʔ）→ a
- qfcy_0004（0.25s）：i˨˩˦ → yi
- qfcy_0005（0.5s）：kʰ a˥˩ n（看，同词韵尾保留）→ kan

原版 oto.ini 两个变体：
- OTO_TEXT：含 VC 行（`qfcy_0002.wav=a sh,…`）+ 拼字产物 Cqian.wav（测导入不吸收）
- OTO_TEXT_STRIPPED：人工剥离版（无 VC 行、无拼字、无 yi 行——测导出派生 CV 追加）
"""

from __future__ import annotations

from pathlib import Path

from fixtures.wavs import write_sine_wav

# (切片名, 时长秒, phones: [(音素, xmin, xmax)], words: [(xmin, xmax, 文本)])
TEXTGRIDS: dict[
    str, tuple[float, list[tuple[str, float, float]], list[tuple[float, float, str]]]
] = {
    "qfcy_0000": (
        0.5,
        [("ʔ", 0.0, 0.1), ("a˥˩", 0.1, 0.45), ("spn", 0.45, 0.5)],
        [(0.0, 0.45, "啊")],
    ),
    "qfcy_0001": (
        0.75,
        [
            ("kʰ", 0.0, 0.08),
            ("o˨˩˦", 0.08, 0.32),
            ("n", 0.32, 0.4),
            ("o˧˥", 0.4, 0.65),
            ("ŋ", 0.65, 0.75),
        ],
        [(0.0, 0.32, "可"), (0.32, 0.75, "能")],
    ),
    "qfcy_0002": (
        0.5,
        [("tɕ", 0.0, 0.07), ("ow˥˩", 0.07, 0.25), ("ʂ", 0.25, 0.33), ("ʐ̩˥˩", 0.33, 0.5)],
        [(0.0, 0.25, "就"), (0.25, 0.5, "是")],
    ),
    "qfcy_0003": (
        0.5,
        [("a˥", 0.0, 0.5)],
        [(0.0, 0.5, "啊")],
    ),
    "qfcy_0004": (
        0.25,
        [("i˨˩˦", 0.0, 0.25)],
        [(0.0, 0.25, "以")],
    ),
    "qfcy_0005": (
        0.5,
        [("kʰ", 0.0, 0.08), ("a˥˩", 0.08, 0.4), ("n", 0.4, 0.5)],
        [(0.0, 0.5, "看")],
    ),
}

# 原版 oto.ini（含 VC 行与拼字产物；条目顺序即优先级）
OTO_TEXT = """# 原版音源 oto.ini（中文，UTF-8）
qfcy_0000.wav=a,0.0,90.0,-470.0,90.0,27.0
qfcy_0001.wav=ke,0.0,80.0,-300.0,80.0,24.0
qfcy_0001.wav=neng,320.0,60.0,-300.0,60.0,18.0
qfcy_0002.wav=jiu,0.0,70.0,-250.0,70.0,21.0
qfcy_0002.wav=shi,250.0,80.0,-250.0,80.0,24.0
qfcy_0002.wav=a sh,300.0,90.0,-150.0,90.0,45.0
qfcy_0003.wav=a,0.0,30.0,-500.0,30.0,9.0
qfcy_0004.wav=yi,0.0,30.0,-250.0,30.0,9.0
qfcy_0005.wav=kan,0.0,80.0,-450.0,80.0,24.0
Cqian.wav=qian,0.0,60.0,-520.0,60.0,18.0
"""

# 人工剥离版：无 VC 行、无 Cqian 拼字、无 yi 行（测派生 CV 追加与基线保真）
OTO_TEXT_STRIPPED = """# 原版音源 oto.ini（剥离版：无 VC、无拼字、yi 被剔除）
qfcy_0000.wav=a,0.0,90.0,-470.0,90.0,27.0
qfcy_0001.wav=ke,0.0,80.0,-300.0,80.0,24.0
qfcy_0001.wav=neng,320.0,60.0,-300.0,60.0,18.0
qfcy_0002.wav=jiu,0.0,70.0,-250.0,70.0,21.0
qfcy_0002.wav=shi,250.0,80.0,-250.0,80.0,24.0
qfcy_0003.wav=a,0.0,30.0,-500.0,30.0,9.0
qfcy_0005.wav=kan,0.0,80.0,-450.0,80.0,24.0
"""


def _tg_text(
    name: str,
    intervals: list[tuple[str, float, float]],
    words: list[tuple[float, float, str]],
) -> str:
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
        f"        intervals: size = {len(words)}",
    ]
    for i, (xmin, xmax, text) in enumerate(words, start=1):
        lines.append(f"        intervals [{i}]:")
        lines.append(f"            xmin = {xmin}")
        lines.append(f"            xmax = {xmax}")
        lines.append(f'            text = "{text}"')
    lines += [
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


def build_henki_bank_zh(root: Path, oto_text: str = OTO_TEXT) -> dict[str, Path]:
    """构造中文 bank 目录 + 原版音源目录，返回 {bank_dir, oto_dir}。"""
    root = Path(root)
    bank_dir = root / "bank" / "henki_bank_zh"
    oto_dir = root / "original_bank_zh"
    (bank_dir / "slices").mkdir(parents=True)
    (bank_dir / "textgrid").mkdir(parents=True)
    oto_dir.mkdir(parents=True)

    (bank_dir / "meta.json").write_text(
        '{"source_name": "fixture-zh", "language": "chinese"}\n', encoding="utf-8"
    )

    for name, (seconds, phones, words) in TEXTGRIDS.items():
        write_sine_wav(bank_dir / "slices" / f"{name}.wav", 44100, seconds, 8000, 440.0)
        (bank_dir / "slices" / f"{name}.lab").write_text("", encoding="utf-8")
        (bank_dir / "textgrid" / f"{name}.TextGrid").write_text(
            _tg_text(name, phones, words), encoding="utf-8"
        )
        # 原版音源目录里的同名 wav（导出时原样拷贝用）
        write_sine_wav(oto_dir / f"{name}.wav", 44100, seconds, 8000, 440.0)

    # 拼字产物（原版目录才有）
    write_sine_wav(oto_dir / "Cqian.wav", 44100, 0.5, 8000, 440.0)
    (oto_dir / "oto.ini").write_text(oto_text, encoding="utf-8")
    (oto_dir / "character.txt").write_text("name=fixture-zh\n", encoding="utf-8")
    return {"bank_dir": bank_dir, "oto_dir": oto_dir}
