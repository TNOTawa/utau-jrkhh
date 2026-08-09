# ADR-0001：JRH v0.1 实现期决策

状态：Accepted
日期：2026-08-07
关联：《计划.md》JRH v0.1 核心规格（封板部分）

## 背景

《计划.md》明确「配置文件暂不定死」「内部派生别名的具体命名……按前述默认答案处理」，
把若干细节留给实现期决定。本 ADR 记录选择与理由。
选择标准：**简单、确定性、可测试、可迁移、低耦合**。

## 决策

### 1. 配置文件格式：JSON（目录结构）

- 权威数据存 `manifest.json` + `data/*.json`，`json.dump(..., sort_keys=True, ensure_ascii=False, indent=2)`。
- 理由：stdlib 零依赖；键序确定性由 `sort_keys` 强制；可 schema 校验；任意语言可读写。
- 未选：YAML（需第三方解析、锚点/别名歧义）、INI（表达能力不足，五段式/分组结构表达困难）。
- 备注：计划提到 YAML 偏好，但明确「未落地」，且 JSON 满足所有硬约束；YAML 可做 FUTURE 转换器。

### 2. 时间存储：采样点 + 句采样率

- Unit 的 timing 五参数存**采样点**（句内时间轴，`float` 允许小数），句存 `sample_rate`。
- oto.ini 毫秒仅在编译时换算：`ms = round(samples * 1000 / sr, 3)`。
- 理由：与「保存原始媒体时间戳 / 工作音频采样点 / 工作音频采样率」的计划结论一致；
  不因采样率变化产生累计误差；换导出采样率可重算（FUTURE）。
- v0.1 约束：句采样率 = Asset 采样率（重采样 FUTURE）。

### 3. 句首/句尾标记：`R`

- 五段式 `1-1-R-ni-hao` / `1-3-hao-a-R` 使用 `R`。
- 理由：用户最终确认的 v0.1 规格示例（JRH_SPEC §5.2 基线）使用 `R`；
  AI 建议的 BOS/EOS/SIL/BR 作为保留标记不冲突——它们语义不同（句边界/静音/呼吸），
  呼吸事件为 FUT-004，届时引入专用标记。

### 4. 派生后缀：`$T` / `$B`

- 与计划最终规格示例一致（`1-2-ni-hao-a$T`、`1-2-ni-hao-a$B`）。
- 命名空间规则：label 字符集显式排除 `$`，派生别名不会与任何 label 冲突。

### 5. 冻结语义：单向 + 计数器防复用

- `freeze` 一次性；`state: frozen` 后不可回退。
- 项目维护 `max_sentence_id_ever` / `max_unit_id_ever`，新 ID = max+1。
- 理由：满足「只增不改、不复用」；计数器实现简单且可测试。

### 6. 冻结后分割/合并编号规则

- 分割：原句保留原 `sentence_id` 与原单元编号；新片段取新句号，单元按来源顺序取新号。
- 合并：保留较小句号；被并入单元的 `unit_id` 无冲突时保留，冲突时按来源顺序取新号。
- 理由：用户显式发起结构修改时允许坐标变化；「不复用」保证旧编号绝不指向新内容。

### 7. RMS 计算区域：主体区域

- `rms_dbfs` 在 `[offset+preutterance, offset+|cutoff|]` 上计算。
- 理由：窗口含前一元音尾巴（属于前一字），主体区域才代表当前字本身。

### 8. L1 连续阈值：`continuity_max_gap_ms = 100`（可配置）

- 计划示例「时间间隔 18 ms」为连续；明显间隔（如被删除单元留下的空隙）不算连续。
- 默认 100ms，编译/选择配置可覆盖；写入 build-report 保证可复现。

### 9. 语言包 `lyric_to_units` 边界

- zh-pinyin：内置常用汉字表 + 拼音串贪心最长前缀切分；表外汉字报显式错误（不静默）。
- 理由：核心零依赖；文本→单位转换本来就是语言包职责，表是数据可增长。
- 已知限制记录于 FINAL_VALIDATION_REPORT。

### 10. 编译冲突策略：失败而非覆盖

- 重复 alias ⇒ 编译失败（退出码 3）+ build-report 记录 conflicts。
- 理由：计划「不允许同名别名被静默覆盖」「显示冲突来自哪个编译目标」。

---

# ADR-0002：质量工具链与 QA 门

状态：Accepted
日期：2026-08-07

## 决策

| 环节 | 工具 | 备注 |
|------|------|------|
| 格式 | ruff format --check | |
| lint | ruff check | |
| typecheck | mypy | jrh、tools、qa.py |
| 测试 | pytest + hypothesis | |
| 覆盖率 | pytest-cov，行 ≥90%（core），关键模块 branch ≥80% | |
| mutation | `tools/mutate.py`（自研轻量 AST 变异器） | mutmut 仅作辅助参考；自研版本输出固定格式便于门禁 |
| 依赖审计 | pip check；pip-audit 可用时执行 | |
| 构建 | `pip install -e .` + compileall | |
| 入口 | `python qa.py`（唯一），CI 同入口 | |

理由：工具全部可通过清华 PyPI 镜像离线安装；`qa.py` 保证本地与 CI 行为一致；
mutation 门禁聚焦核心公式模块（timing 公式、别名生成、排序、选择层级），
防止「覆盖率高但断言无效」。

## 后果

- 新增依赖必须先加入 `requirements-dev.txt` 并在 CI 安装。
- mutation 门禁只统计「关键操作符」mutants（运算符/比较/常量/条件反转），
  不统计字符串/文档类 mutants，避免噪声。
