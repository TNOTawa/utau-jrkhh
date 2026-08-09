"""测试夹具：确定性 WAV 生成（纯 stdlib，跨平台逐字节一致）。"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def write_sine_wav(
    path: Path,
    sample_rate: int = 44100,
    duration_seconds: float = 3.0,
    amplitude: int = 12000,
    frequency: float = 440.0,
) -> Path:
    """生成单声道 16bit 正弦 WAV。参数相同 ⇒ 文件逐字节相同。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(sample_rate * duration_seconds)
    frames = bytearray()
    for i in range(n):
        v = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
        frames += struct.pack("<h", v)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(bytes(frames))
    return path


def read_wav_samples(path: Path) -> list[int]:
    """用 stdlib wave 读取 int16 采样序列（用于逐样本比对，独立于 soundfile）。"""
    with wave.open(str(path), "rb") as w:
        assert w.getsampwidth() == 2
        n = w.getnframes()
        raw = w.readframes(n)
    fmt = "<" + "h" * n
    return list(struct.unpack(fmt, raw))
