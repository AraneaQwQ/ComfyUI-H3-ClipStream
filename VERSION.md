# 版本说明（VERSION.md）

> 版本铁规：每次改动前，把旧版本完整快照存入 `archive/<日期>-<commit 短 hash>/`，并在本文件顶部追加一条说明。
> 只有用户的明确命令才能删改 `archive/` 中的旧版本。

## 2026-10-03 · `03e3124`（当前基线）

- 快照：`archive/2026-10-03-03e3124/`（42 个文件 / 530 KB，由 `git archive HEAD` 解出，与 `git ls-files` 一一对应）。
- 该基线包含 `v0.7.3` 的全部内容（Long Builder 面板化 + 按镜头序号定序），且已运行时验证。
- 本次改动（下一版 `v0.7.4`）：Clip Bin Picker 也改成选单驱动，并且能在选单里新建/删除项目——
  - `web/clip_bin_picker.js`：标题栏的项目名标签换成项目下拉框（列出素材库里每个文件夹并标卡片数），第一项 `＋ 新建项目…` 展开面板内的名字输入框 → 建库并把节点切过去；`project_name` 控件仍可手输，行为不变。
  - `clipbin/clip_bin_manager.py` 新增 `create_project()` / `delete_project()` 与 `MAX_PROJECT_NAME_LENGTH`：清洗名字、同名幂等（选中而非重复创建）、返回真正写出的文件夹名；删除整个项目（含全部卡片与归档视频），并要求 `confirm` 重复一遍项目名，防止另一个标签页里停着的面板删错文件夹。**两者都不带 `@project_locked`**——该装饰器经 `get_project_dir()` 顺手建目录，会让「是否已存在」永远为真。
  - 顺带修根因：锁的 key 计算抽成 `_project_lock()`，不再经 `get_project_dir()` 建目录（原来每次带锁调用都会顺手留下空文件夹），删除项目时复用同一把锁，避免边删边存。
  - `clipbin/clip_bin_api.py`：`list_video_projects_api()` → `list_projects_api(videos_only=False)`，`GET /minimax/clip_bin/projects` 支持 `?videos_only=1`；新增 `POST /minimax/clip_bin/project`（新建）与 `POST /minimax/clip_bin/project/delete`（删除整个项目）；同源校验抽成 `_csrf_block()`，三处写操作共用。
  - 样式合并：项目下拉框样式移到 `web/clip_bin_picker.css`（`.minimax-clip-bin-project`），删掉 `web/long_builder.css` 里的 `.h3-lb-project`；新增 `.minimax-clip-bin-new*`（内联新建行）与 `.minimax-clip-bin-danger*`（内联删除确认行）。
  - Long Builder 面板改请求 `?videos_only=1`，可见行为不变。
  - 测试 112 → 125：`tests/test_projects_api.py` 抽出 `BinFixture`，新增 `TestProjectCreation`（新建、同名幂等、名字清洗、空名/超长名拒绝）、`TestProjectDeletion`（删整库、连带删视频、`confirm` 不匹配报错、已不存在返回 `deleted: False`、清洗名对齐）与全量列表计数用例。
