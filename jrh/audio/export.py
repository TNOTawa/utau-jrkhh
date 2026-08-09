"""原句 WAV 导出：每句一个 WAV（Asset 切片，共享不复制）。"""

from __future__ import annotations

from pathlib import Path

from ..core.compile_engine import sentence_wav_name
from ..core.project import JRHProject


def export_sentence_wavs(project: JRHProject, out_dir: Path) -> dict[int, str]:
    """为每个句子导出 sentence_{id:03d}.wav（PCM16，与素材同采样率）。返回 {sid: 文件名}。"""
    sf = _require("soundfile")
    import numpy as np  # noqa: PLC0415

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    produced: dict[int, str] = {}
    for sent in project.sentences_sorted():
        asset = project.get_asset(sent.asset_id)
        src = project.path / asset.file
        data, sr = sf.read(
            str(src), start=sent.start_sample, stop=sent.end_sample, dtype="float64", always_2d=True
        )
        if sr != sent.sample_rate:
            raise RuntimeError(f"asset 采样率 {sr} 与句子记录 {sent.sample_rate} 不一致")
        if data.shape[0] != (sent.end_sample - sent.start_sample):
            raise RuntimeError(
                f"asset {asset.id} 样本数变化（{data.shape[0]} ≠ {sent.end_sample - sent.start_sample}）"
            )
        name = sentence_wav_name(sent.sentence_id)
        sf.write(str(out_dir / name), data.astype(np.float64), sr, subtype="PCM_16")
        produced[sent.sentence_id] = name
    return produced


def _require(name: str):
    try:
        return __import__(name)
    except ImportError as e:
        from ..core.errors import MissingDependencyError

        raise MissingDependencyError(
            f"缺少依赖 {name}（音频操作需要 numpy/soundfile，请安装 requirements-core.txt）"
        ) from e
