# UTAU 式人力音源调节工具（utau-jrkhh）

> UTAU-jrkhh ((Jinriki Helper) Helper)

本仓库包含两部分：

1. **JRH 核心（本仓库的主线）**：`jrh/` 包 —— 人力音源母版格式（JRH v0.1）的
   数据模型、CLI、编译引擎、候选选择引擎与 OpenUtau 适配层。
2. **旧版 GUI 工具**：`src/` + `main.py` —— 基于 customtkinter 的 oto.ini 调节工具
   （历史功能，与 JRH 核心无关）。

---

## JRH 是什么

JRH（JRH 母版格式，v0.1）是一种**以原素材连续片段为基础、以单字永久坐标为身份、
以 VCV/CVVC 式原音设定为唯一人工参数、以五段式别名和自定义音素器为核心运行方式**的
人力音源母版格式。详见 `docs/JRH_SPEC.md`。

- **Asset → Sentence → Unit** 三级模型；Unit 身份 = 永久坐标 `句号:字号`（如 `12:6`）。
- 每个字只维护**一套**原音设定（offset/consonant/cutoff/preutterance/overlap），
  编译时自动派生 FULL / `$T`（过渡）/ `$B`（主体）/ CV 搜索别名。
- 五段式别名（如 `1-2-ni-hao-a`）后三项仅人类可读；程序身份只用永久坐标。
- 冻结编号后：只增不改、不复用（改文字/边界/重分析都不改变编号）。
- 候选选择按确定性层级回退：
  原句连续 → 完整原音 → 过渡+主体 → 当前字主体 → 语言包替代 → 缺音。
- 核心**不依赖** GUI、OpenUtau、ASR 模型、GPU、网络 API。

## 快速开始（新用户）

```powershell
cd F:\Coding\utau-jrkhh
pip install -r requirements-dev.txt   # 开发/QA 工具链
pip install numpy soundfile           # 音频 IO（分析 RMS / 导出 WAV 需要）
pip install -e .                      # 安装 jrh 命令
```

### 最小工作流

```powershell
jrh init my_voicebank.jrh --language-pack jrh.zh-pinyin
jrh asset-add my_voicebank.jrh source.wav
jrh sentence-create my_voicebank.jrh asset-001 --start 0 --end 441000
jrh unit-create my_voicebank.jrh 1 --label hao --offset 0 --consonant 4410 `
    --cutoff -22050 --preutterance 4410 --overlap 4410
jrh analyze my_voicebank.jrh
jrh group my_voicebank.jrh hao --manual "1:1,2:1"
jrh validate my_voicebank.jrh
jrh compile my_voicebank.jrh
jrh phonemize my_voicebank.jrh ni hao a --strict
```

所有命令支持 `--format json`（机器可读）；`--format` 是全局参数，放在子命令之前：

```powershell
jrh --format json select my_voicebank.jrh ni hao a
```

退出码：`0` 成功 / `1` 数据或运行时错误 / `2` 用法错误 / `3` 验证失败 / `4` strict 缺音。

### CLI 子命令总览

| 类别 | 命令 |
|------|------|
| 项目 | `init` `info` `language-pack` |
| 素材 | `asset-add` `asset-list` `asset-info` `asset-remove` |
| 句子 | `sentence-create` `sentence-update` `sentence-delete` `sentence-split` `sentence-merge` `sentence-list` `sentence-renumber` |
| 单元 | `unit-create` `unit-update` `unit-delete` `unit-list` `unit-renumber` |
| 候选 | `group`（--manual/--auto/--show） |
| 分析 | `analyze` |
| 校验 | `validate` `integrity` |
| 编译 | `compile`（--dry-run/--clean/--gap/--out） |
| 选择 | `select` `phonemize`（--strict） |
| 冻结 | `freeze` |

## 测试与 QA

单一质量门入口（本地与 CI 完全一致）：

```powershell
python qa.py            # 完整 QA（含覆盖率与变异测试，约 30 分钟）
python qa.py --quick    # 开发期快速检查（跳过覆盖率与变异）
```

`qa.py` 依次执行：compileall → ruff format → ruff check → mypy →
全量 pytest（unit/integration/acceptance/golden/negative/property/regression）→
覆盖率门禁（jrh.core/formats 行 ≥ 90%，关键模块 branch ≥ 80%）→
变异测试（`tools/mutate.py`，有效杀灭率 ≥ 90%）→ pip check →
`pip install -e .` → CLI smoke（`tools/smoke_cli.py`）。

产物：`qa-report.json`、`coverage-report.json`、`mutation-report.json`。

## 项目结构

```
jrh/
  core/           ★ 核心（纯 stdlib）
    model.py        Asset/Sentence/Unit/Timing/候选分组/分析汇总
    ids.py          永久坐标与 ID 分配器
    project.py      加载/保存/冻结/CRUD（唯一修改入口）
    analysis.py     时长/RMS 统计 + 自动建议排序
    compile_engine.py  编译公式（FULL/$T/$B/CV）+ 冲突检测 + 报告
    selection.py    候选选择引擎（L1~L6 + 确定性 tie-break + 解释）
    validate.py     schema + 语义验证
    integrity.py    数据完整性（哈希/引用/产物一致性）
    util.py         原子写 / 严格 JSON
  languages/     语言包（zh-pinyin、ja-romaji；可扩展）
  formats/        oto.ini 读写（毫秒换算）
  audio/          WAV 探测/导出/RMS（numpy/soundfile，惰性导入）
  phonemizer/     OpenUtau 适配层（只做结果转换）
  cli/            CLI 入口
tests/            unit / integration / acceptance / golden / negative / property / regression
tools/            mutate.py（变异测试）smoke_cli.py（CLI 冒烟）
docs/             JRH_SPEC / REQUIREMENTS / ARCHITECTURE / TEST_PLAN / ADR / FINAL_VALIDATION_REPORT
qa.py             质量门（唯一 QA 入口）
```

## 文档索引

- `docs/JRH_SPEC.md` —— JRH v0.1 格式规范（权威）
- `docs/REQUIREMENTS.md` —— 需求（MUST/SHOULD/FUTURE）+ 追踪矩阵
- `docs/ARCHITECTURE.md` —— 分层与依赖方向
- `docs/TEST_PLAN.md` —— 测试策略
- `docs/ADR-0001-jrh-v0.1-decisions.md` —— 实现期决策
- `docs/FINAL_VALIDATION_REPORT.md` —— 最终验证报告

## 旧版 GUI（历史功能）

```powershell
pip install -r requirements.txt
pip install scipy
python main.py
```

## 许可

[MIT](LICENSE)
