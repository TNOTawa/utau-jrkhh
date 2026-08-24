"""VC 补充导出：原版 oto.ini 逐字节原样 + VC/派生 CV 追加行 + 所需 wav 拷贝。

无差别保证（针对 henki 导入的母版）：
- 非 VC/追加行 = 原版文件**逐字节原样**（不改顺序、不重序列化、不重编码；
  追加行纯 ASCII，与原版 SJIS/UTF-8 编码兼容共存）
- VC 行 = 全新含空格别名（导入时已验证原版别名不含空格），不可能冲突；
  中文 VC 别名为 presamp 短 ID（`an t`/`ir zh`），与交付的 presamp.ini 同源
- 派生 CV 追加：仅对「原版中不存在该 base 别名」的母版 Unit 追加 CV 行
  （拼字 Unit 必然追加；手剥版剔除的切片音节自动补齐），绝不与原版重复
- 中文母版另交付 presamp.ini（内置标准模板逐字节），OpenUtau 内置 zh-cvv
  音素器依赖它生成短 ID VC 别名
- 原版引用的 wav 从原版目录原样拷贝；VC/追加 CV 行引用句 wav（整资产句
  「定向已有文件」引用资产原文件名，不重复复制）
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..core.compile_engine import CompileConfig, compile_project
from ..core.errors import DataError, InvalidInputError
from ..core.project import JRHProject
from ..core.util import write_json
from ..formats.oto_ini import OtoLine, read_oto


def export_vc_supplement(project: JRHProject, out_dir: str | Path) -> dict:
    """导出「原版 + VC 追加」音源目录。返回确定性报告 dict。"""
    src = project.manifest.get("import_source") or {}
    oto_ini, oto_dir = src.get("oto_ini"), src.get("oto_dir")
    if not oto_ini or not oto_dir:
        raise InvalidInputError(
            "项目不是 henki 导入（缺少 import_source.oto_ini），无法导出 VC 补充"
        )
    oto_path = Path(oto_ini)
    orig_dir = Path(oto_dir)
    if not oto_path.exists():
        raise DataError(f"原版 oto.ini 不存在: {oto_path}")

    result = compile_project(project, CompileConfig(cvvc=True))
    vc_entries = [e for e in result.entries if e.kind == "vc"]

    original_entries = read_oto(oto_path)
    original_aliases = {e.alias for e in original_entries}
    if any(" " in a for a in original_aliases):
        raise DataError("原版 oto.ini 别名含空格，与 VC 别名命名空间冲突，拒绝导出")
    for vc in vc_entries:
        if vc.alias in original_aliases:
            raise DataError(f"VC 别名与原版冲突: {vc.alias}")

    # 派生 CV 追加：仅原版缺失的 base（source_label = 语言包单位）——拼字/被剔除音节补齐
    original_bases = {_base_alias(a) for a in original_aliases}
    cv_append = [
        e for e in result.entries if e.kind == "cv" and e.source_label not in original_bases
    ]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 原版引用的 wav 原样拷贝（字节一致）
    copied: set[str] = set()
    missing: list[str] = []
    for e in original_entries:
        if e.wav in copied:
            continue
        src_wav = orig_dir / e.wav
        if not src_wav.exists():
            missing.append(e.wav)
            continue
        shutil.copy2(src_wav, out / e.wav)
        copied.add(e.wav)
    if missing:
        raise DataError(f"原版目录缺少 wav（前 10 个）: {', '.join(sorted(missing)[:10])}")

    # VC/追加 CV 行引用的句 wav（整资产句定向已有文件，见 audio.export）
    from ..audio.export import export_sentence_wavs

    export_sentence_wavs(project, out)

    # 中文母版：交付 presamp.ini（内置标准模板逐字节）
    presamp_written = False
    if project.manifest.get("language_pack") == "jrh.zh-pinyin":
        from ..languages.presamp import PRESAMP_INI_TEXT

        (out / "presamp.ini").write_bytes(PRESAMP_INI_TEXT.encode("ascii"))
        presamp_written = True

    # oto.ini = 原版逐字节 + VC 追加行 + 派生 CV 追加行（纯 ASCII）
    original_bytes = oto_path.read_bytes()
    if not original_bytes.endswith(b"\n"):
        original_bytes += b"\n"
    appended = vc_entries + cv_append
    appended_lines = [
        OtoLine(
            wav=e.wav,
            alias=e.alias,
            offset_ms=e.params["offset"],
            consonant_ms=e.params["consonant"],
            cutoff_ms=e.params["cutoff"],
            preutterance_ms=e.params["preutterance"],
            overlap_ms=e.params["overlap"],
        ).to_line()
        for e in sorted(appended, key=lambda x: (x.wav, x.alias))
    ]
    payload = original_bytes + ("\n".join(appended_lines) + "\n").encode("ascii")
    (out / "oto.ini").write_bytes(payload)

    report = {
        "output": str(out),
        "original_entries": len(original_entries),
        "original_wavs_copied": len(copied),
        "vc_entries": len(vc_entries),
        "vc_aliases": sorted({e.alias for e in vc_entries}),
        "appended_cv_entries": len(cv_append),
        "appended_cv_aliases": sorted({e.alias for e in cv_append}),
        "presamp_ini": presamp_written,
        "sentence_wavs": sorted({e.wav for e in appended}),
    }
    write_json(out / "vc-supplement-report.json", report)
    return report


def _base_alias(alias: str) -> str:
    """剥离末尾数字编号（与 importer 同规则：hao1 → hao）。"""
    import re

    m = re.match(r"^(.*?)(\d+)$", alias)
    return m.group(1) if m else alias
