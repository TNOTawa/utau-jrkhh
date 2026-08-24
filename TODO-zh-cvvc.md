# TODO：中文音源支持 —— ✅ 已完成（本轮交付）

> 状态：**中文全链路已实现并通过全量测试（593 passed）**。
> 本文件保留为收尾记录与后续工作清单。

## 已完成（本轮）

- [x] **1. 中文音素映射**：`jrh/importers/mfa_zh.py` —— MFA 普通话音素 → zh-pinyin 音节。
      规则移植参考插件生效路径并按 **DJUTAU bank 全量实测校准**（459 TextGrid / 99 种音素 /
      4005 音节，非法标签 3/4005 = 0.07%）：声调剥离、介音吸收（tɕ+ow=就 jiu、tɕʷ+e=觉 jue）、
      腭化/唇化声母虚拟介音（ʎ+ɛ+n=连 lian、xʷ+a=花 hua）、o+ŋ=eng / u+ŋ=ong、
      裸 o 多音映射（这=zhe、那=na、得=de）、ɲ+y=语 yu、裸 ʐ̩=日 ri、儿化 ɻ/ɚ→er 独立音节、
      ʔ 作声母兼词首边界、n 韵尾同词+音位配列约束（防「可能」→kon）、零声母虚拟
      consonant=min(30ms, 元音首音素×0.2)。
- [x] **2. 中文 henki 导入**：`henki.py` 按 `meta.language` 自动分发（japanese/chinese）；
      中文**每切片独立成句**、单切片资产以切片文件命名（`assets/qfcy_0000.wav`，
      供「定向已有文件」）；words 层词区间参与韵尾约束；窗口钳制统一处理浮点噪声。
- [x] **3. 中文 VC 别名方案**：**presamp 标准短 ID**（`an t`/`ir zh`/`i0 c`/`e0 j`/`vn q`/
      `i ny`/`a hw`），`pinyin.py` 的 `vc_vowel`/`vc_consonant` 返回；短 ID 表 =
      `jrh/languages/presamp.py` 内置标准 presamp.ini（3920 字节、与生态模板逐字节一致；
      **单一事实来源**：交付文件 + 别名映射 + OpenUtau 内置 zh-cvv 音素器三处同源，
      源码级实证 zh-cvv 读音源内 presamp.ini 的 [VOWEL]/[CONSONANT] 生成
      `{元音ID} {辅音ID}` 空格分隔别名、VC 放负位置、缺别名回退 CV）。
      枚举外音节（yo/lo/den/…）两侧 None → 不生成 VC（与 OpenUtau 回退一致）。
- [x] **4. 自动拼字**：`jrh combine <project> [--dry-run] [--config <json>]` —— 母版侧
      （每音节一个 Asset+Sentence+Unit）；缺失集合 = 410 − 母版已有 label；源选择 =
      同 label 组内有效组序 rank0 + 跨 label 统计（辅音近中位时长/元音最长）；
      模糊回退 sh~s/zh~z/ch~c/l~n~r/f~h + 前鼻/后鼻（报告标注 fuzzy）；crossfade 移植
      本项目 `_enhanced_crossfade`（RMS 0.5~2.0 + 余弦 S-curve + 2ms 端点）到
      `jrh/audio/combine.py`；冻结项目拒绝；全确定性。
- [x] **5. 中文 export-vc**：`vc_supplement.py` 语言无关扩展 —— 中文母版交付
      **presamp.ini**（内置标准模板逐字节）；追加行 = VC + **派生 CV**
      （仅原版缺失的 base 别名——拼字 Unit/被剔除音节自动补齐）；原版 oto 逐字节保真 +
      原版 wav 原样拷贝；空格冲突校验沿用（未剥 VC 行的手剥前版本会被明确拒绝）。
- [x] **6. 已有功能对齐**：优先级保留（原版组序 → candidate_groups 人工排序）、
      原参数原样（毫秒→采样点无损）、`--dry-run` 映射报告、中文合成 bank 夹具、
      单元/验收/中文 cvvc golden 测试全齐。
