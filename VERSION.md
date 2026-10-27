# 版本说明（VERSION.md）

> 版本铁规：每次改动前，把旧版本完整快照存入 `archive/<日期>-<commit 短 hash>/`，并在本文件顶部追加一条说明。
> 只有用户的明确命令才能删改 `archive/` 中的旧版本。

## 2026-10-27 · `c456e07`（当前功能基线）

- 功能提交 `c456e07 feat: optimize clip media handling and long builder playback` 汇总下方五轮累计改动：Clip Bin 读取与 MP4 存盘性能优化、Long Builder 原速恢复、三区面板与分区顺序、恢复原速时自动匹配输出帧率。共 14 个文件，未改动节点 id，Long Builder 新输入仍只追加在原 schema 末尾。
- 发布副本与已测开发副本逐文件核对为 **53 文件 / 0 差异**；提交前复跑完整 Python **205 项通过、1 项既有权限跳过**，前端 **30 项通过**，全部 **8 个 JS** 语法及 Python 编译检查通过。真实 FFmpeg 的 `0.5x` / `0.75x` 两组均保留 **96/96 帧**，音调均为 440Hz。
- 运行副本已同步并核对 **53 文件 / 0 mismatch / 0 stale**。用户已确认可以推送；本次只更新 `main`，**不创建 tag**。

## 2026-10-27 · Long Builder 原速恢复自动帧率（已纳入 `c456e07`）

