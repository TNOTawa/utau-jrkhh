# 需求规格（REQUIREMENTS）

来源：《计划.md》多轮讨论，按「决策解释规则」取**较晚且经用户确认**的结论。
优先级定义：**MUST**（当前稳定版本必须实现）／**SHOULD**（建议，不影响核心发布）／**FUTURE**（明确可后置）。

## 1. MUST 需求

| ID | 需求 | 验证方式 |
|----|------|----------|
| MUST-001 | JRH Core 独立于 GUI、OpenUtau、ASR/Whisper/FunASR/SOFA、GPU、网络 API、传统 UTAU 格式；纯 stdlib 可加载/验证/修改/保存/编译 | 架构检查 + 测试不 import 上述模块 |
| MUST-002 | 核心功能全部有 CLI；GUI 不是业务逻辑唯一入口 | acceptance CLI 测试 |
| MUST-003 | 项目创建/打开/保存（manifest + data 目录，JSON 确定性输出） | unit/integration |
| MUST-004 | Asset 导入（sha256、采样率、时长探测）与列表/详情查看 | unit/integration |
| MUST-005 | Sentence 创建/修改/删除/分割/合并/列表 | unit/integration |
| MUST-006 | Unit 创建/修改/删除/列表；原音五参数修改 | unit/integration |
| MUST-007 | 永久坐标 `s:u`；冻结后编号不变、不复用、新增不改变既有坐标 | unit + frozen 场景 |
| MUST-008 | 候选分组：当前字分组、人工排序、恢复自动排序、禁用候选 | unit/integration |
| MUST-009 | 时长/RMS 分析与汇总统计（median/MAD/mean/variance，全局 + 素材局部） | unit |
| MUST-010 | JRH validation（schema + 语义 + 别名安全 + 时间范围） | unit + acceptance |
| MUST-011 | 数据完整性检查（文件存在、sha256、引用完整） | unit + acceptance |
| MUST-012 | 编译：FULL / TRANSITION($T) / BODY($B) / CV 别名生成，公式代码化 | golden tests |
| MUST-013 | 编译输出：原句 WAV（每句一个，共享不复制）、oto.ini、alias-map.json、build-report.json | golden tests |
| MUST-014 | 别名冲突检测，冲突不得静默覆盖（编译失败 + 报告） | negative tests |
| MUST-015 | 编译可重复（同输入同版本同配置 ⇒ 逐字节一致）；clean rebuild 一致 | acceptance/golden |
| MUST-016 | 候选选择引擎：L1 连续 → L2 FULL → L3 拆分 → L4 主体 → L5 替代 → L6 缺音 | table-driven unit |
| MUST-017 | 选择确定性 tie-break：连续性 > 人工排序 > 统计辅助 > 永久编号；禁用候选永不选中；人工排序不被重分析覆盖 | unit |
| MUST-018 | 每次选择输出解释信息（层级、原因、落选理由、来源） | unit |
| MUST-019 | phonemizer 模拟：给定单位序列输出实际 phoneme（alias、position、层级、来源） | acceptance |
| MUST-020 | OpenUtau 层仅为适配器，调用同一选择引擎（本仓库以 selection core + 模拟 CLI 提供契约） | 架构 + 模拟测试 |
| MUST-021 | 退出码稳定：0/1/2/3/4（见 JRH_SPEC §9） | acceptance |
| MUST-022 | 单一 QA 入口 `python qa.py`：format/lint/typecheck/单元/集成/验收/golden/覆盖率/mutation/依赖/构建/CLI smoke；任一 MUST 项非零即失败 | CI 同入口 |
| MUST-023 | 核心业务逻辑行覆盖率 ≥ 90%，关键模块 branch ≥ 80% | coverage gate |
| MUST-024 | mutation testing 覆盖核心公式模块，关键 surviving mutants 为零 | mutation gate |
| MUST-025 | 文档：README（新用户从零构建 + QA）、JRH_SPEC、REQUIREMENTS、ARCHITECTURE、TEST_PLAN、ADR、FINAL_VALIDATION_REPORT | 文档检查 |
| MUST-026 | 无 stub/placeholder/TODO 替代 MUST 功能；不吞异常；不静默忽略损坏 | 代码审查 + 负例测试 |

## 2. SHOULD 需求