- 运行时验证：已把 6 个运行时文件覆盖到 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\ComfyUI-H3-ClipStream\` 并逐文件哈希核对（开发副本全部运行时文件无差异）。用户实测确认项目选单、新建项目与删除整个项目均正常 → **`v0.7.4` 运行时验证通过**，不需要回退。

## 2026-10-03 · `fffdee0`（上一基线）

- 快照：`archive/2026-10-03-fffdee0/`（39 个文件 / 496 KB，由 `git archive HEAD` 解出，与 `git ls-files` 一一对应）。
- 该基线包含 `v0.7.2` 的全部内容（Long Builder 首版：按血缘回溯定序，8 个输入 / 6 个输出）。
- 本次改动（下一版 `v0.7.3`）：按用户反馈把 Long Builder 做简单——
  - 镜头顺序改为**按卡片上的镜头序号升序**（`Shot 1 → Shot 2 → …`，缺前几段就从 `Shot 4` 开始），不再沿 `parent_clip_id` 回溯；删除 `end_clip_id` / `start_clip_id` / `clip_sequence` / `skip_missing` 以及 `MAX_CHAIN` / `INITIAL_MARKERS`。
  - 新增 `exclude_clips`（面板点卡片排除，手动填镜头标签片段也可以）；序号缺口、缺归档视频一律只写日志告警，不报错。
  - 输出只剩一个 `io.Video.Output('video')`，节点上直接内联预览（`ui.PreviewVideo` + `InputImpl.VideoFromFile`）；`report` / `total_frames` / `duration_seconds` / `filename` / `subfolder` 接口全部去掉，逐段审计写进 ComfyUI 日志。
  - 全部输入 `advanced=True`，收在高级开关后面。
  - 新增前端面板 `web/long_builder_panel.js` + `web/long_builder.css`：项目下拉框（只列有归档视频的项目）+ 卡片墙 + 点卡片排除 + hover 播放 + 摘要行；复用 `web/dom_panel.js` 与 `clip_bin_picker.css`。
  - 新增只读接口 `GET /minimax/clip_bin/projects`（`clipbin/clip_bin_api.py::list_video_projects_api`）。
  - 测试 96 → 112：新增 `tests/test_projects_api.py`，重写 `tests/test_long_builder.py` 的定序/排除用例，`tests/test_node_schema.py` 增加 advanced 与单输出断言。

## 2026-10-02 · `2ec770a`（上一基线）

- 快照：`archive/2026-10-02-2ec770a/`（36 个文件 / 440 KB，由 `git archive HEAD` 解出，与 `git ls-files` 一一对应）。
- 该基线包含：下一节 `v0.7.0` 的全部内容 + `tests/` 测试套件（61 用例）+ 本文件的版本铁规 + `.gitignore` 排除 `archive/`。
- 本次改动（下一版）：新增 `MiniMaxClipBinLongBuilder` 长视频拼接节点——按镜头顺序读取卡片内的 MP4，做一致性预检后用 ffmpeg 拼接成一个长片。卡片显示与 meta 字段**不变**：重叠帧只在拼接节点的报告里说明，不在卡片上加注（用户反馈：卡片上加注会让人误以为「当前保存的视频里有重叠」，指代不清）。

## 2026-10-02 · `84c1484`（更早基线）

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
| `v0.7.2` | `fffdee0` | 长视频拼接节点 `MiniMaxClipBinLongBuilder`（第 11 个节点） |
| `v0.7.3` | `5c7330d` | Long Builder 面板化 + 按镜头序号定序（去掉血缘回溯、多余输入与输出接口）。运行时已验证：用户覆盖运行副本后确认面板、`/minimax/clip_bin/projects` 与节点内联预览正常（单元 112 用例 + 真 ffmpeg/ffprobe 冒烟亦通过） |
| `v0.7.4` | `2b46aa2` | Clip Bin Picker 项目选单 + 选单内新建/删除项目（`create_project`、`delete_project`、`POST /minimax/clip_bin/project[/delete]`、`?videos_only=1`） |

打 tag 与校验：

```powershell
git tag -a v0.7.0 84c1484 -m "V3 API migration baseline"
git tag -a v0.7.1 2ec770a -m "version rule + test suite"
git tag -a v0.7.2 fffdee0 -m "Clip Long Builder: shot-order concat with ffprobe pre-check"
git tag -a v0.7.3 HEAD -m "Long Builder panel: pick project + cards, order by shot number, single video output"
git merge-base --is-ancestor v0.7.0 HEAD   # 退出码 0 = 可达
```

## 测试

```powershell
cd C:\Users\az\Documents\Codex\projects\ComfyUI-H3-ClipStream
$env:COMFYUI_ROOT = 'E:\ai\ComfyUI-aki-v3\ComfyUI'
& 'E:\ai\ComfyUI-aki-v3\python\python.exe' -m unittest discover -s tests -t .
```

- 当前结果：`Ran 125 tests ... OK (skipped=1)`（61 → 96 → 112 → 119 → 125：`tests/test_long_builder.py` 重写定序用例，`tests/test_projects_api.py` 覆盖项目列表、新建与删除）。唯一 skip 是 Windows 上创建目录符号链接需要权限（WinError 1314），该用例在有权限时会跑。
- `COMFYUI_ROOT` 只在 schema 测试里必需；从 `custom_nodes` 下运行时会自动推断根目录。
- 覆盖范围：
  - `tests/test_frame_grid.py`：像素帧 ↔ latent step 往返、`VIDEO_RUN_GRID` 每点可达、`context_length` 只落在整 step 上、clipbin 与 motion_context 两套帧数口径一致。
  - `tests/test_latent_codec.py`：`_unpack_latent` / `_pack_latent` / `_standardize_image_tensor` / `_standardize_audio_dict` 的容器形状与不改动源对象。
  - `tests/test_asset_paths.py`：`checked_asset_dir` 拒绝越界 id、嵌套项目目录和符号链接卡片；预览 URL 随卡片重写而变。
  - `tests/test_clip_bin_store.py`：单卡与双卡存取往返、项目索引排序与丢失后重建、删除语义、shot tag slug 与唯一性、Auto tag 按项目递增。
  - `tests/test_long_builder.py`：镜头序号升序定序（`Shot 12` 排在 `Shot 2` 之后）、无数字标签按 `created_at` 排在带序号卡片之后、`exclude_clips` 按 `clip_id` 或镜头标签片段排除、序号缺口告警、缺归档视频只告警不报错、preview 的 filename/subfolder 可寻址、变体选择策略、ffprobe JSON 解析与帧率分数解析、`classify_join` 的分辨率/帧率/音轨/采样率判定、`seam_warnings` 的未裁接缝判定（首段永不告警）、concat list 转义，以及 `MiniMaxClipBinLongBuilder` 的端到端装配（用假 ffmpeg/ffprobe）。
  - `tests/test_projects_api.py`：`list_projects_api()` 列出全部项目及其卡片数/视频数，`videos_only=True` 只留能成片的库；`create_project()` 新建空库、同名幂等、返回清洗后的文件夹名、空名与超长名报错；`delete_project()` 删除整库（含视频）、`confirm` 不匹配报错、库已不存在时返回 `deleted: False` 且不建幽灵目录。
  - `tests/test_node_schema.py`：锁定 11 个节点的 id / category / 输入 id 与 optional / 输出 display_name 顺序 / Picker mode 选项 / `context_length` 选项 / `is_output_node` / Long Builder 输入全部 advanced 且只有一个 `video` 输出，并校验 `H3ClipStreamExtension().get_node_list()` 返回同一批。
- 升级节点或改动 schema 时，`test_node_schema.py` 会失败——那是有意的：先改测试再改实现，README 的节点表同步更新。

## 已知问题（未修，已用测试锁定现状）

- `clipbin/_shared.py` 的 `_unpack_latent`：`torch.Tensor` 本身有 `.unbind`，所以「纯张量」分支不可达。未加 batch 轴的 `[C,T,H,W]` 会按 C 轴拆分，第二段被当成 audio 并加上 batch 轴。ComfyUI 实际传入的是批处理形状，不受影响；`tests/test_latent_codec.py::test_unbatched_bare_tensor_is_split_on_its_channel_axis` 记录了这个行为。改动它属于功能升级，需要单独决定。

## 变更记录

- 2026-10-02：建立 `archive/` + `VERSION.md` 版本基线（本文件）；`.gitignore` 排除 `archive/`。
- 2026-10-02：新增 `tests/`（61 用例，5 个套件 + `tests/_support.py` 装载助手）。
- 2026-10-02：重建 tag 线 —— `v0.7.0` → `84c1484`、`v0.7.1` → `2ec770a`；旧 `v0.2.0`–`v0.6.2` 标注为不可达历史线并保留。
- 2026-10-03：新增 `clipbin/long_builder.py` + `clipbin/long_nodes.py`（`MiniMaxClipBinLongBuilder`，第 11 个节点）；`clipbin/clip_bin_manager.py` 抽出 `sanitize_project_name()` 供长片输出目录复用（行为不变）；`tests/test_long_builder.py` 35 用例，`tests/test_node_schema.py` 改为按 `MODULES` 元组锁定 11 个节点；README 新增「长视频拼接」章节与规范接线表。卡片显示与 meta 字段不变。
- 2026-10-03：`v0.7.2` → `fffdee0`。
- 2026-10-03：`v0.7.3` 运行时验证通过；记录「混合帧率不修」的判定（MiniMax H3 归档视频恒为 24fps），代码未改。
- 2026-10-03：Clip Bin Picker 项目选单（`web/clip_bin_picker.js`）+ 选单内新建项目：`clipbin/clip_bin_manager.py::create_project`、`clipbin/clip_bin_api.py` 的 `list_projects_api(videos_only)` 与 `POST /minimax/clip_bin/project`、`_csrf_block()` 抽取；下拉框样式合并进 `web/clip_bin_picker.css`；Long Builder 面板改用 `?videos_only=1`；README 中英文新增「项目选单 / Project menu」章节；测试 112 → 119。
- 2026-10-03：Long Builder 简化（`v0.7.3`）——`clipbin/long_builder.py` 改按镜头序号定序（新增 `shot_number` / `shot_sort_key` / `numbering_gaps` / `resolve_shot_order`，删除血缘回溯与 `MAX_CHAIN` / `INITIAL_MARKERS`）；`clipbin/long_nodes.py` 输入全 advanced、输出单个 `video` 并内联预览；`clipbin/clip_bin_api.py` 新增 `list_video_projects_api` 与 `GET /minimax/clip_bin/projects`；新增 `web/long_builder_panel.js`、`web/long_builder.css`；README 中英文「长视频拼接」章节同步（面板、序号定序、选项表、日志取代 report）。
