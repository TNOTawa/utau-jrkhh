"""原句 WAV 导出：每句一个 WAV（Asset 切片，共享不复制）。

整资产句（句范围 == 整个资产）「定向已有文件」：不重新编码，
直接把资产原文件复制为句 WAV 名（文件名 = 资产文件名，见
compile_engine.sentence_wav_name），避免与音源目录里已存在的同源 wav 重复。
其余句子写出 sentence_{id:03d}.wav（PCM16，与素材同采样率）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..core.compile_engine import sentence_wav_name
from ..core.errors import DataError
from ..core.project import JRHProject


def export_sentence_wavs(project: JRHProject, out_dir: Path) -> dict[int, str]:
    """为每个句子生成句 WAV。返回 {sid: 文件名}。"""
    sf = _require("soundfile")
    import numpy as np  # noqa: PLC0415

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    produced: dict[int, str] = {}
    name_sources: dict[str, str] = {}  # 句 WAV 名 → 资产文件（冲突检测）
    for sent in project.sentences_sorted():
        asset = project.get_asset(sent.asset_id)
        name = sentence_wav_name(project, sent)
        if name in name_sources and name_sources[name] != asset.file:
            raise DataError(
                f"句 WAV 文件名冲突: {name} 同时来自资产 {name_sources[name]} 与 {asset.file}"
            )
        name_sources[name] = asset.file
        if sent.start_sample == 0 and sent.end_sample == asset.num_samples:
            # 整资产句：定向已有文件（字节复制同一文件，不重复转码）
            shutil.copy2(str(project.path / asset.file), str(out_dir / name))
            produced[sent.sentence_id] = name
            continue
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
