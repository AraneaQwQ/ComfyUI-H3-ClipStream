# 版本说明（VERSION.md）

> 版本铁规：每次改动前，把旧版本完整快照存入 `archive/<日期>-<commit 短 hash>/`，并在本文件顶部追加一条说明。
> 只有用户的明确命令才能删改 `archive/` 中的旧版本。

## 2026-10-02 · `2ec770a`（当前基线）

- 快照：`archive/2026-10-02-2ec770a/`（36 个文件 / 440 KB，由 `git archive HEAD` 解出，与 `git ls-files` 一一对应）。
- 该基线包含：下一节 `v0.7.0` 的全部内容 + `tests/` 测试套件（61 用例）+ 本文件的版本铁规 + `.gitignore` 排除 `archive/`。
- 本次改动（下一版）：新增 `MiniMaxClipBinLongBuilder` 长视频拼接节点——按镜头顺序读取卡片内的 MP4，做一致性预检后用 ffmpeg 拼接成一个长片。卡片显示与 meta 字段**不变**：重叠帧只在拼接节点的报告里说明，不在卡片上加注（用户反馈：卡片上加注会让人误以为「当前保存的视频里有重叠」，指代不清）。

## 2026-10-02 · `84c1484`（上一基线）

- 快照：`archive/2026-10-02-84c1484/`（28 个文件 / 391 KB，与 `git ls-files` 一一对应，排除 `.git`、`__pycache__`、`archive/`）。
- 该基线包含：ComfyUI V3 API 迁移（`io.ComfyNode` + `ComfyExtension` + `define_schema` + Nodes 2.0 DOM）、卡片删除（单卡/双卡，含路径安全与项目锁）、Picker 缩放控件、`enable_audio_context` 开关、raw-bytes 提取性能修复、Dual Saver/Picker 与 `h3-clipstream` 存储目录改名。
- 版本只存在于 git tag 与本文件；源码中没有版本字符串，也没有需要改的 `pyproject.toml`。
- 归档目录不进版本控制：`archive/` 已写入 `.gitignore`。需要把归档纳入 git 时请明确说明。

## Tag 线（重建）

旧 tag `v0.2.0`–`v0.6.2` 全部**不是** `main` 的祖先（历史被重写过，九个 tag 指向的提交都不可达）。它们保留在仓库里不动，只作为「不可达历史线」记录：

| 旧 tag | 指向 | 状态 |
| --- | --- | --- |
| `v0.2.0`…`v0.6.2` | `c140ae9`…`5335715` | 不可达历史线，保留不删 |

新线从 `v0.7.0` 起，与 `main` 的祖先关系可验证：

| tag | 指向 | 含义 |
| --- | --- | --- |
| `v0.7.0` | `84c1484` | V3 API 迁移基线（本文件描述的快照） |
| `v0.7.1` | `2ec770a` | 版本铁规落地 + `tests/` 测试套件 |
| `v0.7.2` | 本提交 | 长视频拼接节点 `MiniMaxClipBinLongBuilder`（第 11 个节点） |

打 tag 与校验：

```powershell
git tag -a v0.7.0 84c1484 -m "V3 API migration baseline"
git tag -a v0.7.1 2ec770a -m "version rule + test suite"
git tag -a v0.7.2 HEAD -m "Clip Long Builder: shot-order concat with ffprobe pre-check"
git merge-base --is-ancestor v0.7.0 HEAD   # 退出码 0 = 可达
```

## 测试

```powershell
cd C:\Users\az\Documents\Codex\projects\ComfyUI-H3-ClipStream
$env:COMFYUI_ROOT = 'E:\ai\ComfyUI-aki-v3\ComfyUI'
& 'E:\ai\ComfyUI-aki-v3\python\python.exe' -m unittest discover -s tests -t .
```

- 当前结果：`Ran 96 tests ... OK (skipped=1)`（61 → 96：新增 `tests/test_long_builder.py` 35 用例）。唯一 skip 是 Windows 上创建目录符号链接需要权限（WinError 1314），该用例在有权限时会跑。
- `COMFYUI_ROOT` 只在 schema 测试里必需；从 `custom_nodes` 下运行时会自动推断根目录。
- 覆盖范围：
  - `tests/test_frame_grid.py`：像素帧 ↔ latent step 往返、`VIDEO_RUN_GRID` 每点可达、`context_length` 只落在整 step 上、clipbin 与 motion_context 两套帧数口径一致。
  - `tests/test_latent_codec.py`：`_unpack_latent` / `_pack_latent` / `_standardize_image_tensor` / `_standardize_audio_dict` 的容器形状与不改动源对象。
  - `tests/test_asset_paths.py`：`checked_asset_dir` 拒绝越界 id、嵌套项目目录和符号链接卡片；预览 URL 随卡片重写而变。
  - `tests/test_clip_bin_store.py`：单卡与双卡存取往返、项目索引排序与丢失后重建、删除语义、shot tag slug 与唯一性、Auto tag 按项目递增。
  - `tests/test_long_builder.py`：血缘反向回溯与断链/循环告警、`start_clip_id` 截断、手写 `clip_sequence` 覆盖、变体选择策略、ffprobe JSON 解析与帧率分数解析、`classify_join` 的分辨率/帧率/音轨/采样率判定、`seam_warnings` 的未裁接缝判定（首段永不告警）、concat list 转义、以及 `MiniMaxClipBinLongBuilder` 的端到端装配（用假 ffmpeg/ffprobe）。
  - `tests/test_node_schema.py`：锁定 11 个节点的 id / category / 输入 id 与 optional / 输出 display_name 顺序 / Picker mode 选项 / `context_length` 选项 / `is_output_node`，并校验 `H3ClipStreamExtension().get_node_list()` 返回同一批。
- 升级节点或改动 schema 时，`test_node_schema.py` 会失败——那是有意的：先改测试再改实现，README 的节点表同步更新。

## 已知问题（未修，已用测试锁定现状）

- `clipbin/_shared.py` 的 `_unpack_latent`：`torch.Tensor` 本身有 `.unbind`，所以「纯张量」分支不可达。未加 batch 轴的 `[C,T,H,W]` 会按 C 轴拆分，第二段被当成 audio 并加上 batch 轴。ComfyUI 实际传入的是批处理形状，不受影响；`tests/test_latent_codec.py::test_unbatched_bare_tensor_is_split_on_its_channel_axis` 记录了这个行为。改动它属于功能升级，需要单独决定。

## 变更记录

- 2026-10-02：建立 `archive/` + `VERSION.md` 版本基线（本文件）；`.gitignore` 排除 `archive/`。
- 2026-10-02：新增 `tests/`（61 用例，5 个套件 + `tests/_support.py` 装载助手）。
- 2026-10-02：重建 tag 线 —— `v0.7.0` → `84c1484`、`v0.7.1` → `2ec770a`；旧 `v0.2.0`–`v0.6.2` 标注为不可达历史线并保留。
- 2026-10-03：新增 `clipbin/long_builder.py` + `clipbin/long_nodes.py`（`MiniMaxClipBinLongBuilder`，第 11 个节点）；`clipbin/clip_bin_manager.py` 抽出 `sanitize_project_name()` 供长片输出目录复用（行为不变）；`tests/test_long_builder.py` 35 用例，`tests/test_node_schema.py` 改为按 `MODULES` 元组锁定 11 个节点；README 新增「长视频拼接」章节与规范接线表。卡片显示与 meta 字段不变。
- 2026-10-03：`v0.7.2` → 本提交。
