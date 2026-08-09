"""音频 IO（numpy/soundfile，惰性导入；core 不依赖本模块）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..core.errors import MissingDependencyError


def _require(name: str):
    try:
        return __import__(name)
    except ImportError as e:
        raise MissingDependencyError(
            f"缺少依赖 {name}（音频操作需要 numpy/soundfile，请安装 requirements-core.txt）"
        ) from e


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_audio_file(path) -> dict[str, float]:
    """探测音频文件：采样率 / 样本数 / 时长（秒）。不支持 → MissingDependency/错误。"""
    sf = _require("soundfile")
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"音频文件不存在: {p}")
    try:
        info = sf.info(str(p))
    except Exception as e:  # noqa: BLE001
        raise MissingDependencyError(
            f"无法读取音频文件（soundfile 不支持该格式?）: {p}: {e}"
        ) from e
    return {
        "sample_rate": float(info.samplerate),
        "num_samples": float(info.frames),
        "duration_seconds": float(info.duration),
    }
