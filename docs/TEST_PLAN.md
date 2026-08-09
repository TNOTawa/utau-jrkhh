# 测试计划（TEST_PLAN）

## 1. 测试层级

| 层级 | 目录 | 内容 |
|------|------|------|
| Unit | `tests/unit/` | 模型、ID、公式、排序、选择引擎（table-driven）、语言包、oto 换算 |
| Integration | `tests/integration/` | 项目生命周期：init→asset→sentence→unit→analyze→freeze→compile→validate |
| Acceptance | `tests/acceptance/` | 通过真实 CLI 子进程跑端到端场景，校验 stdout JSON 与退出码 |
| Golden | `tests/golden/` | 固定 fixture 编译结果逐字段/逐字节比对（含 generator 脚本） |
| Negative | `tests/negative/` | 损坏输入：schema 错、非法 timing、别名不安全字符、哈希不符、文件缺失、范围越界、重叠/零长范围 |
| Property | `tests/property/` | hypothesis：序列化 round-trip、ID 分配器不变量、排序稳定性、公式恒等 |
| Regression | `tests/regression/` | QA 阶段发现的 bug 先加回归测试再修复 |

## 2. 必须覆盖的场景（MUST）

- 空项目；单/多 Asset；单/多 Sentence；单 Unit；大量同音 Unit
- Sentence split / merge；Unit delete / insert
- frozen IDs（改文字/边界/重分析不变号；删除不复用；新增不改旧号）
- alias collision；unsafe alias characters
- missing source file；source hash mismatch
- invalid / overlapping / zero-length time ranges；不同 sample rate（44100/48000 并存）
- 人工排序；恢复自动排序；disabled candidate
- FULL 命中 / context(L2) 命中 / L3 拆分 / L4 body / L5 替代 / 完全缺音（L6）
- 同一句连续选择；跨素材选择
- 重复编译一致性；clean rebuild（删除 build 目录后重建逐字节一致）
- serialization round trip；schema invalid data

## 3. 不变量专项测试

- `test_frozen_ids.py`：Permanent Coordinate
- `test_traceability.py`：Source Timeline（Unit → Asset 时间轴、alias → 来源反查）
- `test_alias_identity.py`：Alias Identity（身份只用 `s:u`；后三项变化不影响查找）
- `test_determinism.py`：同输入 ⇒ 同输出（编译/选择/报告逐字节一致）

## 4. 选择引擎 table-driven 设计

`tests/unit/test_selection.py` 每个 case 由 dict 描述：

```python
{
  "name": "L2 full 命中优先于人工排序",
  "targets": ["ni", "hao", "a"],
  "manual_orders": {"hao": {"mode": "manual", "ordered_unit_ids": ["5:4", "1:2"]}},
  "expect": {"levels": ["full", "full", "full"], "units": ["1:1", "1:2", "1:3"]},
  "expect_explanation": {"1:2": {"level": "full", "reason_contains": ["leading vowel"]}},
}
```

覆盖：每层级命中/落空、同层 tie-break 每一条规则、禁用候选、人工排序 vs 自动、
编号兜底、L3 的 $T/$B 组合、L5 替代、L6 缺音、确定性（同一 case 双跑一致）。

## 5. Golden 测试设计

- `tests/fixtures/`：`make_fixture.py` 用 stdlib `wave` 生成确定性正弦 WAV
  （固定频率/采样率/时长），并生成标准 JRH fixture 项目。
- `tests/golden/data/`：检入预期产物：
  - `oto.ini`（文本逐字节）
  - `build-report.json` / `alias-map.json`（逐字节）
  - `sentence_*.wav`（逐字节；fixture 生成确定性，故 WAV 可检入）
- 修改编译规则时须显式更新 golden（generator 脚本 + diff 流程）。

## 6. 质量门（qa.py 单入口）

顺序（任一失败即非零退出）：

1. `compileall`（语法/构建）
2. `ruff format --check`（格式）
3. `ruff check`（lint）
4. `mypy jrh tools qa.py`（typecheck）
5. `pytest` 全量（unit/integration/acceptance/golden/negative/property/regression）
6. coverage gate：核心模块行覆盖率 ≥ 90%（`pytest --cov=jrh.core...`）
7. mutation gate：`tools/mutate.py`（核心公式模块，关键 mutants 全杀）
8. `pip check` + 依赖审计（`pip-audit` 可用时执行）
9. `pip install -e .`（构建可安装）
10. CLI smoke tests（脚本化调用全部子命令）
11. 架构纯净检查（core 不 import 第三方/`src`）

## 7. CI

`.github/workflows/qa.yml` 与本地完全同入口：`python qa.py`。

## 8. QA 阶段（实现完成后执行）

独立视角实际运行 CLI（不只跑 unit test）：

```
clean env（临时 venv + pip install -e .）
→ jrh init → asset add fixture → sentence create ×N → unit create ×N
→ analyze → group order（auto/manual/disable）→ validate
→ compile → validate 产物 → phonemize 模拟 → 删除 builds → 重建 → 逐字节比对
```

并主动构造损坏 JRH（坏 JSON、坏 schema、错哈希、越界范围、重复坐标）验证错误处理。
QA 发现 bug：先加 regression test → 修复 → 全量回归。
