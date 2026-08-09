"""JRH 核心包：人力音源母版格式（v0.1）。

分层约定：
- jrh.core      纯 stdlib，不依赖任何第三方包与 GUI
- jrh.languages 语言包（纯数据 + 规则）
- jrh.formats   传统格式适配（oto.ini）
- jrh.audio     音频 IO（numpy/soundfile，惰性导入）
- jrh.phonemizer OpenUtau 薄适配层
- jrh.cli       CLI 入口
"""

__version__ = "0.1.0"
