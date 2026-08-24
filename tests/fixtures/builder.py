"""标准演示项目构造器（测试共用，确定性）。

结构（与 golden fixture 一致）：
- asset-001: 44100 Hz 3.0s 正弦
  - sentence 1 [0, 88200)：1:1 ni / 1:2 hao / 1:3 a
  - sentence 2 [88200, 132300)：2:1 wo / 2:2 hao / 2:3 ma
- asset-002: 48000 Hz 1.0s 正弦（不同采样率场景）
  - sentence 3 [0, 48000)：3:1 hao / 3:2 jiu
- hao 组人工排序 [3:1, 1:2, 2:2]
"""

from __future__ import annotations

from pathlib import Path

from jrh.core.model import Asset, Timing
from jrh.core.project import JRHProject

from .wavs import write_sine_wav

# 句 1 单元（44100 Hz，采样点）
S1_UNITS = [
    ("ni", Timing(2205.0, 11025.0, -35280.0, 4410.0, 4410.0)),
    ("hao", Timing(35280.0, 11025.0, -39690.0, 4410.0, 4410.0)),
    ("a", Timing(66150.0, 0.0, -17640.0, 0.0, 0.0)),
]
# 句 2 单元
S2_UNITS = [
    ("wo", Timing(2205.0, 11025.0, -26460.0, 4410.0, 4410.0)),
    ("hao", Timing(24255.0, 11025.0, -17640.0, 4410.0, 4410.0)),
    ("ma", Timing(33075.0, 11025.0, -11025.0, 0.0, 0.0)),
]
# 句 3 单元（48000 Hz）
S3_UNITS = [
    ("hao", Timing(2400.0, 9600.0, -28800.0, 4800.0, 4800.0)),
    ("jiu", Timing(28800.0, 9600.0, -19200.0, 4800.0, 4800.0)),
]

HAO_MANUAL_ORDER = ["3:1", "1:2", "2:2"]


def build_split_project(tmp_path: Path) -> Path:
    """专用于 L3 split 场景的项目（selection 测试共用）：
    句1: wo hao（存在，但 leading 为 o）
    句2: ni hong（2:2 hong 提供 leading i + initial h 的过渡）
    """
    from jrh.core.model import Asset, Timing

    root = Path(tmp_path)
    proj = JRHProject.create(root / "split.jrh")
    proj.add_asset(
        Asset(
            id="a1",
            file="assets/x.wav",
            kind="audio",
            sha256="0" * 64,
            sample_rate=44100,
            num_samples=20000,
            duration_seconds=0.5,
        )
    )
    proj.create_sentence("a1", 0, 20000)
    proj.create_unit(1, "wo", Timing(0, 100, -9000, 0, 0))
    proj.create_unit(1, "hao", Timing(6000, 100, -10000, 0, 0))
    proj.create_sentence("a1", 0, 20000)
    proj.create_unit(2, "ni", Timing(0, 100, -9000, 0, 0))
    proj.create_unit(2, "hong", Timing(6000, 4410, -10000, 0, 0))
    proj.save()
    return root / "split.jrh"


# 预置分析值（确定性；时长来自公式，RMS 为固定常数便于测试）
ANALYSIS: dict[str, dict] = {
    "1:1": {"duration_ms": 800.0, "rms_dbfs": -20.0},
    "1:2": {"duration_ms": 900.0, "rms_dbfs": -20.0},
    "1:3": {"duration_ms": 400.0, "rms_dbfs": -20.0},
    "2:1": {"duration_ms": 600.0, "rms_dbfs": -19.0},
    "2:2": {"duration_ms": 400.0, "rms_dbfs": -19.0},
    "2:3": {"duration_ms": 250.0, "rms_dbfs": -19.0},
    "3:1": {"duration_ms": 600.0, "rms_dbfs": -22.0},
    "3:2": {"duration_ms": 400.0, "rms_dbfs": -22.0},
}