- [x] **附加（用户要求）**：`export_sentence_wavs` **整资产句「定向已有文件」**——
      句 WAV 文件名 = 资产文件名、原样复制不重复转码（日语+中文统一生效；
      henki 单切片句与拼字句命中，多切片句仍写 sentence_NNN.wav）。
- [x] **文档**：JRH_SPEC §5.1/§5.3/§7/§12（中文导入、presamp 短 ID、combine、
      定向已有文件）；AGENTS.md 同步。

## 关键事实与坑（本轮实证）

- **presamp.ini 官方规范已核验**（SuibianP/utau-zh-docs，全文见 `presamp-spec.md`）：
  `[VOWEL] v=V=CV,…=vol`（vol 未启用）、`[CONSONANT] c=CV,…=flag`（flag=交叉渐变开关，
  b/p/d/t/g/k=1 是爆破音不做交叉渐变）。参考插件**不写** presamp.ini（内置字典），
  本项目的 presamp.ini 交付是自建能力，模板取自三色あやか/Nottthat_CN 两份逐字节相同的
  标准文件。
- **OpenUtau 内置 zh-cvv 源码核验**（`OpenUtau.Plugin.Builtin/ChineseCVVCPhonemizer.cs`）：
  读音源内 presamp.ini 的 [VOWEL]/[CONSONANT]/[REPLACE]；VC 别名 `"{prevVowel} {consonant}"`；
  VC 放负位置 `position = -vcLen`；缺 VC 回退 CV 原文。→ 交付完整标准 presamp.ini 即保证
  兼容，别名永不漂移。
- **MFA 词典形态**（mfa_zh.py 内注释详列）：腭音吸收介音（就=tɕ+ow、见=tɕ+e+n）、
  o+ŋ=eng（能/成/朋/正）vs u+ŋ=ong（中/工/动）、裸 o 多音（这/可/热/得/特/那）、
  m+w+o=末 mo、p+w+o=伯 bo、j+u+ŋ=用 yong、ɲ+y=语 yu、tɕʷ/ɕʷ=决/雪。**勿回退**。
- **整资产句定向已有文件**改变了 henki 导入的资产命名与编译产物 wav 名：
  默认 golden 已重生成（仅句 3 的 `sentence_003.wav→src2.wav`，人工核对过），
  ja cvvc golden 不受影响。
- 参考插件的中文 VC 宽窗口 bug（L1444）继续**不移植**（本项目 `vc_timing()` 已修正）。

## 后续工作（未做，按需开启）

- [ ] **presamp.ini 子集裁剪版**（按 bank 实际覆盖裁剪；用户已同意留作 TODO，
      当前交付完整标准模板）。
- [ ] **中文标注人工精修后重新导出**：`import-henki`（DJUTAU）→ `combine`（全自动）→
      用户手动精修母版 timing/标注 → `export-vc`。当前流程已按此设计就绪；
      DJUTAU 实测导入：459 句 / 4005 单元 / 原版 1018 条参数吸收（其余逐条报告）。
- [ ] 用户的**人工剥离版 oto** 到位后替换 `--oto` 输入做最终交付验证。
- [ ] 三色あやか 转 JRH（无 TextGrid 路径，价值存疑，暂缓）。
- [ ] 日语 `jrh combine`（机制可扩展，本轮锁定中文）。
- [ ] 句 wav 冲突检测的极端场景加固（同名不同资产的手工项目）。

## 验收标准核对（全部通过）

- ✅ 中文 bank → 母版导入：原参数原样、组序保留、dry-run 报告、缺失逐条列出
- ✅ `compile --cvvc` 中文产出 presamp 短 ID（`e n`/`ou sh`/`i h`/`ao m`…）
- ✅ `export-vc` 中文：原版逐字节 + VC/派生 CV 追加 + wav 拷贝 + presamp.ini 交付
- ✅ 自动拼字：缺失 CV 音节补齐（母版侧，crossfade 合成，报告/配置/模糊回退）
- ✅ 全部新能力有 unit/CLI/golden 测试；`qa.py` 通过（mypy 的 numpy 存根问题为
      已知预存环境问题，与本次改动无关，此前已用未改动文件实证）
