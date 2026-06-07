# AGENTS.md - UTAU 音素优先级调节工具

## 项目概述
基于 customtkinter + matplotlib 的桌面 GUI 工具，用于可视化管理和排序 UTAU 音源的 `oto.ini` 条目优先级。

## 启动命令
```powershell
cd F:\Coding\utau-jrkhh
pip install -r requirements.txt    # 首次
pip install scipy                  # 缺失依赖，必须安装
python main.py
```

## 缺失依赖警告
`requirements.txt` 中未列出 `scipy`，但 `waveform_display.py` 依赖 `from scipy.signal import spectrogram`。务必先 `pip install scipy`。

## 目录结构
```
主入口: main.py → src/gui.py (App)
音源数据: 音源/{音源名}/oto.ini + character.txt + *.wav
参考数据: list.txt                            - 日语完整音素表（平假名 + 罗马音，119个）
源码: src/
  gui.py                  - 主界面（三栏 + 搜索栏 + 工具栏 + 全局快捷键）
  oto_parser.py           - oto.ini 读写、分组、拖拽重编号、改名、合并、平假名→罗马音
  audio_player.py         - 音频播放（单 worker 线程 + queue.Queue，主线程零阻塞）
  waveform_display.py     - 波形+频谱双 subplot，异步加载+缓存，Ctrl+滚轮缩放，拖拽平移
  draggable_list.py       - 支持拖拽排序的 tk.Listbox 子类
  phoneme_combine_dialog.py   - 新增拼字对话框（CV 拼接 + crossfade + 缺失提示）
  batch_combine_dialog.py     - 批量拼字对话框（list.txt 完整性检测 + 一键生成）
  phoneme_group_dialog.py     - 分组改名/合并对话框（右键菜单触发）
  perf_trace.py           - 性能追踪（默认禁用，仅开发调试用）
```

## 关键架构约定

### oto.ini 编码
日语音源文件常为 **Shift_JIS** 编码。`oto_parser._detect_encoding()` 按 `shift_jis → cp932 → utf-8 → gbk` 顺序自动检测。保存时沿用检测到的编码。**不要假定 UTF-8**。

### cutoff 参数语义（JinrikiHelper 约定）
`oto.ini` 中 `cutoff` 为负值，含义是 **cutoff = -音素片段时长**，而非从文件末尾算起的偏移。
播放区间：`[offset, offset + |cutoff|]`。
这与其他 UTAU 工具的 cutoff 语义不同，修改播放逻辑时必须遵守此约定。

### 音素分组规则
`get_base_phoneme(alias)` 用正则 `^(.*?)(\d+)$` 剥离末尾数字编号，`音源名前` → `音源名前`。
- `こ` → `こ`、`こ1` → `こ`、`ts2` → `ts`
加载时 `_normalize_entries()` 对每组按编号排序并自动重编号（位置 0 → 无后缀，位置 N → `{base}{N}`）。
组内拖拽排序后立即重编号。保存时使用 `entry.to_line()` 序列化。

### 音频播放线程模型
`AudioPlayer` 使用单一守护 worker 线程 + `queue.Queue` 消息队列：
- 主线程仅 `queue.put(("play", ...))` 或 `queue.put(("stop",))`，永不执行 IO
- worker 拿到 play 命令后先调用 `_drain_latest()` 排空队列取最新命令，跳过中间所有滞留请求
- 播放使用 `sd.play(blocking=False)` + 轮询 `sd.get_stream().active`，每 120ms 检查新命令
- **不要在主线程调用 `sd.play/stop/sf.read`**，否则会阻塞 UI
- `cleanup()` 方法在窗口 destroy 时调用，停止播放并清理

### 波形/频谱缓存
渲染数据缓存在 **系统临时目录** `utau_waveform_cache/`，按文件路径 + mtime 的 MD5 命名 `.npz` 文件。
- `{hash}_wf.npz`：降采样波形（≤4000 点峰值包络）
- `{hash}_sp.npz`：频谱（nperseg=2048, float32, dB 归一化）
缓存未压缩（`np.savez`），修改渲染逻辑后需更新 `_cache_key` 中的版本号（当前 `v5`）。

### CJK 字体
`draggable_list._get_cjk_font()` 按 `Microsoft YaHei → Meiryo → MS Gothic → SimHei → Yu Gothic UI` 顺序查找系统已安装字体。Listbox 构造时必须通过此函数获取字体，否则日语假名显示为方块。

### 性能追踪
`src/perf_trace.py` 提供 `trace()` / `end()` 记录耗时，`flush()` 追加到 `perf_trace.log`。当前在 `App.__init__` 末尾调用 `perf_trace.disable()` 禁用。调试时删除 `disable()` 调用并重启即可激活。**注意**：启用追踪时多线程 lock 竞争可能引入额外延迟，分析结果需考虑此偏差。

## 新增功能 (v2)

### 搜索栏
顶部搜索框实时过滤左侧分组列表，支持平假名/罗马音模糊匹配。搜索结果显示匹配数/总数（如 `5/48`）。搜索时清空样本列表和波形。