- 快照：`archive/2026-10-27-builder-auto-fps/` 保存本轮修改前的完整累计工作树（53 文件，不含 `.git`、历史 `archive/` 与缓存）。
- `fps` 的面板名称与说明改为「基准帧率」，输入 id、schema 顺序和默认值不变。普通重编码及 `1.0x` 仍直接按基准帧率输出；恢复原速时自动计算 `输出帧率 = 基准帧率 ÷ 切片慢放倍率`，因此 `24fps + 0.5x → 48fps`、`24fps + 0.75x → 32fps`，不再为了恢复原速而丢弃约一半或四分之一的已渲染帧。
- FFmpeg 仍使用 `setpts + fps` 同步缩短视频时间轴，音频继续 `atempo` 保音调；无损直拷规则、`copy` 冲突报错和既有输入接口均未改变。重编码后的回退帧数按输出时长 × 自动输出帧率计算，直拷仍按源段实测帧数求和。面板速度说明直接显示自动输出帧率，报告同时记录基准与输出帧率。
- 自动验证：完整 Python 回归 **205 项通过、1 项跳过**（既有 Windows 目录链接权限用例）；前端 **30 项通过**；全部 **8 个 `web/*.js`** 语法检查通过，两个改动 Python 文件编译通过。真实 FFmpeg 使用同一段 4 秒 / 96 帧 / 24fps / 440Hz 素材分别验证：`0.5x` 恢复为 48fps、`0.75x` 恢复为 32fps，两种结果都准确保留 **96/96 帧**，音频峰值均为 **440Hz**。
- 部署：已同步到 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\ComfyUI-H3-ClipStream`，首次复制本轮 8 个差异文件，完整核对 **53 文件 / 0 mismatch / 0 stale**。功能提交为 `c456e07`，未打 tag。
- 未验证：ComfyUI 内实际项目拼接与面板文案由用户手动验收；测试前需完全重启 ComfyUI 并 `Ctrl+F5`。

## 2026-10-27 · Long Builder 分区顺序调整（已纳入 `c456e07`）

- 快照：`archive/2026-10-27-builder-section-order/` 保存调整前的完整累计工作树（53 文件，不含 `.git`、历史 `archive/` 与缓存）。
- 面板展示顺序改为「01 拼接与速度 / 02 项目与卡片 / 03 成片预览」，拼接设置置顶；仅调整 DOM 追加顺序和编号，参数、执行逻辑、卡片区域伸缩及预览折叠行为不变。
- 验证：全部 8 个 `web/*.js` 语法检查通过，前端 29 项回归通过。浏览器最终视觉由用户验收；已纳入 `c456e07`，未打 tag。

## 2026-10-27 · Long Builder 原速恢复与三区面板（已纳入 `c456e07`）

- 快照：`archive/2026-10-27-970f020/` 保存本轮修改前的完整 `970f020` Git 基线（50 文件，由 `git archive HEAD` 解出）；前两轮性能优化的运行副本改动已合并回本开发副本，没有被本轮覆盖回退。
- `MiniMaxClipBinLongBuilder` 在输入末尾追加 `playback_speed` / `playback_speed_custom`，旧工作流位置不变。用户选择切片当初的慢放倍率，Builder 自动按倒数恢复原速；`1.0x` 保持原行为，`0.5x → 2x`、`0.75x → 约 1.333x`。恢复时视频使用 `setpts + fps` 重编码，音频使用分段 `atempo` 保音调；`copy` 与速度恢复冲突会中文报错，普通参数一致的 `1.0x` 拼接仍无损直拷。
- 面板重组为「01 项目与卡片 / 02 拼接与速度 / 03 成片预览」。项目、刷新、卡片缩放与卡片墙同区；变体、拼接、帧率、输出名与速度设置同区；原生 widgets 只隐藏、不改序列化位置。速度选项直接显示恢复倍率，摘要显示恢复后的成片时长，自定义倍率只在 `custom` 时启用。卡片拖拽、屏蔽、缩放和预览折叠逻辑继续复用。
- 同时修正 `tests/test_mp4_encoding.py` 的 `_support` 导入，避免 `unittest discover` 误加载 ComfyUI 自带的 `tests` 包而造成“测试没真正跑到”。
- 自动验证：完整 `unittest discover -s tests` **204 项通过、1 项跳过**；跳过仍是 Windows 无目录链接权限的既有用例。前端 **29 项通过**，全部 **8 个 `web/*.js`** 语法检查通过。真实 FFmpeg 以 4 秒 / 96 帧 / 24fps / 440Hz 素材验证 `0.5x` 恢复：视频 2 秒 / 48 帧 / 24fps，音频峰值仍为 440Hz；并消除了 `setpts + -r` 组合尾部多约 2 帧的问题。
- 未验证：浏览器中的三区最终视觉、卡片拖拽及实际项目手操由用户验收。已纳入 `c456e07`，未打 tag；Python 改动需完全重启 ComfyUI，之后硬刷新页面。

## 2026-10-24 · 性能优化第二轮（已纳入 `c456e07`）

- 快照：`archive/2026-10-24-970f020-performance-round1/` 保存用户已验收的第一轮完整工作树（50 文件，逐文件哈希一致）。
- Clip Bin 的 MP4 编码改为每次转换并写入 8 帧，不再为整段视频同时保留转换后的 uint8 张量与完整 `rawvideo` 字节副本。
- ffmpeg 参数、音频、保存位置与卡片数据不变。stdout/stderr 不再形成可堵塞管道；stdin 关闭后等待结果，异常时清理未退出进程。
- 自动验证：`tests/test_mp4_encoding.py` 3 条（真实 ffmpeg 的 8+2 帧写入、帧数/像素/音频流、非零退出、BrokenPipe 清理）；完整 `unittest discover` **198 条通过、1 条跳过**。跳过仍是 Windows 无目录链接权限的既有 `test_rejects_a_card_that_is_a_link`，与本轮无关。
- 尚未做 ComfyUI 内大项目峰值内存计时；后续已同步运行副本并纳入 `c456e07`，未单独标记版本。

## 2026-10-24 · 性能优化第一轮（已纳入 `c456e07`）

- 快照：`archive/2026-10-24-970f020-performance/` 保存本轮修改前的完整 `970f020` 基线。
- 本轮范围：Long Builder 复用完整且仍匹配文件状态的 probe 缓存，并用字典解析卡片元数据；Picker 合并执行完成刷新，选卡不再发起两次图库请求。拼接规则与节点接口不变。
- 自动验证：专项 `tests.test_long_builder + tests.test_projects_api` **85/85 通过**；完整 `unittest discover` **195 条通过、1 条跳过**。跳过项是 `test_rejects_a_card_that_is_a_link`，当前 Windows 进程没有创建目录链接权限（WinError 1314），与本轮改动无关；两仓库全部 24 个 `web/*.js` 均通过 `node --check`。
- 尚未做真实项目请求计数或性能计时；后续已同步运行副本并纳入 `c456e07`，未单独标记版本。

## 2026-10-24 · `e42d748`（当前基线，= tag `v0.9.0`）

- 快照：改动前的状态就是 `7b7cff1`（= tag `v0.8.0`），已在 `archive/2026-10-24-7b7cff1/`；提交后的快照在 `archive/2026-10-24-e42d748/`（50 个文件，由 `git archive v0.9.0` 解出，与提交内容逐字节相同）。
- 本 tag 只含上面两条（Dual Picker 版本名称与时长合并、Picker 运行模式三枚大按钮），都只改 `web/clip_bin_picker.js` / `.css`。两条记录里的「未提交」字样已改成指向本 tag。
- 本轮复跑核查：`python -m unittest discover -s tests` → `Ran 194 tests in 1.153s ... OK (skipped=1)`；`work/check_plugin_web.ps1` → `syntax failures: 0`；`work/sync_clipstream.ps1` → **50 files / mismatch 0 / stale 0**。
- 本轮**没有**复跑需要浏览器与真实项目数据的探针：`work/dual_card_layout.mjs`（上一轮 3/3）与 `work/clip_picker_mode.mjs`（上一轮 8 passed）沿用上一轮的实测记录，不能算本轮复验。
- 未验证：两种 Picker 的按钮与卡片最终视觉观感由用户实机确认。


## 2026-10-24 · Dual Picker 版本名称与时长合并（已提交，见 Tag 线 v0.9.0）

- 快照：`archive/2026-10-24-7b7cff1-dual-labels/` 保存本轮修改前完整工作树；`archive/2026-10-24-7b7cff1-dynamic-variant/` 保存动态血缘修正前工作树。
- Dual Picker 卡片原先在时长行与徽标行重复显示「一采 / 二采」。现在合并为两条紧凑信息行：左侧版本名称、右侧对应实测时长，不再额外保留重复的第三行。名称按每张卡片的 `parent_clip_id` 决定：`[INITIAL]` / `[INITIAL_GENERATION]` 显示 `二采·原始`，真实父镜头 ID 的接续卡片显示 `二采·裁切后`，血缘缺失时只显示 `二采`，不乱贴裁切标签；一采始终显示 `一采·原始`。首段悬停说明「不经过接续裁切」，接续二采悬停说明「经过裁切，与一采时长不同属于正常现象」。预览弹窗使用同一套动态名称。
- 普通 Picker 的非 variants 卡片、执行逻辑、保存数据与项目内容均不变。
- 测试：全插件 JS 语法 **0 failures**；既有 Long Builder 布局回归 **16 passed**。独立 Chrome 读取现有项目 `1` 的真实 Dual 卡片（1 张首段 + 2 张接续）并缩到 520px 节点宽度，`work/dual_card_layout.mjs` → **3/3 passed**：首段/接续名称分别正确、旧重复时长行消失、名称与时长无重叠/溢出、裁切提示只用于接续；截图 `work/probe/dual-card-layout.png` 已生成。
- 部署：已同步 ComfyUI 运行副本，只改 `web/clip_bin_picker.js` / `.css`，`Ctrl+F5` 后验收。已随 v0.9.0 提交并推送。

## 2026-10-24 · Picker 运行模式大按钮（已提交，见 Tag 线 v0.9.0）

- 快照：`archive/2026-10-24-7b7cff1/` 保存本轮改动前完整工作树。
- `MiniMax H3 Clip Bin Picker` 与 `MiniMax H3 Dual Clip Picker` 的 `mode` 下拉框改为面板顶部三枚大按钮：`自动接续` / `强制首段` / `严格接续`，当前项高亮，下方显示该模式的一句话说明。视觉与 H3 Segment Picker 的裁切/投放大按钮一致。
- 原 `mode` combo 仅隐藏，仍按原位置序列化；按钮写入完整原始选项字符串，Python 的 Auto / Force Initial / Strict 前缀判断、旧工作流与执行行为均不变。切换只写模式值，不重载卡片、不改变节点尺寸。
- 修改文件：`web/clip_bin_picker.js`、`web/clip_bin_picker.css`。
- 测试：`work/check_plugin_web.ps1` 两个插件 JS 语法 **0 failures**；Long Builder 既有 JS 回归 **16 + 9 passed**。独立 Chrome 以真实鼠标事件点击两种 Picker 的全部三个按钮，`work/clip_picker_mode.mjs` → **8 passed, 0 failed**，逐项确认完整模式值、唯一高亮/aria-pressed、说明文字与节点尺寸不变。
- 部署：已同步 ComfyUI 运行副本，`web/clip_bin_picker.js` 与 `.css` 两个文件更新，全仓 **50 files / mismatch 0 / stale 0**。只改前端，`Ctrl+F5` 后验收。
- 未做：节点最终视觉效果由用户实机确认。已随 v0.9.0 提交并推送。

## 2026-10-19 · `37e334f`（上一基线，= tag `v0.8.0`）

- 快照：`archive/2026-10-18-481aa42/`（46 个文件 / 661,667 字节，由 `git archive HEAD` 解出，与 `git ls-files` 一一对应）。
- 该基线包含 `v0.7.6` 的全部内容（Long Builder 卡片上的屏蔽按钮 + 一键全部加回），且已运行时验证。
- 本次改动（`v0.8.0`）：已 commit `37e334f`（12 文件 / +1725 −173）+ annotated tag `v0.8.0`（tag 对象 `bf9038d`），已推送 `origin/main`（远端 main = `37e334f`）与 `v0.8.0`。内容：按《H3 ClipStream — Motion Context v0.7.1 兼容升级任务书》逐项对齐上游 `NikoDemon80/ComfyUI-H3-Motion-Context` 的 `518c083`（Release 0.7.1，含 `b911783` / `8ec8ba4` / `e9ec557`）。旧的上游基线是 `5335715`（0.6.2）。
  - 新增三个实验性节点（上游算法与 docstring 逐字保留，只把节点类改写成 V3）：`motion_context/sigma_tools.py` → `MiniMaxH3SigmasTailClipStream`（cat `sampling/custom_sampling/sigmas`）、`motion_context/refine_blend.py` → `MiniMaxH3RefineBlendClipStream`（cat `latent/minimax`，保留 `check_lazy_status`，`refined` 是 optional + lazy 输入）、`motion_context/join_match.py` → `MiniMaxH3JoinMatchClipStream`（cat `latent/minimax`）。输入顺序与上游一致；`return (x,)` → `io.NodeOutput(x)`；`def apply` → `@classmethod execute`；节点 id 一律带 `ClipStream` 后缀，避免与独立安装的上游插件撞名。三个文件顶部都写了 `Adapted from NikoDemon80/ComfyUI-H3-Motion-Context v0.7.1 (GPLv3) on 2026-10-18`。
  - `motion_context/__init__.py` 把三组节点并入 `NODE_LIST`；插件根的 `__init__.py` 经 `CONTEXT_NODES` 自动服务，不需要改。
  - `motion_context/nodes.py` 移植 0.6.3–0.7.1 的改动：0.34.0 的措辞、`audio_context_length` 默认 24 → 18（tooltip 说明「已存工作流保持原值」，所以旧存档不会被改写）、`_under_root()`（用 `normcase` 比较）/ `_under_output()` / `LATENT_FOLDERS = ("output", "input")` / `_resolve_input_latent()` / `_resolve_latent_path(path, clip_index, folder)`；Save Latent 返回 `ui = {"latents": [...]}`（普通 dict，不是 `ui.PreviewVideo`）；Load Latent 末尾新增 optional `stock_format` / `folder`，`fingerprint_inputs` 加 `:stock` 后缀并支持 NestedTensor。新 widget 全部放最后，旧存档格式不变。
  - `web/h3_motion_context.js`：Chain 前端联动 refine 双采样链路——`REFINE` 常量、`findPair()` 返回 `refines`、`syncRefines()` 在 `advance()` / `resetFirst()` 时同步 `use_refine`。
  - `scripts/sync_upstream.sh` 重写：按 URL 认 remote（`upstream` / `motion-context` 都兼容）、离线时 fetch 失败不致命、`BASELINE = "518c083"` 的增量日志、VERBATIM / PORTED / LOCAL_ONLY 三分类（`--apply` 只覆盖 VERBATIM，PORTED 永不覆盖）、逐文件差异行数、`--diff` / `--log` 模式、上游未映射新文件的检测；避开了 `set -e` 下 `A && B` 失败就退出的写法。**本沙箱无法启动 bash**（`C:\Program Files\Git\bin\bash.exe -c` → `couldn't create signal pipe, Win32 error 5`），因此这个脚本只做了逐行审查，没有 `bash -n` 与试跑。
  - 测试 147 → 194：新增 `tests/test_experiment_nodes.py`（47 用例，覆盖帧数 cycle、Refine Blend 的权重与 `check_lazy_status`、Join Match 的直通与报错、Sigmas Tail 的只改尾部与 tensor 保持、latent 路径与 fingerprint）。`tests/test_node_schema.py` 扩到 14 个节点，category 断言改成逐节点，并新增「所有 `MiniMaxH3*` 端口节点 id 都带 `ClipStream` 后缀」的断言。
- 运行时验证：**已通过（用户 2026-10-18/19 实机）**。用户重启 `E:\ai\ComfyUI-aki-v3` 的 ComfyUI 后，日志出现 `h3_motion_context: nodes registered.` 与 `[Clip Bin API] Successfully registered /minimax/clip_bin routes`，ClipStream 导入 0.0 秒、无 `FAILED to import`；`GET /minimax/clip_bin/projects?videos_only=1` 返回 22 个项目；Long Builder 读取与拼接正常（项目「跑步测试1」6 段 → 634 帧 / 26.42s，无损直拷）。用户确认 refine 双采样链路能接进旧工作流，Long Builder 未受影响——期间一次「读不到保存的内容」经核对是重启前旧页面的缓存 JS（开发副本与运行副本 50/50 文件 SHA256 逐文件一致，见 `work/diff_cs.ps1`；接口实测正常），硬刷新后恢复。本环境复跑 `Ran 194 tests ... OK (skipped=65)`、`tests/js/long_builder_fit.test.mjs` 16 pass、`tests/js/long_builder_order.test.mjs` 9 pass（两个文件 `# fail 0`）。仍未做：上游任务书要求的 GPU 画质 A–E 对比（本环境没有 H3 采样条件）。覆盖运行副本用 `work/sync_clipstream.ps1`，它按目录递归枚举（只跳过 `archive` / `.git` / `__pycache__`），新增的 3 个 py 会被自动复制。

## 2026-10-11 · `a211f5e`（上一基线，= tag `v0.7.6`）

- 快照：`archive/2026-10-11-ccb80ac/`（46 个文件 / 637 KB，由 `git archive HEAD` 解出，与 `git ls-files` 一一对应）。
- 该基线包含 `v0.7.5` 的全部内容（Long Builder 卡片实测参数 + 拖拽排序 + 节点尺寸不漂移 + 首段生成不再误报接缝），且已运行时验证。
- 本次改动（`v0.7.6`）：已 commit `a211f5e`（6 文件 / +184 −30）+ annotated tag `v0.7.6`（tag 对象 `919a140`），已推送 `origin/main`（远端 main = `a211f5e`）与 `v0.7.6`。用户 2026-10-11 明确「可以留」→ 保留并推送。Long Builder 的卡片屏蔽改成「卡片上的按钮」，并加一键全部加回——
  - `web/long_builder_panel.js`：卡片体新增一行开关按钮 `.h3-lb-join-toggle`（在片 = `⊘ 移出成片`，已排除 = `↺ 加入成片`），并删掉整张卡片的 `item.onclick`。原因：卡片本身可拖拽排序，「点卡片 = 排除」和拖拽抢同一批像素，鼠标想读参数就误改一次成片；按钮同时给出可用的命中面积（9:16 竖屏卡片上尤其重要）。摘要行不再只写「点卡片可加回来」，改成带 `↺ 全部加回` 按钮（`restoreAll()` 只清空 `exclude_clips`，不动 `clip_order`，手动排好的顺序保持不变）。
  - `web/long_builder.css`：`.h3-lb-off` 只压暗缩略图——原来整卡 `opacity: .45` 会把「加回来」的按钮一起压掉，读不清；新增 `.h3-lb-join-toggle` / `.h3-lb-join-off` / `.h3-lb-restore-row` / `.h3-lb-restore-all`；`.h3-lb-container .h3-lb-card { cursor: default }`（可拖拽卡片的 `grab` 仍由后面的规则给出）；`.h3-lb-container .minimax-clip-body { padding-right: 8px }`——共享样式的 38px 右内边距是给素材库卡片右下角的删除按钮留的，Long Builder 卡片没有那个按钮，那 30 像素是白丢的宽度。
  - `web/long_builder_fit.js`：`rowHeightFor()` 里写死的 `+ 62` 抽成 `CARD_BODY_H = 86`。卡片体现在是三行（镜头名 / 实测参数 / 开关按钮），估算不跟着长，`⤢ 适应` 与缩放就会按两行的旧高度少算一行——面板虽然实测真实高度，但实测读不到时用的就是这个估算。
  - 测试：JS 24 → 25（`tests/js/long_builder_fit.test.mjs` 新增「行高估算覆盖整张卡片体」，锁 `rowHeightFor == thumbHeightFor + CARD_BODY_H` 且 `CARD_BODY_H > 62`）。本次只改前端，Python 147 用例仍 `OK (skipped=1)`。
- 运行时验证：**ComfyUI 内的实测仍未做**（本环境复跑过 `Ran 147 tests ... OK (skipped=1)`、JS 16/9 全绿、`work/check_plugin_web.ps1` 0 failures，并用 `work/sync_clipstream.ps1` 核对运行副本 46 文件 / 0 mismatch / 0 stale）。只改前端 → 覆盖运行副本 + 浏览器 Ctrl+F5 即可，不需要重启 ComfyUI。复测点：卡片上的 `⊘ 移出成片` / `↺ 加入成片` 只切换这一段、卡片不再因为点击而改变成片；`↺ 全部加回` 只清排除、不动手动排好的顺序；`⤢ 适应` 与缩放按三行卡片体估算（不再少算一行）。

## 2026-10-04 · `f630d44`（上一基线）

- 快照：`archive/2026-10-04-f630d44/`（42 个文件 / 560 KB，由 `git archive HEAD` 解出，与 `git ls-files` 一一对应）。
- 该基线包含 `v0.7.4` 的全部内容（Clip Bin Picker 项目选单 + 选单内新建/删除项目），且已运行时验证。
- 本次改动（下一版 `v0.7.5`）：Long Builder 卡片显示真实视频参数，并且卡片可以拖拽排序——
  - `clipbin/clip_bin_api.py`：新增 `_video_probe_fields()`，按「文件名 + size + mtime」把 ffprobe 结果缓存在卡片 `meta.json` 的 `video_probe` 里（换文件即重测；读不到返回 0 且不缓存，下次请求重试）；列表接口把它平铺成 `video_width/video_height/video_fps/video_frames/video_duration_seconds` 交给前端（加入 `_FRONTEND_ONLY_KEYS`，不写回 meta）。`get_project_clips_api(project_name, variant_policy="", want_probe=False)` 与 `GET /minimax/clip_bin/list?variant_policy=&probe=1` 让卡片显示「这个节点实际会拼的那个文件」的实测参数；`probe=1` 才是「请实测」的开关，Picker 两个参数都不传，因此不会为它不显示的字段付 ffprobe 成本（那里本来已经按卡片测过一次时长）。`probe` 参数改为调用时解析，测试可以替换 `clip_bin_api.probe_video_streams`。
  - `clipbin/long_builder.py`：`resolve_shot_order(clips, exclude_text, clip_order="")` 支持手动顺序——`clip_order` 用与 `exclude_clips` 相同的引用写法并按从上到下读；没被点名的卡片按镜头序号补在后面（拖完之后新生成的段不会消失）；已删除的引用只告警跳过；重复引用只算一次；被排除的卡片即使被点名也不参与。`build_long_video(..., clip_order=...)` 透传。
  - `clipbin/long_nodes.py`：新增 `clip_order`（optional + advanced，位置在 `exclude_clips` 之后，已保存工作流的其余参数顺序不变）。
  - 新增 `web/long_builder_order.js`：「卡片墙顺序 = 成片顺序」的纯函数（`sortCards` / `resolveDeckOrder` / `moveCard` / `shotNumber`），与 `long_builder.py` 同规则，可脱离 ComfyUI 单独测试。
  - `web/long_builder_panel.js`：卡片显示实测「分辨率 · 时长」（读不到显示 `—`，tooltip 给文件名/帧数/帧率）；列表请求带上本节点的 `variant_policy` 与 `probe=1`；可拼接的卡片 `draggable`，拖到另一张卡片左/右半边即插到其前/后，卡片墙空档投放＝移到末尾，落点用插入线指示，拖完 400ms 内忽略 click（不会误触排除）；新顺序写入 `clip_order` 控件；参与拼接的卡片左上角标 `#1/#2…` 位置；顺序条说明当前是「按镜头序号」还是「手动」，手动时出现 `↺ 按镜头序号` 一键清空；摘要行在全部时长都实测到时给出成片总时长。
  - `web/long_builder.css`：`.h3-lb-order-bar/-hint/-reset`、`.h3-lb-place`、`.h3-lb-dragging`、`.h3-lb-drop-before::before`、`.h3-lb-drop-after::after`，以及 `prefers-reduced-motion` 下关闭卡片过渡。
  - `clipbin/long_builder.py` 再加一道首段生成检测：新增 `is_initial_generation()`，`build_long_video` 按卡片 `parent_clip_id` 里的 `[INITIAL]` / `[INITIAL_GENERATION]` 标记给每段打上 `is_initial`；`seam_warnings` 跳过这类段——首段生成没有 pinned 重叠帧，「视频帧数 == latent 帧数」正是它的正常形态，被拖到成片中间也不该报「未裁」。未接血缘（`parent_clip_id` 为空）不算首段，接缝检查保持原样，避免把真的没裁的段放过。新增 `TestInitialGenerationMarker`（5 例）、两个接缝用例与一个端到端用例（首段卡排到第 2 位仍 0 警告）。
  - 测试 125 → 147（Python），另加 24 个 JS 用例（9 个顺序 + 15 个尺寸）：`tests/test_long_builder.py::TestManualCardOrder` + 端到端「拖出来的顺序就是拼的顺序」；`tests/test_projects_api.py::TestCardVideoProbe`（首次实测、缓存命中不再跑 ffprobe、文件被替换后重测、无归档视频返回 0 且不缓存、`variant_policy` 决定测哪个变体、不请求实测时完全不跑 ffprobe 也不返回这些字段）；`tests/test_node_schema.py` 输入表加入 `clip_order`；`tests/js/long_builder_order.test.mjs`（9 例）、`tests/js/long_builder_fit.test.mjs`（15 例）。
- 卡片缩放与节点尺寸（前端）：新增 `web/long_builder_fit.js` 把「卡片多大、要多大的区域才放得下」从 DOM 里拆成纯函数。规则改为**缩放只改卡片，不改节点宽度**：`planZoomHeight()` 先按旧行数（`visibleRows()` 只数整行）再按新行高还原同样的行数，超过视口就夹住但永远保留一整行；`⤢ 适应` 走 `planFitHeight()`，按当前宽度排到最多 `MAX_ROWS=2` 行、其余滚动；删掉旧的 `planDeck()` / `MAX_COLUMNS`（它同时改宽度，是「点放大就排成一行」的根因）。`web/long_builder_panel.js` 相应改成 `deckGeometry()` / `applyHeight()`（只 `setSize([当前宽, 新高度])`）/ `zoomFit()`，缩放按钮在改 CSS 变量前先取几何。
- 刷新不再把节点越缩越小（用户实测反馈）：卡片墙是 `flex: 1 1 0`，而面板 DOM widget 有自己的 `getMinHeight`，节点一旦比面板下限还小，卡片墙就不再跟着节点缩小——「按增量再要一次高度」于是每次刷新都少一点，直到撞上 `min_size`。修法：`applyHeight()` 先把目标高度夹到 `nodeChromeHeight() + PANEL_MIN_HEIGHT`（`PANEL_MIN_HEIGHT` 同一个数字也喂给 `addPanel`，两处不再各写一份），`sizeDeckTo()` 改成「要一个高度 → 下一帧复测 → 误差 >8px 再修一次，最多两轮；卡片墙根本没动说明已到下限，停」；`planFitHeight()` / `planZoomHeight()` 新增 `padV`（`DECK_PAD_V = 14`，即 `clip_bin_picker.css` 的 `padding: 4px 2px 10px 2px`），规划的是卡片墙的外框高度，不再永远差 14px。自动适配改成 `fitOnce()`：一个节点只在第一次出现卡片时布局一次，`loadCards()`（刷新按钮、换项目、拖卡片、改变体、后台变更事件）不再改节点尺寸，只有 `⤢ 适应` 与 `+/−` 会。JS 用例 13 → 15（`padV` 两条）。
- 成片预览可收起：ComfyUI 0.38 把成片预览做成 `type="video"` 的 DOM widget，`widget.hidden` 会被 `getLayoutWidgets()` / `isWidgetVisible()` 跳过，所以面板的 `▼ 收起成片` / `▶ 展开成片` 把它从布局里摘掉（不是留一条空白），节点因此能缩得很小；展开时按实测高度（`computedHeight` / 元素高度）把空间还回去。面板在 `addDOMWidget` 上包一层，捕获 ComfyUI 新建的预览 widget 并套用用户上次的选择；档位与收起状态存在 `localStorage`（`h3.clipstream.longBuilder.filmPreview`）。`web/long_builder.css` 的 footer 改成一行（`.h3-lb-footer-text` + `.h3-lb-film-toggle`，未运行时禁用）。
- 展开成片不再把节点越加越长（用户实测反馈，第二次修复才找对原因）：litegraph 的 `LGraphNode._arrangeWidgets()` 把节点剩余空间用 `distributeSpace()` **平均分给所有可增长 widget**——面板的 `getMaxHeight` 未定义 → `maxSize = Infinity`，成片预览的 DOM widget 同样无上限——所以预览自己就会占走一半空间，而「占多少」又随节点高度一起长。旧代码在此之上再 `applyHeight(+实测预览高度)` 是第二次加，于是每次展开净增一段且永远不收敛。改成**绝对还原**：收起时记下当前节点高度（`heightWithFilm`），展开时 `applyHeight(heightWithFilm)`，只做还原不做加法；重载后恢复「收起」状态时也记一次，所以从历史记录里展开同样回到原高度。收起仍按实测的预览高度还空间（这一步本来就是对的：预览消失后面板独占剩余空间，卡片墙高度不变）。另：`sizeDeckTo()` 收敛轮数 2 → 4——预览在场时每轮只能补上一半误差，四轮内收敛到 ≤8px。
- 运行时验证：已把改动的运行时文件覆盖到 `E:\ai\ComfyUI-aki-v3\ComfyUI\custom_nodes\ComfyUI-H3-ClipStream\` 并逐文件哈希核对（开发副本与运行副本全部运行时文件无差异）。用户实测确认卡片显示分辨率/时长、拖拽排序、首段生成不再报接缝告警、卡片缩放 100%–400% 与换行、成片预览收起/展开、刷新不再把节点缩到最小、展开成片不再累积增高均正常 → **`v0.7.5` 运行时验证通过**，不需要回退。
## 2026-10-03 · `03e3124`（上一基线）

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
| `v0.7.5` | `ccb80ac` | Long Builder 卡片实测分辨率/时长 + 拖拽排序 + 首段生成不再误报接缝 + 卡片缩放换行与节点尺寸不漂移。运行时已验证 |
| `v0.7.6` | `a211f5e` | Long Builder 卡片屏蔽改成卡片上的按钮（`⊘ 移出成片` / `↺ 加入成片`）+ 摘要行 `↺ 全部加回`；只改前端。已推送 `origin/main` |
| `v0.8.0` | `37e334f` | 上游 Motion-Context 0.7.1 的三个实验节点（Refine Blend / Join Match / Sigmas Tail）+ Save/Load Latent 改进 + Chain 联动 + `sync_upstream.sh` 重写；见本文件 2026-10-18 段 |
| `v0.9.0` | `e42d748` | Dual Clip Picker 卡片把重复的「一采/二采」行合并成「版本名称 + 对应实测时长」两条紧凑信息行（名称按 `parent_clip_id` 决定：`[INITIAL]`/`[INITIAL_GENERATION]` = `二采·原始`，真实父镜头 = `二采·裁切后`，血缘缺失只写 `二采`；首段悬停说明不经过接续裁切），预览弹窗同一套名称；Clip Bin Picker 与 Dual Clip Picker 的 `mode` 下拉框改为面板顶部三枚大按钮（自动接续 / 强制首段 / 严格接续）+ 一句话说明，combo 只隐藏、仍按原位置序列化，Python 的 Auto / Force Initial / Strict 前缀判断与旧工作流不变。测试：`Ran 194 tests ... OK (skipped=1)`、JS 语法 0 failures、独立 Chrome `work/dual_card_layout.mjs` 3/3 与 `work/clip_picker_mode.mjs` 8 passed、运行副本 50 files / mismatch 0 / stale 0。已推送 `origin/main` 与 `v0.9.0` |

> 上游仓库自己也有 `v0.7.0` / `v0.7.1` 这两个 tag，和我们这条线**同名不同指**。因此本次不用 `v0.7.7`，直接进 `v0.8.0`；`git tag -l` 里看到的 `v0.7.x` 全部是我们自己的（`git rev-list -n1 v0.7.x` 可核对指向）。

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
node tests/js/long_builder_order.test.mjs   # 前端卡片墙顺序（纯函数，不需要 ComfyUI）
node tests/js/long_builder_fit.test.mjs     # 前端卡片大小与区域高度（同上）
```

- 当前结果：`Ran 194 tests ... OK (skipped=1)` + `# pass 9` + `# pass 16`（JS 共 25 项）（61 → 96 → 112 → 119 → 125 → 147 → 194：新增三个实验节点与 latent 路径的用例；前端规则在 `tests/js/` 下两个文件，用 node 跑）。唯一 skip 是 Windows 上创建目录符号链接需要权限（WinError 1314），该用例在有权限时会跑。
- `COMFYUI_ROOT` 只在 schema 测试里必需；从 `custom_nodes` 下运行时会自动推断根目录。
- 覆盖范围：
  - `tests/test_frame_grid.py`：像素帧 ↔ latent step 往返、`VIDEO_RUN_GRID` 每点可达、`context_length` 只落在整 step 上、clipbin 与 motion_context 两套帧数口径一致。
  - `tests/test_latent_codec.py`：`_unpack_latent` / `_pack_latent` / `_standardize_image_tensor` / `_standardize_audio_dict` 的容器形状与不改动源对象。
  - `tests/test_asset_paths.py`：`checked_asset_dir` 拒绝越界 id、嵌套项目目录和符号链接卡片；预览 URL 随卡片重写而变。
  - `tests/test_clip_bin_store.py`：单卡与双卡存取往返、项目索引排序与丢失后重建、删除语义、shot tag slug 与唯一性、Auto tag 按项目递增。
  - `tests/test_long_builder.py`：镜头序号升序定序（`Shot 12` 排在 `Shot 2` 之后）、无数字标签按 `created_at` 排在带序号卡片之后、`exclude_clips` 按 `clip_id` 或镜头标签片段排除、序号缺口告警、缺归档视频只告警不报错、preview 的 filename/subfolder 可寻址、变体选择策略、ffprobe JSON 解析与帧率分数解析、`classify_join` 的分辨率/帧率/音轨/采样率判定、`seam_warnings` 的未裁接缝判定（成片首段与首段生成卡片永不告警）、concat list 转义，以及 `MiniMaxClipBinLongBuilder` 的端到端装配（用假 ffmpeg/ffprobe）；`TestManualCardOrder` 锁定 `clip_order`：手动顺序优先、未点名的按序号追加、已删除引用只告警、重复引用只算一次、被排除的卡片不因为被点名就回来，端到端用例断言 ffmpeg 收到的文件顺序就是拖出来的顺序；`TestInitialGenerationMarker` 与 `TestSeamWarnings` 的新用例锁定「首段生成」不被误报为未裁，而未接血缘的中间段照旧判定。
  - `tests/test_projects_api.py`：`list_projects_api()` 列出全部项目及其卡片数/视频数，`videos_only=True` 只留能成片的库；`create_project()` 新建空库、同名幂等、返回清洗后的文件夹名、空名与超长名报错；`delete_project()` 删除整库（含视频）、`confirm` 不匹配报错、库已不存在时返回 `deleted: False` 且不建幽灵目录；`TestCardVideoProbe` 用假 probe 锁定卡片视频参数的测量与缓存（每个文件只测一次、size/mtime 变了重测、无视频不缓存）以及 `variant_policy` 决定测哪个变体。
  - `tests/test_experiment_nodes.py`：三个实验节点的纯函数与执行路径。帧数 cycle（`pixel_frames` 的 0/1/5/9/13/17/18/22、`steps_for_frames(5/22/39/56) = 2/7/12/17`、`nearest_valid(20)` 的候选）；Refine Blend 的权重表、`check_lazy_status`（不接 `refined` 或 `use_refine = False` 时不请求它）、hold 段逐帧不变、首段（无 pin）全取 refined、非法 hold 报错、形状不符报错、音频取 original 或 refined、容器保持（list 与 NestedTensor）；Join Match 的直通与报错、`shot_motion` 静止 = 0 与运动 > `STILL_MAX`、`STILL_MAX` 落在 0.40–0.58 的实测间隙里；Sigmas Tail 的直通 / 只改尾部 / 正负强度升降 / 平坦段强制递减 / 过短直通 / tensor 保持与 `same_kind`；latent 路径的 `_under_root` 越界与 `normcase`、input 模式、非法 folder 报错、`_%05d` 与自动编号 hint、Load 默认 list、`stock_format` 出 NestedTensor、clip 0 返回 None、fingerprint 的 `:owned` / `:stock` / `disabled` / NaN、Save 的 `ui["latents"]`。
- `tests/js/long_builder_order.test.mjs`：`node tests/js/long_builder_order.test.mjs`。锁定前端与后端同规则：默认按镜头序号、`Shot 12` 在 `Shot 2` 之后、手动顺序优先且未点名的按序号追加、不能拼接的卡片排在最后且不进 `joinIds`、`deck` 前 N 张就是 `joinIds`（面板的位置角标依赖这条不变量）、`moveCard` 的前后插入与「拖到自己/未知卡片上 = 不变」。
  - `tests/test_node_schema.py`：锁定 14 个节点的 id / category（逐节点断言，实验节点在 `latent/minimax` 与 `sampling/custom_sampling/sigmas`）/ 输入 id 与 optional / 输出 display_name 顺序 / Picker mode 选项 / `context_length` 选项 / `is_output_node` / Long Builder 输入全部 advanced 且只有一个 `video` 输出 / Load Latent 末尾的 `stock_format` 与 `folder`，并校验 `H3ClipStreamExtension().get_node_list()` 返回同一批；`test_ported_upstream_ids_keep_the_clipstream_suffix` 锁住所有 `MiniMaxH3*` 端口节点的 id 后缀。
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
- 2026-10-04：Long Builder 卡片显示真实视频参数 + 拖拽排序（`v0.7.5`）——`clipbin/clip_bin_api.py` 新增 `_video_probe_fields()` 与 `video_probe` 缓存、`get_project_clips_api` 接受 `variant_policy` 与 `probe=1` 门控；`clipbin/long_builder.py::resolve_shot_order` 与 `clipbin/long_nodes.py` 新增 `clip_order`；新增 `web/long_builder_order.js`，`web/long_builder_panel.js` 显示实测分辨率/时长并支持拖拽重排，`web/long_builder.css` 加拖拽与位置样式；测试 125 → 139，新增 `tests/js/long_builder_order.test.mjs`（9 用例）；README 中英文「长视频拼接」章节同步。同日再修 `clipbin/long_builder.py`：`seam_warnings` 增加首段生成检测（`is_initial_generation` / `is_initial`），首段卡片不再被误报为「未裁接缝」，测试 139 → 147。
- 2026-10-11：Long Builder 卡片屏蔽改成卡片上的按钮（`v0.7.6`）——`web/long_builder_panel.js` 卡片体加 `.h3-lb-join-toggle`、去掉整卡 `item.onclick`（与拖拽抢事件）、摘要行加 `↺ 全部加回`（`restoreAll()` 只清 `exclude_clips`）；`web/long_builder.css` 只压暗缩略图并补按钮/恢复行样式与 `cursor: default`；`web/long_builder_fit.js` 的行高估算 `+62` → `CARD_BODY_H = 86`；JS 测试 24 → 25；README 中英文同步。
- 2026-10-03：Long Builder 简化（`v0.7.3`）——`clipbin/long_builder.py` 改按镜头序号定序（新增 `shot_number` / `shot_sort_key` / `numbering_gaps` / `resolve_shot_order`，删除血缘回溯与 `MAX_CHAIN` / `INITIAL_MARKERS`）；`clipbin/long_nodes.py` 输入全 advanced、输出单个 `video` 并内联预览；`clipbin/clip_bin_api.py` 新增 `list_video_projects_api` 与 `GET /minimax/clip_bin/projects`；新增 `web/long_builder_panel.js`、`web/long_builder.css`；README 中英文「长视频拼接」章节同步（面板、序号定序、选项表、日志取代 report）。
- 2026-10-18：上游 Motion-Context 基线 `5335715`（0.6.2）→ `518c083`（0.7.1）。新增三个实验节点（Refine Blend / Join Match / Sigmas Tail：上游算法原样、节点类是 V3、id 带 `ClipStream` 后缀），移植 Save/Load Latent 的改进（`stock_format`、`folder`、`ui.latents`、路径安全），Chain 前端联动 refine 链路，重写 `scripts/sync_upstream.sh`。
- 2026-10-18：新增 `tests/test_experiment_nodes.py`（47 用例），测试 147 → 194；`tests/test_node_schema.py` 扩到 14 个节点。
