# JRH v0.1 格式规范

> 状态：Stable（v0.1 实现基线）
> 来源：《计划.md》末尾封板的「JRH v0.1 核心规格」（用户确认的最终总结，优先于早期讨论）。
> 本文件是唯一权威规范；实现与测试均以本文件为准。

## 1. 定位

JRH（Jinriki Helper Recording? / JRH 母版格式）是一种**人力音源母版格式**：

> 以原素材连续片段为基础、以单字永久坐标为身份、以 VCV/CVVC 式原音设定为唯一人工参数、
> 以五段式别名和自定义音素器为核心运行方式，并自动附带拆拼别名与简单 CV 搜索别名。

- JRH 是**母版（源代码）**；`oto.ini` 等传统格式是**编译产物**，可随时删除重建。
- 传统格式（CV/CVVC/VCV）只是主动兼容层，**不**为它们维护独立原音参数。
- 机器（ASR/SOFA/静音检测/时长/RMS）只提供草稿与辅助排序，人工是最终权威。
- 核心不依赖：GUI、OpenUtau、ASR 模型、GPU、网络 API、传统 UTAU 格式。

## 2. 层级模型

```
Asset（原素材，不可变）
└── Sentence（原素材时间轴上的连续发声片段）
    └── Unit（句内单字，人工维护单位）
```

| 层级 | 身份 | 说明 |
|------|------|------|
| Asset | `asset_id`（字符串，如 `asset-001`） | 原始音频/视频文件，内容不可变 |
| Sentence | `sentence_id`（正整数，冻结后永久） | 连续发声片段；一个句子对应一个导出 WAV |
| Unit | `sentence_id:unit_id`（永久坐标） | 一个字；人工维护的唯一单位 |

**永久坐标**：`s:u`（如 `12:6`）是 Unit 的唯一身份。五段式别名中的后三项只是人类可读说明，
程序内部**禁止**通过解析后三项来定位 Unit。

## 3. 编号生命周期

- **制作阶段（draft）**：允许整理编号（分割、合并、重排）。
- **冻结（freeze）**：一次性操作，冻结后：
  - 修改文字、发音单位、时间边界、重新分析 **均不得改变编号**；
  - 删除的编号**永久保留空位，不得复用**；
  - 新增 Unit 只能取得新编号（`max_id_ever + 1` 递增）；
  - 追加新 Sentence 同理。
- **冻结后分割句子**：原句保留原 `sentence_id` 与其单元原编号；新片段获得**新** `sentence_id`，
  其单元按来源顺序取得句内新编号（分配器保证不复用已删除编号）。
- **冻结后合并句子**：保留较小 `sentence_id`；被并入句的单元尽量保留原 `unit_id`，
  冲突时按来源顺序分配新编号。
- 项目元数据维护 `max_sentence_id_ever` / `max_unit_id_ever`，保证删除后编号不复用。

## 4. 项目结构

开发状态为目录；发布状态可打包为 ZIP 容器（v0.1 只实现目录形式，ZIP 为 FUTURE）。

```
my_voicebank.jrh/
├── manifest.json              # 格式标识、schema 版本、生成器信息、冻结状态
├── data/
│   ├── assets.json            # 原素材列表（不可变）
│   ├── sentences.json         # 句子列表（按句编号排序）
│   ├── units.json             # 单元列表（按 (sentence_id, unit_id) 排序）
│   ├── candidate_groups.json  # 当前字候选分组顺序状态
│   └── analysis.json          # 分析汇总缓存（可随时重新计算）
├── assets/                    # 原素材文件（可选；允许相对路径引用包外文件）
└── builds/                    # 编译产物（全部可删除重建）
    └── openutau-jrh/
        ├── sentence_001.wav   # 每句一个原句 WAV
        ├── oto.ini
        ├── alias-map.json     # 编译别名 → 来源坐标反查表
        └── build-report.json  # 结构化编译报告
```

- 所有 JSON：`json.dump(..., sort_keys=True, ensure_ascii=False, indent=2)`，
  键序确定性由 `sort_keys=True` 强制保证。