def build_demo_project(
    root: Path,
    with_audio: bool = True,
    language_pack: str = "jrh.zh-pinyin",
    freeze: bool = False,
) -> Path:
    """构造标准演示项目，返回项目路径。"""
    root = Path(root)
    proj_path = root / "demo.jrh"
    proj = JRHProject.create(proj_path, language_pack)

    assets_dir = proj_path / "assets"
    wav1 = write_sine_wav(assets_dir / "src1.wav", 44100, 3.0, 12000, 440.0)
    wav2 = write_sine_wav(assets_dir / "src2.wav", 48000, 1.0, 9000, 550.0)

    if with_audio:
        import hashlib

        from jrh.audio.probe import probe_audio_file

        for aid, wav in (("asset-001", wav1), ("asset-002", wav2)):
            info = probe_audio_file(wav)
            proj.add_asset(
                Asset(
                    id=aid,
                    file=str(wav.relative_to(proj_path)).replace("\\", "/"),
                    kind="audio",
                    sha256=hashlib.sha256(wav.read_bytes()).hexdigest(),
                    sample_rate=int(info["sample_rate"]),
                    num_samples=int(info["num_samples"]),
                    duration_seconds=float(info["duration_seconds"]),
                )
            )
    else:
        proj.add_asset(
            Asset(
                id="asset-001",
                file="assets/__missing.wav",
                kind="audio",
                sha256="0" * 64,
                sample_rate=44100,
                num_samples=132300,
                duration_seconds=3.0,
            )
        )
        proj.add_asset(
            Asset(
                id="asset-002",
                file="assets/__missing.wav",
                kind="audio",
                sha256="0" * 64,
                sample_rate=48000,
                num_samples=48000,
                duration_seconds=1.0,
            )
        )

    proj.create_sentence("asset-001", 0, 88200)
    for label, timing in S1_UNITS:
        proj.create_unit(1, label, timing)
    proj.create_sentence("asset-001", 88200, 132300)
    for label, timing in S2_UNITS:
        proj.create_unit(2, label, timing)
    proj.create_sentence("asset-002", 0, 48000)
    for label, timing in S3_UNITS:
        proj.create_unit(3, label, timing)

    proj.group_set_manual("hao", HAO_MANUAL_ORDER)

    from jrh.core import analysis as analysis_mod

    for coord, values in ANALYSIS.items():
        s, u = (int(x) for x in coord.split(":"))
        proj.set_unit_analysis(s, u, dict(values))
    proj.set_analysis_summary(analysis_mod.build_summary(proj))
    proj.save()
    if freeze:
        proj.freeze()
    return proj_path


# ── 日语 CVVC 演示项目（44100 Hz）────────────────────────────────
# 覆盖：促音借位+去重（あって → a t）、ん（o n）、编号（a t / a t1）、
#       零声母不生成（おえ）、句尾不生成。
JA_S1_UNITS = [
    ("a", Timing(0.0, 0.0, -20000.0, 0.0, 0.0)),
    ("xtsu", Timing(20000.0, 10000.0, -10000.0, 0.0, 0.0)),
    ("te", Timing(30000.0, 8000.0, -22000.0, 2000.0, 2000.0)),
]
JA_S2_UNITS = [
    ("ko", Timing(0.0, 6000.0, -24000.0, 2000.0, 2000.0)),
    ("n", Timing(24000.0, 14000.0, -14000.0, 0.0, 0.0)),
    ("ni", Timing(38000.0, 7000.0, -22000.0, 2000.0, 2000.0)),
    ("chi", Timing(60000.0, 6000.0, -14000.0, 1000.0, 1000.0)),
    ("ha", Timing(74000.0, 6000.0, -16000.0, 2000.0, 2000.0)),
]
JA_S3_UNITS = [
    ("ka", Timing(0.0, 6000.0, -24000.0, 2000.0, 2000.0)),
    ("ka", Timing(24000.0, 6000.0, -24000.0, 2000.0, 2000.0)),
]
JA_S4_UNITS = [
    ("ka", Timing(0.0, 6000.0, -24000.0, 2000.0, 2000.0)),
    ("te", Timing(24000.0, 8000.0, -24000.0, 2000.0, 2000.0)),
]
JA_S5_UNITS = [
    ("o", Timing(0.0, 0.0, -15000.0, 0.0, 0.0)),
    ("e", Timing(15000.0, 0.0, -15000.0, 0.0, 0.0)),
]
JA_SENTENCES = [
    (0, 60000, JA_S1_UNITS),  # あって
    (0, 90000, JA_S2_UNITS),  # こんにちは
    (0, 50000, JA_S3_UNITS),  # かか
    (0, 50000, JA_S4_UNITS),  # かて
    (0, 30000, JA_S5_UNITS),  # おえ
]


def build_ja_demo_project(root: Path, with_audio: bool = True, freeze: bool = False) -> Path:
    """构造日语演示项目（jrh.ja-romaji），返回项目路径。"""
    root = Path(root)
    proj_path = root / "ja-demo.jrh"
    proj = JRHProject.create(proj_path, "jrh.ja-romaji")

    assets_dir = proj_path / "assets"
    wav = write_sine_wav(assets_dir / "ja_src.wav", 44100, 5.0)

    if with_audio:
        import hashlib

        from jrh.audio.probe import probe_audio_file

        info = probe_audio_file(wav)
        proj.add_asset(
            Asset(
                id="asset-001",
                file=str(wav.relative_to(proj_path)).replace("\\", "/"),
                kind="audio",
                sha256=hashlib.sha256(wav.read_bytes()).hexdigest(),
                sample_rate=int(info["sample_rate"]),
                num_samples=int(info["num_samples"]),
                duration_seconds=float(info["duration_seconds"]),
            )
        )
    else:
        proj.add_asset(
            Asset(
                id="asset-001",
                file="assets/__missing.wav",
                kind="audio",
                sha256="0" * 64,
                sample_rate=44100,
                num_samples=220500,
                duration_seconds=5.0,
            )
        )

    for start, end, units in JA_SENTENCES:
        sent = proj.create_sentence("asset-001", start, end)
        for label, timing in units:
            proj.create_unit(sent.sentence_id, label, timing)

    proj.save()
    if freeze:
        proj.freeze()
    return proj_path
