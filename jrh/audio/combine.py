"""自动拼字的音频合成：辅音段 + 元音段 crossfade 拼接为 CV 音节 WAV。

算法移植自本仓库 src/phoneme_combine_dialog.py::_enhanced_crossfade（已验证实现）：
1. 动态 crossfade 长度（较短片段的 30%，上限 30ms，下限 5ms）
2. 全局 RMS 振幅匹配（增益限制 0.5~2.0，避免音量跳变）
3. 余弦 fade（S-curve，消除线性 fade 的中间凹陷）
4. 端点 2ms fade-in/out，去除首尾咔哒

片段取值（JRH timing 约定）：
- 辅音源：[offset, offset + consonant)
- 元音源：[offset + consonant, offset + |cutoff|)

numpy/soundfile 惰性导入（audio 模块惯例；jrh/core 保持纯 stdlib）。
"""

from __future__ import annotations

from pathlib import Path

from ..core.model import Unit
from ..core.project import JRHProject


def _require(name: str):
    try:
        return __import__(name)
    except ImportError as e:
        from ..core.errors import MissingDependencyError

        raise MissingDependencyError(
            f"缺少依赖 {name}（音频操作需要 numpy/soundfile，请安装 requirements-core.txt）"
        ) from e


def enhanced_crossfade(audio1, audio2, sr: int, max_crossfade_ms: float = 30.0):
    """增强 crossfade 拼接（返回与 audio1 同 dtype 的一维数组）。"""
    import numpy as np  # noqa: PLC0415

    if len(audio1) == 0 or len(audio2) == 0:
        return np.concatenate([audio1, audio2])

    max_cf = int(max_crossfade_ms / 1000 * sr)
    min_cf = int(5 / 1000 * sr)
    cf = int(min(len(audio1), len(audio2)) * 0.30)
    cf = max(min_cf, min(cf, max_cf))
    cf = min(cf, len(audio1) - 1, len(audio2) - 1)
    if cf < 2:
        return np.concatenate([audio1, audio2])

    # RMS 振幅匹配：对整段 audio2 施加增益（限制 0.5~2.0）
    rms1 = np.sqrt(np.mean(audio1.astype(np.float64) ** 2))
    rms2 = np.sqrt(np.mean(audio2.astype(np.float64) ** 2))
    if rms2 > 1e-6 and rms1 > 1e-6:
        gain = rms1 / rms2
        gain = float(np.clip(gain, 0.5, 2.0))
        audio2 = audio2.astype(np.float64) * gain
        audio2 = audio2.astype(audio1.dtype)

    tail = audio1[-cf:]
    head = audio2[:cf]

    t = np.linspace(0.0, 1.0, cf)
    fade_out = 0.5 * (1.0 + np.cos(np.pi * t))
    fade_in = 0.5 * (1.0 - np.cos(np.pi * t))

    crossfaded = tail.astype(np.float64) * fade_out + head.astype(np.float64) * fade_in
    crossfaded = crossfaded.astype(audio1.dtype)

    result = np.concatenate([audio1[:-cf], crossfaded, audio2[cf:]])

    edge_samples = int(2 / 1000 * sr)
    if edge_samples > 1 and len(result) > edge_samples * 4:
        fade_in_curve = np.linspace(0.0, 1.0, edge_samples).astype(result.dtype)
        fade_out_curve = np.linspace(1.0, 0.0, edge_samples).astype(result.dtype)
        result[:edge_samples] = result[:edge_samples] * fade_in_curve
        result[-edge_samples:] = result[-edge_samples:] * fade_out_curve

    return result


def combine_cv(
    project: JRHProject,
    consonant_unit: Unit,
    vowel_unit: Unit,
    out_path: Path,
) -> dict | None:
    """辅音源 + 元音源 → CV 音节 WAV（PCM16）。

    返回 {total_samples, sample_rate, consonant_samples}；源音频缺失或
    采样率不一致返回 None（由调用方报告跳过）。
    """
    sf = _require("soundfile")

    c_sent = project.get_sentence(consonant_unit.sentence_id)
    v_sent = project.get_sentence(vowel_unit.sentence_id)
    if c_sent.sample_rate != v_sent.sample_rate:
        return None
    sr = c_sent.sample_rate

    c_asset = project.get_asset(c_sent.asset_id)
    v_asset = project.get_asset(v_sent.asset_id)
    c_path = project.path / c_asset.file
    v_path = project.path / v_asset.file
    if not c_path.exists() or not v_path.exists():
        return None

    c_t, v_t = consonant_unit.timing, vowel_unit.timing
    c_start = int(c_sent.start_sample + c_t.offset)
    c_end = int(c_sent.start_sample + c_t.offset + c_t.consonant)
    v_start = int(v_sent.start_sample + v_t.offset + v_t.consonant)
    v_end = int(v_sent.start_sample + v_t.window_end())

    c_data, c_sr = sf.read(str(c_path), dtype="float64", always_2d=True)
    v_data, v_sr = sf.read(str(v_path), dtype="float64", always_2d=True)
    if c_sr != sr or v_sr != sr:
        return None
    c_seg = c_data[c_start:c_end, 0]
    v_seg = v_data[v_start:v_end, 0]
    if len(c_seg) == 0 or len(v_seg) == 0:
        return None

    combined = enhanced_crossfade(c_seg, v_seg, sr)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), combined, sr, subtype="PCM_16")
    return {
        "total_samples": int(len(combined)),
        "sample_rate": sr,
        "consonant_samples": int(round(c_t.consonant)),
    }
