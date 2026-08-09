"""主体区域 RMS 计算（机器辅助，非权威）。"""

from __future__ import annotations

import math

from ..core.model import Unit
from ..core.project import JRHProject


def unit_rms_dbfs(project: JRHProject, unit: Unit) -> float | None:
    """Unit 主体区域 [offset+preutterance, offset+|cutoff|] 的 RMS（dBFS）。

    返回 None 表示无法读取音频（文件缺失等）；静音下限 -120 dBFS。
    """
    sf = _require("soundfile")
    import numpy as np  # noqa: PLC0415

    sent = project.get_sentence(unit.sentence_id)
    asset = project.get_asset(sent.asset_id)
    src = project.path / asset.file
    if not src.exists():
        return None
    start = int(sent.start_sample + unit.timing.body_start())
    stop = int(sent.start_sample + unit.timing.window_end())
    if stop <= start:
        return None
    try:
        data, _ = sf.read(str(src), start=start, stop=stop, dtype="float64", always_2d=True)
    except Exception:  # noqa: BLE001
        return None
    x = data[:, 0] if data.ndim > 1 and data.shape[1] > 1 else data.ravel()
    if x.size == 0:
        return None
    rms = math.sqrt(float(np.mean(np.square(x))))
    if rms < 1e-12:
        return -120.0
    return max(20.0 * math.log10(rms + 1e-12), -120.0)


def _require(name: str):
    try:
        return __import__(name)
    except ImportError as e:
        from ..core.errors import MissingDependencyError

        raise MissingDependencyError(
            f"缺少依赖 {name}（音频操作需要 numpy/soundfile，请安装 requirements-core.txt）"
        ) from e
