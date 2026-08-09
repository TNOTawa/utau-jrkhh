"""oto.ini 读写（UTAU 传统格式适配层）。

- 毫秒换算公式：ms = round(samples * 1000 / sr, 3)，输出去掉尾随零。
- 编码：UTF-8（本工具产物；读取兼容 Shift_JIS 检测，见 read_oto）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import DataError
from ..core.util import atomic_write_text


def fmt_ms(value: float) -> str:
    """毫秒值 → oto.ini 字符串（确定性：去尾零、-0 归零）。"""
    v = round(float(value), 3)
    if abs(v) < 1e-9:
        return "0"
    s = f"{v:.3f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    return s


@dataclass
class OtoLine:
    wav: str
    alias: str
    offset_ms: float
    consonant_ms: float
    cutoff_ms: float
    preutterance_ms: float
    overlap_ms: float

    def to_line(self) -> str:
        return (
            f"{self.wav}={self.alias},{fmt_ms(self.offset_ms)},{fmt_ms(self.consonant_ms)},"
            f"{fmt_ms(self.cutoff_ms)},{fmt_ms(self.preutterance_ms)},{fmt_ms(self.overlap_ms)}"
        )


_OTO_LINE_RE = re.compile(r"^(.+?)=(.+?),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)$")


def write_oto(path: Path, lines: list[OtoLine]) -> None:
    text = "\n".join(line.to_line() for line in lines) + "\n"
    atomic_write_text(path, text)


def read_oto(path: Path) -> list[OtoLine]:
    """读取 oto.ini（兼容 shift_jis/cp932/utf-8/gbk 自动检测）。"""
    if not path.exists():
        raise DataError(f"oto.ini 不存在: {path}")
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise DataError(f"无法读取 oto.ini {path}: {e}") from e
    encoding = _detect_encoding(raw)
    text = raw.decode(encoding, errors="replace")
    out: list[OtoLine] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _OTO_LINE_RE.match(line)
        if m:
            out.append(
                OtoLine(
                    wav=m.group(1),
                    alias=m.group(2),
                    offset_ms=float(m.group(3)),
                    consonant_ms=float(m.group(4)),
                    cutoff_ms=float(m.group(5)),
                    preutterance_ms=float(m.group(6)),
                    overlap_ms=float(m.group(7)),
                )
            )
    return out


def _detect_encoding(raw: bytes) -> str:
    """编码检测：UTF-8 优先（本项目产物恒为 UTF-8/ASCII），
    其次 shift_jis → cp932 → gbk（兼容传统日语音源，启发式，best-effort）。

    已知局限：SJIS/CP932/GBK 字节范围重叠，个别字符可能误判；
    本项目自己的编译产物为 ASCII 安全，不受影响。
    """
    for enc in ("utf-8", "shift_jis", "cp932", "gbk"):
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"