- 所有引用关系通过显式 ID 表达，禁止隐式依赖文件顺序。

### 4.1 manifest.json

```json
{
  "format": "JRH",
  "schema_version": "0.1.0",
  "generator": {"name": "utau-jrkhh", "version": "0.1.0"},
  "state": "draft",
  "language_pack": "jrh.zh-pinyin",
  "id_counters": {"max_sentence_id_ever": 3, "max_unit_id_ever": 9},
  "capabilities": ["source-timeline", "context-units", "candidate-groups"]
}
```

`state` 取值：`draft` | `frozen`。冻结后 `state` 不得回退。

### 4.2 data/assets.json

```json
{
  "assets": [
    {
      "id": "asset-001",
      "file": "assets/source_01.wav",
      "kind": "audio",
      "sha256": "…",
      "sample_rate": 48000,
      "num_samples": 1920000,
      "duration_seconds": 40.0
    }
  ]
}
```

- `file` 为相对项目根目录的路径；文件存在性由 validation/integrity 校验。
- Asset 不可变：任何修改 = 新增 Asset。`sha256` 用于完整性检测。
- 视频/时间戳映射字段（`source_time_base` 等）为 FUTURE。

### 4.3 data/sentences.json

```json
{
  "sentences": [
    {
      "sentence_id": 1,
      "asset_id": "asset-001",
      "sample_rate": 48000,
      "start_sample": 57600,
      "end_sample": 172800,
      "segmentation": {
        "provider": "manual",
        "confidence": null,
        "original_start_sample": 57600,
        "original_end_sample": 172800,
        "manually_adjusted": false
      }
    }
  ]
}
```

- 句边界用**采样点**（在 Asset 时间轴上、以 `sample_rate` 为准）表达。
- v0.1 约束：`sentence.sample_rate == asset.sample_rate`（重采样为 FUTURE）。
- `start_sample < end_sample`；句范围必须在 Asset 范围内（validation 校验）。

### 4.4 data/units.json

```json
{
  "units": [
    {
      "sentence_id": 1,
      "unit_id": 2,
      "label": "hao",
      "enabled": true,
      "timing": {
        "offset": 48000,
        "consonant": 22000,
        "cutoff": -115200,
        "preutterance": 14400,
        "overlap": 9600
      },
      "analysis": {"duration_ms": 2400.0, "rms_dbfs": -18.7}
    }
  ]
}
```

- `label`：语言包定义的录音单位（如无声调拼音 `hao`、罗马音 `ko`）。
- `timing`：唯一一套原音设定，单位 = **句内时间轴上的采样点**（float 允许小数）。
- `analysis`：机器辅助缓存（可重算），不是权威数据。
- `enabled=false`：禁用候选（爆音/读错等），**任何层级都不得自动选中**。

### 4.5 原音设定（唯一一套，VCV/CVVC 式五参数）

参考 UTAU 社区 VCV/CVVC 标法，含义：

| 参数 | 语义 |
|------|------|
| `offset` | 原音窗口起点：前一音可延续尾部的取样起点 |
| `consonant` | 固定范围长度：从 offset 起到当前字起音/过渡结束（辅音结束点） |
| `cutoff` | **负值**，`cutoff = -窗口时长`（JinrikiHelper 约定；播放区间 `[offset, offset+\|cutoff\|]`） |
| `preutterance` | 从 offset 到当前字发音起点（先行発声点）的距离 |
| `overlap` | 从 offset 起与前一音交叠的区域长度 |

由此导出五个时间点：

```
offset ─── offset+overlap ─── offset+preutterance ─── offset+consonant ─── offset+|cutoff|
窗口起点     交叠点             当前字起音点           过渡/辅音结束点          窗口终点
```

**有效性约束（validation 强制）**：

```
0 ≤ overlap ≤ preutterance ≤ |cutoff|
0 ≤ consonant ≤ |cutoff|
```

纯元音字（无辅音）：`consonant = preutterance = overlap = 0` 合法。
句首字窗口起点即该字本身的起音（没有前一元音尾巴）。

### 4.6 候选分组（data/candidate_groups.json）

