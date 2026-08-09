# FINAL_VALIDATION_REPORT（最终验证报告）

状态：**通过**（Stable Implementation 完成条件全部满足）
日期：2026-08-07
范围：JRH v0.1（`jrh/` 核心 + CLI + OpenUtau 适配层 + QA 工具链）

> 本报告所有数字均来自实际执行（`python qa.py` 全量运行 + `python tools/qa_clean_env.py`），
> 不是推测值。

## 1. 已实现的需求

`docs/REQUIREMENTS.md` 中全部 MUST 需求（MUST-001 ~ MUST-026）均已实现：

| 领域 | 实现 |
|------|------|
| 核心数据模型 | Asset/Sentence/Unit/Timing/候选分组/分析汇总（`jrh/core/model.py`） |
| 永久坐标与冻结 | `s:u` 身份；冻结后只增不改、不复用（每句 `max_unit_id_ever` + 全局计数器） |
| 项目生命周期 | 创建/打开/保存（原子写、JSON 确定性）、资产导入、句/单元 CRUD、分割/合并 |
| 分析 | 时长（纯计算）+ RMS（音频）+ 全局/素材局部统计（median/MAD） |
| 编译 | FULL / `$T` / `$B` / CV 公式（JRH_SPEC §5）、冲突检测（失败不写产物）、build-report |
| 选择引擎 | L1 连续 → L2 FULL → L3 拆分 → L4 主体 → L5 替代 → L6 缺音；确定性 tie-break；解释输出 |
| OpenUtau 适配 | `jrh/phonemizer/adapters.py` 薄转换层 + `phonemize` 模拟 CLI（同一选择核心） |
| CLI | 全部子命令；`--format json`；退出码 0/1/2/3/4 |
| 语言包 | zh-pinyin（标准 410 音节）、ja-romaji（Hepburn 全表） |
| 验证与完整性 | `validate`（schema+语义）、`integrity`（哈希/引用/产物一致性） |
| 质量门 | `python qa.py`（11 步单入口），CI（`.github/workflows/qa.yml`）同入口 |

## 2. 未实现的 SHOULD / FUTURE

| ID | 需求 | 说明 |
|----|------|------|
| SHOULD-001 | 传统 oto.ini 无损导入为 JRH 草稿 | 未实现（见已知限制） |
| SHOULD-003 | 内置静音检测分句 | 未实现（句边界由人工/外部提供） |
| SHOULD-005 | ZIP 容器形式的 .jrh 发布包 | 未实现（目录形式可用） |
| FUT-001~011 | ASR/G2P/SOFA Provider、呼吸音、英语语言包、CVVC/VCV 编译目标、整句动态规划、深层 C+V 拼接、视频时间戳、旧项目迁移 | 明确后置，未升级为 MUST 依赖 |

## 3. 测试统计（382 个，全部通过）

| 类别 | 数量 |
|------|------|
| unit | 297 |
| integration | 14 |
| acceptance（真实 CLI 子进程） | 28 |
| golden | 5 |
| negative | 23 |
| property（hypothesis） | 8 |
| regression | 7 |
| **合计** | **382** |

## 4. 覆盖率

- `jrh/core` + `jrh/formats` 行覆盖率：**96.9%**（门禁 90%）
- 关键模块 branch 覆盖率：model/analysis/selection/compile_engine/oto_ini 均 ≥ 80%
- 明细见 `coverage-report.json`

## 5. 变异测试（232 个变异，全部模块 100% 有效杀灭率）

| 模块 | 杀死/总数 | 有效杀灭率 | 等价白名单 |
|------|-----------|------------|------------|
| model.py | 58/60 | 100% | 2 |
| compile_engine.py | 41/46 | 100% | 5 |
| analysis.py | 42/48 | 100% | 6 |
| selection.py | 60/60 | 100% | 0 |
| oto_ini.py | 16/18 | 100% | 2 |
| **合计** | **217/232** | **100%** | **15** |

