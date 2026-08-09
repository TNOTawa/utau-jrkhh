# 架构（ARCHITECTURE）

## 1. 分层

```
┌─────────────────────────────────────────────┐
│ jrh.cli           CLI（argparse，JSON/文本输出，退出码） │
├─────────────────────────────────────────────┤
│ jrh.core          ★ 核心（纯 stdlib，无任何外部依赖）    │
│   model.py           Asset/Sentence/Unit/Project 数据模型
│   ids.py             永久坐标解析/格式化、ID 分配器
│   project.py         加载/保存/冻结/CRUD（唯一修改入口）
│   candidate_groups.py 候选分组 + 人工排序状态
│   analysis.py        时长/RMS 统计 + 自动建议排序
│   compile_engine.py  编译公式（FULL/$T/$B/CV）+ 报告
│   selection.py       候选选择引擎（L1~L6 + tie-break + 解释）
│   validate.py         schema + 语义验证
│   integrity.py        数据完整性（哈希/引用/文件存在）
├─────────────────────────────────────────────┤
│ jrh.languages      语言包（纯数据 + 规则，stdlib）      │
│   base.py            LanguagePack 接口
│   pinyin.py          jrh.zh-pinyin（无声调拼音）
│   romaji.py          jrh.ja-romaji（Hepburn，复用现有表）
├─────────────────────────────────────────────┤
│ jrh.formats        传统格式适配（编译目标）             │
│   oto_ini.py         oto.ini 写入/读取（毫秒换算）      │
├─────────────────────────────────────────────┤
│ jrh.audio          音频 IO（numpy/soundfile，惰性导入）  │
│   probe.py           Asset 探测（sr/时长/sha256）
│   export.py          原句 WAV 导出
│   rms.py             主体区域 RMS 计算
├─────────────────────────────────────────────┤
│ jrh.phonemizer     OpenUtau 适配（薄层，只调用 selection）│
│   adapters.py         Phoneme 列表结构（alias/position）│
└─────────────────────────────────────────────┘
```

## 2. 依赖方向（禁止反向）

```
cli → core, languages, formats, audio, phonemizer
phonemizer → core.selection（禁止把搜索算法复制进适配层）
audio → 仅 numpy/soundfile（惰性 import；core 不得 import audio）
core → 仅 stdlib
languages → 仅 stdlib
```

- `jrh/core` 导入任何第三方包（numpy/scipy/soundfile）或 `src/`（GUI）→ 架构违规，CI 检查。
- `jrh/audio` 的依赖在 `audio.py` 内部 `importlib` 惰性加载；CLI 命令在用到时显式报
  「缺少 numpy/soundfile」的稳定错误，而不是 import 时崩溃。

## 3. 数据流

### 3.1 编辑流

```
init → asset add → sentence create → unit create（label + timing）
     → analysis run → group order（auto 建议 / manual 排序）
     → validate → freeze → compile → validate
```

所有修改经由 `JRHProject` 单一入口，操作后写回磁盘（原子写：临时文件 + rename）。

### 3.2 编译流

```
JRHProject + LanguagePack + CompileConfig
  → compile_engine.compile()
      ├─ 逐 Unit：FULL / $T（consonant>0）/ $B / CV 参数公式（毫秒换算）
      ├─ 别名生成 + 冲突检测（冲突 ⇒ 失败，不写产物）
      ├─ 原句 WAV 导出（audio.export，--dry-run 跳过）
      ├─ oto.ini（固定排序）+ alias-map.json + build-report.json
      └─ 返回 BuildResult（含全部条目/冲突/报告）
```

### 3.3 选择流（phonemizer 契约）

```
目标单位序列 [t1..tn]（label + 前后文）
  → selection.select_sequence(project, pack, targets, prev=…)
      → 每单位：Level 判定 → 候选集 → 确定性排序 → 解释
  → phonemizer.adapters.to_phonemes(result)
      → [{phoneme: alias, position_ms: x}, ...]   # L3 返回 $T(负位置)+$B(0)
```

## 4. 关键设计决策（详见 ADR）

| 决策 | 结论 | ADR |
|------|------|-----|
| 配置文件格式 | JSON（stdlib、确定性、可校验） | ADR-0001 |
| 时间存储 | 采样点（句内时间轴 + 句采样率），oto 毫秒仅编译时换算 | ADR-0001 |
| 句首/句尾标记 | `R`（用户最终规格示例所用；BOS/EOS/SIL 保留未来） | ADR-0001 |
| 派生后缀 | `$T` / `$B` | ADR-0001 |
| 冻结语义 | 单向；`max_*_ever` 计数防编号复用 | ADR-0001 |
| 分割/合并编号规则 | 分割：原句留原号，新句取新号；合并：保留较小句号，冲突单元取新号 | ADR-0001 |
| RMS 区域 | 主体区域 `[offset+preutterance, offset+\|cutoff\|]` | ADR-0001 |
| L1 连续阈值 | `continuity_max_gap_ms` 默认 100ms，可配置 | ADR-0001 |
| 质量工具链 | pytest-cov / ruff / mypy / mutmut + 自研 mutation harness | ADR-0002 |

## 5. 稳定性保障

- **确定性**：所有 JSON `sort_keys=True`；所有列表排序显式 key；无集合/随机依赖。
- **原子写**：项目保存与编译产物写盘均「临时文件 + os.replace」。
- **失败显式**：任何损坏输入产生结构化错误（错误码 + 稳定退出码），不吞异常。