人工只维护「当前字」分组：

```json
{
  "groups": {
    "hao": {
      "mode": "manual",
      "ordered_unit_ids": ["5:4", "1:2", "8:1"]
    },
    "ni": {"mode": "auto"}
  }
}
```

- `mode=auto`：由时长/RMS 机械辅助给出初始顺序（可随时重算，不持久化顺序本身）。
- `mode=manual`：用户拖拽后进入人工模式；**重新分析不得静默覆盖**。
- 恢复自动排序 = 显式设置 `mode=auto`。
- 分组内缺条目的情况：`manual.ordered_unit_ids` 未覆盖的 Unit 排在已列条目之后，
  按（自动辅助顺序，永久编号）排序。
- 分组定义：`label` 相同的所有 enabled 或 disabled Unit 均属该组。

### 4.7 分析汇总（data/analysis.json，可重建缓存）

```json
{
  "revision": 3,
  "global": {
    "duration_ms": {"count": 1834, "mean": 412.6, "median": 386.0, "variance": 12842.1, "mad": 74.0},
    "rms_dbfs": {"count": 1834, "mean": -19.4, "median": -18.9, "variance": 18.2, "mad": 2.7}
  },
  "per_asset": {
    "asset-001": {"duration_ms": {"count": 120, "median": 390.0, "mad": 70.0}, "rms_dbfs": {"count": 120, "median": -24.1, "mad": 1.9}}
  }
}
```

- 统计只纳入：启用、且未被删除的普通 Unit。
- 推荐以 `median + MAD` 为主（稳健，抗异常值）；均值/方差保留参考。
- 用户修改边界、删除、新增后缓存失效，重新统计（线性计算，无模型）。

## 5. 编译契约（Compiler Contract）

目标：`openutau-jrh`（v0.1 唯一官方目标；CV/CVVC/VCV 兼容目标为 FUTURE/SHOULD）。

### 5.1 派生规则（唯一权威公式）

输入：Unit 的 `timing`（采样点，句子采样率 `sr`）。输出：oto.ini 条目（毫秒）。

毫秒换算公式：`ms = round(samples * 1000 / sr, 3)`，输出时去掉尾随零。

**FULL（五段式原生别名）**：原样五参数。

**TRANSITION（`$T`，过渡片段）**：区域 `[offset, offset+consonant]`，仅当 `consonant > 0` 时生成。

```
offset_T     = offset
consonant_T  = consonant
cutoff_T     = -consonant
preutterance_T = 0
overlap_T    = min(overlap, consonant)
```

**BODY（`$B`，当前字主体）**：区域 `[offset+preutterance, offset+|cutoff|]`。

```
offset_B     = offset + preutterance
consonant_B  = max(consonant - preutterance, 0)
cutoff_B     = cutoff + preutterance        # 恒 ≤ 0
preutterance_B = 0
overlap_B    = 0
```

**CV（简单搜索别名）**：与 `$B` 同一区域、同一参数；命名按候选分组顺序：
排序第 0 → `label`，第 n → `label{n}`。

**不生成**：ENDING / 尾元音释放类别名（句尾直接使用当前字原音尾部）。

### 5.2 别名命名

五段式：`{sentence_id}-{unit_id}-{prev}-{cur}-{next}`