### 全局快捷键
所有快捷键在输入框（Entry/Text/TEntry）焦点下不触发（`_is_typing_widget()` 检查）：
| 按键 | 功能 |
|------|------|
| `Q` / `E` | 上一个/下一个分组 |
| `W` / `S` | 波形放大/缩小 |
| `A` / `D` | 波形左移/右移 |
| `1`~`5` | 设置 offset / overlap / preutterance / consonant / cutoff 标记到鼠标位置 |
| `Space` | 播放/暂停当前样本 |
| `↑` / `↓` | 组内上移/下移条目（自动重编号） |
| `Delete` | 停止播放 |
| `Ctrl+滚轮` | 缩放波形 |
| `左键拖拽` | 平移波形 |

标记设置逻辑（`_on_set_marker`）：
- `offset` → 直接设为鼠标时间
- `overlap` / `preutterance` / `consonant` → 相对于 offset 的偏移
- `cutoff` → `-(鼠标时间 - offset)`，保证为负值

### 分组右键菜单
右键分组弹出菜单，支持两种操作：
1. **改名** (`RenameGroupDialog`)：修改组名，允许将条目合并到目标组（若目标组已存在则弹出确认）
2. **合并到...** (`MergeGroupDialog`)：选择目标组进行合并，被合并组的条目 alias 前缀变为目标组前缀，目标组自动重编号

底层 API：`OtoBank.rename_group(base, new_base)` / `OtoBank.merge_group(from_base, to_base)`

### 新增拼字 (PhonemeCombineDialog)
拼合两个音素条目（辅音源+元音源），生成新的组合音素：
- 输入目标别名后自动拆分 CV（`split_japanese_cv`），左侧显示相同辅音分组，右侧显示相同元音分组
- 支持平假名 ↔ 罗马音一键切换
- "缺少"下拉菜单列出 `list.txt` 完整表中缺失的音素，选中后自动填入别名
- 音频拼接函数 `combine_audio_entries()` 使用 `_enhanced_crossfade()`：
  - 辅音取 `[offset, offset+consonant)` 片段，元音取 `[offset+consonant, offset+|cutoff|)` 片段
  - RMS 振幅匹配（增益限制 0.5~2.0）、余弦 fade（S-curve）、端点 2ms fade-in/out
- 生成文件名格式 `C{alias}.wav`（存在则追加 `_1`, `_2`...）
- oto 参数：offset=0, consonant/overlap/preutterance 继承辅音源，cutoff=-总时长
- 应用后通知主窗口 `refresh_after_combine()` 刷新并定位到新分组

### 批量拼字 (BatchCombineDialog)
基于 `list.txt` 的 119 个完整音素对照 `ALL_REQUIRED_PHONEMES`，检测缺失音素并批量生成：
- 自动分组缺失音素的辅音/元音类型，左右两栏分别配置来源样本
- 辅音候选分组支持降级回退（`_CONSONANT_FALLBACK`：如 `pw→p`, `ky→k`）
- 底栏总览用红/绿标注每个缺失音素的配置状态
- 一键生成：遍历所有缺失音素，用各自的辅音/元音样本组合生成 wav + oto 条目
- 生成逻辑与新增拼字一致

### oto_parser 新增 API
```python
OtoBank.rename_group(base, new_base) → bool    # 重命名分组（target 已存在返回 False）
OtoBank.merge_group(from_base, to_base)         # 合并分组并重编号
OtoBank.add_entry_to_group(entry, base)         # 追加条目到分组末尾并重编号
hiragana_to_romaji(text) → str                  # 平假名 → 罗马音
```
`rename_group` 和 `merge_group` 均保持条目在全局列表中的原有物理顺序。

### 平假名/罗马音双向转换
- `hiragana_to_romaji()`（`oto_parser.py`）：支持所有 119 个音素 + 小写假名/促音
- `_romaji_to_hiragana()`（`phoneme_combine_dialog.py`）：反向转换，最长前缀匹配（3→2→1 字符）

## 常规操作
- 打开音源：工具栏「打开音源文件夹」，选择含 `oto.ini` 的目录
- 搜索：在搜索框输入平假名/罗马音关键词实时过滤分组
- 切换分组：鼠标滚轮或 ↑↓ 键在左侧分组列表上移动，或 `Q`/`E` 全局快捷键
- 拖拽排序：在中间样本列表按住条目拖放到目标位置，组内立即重编号
- 标记设置：在右侧波形中移动鼠标到目标位置，按 `1`~`5` 分别设置标记点
- 分组操作：右键分组名 → 改名 / 合并到...
- 新增拼字：工具栏「新增拼字」，选择辅音+元音来源样本，设置目标别名
- 批量拼字：工具栏「批量拼字」，为每种辅音/元音类型配置来源，一键生成所有缺失音素
- 保存：工具栏「保存 oto.ini」写回原文件（覆盖）
- 撤销：工具栏「撤销更改」从磁盘重新加载

## 严格遵守

以瞎猜接口为耻，以认真查询为荣。
以模糊执行为耻，以寻求确认为荣。
以臆想业务为耻，以人类确认为荣。
以创造接口为耻，以复用现有为荣。
以跳过验证为耻，以主动测试为荣。
以破坏架构为耻，以遵循规范为荣。
以假装理解为耻，以诚实无知为荣。
以盲目修改为耻，以谨慎重构为荣。