| ID | 需求 | 备注 |
|----|------|------|
| SHOULD-001 | `oto.ini`（传统 UTAU）可无损导入为 JRH 草稿 | 迁移友好 |
| SHOULD-002 | `phonemize` 输出 OpenUtau Phoneme 结构（alias + position ms） | 与 OU 契约对齐 |
| SHOULD-003 | 静音检测分句（无模型能量阈值）作为内置 SegmentationProvider | 默认离线 |
| SHOULD-004 | build 缓存删除后重建（`compile --clean`） | QA 场景 |
| SHOULD-005 | ZIP 容器形式的 `.jrh` 发布包读写 | 格式一致性 |
| SHOULD-006 | 多语言包可注册/选择（CLI `--language-pack`） | 接口已定 |

## 3. FUTURE 需求（明确后置，不得升级为 MUST 依赖）

| ID | 需求 | 后置原因 |
|----|------|----------|
| FUT-001 | ASR Provider（阿里系/Whisper，本地或 API） | 自动标注扩展包 |
| FUT-002 | G2P Provider | 同上 |
| FUT-003 | SOFA Aligner Provider（替代 MFA） | 同上 |
| FUT-004 | 呼吸音事件（inhale/exhale/aspirated release/…）标注 | 独立事件类型 |
| FUT-005 | 英语 ARPA/X-SAMPA 语言包 | 语言包机制先行 |
| FUT-006 | CV/CVVC/VCV 兼容编译目标（含降级报告） | 编译契约先行 |
| FUT-007 | 整句动态规划路径选择（非逐字贪心） | 局部确定性选择先行 |
| FUT-008 | 深层 C+V 拆音拼接（实验开关） | 质量风险高 |
| FUT-009 | 视频素材时间戳映射（source_time_base 等） | 音频先落地 |
| FUT-010 | 旧 JinrikiHelper 工程/现有排序迁移 | 非首阶段 |
| FUT-011 | 自动质量排序的其他策略（按 RMS 等） | 接口已留 |

## 4. Requirement → Implementation → Test 追踪矩阵

| Requirement | Implementation（模块） | Test |
|-------------|------------------------|------|
| MUST-001 | `jrh/core/*`（stdlib only） | `tests/unit/test_core_purity.py` |
| MUST-002/019/021 | `jrh/cli/main.py` | `tests/acceptance/*` |
| MUST-003~006 | `jrh/core/model.py`, `jrh/core/project.py` | `tests/unit/test_project_*.py`, `tests/integration/test_lifecycle.py` |
| MUST-007 | `jrh/core/ids.py`, `project.freeze()` | `tests/unit/test_frozen_ids.py` |
| MUST-008 | `jrh/core/candidate_groups.py` | `tests/unit/test_candidate_groups.py` |
| MUST-009 | `jrh/core/analysis.py`, `jrh/audio/probe.py` | `tests/unit/test_analysis.py` |
| MUST-010 | `jrh/core/validate.py` | `tests/negative/*` |
| MUST-011 | `jrh/core/integrity.py` | `tests/negative/test_integrity.py` |
| MUST-012~015 | `jrh/core/compile_engine.py`, `jrh/formats/oto_ini.py`, `jrh/audio/export.py` | `tests/golden/*`, `tests/acceptance/test_compile.py` |
| MUST-016~018 | `jrh/core/selection.py` | `tests/unit/test_selection.py`（table-driven） |
| MUST-020 | `jrh/phonemizer/adapters.py`（返回 phoneme 列表的薄适配层） | `tests/unit/test_phonemizer_adapter.py` |
| MUST-022 | `qa.py`, `.github/workflows/qa.yml` | 手工执行 + CI |
| MUST-023 | 覆盖率配置 | `qa.py` coverage gate |
| MUST-024 | `tools/mutate.py` | `qa.py` mutation gate |
| MUST-025 | `docs/*`, `README.md` | 文档检查 |
| MUST-026 | 全代码库 | 负例 + review |

## 5. 已确认的核心不变量（对应测试）

见 `JRH_SPEC.md §10`：Permanent Coordinate、Source Timeline、Alias Identity、Determinism。
每个不变量有专门的测试文件（`test_frozen_ids.py`、`test_traceability.py`、
`test_alias_identity.py`、`test_determinism.py`）。