等价变异白名单（`tools/mutate.py` 的 `EQUIVALENT_WHITELIST`）均附理由；
新增等价判定必须给出理由。**关键 surviving mutants 为零。**

## 6. QA 场景（实际执行）

`python tools/qa_clean_env.py`（干净 venv 全流程）全部通过：

```
clean env → install → create JRH → import fixture → edit → analyze → sort →
freeze → validate → compile（记录产物哈希）→ phonemize 模拟 →
销毁 build 重建（逐字节一致）→ 重复编译一致 → 损坏输入显式报错 →
干净环境 pip check → 干净环境完整 QA（--quick）
```

## 7. 发现并修复的 bug（先加回归测试再修复，`tests/regression/` 固化）

| # | 问题 | 修复 |
|---|------|------|
| REG-1 | 五段式别名生成引用不存在的变量 `cur`（NameError） | 改为 `cur_label` |
| REG-2 | `renumber_sentences` 未重映射单元坐标键（坐标悬空） | 整体重映射 |
| REG-3 | `merge_sentences` 晚句单元 offset 未按句起点差平移、键泄漏 | 重写（含 offset 平移规则） |
| REG-4 | validate 在句子引用缺失时崩溃（build_summary 直接 get_sentence） | 跳过缺失句并报告 |
| REG-5 | analysis 含 inf/NaN 被静默接受 | 加载时拒绝非有限数值 |
| REG-6 | integrity 遇到被目录占用的产物文件崩溃 | read_oto/read_json_strict 显式 DataError |
| REG-7 | 变异隔离中真实包遮蔽变异包 | 中性 cwd + PYTHONPATH + conftest 条件插入 |
| 另 | oto.ini 编码检测顺序（UTF-8 排在 SJIS 后会被误读） | UTF-8 优先 |
| 另 | 变异常量工厂丢失替换值（闭包 bug，曾使全部常量变异失效） | 闭包绑定 repl |
| 另 | 本机 GBK 控制台导致 QA 子进程输出解码崩溃 | 子进程 errors="replace" + stdout 重配置 |

## 8. 已知限制

- 语言包 `lyric_to_units` 汉字表为常用子集（约 70 字）；表外汉字需直接输入拼音（显式报错，不静默）。
- oto.ini 读取的 SJIS/CP932/GBK 启发式检测存在字节重叠误判可能（本项目编译产物为 ASCII 安全，不受影响）。
- 深层 `C+V` 拆音拼接为 FUTURE（默认到「过渡+主体」为止）。
- 英语 ARPA/X-SAMPA 语言包为 FUTURE。
- 变异白名单中的行号随代码变更需同步更新（有注释说明）。
- 本机 `pip check` 存在无关历史包冲突（parselmouth 等旧 GUI 时代依赖），已过滤不计入门禁；干净环境通过。

## 9. Clean build 命令

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e . numpy soundfile pytest pytest-cov hypothesis ruff mypy
```

## 10. 完整 QA 命令

```powershell
python qa.py                      # 完整（含覆盖率与变异，约 45 分钟）
python tools/qa_clean_env.py      # clean-env 场景自检
```

## 11. 结论

所有 MUST 需求已实现并通过验证；Requirement Matrix 无未解释的 MUST；
核心 CLI 可操作；Core 不依赖模型/GUI（纯 stdlib，测试强制）；编译可重复
（golden + clean rebuild 逐字节一致）；选择确定性；OpenUtau 适配层复用同一
选择核心；关键数据不变量（Permanent Coordinate / Source Timeline / Alias Identity /
Determinism）均有专项测试；全部 acceptance/regression 通过；QA 实际执行；
覆盖率 96.9%、变异有效杀灭率 100%；lint/typecheck/build 通过；
clean environment 可重现；README 含从零构建与 QA 指引；
不存在未说明的 stub、placeholder 或临时实现。

**宣布：JRH v0.1 Stable Implementation 完成。**