- `prev/cur/next` 为语言包生成的可读显示单位；句首/句尾使用保留标记 `R`（休止）。
- 派生后缀：`$T` / `$B`，如 `1-2-ni-hao-a$T`、`1-2-ni-hao-a$B`。
- 保留标记与派生后缀构成内部命名空间，语言包不得产出含 `$` 的 label。
- **别名字符集（label 允许字符）**：Unicode 字母、数字及 `@{}#.:_~+<>[]()%`。
  禁止：空白、`,` `=` `;` `"` `'` `\` `-` 及控制字符（validation 强制）。

### 5.3 输出文件

- **原句 WAV**：每句一个 `sentence_{id:03d}.wav`，内容 = Asset 的 `[start_sample, end_sample)`。
  所有别名共享同一 WAV，**禁止无意义复制音频**。
- **oto.ini**：`wav=alias,offset,consonant,cutoff,preutterance,overlap`（毫秒）；
  编码 UTF-8；条目排序：按 `(sentence_id, unit_id, kind)`，
  `kind` 顺序 = FULL(0) → TRANSITION(1) → BODY(2) → CV(3)。
- **alias-map.json**：`{alias: {sentence_id, unit_id, kind, wav, params}}`，
  用于编译产物反查 JRH 来源（Source Timeline 不变量）。
- **build-report.json**（结构化）：

```json
{
  "target": "openutau-jrh",
  "project": {"language_pack": "jrh.zh-pinyin", "frozen": true},
  "config": {"suffix_transition": "$T", "suffix_body": "$B", "rest_marker": "R", "continuity_max_gap_ms": 100},
  "summary": {"aliases_total": 42, "full": 12, "transition": 9, "body": 12, "cv": 9, "conflicts": 0, "missing": 0, "degraded": 0},
  "entries": [{"alias": "…", "sentence_id": 1, "unit_id": 2, "kind": "full", "wav": "sentence_001.wav", "params": {...}}],
  "conflicts": [{"alias": "…", "sources": ["1:2", "5:4"]}],
  "missing": [],
  "degraded": [],
  "unrepresentable": []
}
```

- **别名冲突不得静默覆盖**：编译时若两个来源产生相同 alias，必须记录到
  `conflicts` 并**整体编译失败**（错误退出，不产出 oto.ini），由用户解决。
- **降级/不可表示**：v0.1 无降级生成项（CV/CVVC 兼容目标才可能降级，FUTURE）；
  字段保留并恒为空数组。

### 5.4 可重复性

相同输入（JRH 数据 + 语言包 + 编译器版本 + 配置）必须产生**完全一致**的：
alias、oto 条目、候选选择、冲突报告、build manifest。
实现禁止依赖无序集合或随机行为；全部排序显式指定。

## 6. 候选选择引擎（Candidate Selection）

与 OpenUtau 解耦的 Core 服务。输入：项目 + 语言包 + 目标序列（`prev/current/next` 单位）
+ 前一个选择结果（连续性上下文）+ 配置。输出：每单位一个选择结果，含解释。

### 6.1 回退层级（确定性）

```
L1 continuous   原素材中真实连续的原音
L2 full         前元音与当前字匹配的完整原音（FULL）
L3 split        过渡片段 $T + 当前字主体 $B
L4 body         仅当前字主体（退化为 CV）
L5 substitute   语言包允许的近似替代
L6 missing      报告缺音
```

定义（目标当前单位 `C`、目标前一单位 `P`、上一次选择 `prev_sel`）：

- **L1**：`label(u)==C` 且 `u.sentence_id == prev_sel.unit.sentence_id` 且
  `u` 是该句内按时间顺序紧随 `prev_sel.unit` 的下一个 Unit（`unit_id` 大于且时间间隔
  `u.window_start - prev_sel.unit.window_end ≤ continuity_max_gap_ms`）。
  无前文（句首/前一个 missing）时跳过 L1。
- **L2**：`label(u)==C` 且 `leading_vowel(u) == target_leading_vowel`，
  其中 `leading_vowel(u)` = u 句内前一 Unit 的韵母/可延续元音（句首为 `None`），
  `target_leading_vowel` = `P==R ? None : pack.final_vowel(P)`。
- **L3**：存在过渡候选 T（`leading_vowel(T)==target_leading_vowel` 且
  `initial(T)==initial(C)` 且 `T.consonant > 0`）**且**存在主体候选 B（`label(B)==C`）。
  同时满足时 level 记为 split，输出 `[$T, $B]` 两个 phoneme。
- **L4**：`label(u)==C` 的任意启用 Unit。
- **L5**：`label(u) ∈ pack.substitutes(C)`（按语言包顺序）。
- **L6**：以上全空。

> 深层 `C+V` 拆音拼接为实验性能力（FUTURE），v0.1 不做。

### 6.2 同层排序（确定性 tie-break）

```
1. 原素材连续性：候选与 prev_sel 同句 → 优先
2. 当前字人工排序（manual mode 顺序；auto mode 用自动建议顺序）
3. 时长/RMS 统计辅助（robust_z 越小越接近音源常态）
4. 永久编号 (sentence_id, unit_id) 字典序兜底
```

- L3 的过渡候选（T）来自多个不同 label 的单元，其「人工排序」取其**自身 label 分组**的
  有效顺序（过渡组不单独维护，计划约定）。
- **禁用候选（enabled=false）在任何层级都不得被选中。**
- **人工排序不得被重新分析静默覆盖**（`mode=manual` 优先级固定高于自动建议）。
- 同一输入必须永远给出同一结果。

### 6.3 解释输出

每次选择必须输出：命中级、所选 Unit、为什么选它（tie-break 各层比较）、
为什么没选其他候选（前若干落选者及理由）、是否降级、使用了哪些来源（s:u 列表）。

## 7. 语言包接口

语言包决定录音单位语义；核心不判断 `hao`/`ko`/`HH` 的语言学意义。

```python
class LanguagePack:
    name: str                       # 如 "jrh.zh-pinyin"
    unit_system: str                # 如 "pinyin-toneless"
    def lyric_to_units(self, lyric: str) -> list[str]   # 文本 → 录音单位
    def final_vowel(self, unit: str) -> str | None      # 韵母/可延续元音
    def initial_consonant(self, unit: str) -> str | None  # 起音辅音
    def substitutes(self, unit: str) -> list[str]       # 有序近似替代
    def validate_unit(self, unit: str) -> bool          # 是否为合法单位
```

v0.1 内置包：

| 包 | 单位 | 说明 |
|----|------|------|
| `jrh.zh-pinyin` | 无声调拼音 | `lyric_to_units`：CJK 查内置常用字表 + 拼音串贪心最长前缀切分；替代 = 同韵母； |
| `jrh.ja-romaji` | Hepburn 罗马音 | 完整假名表（沿用现有 `src/oto_parser.py` 的表）；替代 = 空 |

- `final_vowel("hao") = "ao"`；`initial_consonant("hao") = "h"`；纯元音 `initial = None`。
- 语言包自定义后续可通过插件/配置扩展（FUTURE）。

## 8. 机器辅助（默认离线可用）

- **时长**：`duration_ms = |cutoff| * 1000 / sr`（纯计算，无音频 IO）。
- **RMS**：对 Unit 主体区域 `[offset+preutterance, offset+|cutoff|]`（句内时间轴）
  计算 `rms_dbfs = 20*log10(rms+ε)`（需音频数据，numpy/soundfile，惰性导入）。
- **自动建议排序**（只用于 `mode=auto`）：
  1. 明显异常项（相对**素材局部**统计的 robust_z，样本不足时退回全局）靠后；
  2. 其余按与音源中位数的距离（先时长偏差、再 RMS 偏差）排序；
  3. 最后按永久编号。
- 不生成「质量总分」；界面不展示虚假评分。

## 9. CLI 契约

- 入口：`jrh`（console script）与 `python -m jrh`。
- 机器可读输出：`--format json`（默认人类可读文本）。
- **退出码**：
  - `0` 成功；
  - `1` 运行时/数据错误；
  - `2` 用法错误（argparse）；
  - `3` 验证失败（`validate`/`integrity` 发现错误，或 `compile` 冲突）；
  - `4` `phonemize --strict` 存在缺音。

## 10. 核心不变量（必须自动测试）

1. **Permanent Coordinate**：冻结后，改文字/发音/边界/重分析不改编号；删除编号不复用；
   新增不改变既有坐标。
2. **Source Timeline**：Unit → Asset 时间轴追溯链完整；
   编译产物（alias → wav → 句范围 → 素材位置）可反查。
3. **Alias Identity**：程序身份只用 `s:u`，不解析后三项。
4. **Determinism**：同输入 + 同版本 + 同配置 ⇒ 逐字节相同输出。

## 11. 版本与迁移

- `schema_version` 变更需更新 validation 与迁移指南（迁移指南 FUTURE）。
- 本规范当前版本 `0.1.0`。
