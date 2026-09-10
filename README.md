# ComfyUI H3 ClipStream

**一个插件，两件事：** 给 MiniMax H3 一个**可视化、可搜索的镜头素材库（Clip Bin）**，并让镜头之间**音画无缝接续（Motion-Context）**。

- **Clip Bin（可视化操作）** 来自 [knoic/ComfyUI-MiniMaxH3-PrefixStream](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream)：把每一段生成的镜头（联合音画 latent + 预览卡 + 镜头标签 + 血缘）归档成画廊，随时挑回任意一段历史镜头。
- **接续引擎（continuation）** 来自 [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)：latent 切片、关键帧锚定的链式接续，**音画都带着走**（不做解码/重编码往返，也不让音频「听起来像」地重新起步）。

> 我们**保留**了 PrefixStream 的可视化 Clip Bin，但**不用**它自带的接续节点（Continuation Config / Applier / Trim Prefix）和那一套引擎（`cache_manager` / `native_masked_av` / `fused_attention` / `rope_aligner`）。接续这件事，**完全交给 Motion-Context** 来做。

把 **Clip Bin Picker 的 `latent`** 接到 **Motion Context 的 `context_latent`**，你就能接续**任意**一段已保存的镜头，而不只是「最新那一段」。

---

## 目录

- [它是怎么工作的](#它是怎么工作的)
- [核心接线图](#核心接线图)
- [安装](#安装)
- [节点清单（8 个）](#节点清单8-个)
- [工作流指南：首段 + 续写](#工作流指南首段--续写)
- [参数要点](#参数要点)
- [许可与来源](#许可与来源)
- [故障排查](#故障排查)

---

## 它是怎么工作的

MiniMax H3 是**音视频一体**模型：视频和音频活在同一个 `NestedTensor([video, audio])` 的 latent 里。

- **Clip Bin Saver** 会把上一段采样器输出的**完整音画 latent** 存进素材库；
- **Clip Bin Picker** 再把任意一段以 `{"samples": NestedTensor([video, audio])}` 的形式**原样吐回**；
- **Motion Context** 的 `context_latent` 输入，要的恰好就是「上一段的采样器输出音画 latent」，内部用 `unbind()` / list 解包——**两种格式天然兼容**。

所以 **Picker 的 `latent` 可以直接接到 `context_latent`**，B 侧零改动。这就是「方案2（一体化插件）」成立的核心：可视化用 A，接续用 B，中间的 latent 接口正好对得上。

---

## 核心接线图

```
[首段]  原生 H3 工作流 (ImageToVideo / ReferenceToVideo / t2v)
          → 采样器 (SamplerCustomAdvanced)
          → 解码 (VAEDecode + VAEDecodeAudio)
          → A: Clip Bin Saver          （归档：存完整音画 latent + 预览卡）

[续写]  A: Clip Bin Picker             （挑镜头，输出 latent / first_frame / tail_frame / clip_id / prompt）
          │
          │  Picker.latent ───────────► B: Motion Context . context_latent
          │  原生 conditioning ───────► B: Motion Context . conditioning
          │  原生目标 latent ─────────► B: Motion Context . latent
          │  原生 VAE ────────────────► B: Motion Context . vae
          │
          ▼
        B: Motion Context 输出 conditioning ─► guider ─► 采样器
          → 解码 (VAEDecode + VAEDecodeAudio)
          → B: Trim  (用 Motion Context 的 trim_frames 裁掉 pinned head，音画同步裁)
          → A: Clip Bin Saver          （再归档，形成下一段可接续的素材）
```

要点：

1. **接续的上下文来源是 A 的 Clip Bin Picker**，不是 B 的 Save/Load 索引链（那是 B 自带的另一套「按 run 跨段」的方案，两者二选一即可）。
2. **`trim_frames` 必须从 Motion Context 接到 Trim**：pinned 的头部帧会回到新片段开头，交付前要裁掉，音画一起裁。
3. A 的 Continuation Config / Applier / Trim Prefix **不接、不用**——接续完全由 B 负责。

---

## 安装

1. 把 `ComfyUI-H3-ClipStream/` 整个文件夹放进 `ComfyUI/custom_nodes/`。
2. （可选）安装依赖：`pip install -r requirements.txt`（ComfyUI 通常已自带 `torch` / `safetensors`）。
3. 重启 ComfyUI，前端 `Ctrl+F5` 硬刷新。

启动日志应看到：

```
h3_motion_context: nodes registered. ComfyUI is not modified; the layout checks run on the first use of a Motion Context node.
```

**首次真正跑一次接续**时，会做布局自检，应看到：

```
h3_motion_context: ComfyUI H3 layout checks passed, anchors and pinned audio will land where intended
```

若自检不通过，节点会**拒绝运行**并打印原因（一次响亮的失败好过一张你没发现的坏图）。

> **要求 ComfyUI 0.34.0 或更新**——H3 从 0.34 起才支持任意关键帧锚定。0.33.4 及更旧版本会明确提示你换用 0.3.1（那个版本同时兼容新/旧）。这个判断读自布局代码本身而非版本号，所以 nightly 或 fork 也能得到正确答案。

---

## 节点清单（8 个）

### 来自 Clip Bin（可视化，类别 `MiniMaxH3/ClipStream`）

| 节点 | 显示名 | 作用 | 主要输入 | 输出 |
| --- | --- | --- | --- | --- |
| `MiniMaxClipBinSaver` | MiniMax H3 Clip Bin Saver (Media Pool) | 把一段 H3 音画 latent 连同预览卡、镜头标签、血缘归档进素材库 | `latent`、`project_name`、`shot_tag`；可选 `images` / `audio` / `prompt` / `parent_clip_id` / `video_file_name` / `save_video` | `clip_id`(STR)、`preview_image`(IMG)、`bin_path`(STR) |
| `MiniMaxClipBinPicker` | MiniMax H3 Clip Bin Picker (Gallery Loader) | 可视化浏览、按 `latest`/`clip_id`/镜头名 载入某段并原样输出其音画 latent；含**三种运行模式** `mode`（Auto / Force Initial / Strict Chaining） | `project_name`、`mode`、`clip_selection`；可选 `custom_clip_path` | `latent`(LATENT)、`tail_frame`(IMG)、`first_frame`(IMG)、`prompt`(STR)、`clip_id`(STR) |

### 来自 Motion-Context（接续引擎，类别 `conditioning/minimax`）

| 节点 | 显示名 | 作用 | 主要输入 | 输出 |
| --- | --- | --- | --- | --- |
| `MiniMaxH3MotionContext` | H3 Motion Context | 把上一段的一段连续帧作为「永不降噪的条件行」钉在新片段头部，音画一起接续 | `conditioning`、`vae`、`latent`、`context_length`(22/5/39/56)、`audio_context_length`(INT)；可选 `context_latent` / `context_frames` / `audio_vae` / `context_audio` | `conditioning`、`trim_frames`(INT) |
| `MiniMaxH3MotionContextTrim` | H3 Motion Context Trim | 把解码后片段的 pinned 头部裁掉，音画同步裁 | `images`、`audio`、`trim_frames` | `images`、`audio` |
| `MiniMaxH3MotionContextSaveLatent` | H3 Motion Context Save Latent | 把本段采样器的音画 latent 落盘，供「下一段」加载（B 自带的跨段方案） | `latent`、`clip_index` | `latent_path`(STR) |
| `MiniMaxH3MotionContextLoadLatent` | H3 Motion Context Load Latent | 读取 Save 落盘的 latent 供 `context_latent` 使用 | `clip_index` | `latent`(LATENT) |
| `MiniMaxH3MotionContextChain` | H3 Motion Context Chain | 审批 / 运行 / 重roll / 自动推进 / 复位索引 / 清空槽位（用它的按钮，别用 ComfyUI 的 Run 走链） | 控制型 | — |
| `MiniMaxH3MotionContextSeamProbe` | H3 Motion Context Seam Probe | 在画布内测量一个接缝：是不是真接续、电平有没有跳（音频透传） | `clip_b_untrimmed`、`trim_frames`；可选 `clip_a_latent` / `audio_vae` / `fps` / `window_ms` / `search_ms` | `audio`、`report`(STR) |

---

## 工作流指南：首段 + 续写

### 首段（库里还没有镜头）

1. 正常搭 H3 首段工作流（ImageToVideo / ReferenceToVideo / t2v → 采样器 → 解码）。
2. 把采样器的 **AV latent** 接到 **Clip Bin Saver**，设好 `project_name` / `shot_tag`。
3. 此时 **Motion Context 的 `context_latent` 不接**（或 Picker 处于 Initial 模式），首段按原生 H3 生成。
4. 跑完，Saver 自动把这段存进素材库画廊。

> Picker 的 `mode`（三种运行模式）：
> - **Auto（推荐）**：库空时自动作为首段全新生成；库非空时自动接续上一段，无需拔线。
> - **Force Initial**：强制开辟首段，忽略库内所有历史素材（无上下文）。
> - **Strict Chaining**：严格接力，库内无镜头时直接报错提示。

### 续写（从任意一段接续）

1. **Clip Bin Picker**：确认 `enable_continuation` 已开启；选 `project_name`，`clip_selection` 填 `latest`（默认接最新）或某段 `clip_id` / 镜头名。
2. 把 **Picker 的 `latent` → Motion Context 的 `context_latent`**。
3. 原生 `conditioning` / 目标 `latent` / `vae` 照常接 Motion Context。
4. 调 `context_length`（画面接续窗口，见下）与 `audio_context_length`（音频尾部窗口）。
5. Motion Context 输出的 `conditioning` → guider → 采样器 → 解码。
6. 解码后的 `images` / `audio` → **Trim**（`trim_frames` 从 Motion Context 接过来）。
7. 裁完的画面/音频 → **Clip Bin Saver** 再归档，形成下一段可接续的素材。

### `context_length`（画面接续帧数）怎么选

只有 **5 / 22 / 39 / 56** 这几个是整数的 latent step，所以只给这几个：

- **5**：刚够流畅，最省。
- **22**：接近无缝，默认推荐。
- **39 / 56**：钉住更多运动，但会从**交付片段的前端**吃掉对应时长（56 相当于拿 2.3 秒渲染去喂你随后要裁掉的帧）。

### `audio_context_length`（音频尾部窗口）

- 独立于画面窗口；**0** 表示跟随画面。
- 窗口是**尾部对齐**钉在视频尾的，只控制声音往回延伸多远。
- **3 的倍数**正好落在 40 Hz 音频网格上，**24 的倍数**是整秒：`24` = 钉住最后 1 秒（默认）。
- 非整格值会自动加宽到最近的整 step。

---

## 运行模式（三种）

`MiniMaxClipBinPicker` 上的 `mode` 提供三种运行模式，**只控制 Picker 自己怎么取上一段**，不触碰任何下游节点的 bypass/启用：

- **Auto（默认，推荐）**：库空时自动作为首段全新生成（输出空 latent）；库非空时自动接续上一段（输出真实 latent）。
- **Force Initial**：强制开辟首段，忽略库内所有历史素材（始终输出空 latent）。
- **Strict Chaining**：严格接力，库内无镜头时直接报错；库非空时接续指定/最新镜头。

> **说明**：首段/Force Initial 时 Picker 输出 `null` 的 `context_latent`；Motion Context 检测到空上下文后**原样透传 conditioning**（`trim_frames=0`），Trim 也随之透传，整条链自然退化为普通首段。请保持 `context_frames` 不接线，否则会改用那张图接续。

> **前端 import 深度**：本插件把 A、B 的前端都平铺到顶层 `web/`，二者与 ComfyUI 标准自定义节点同深度，import 一律用 **2 级** `../../scripts/app.js`（与 B 的 `h3_motion_context.js` 一致）。若日后新增前端，请沿用 2 级，勿用 3 级，否则扩展会因找不到 `app.js` 而静默失效。

---

## 参数要点

- **分辨率必须一致**：`context_latent` 必须和正在生成的片段**同分辨率**（B 会拒绝跨分辨率）。
- **音画一体**：接了 `context_latent` 后，画面与声音都从它里切出来，`context_frames` / `context_audio` / `audio_vae` 会被忽略——这是最省质量、最顺的接法。
- **首段别 mute Motion Context**：首段让它透传 conditioning 并返回 `trim_frames=0` 即可（用 B 的 Save/Load 链时，首段 Load 0 不读文件）。
- **走 B 的 Save/Load 链时**：Load 的索引 = 你「从哪段接续」，Save 的索引 = 「本段是哪段」。首段 Load 0 / Save 1；做第 2 段 Load 1 / Save 2。**别用 ComfyUI 的 run-on-change 走链**，用 **Chain** 节点。Chain 只在 Load/Save/Chain 三个节点**同一画布分组**内才生效。

---

## 许可与来源

- 本插件合并了两个开源上游，按**更严格的一方**分发：**GPLv3**（见 `LICENSE`）。
- **Motion-Context**（GPLv3）：[NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)，作者 NikoDemon80。以 `motion_context/` 子包**原样**收录：`nodes.py` / `layout_contract.py` / `csrf_guard.py` / `probe_node.py` + `web/h3_motion_context.js`。
- **Clip Bin**（MIT）：[knoic/ComfyUI-MiniMaxH3-PrefixStream](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream)，作者 knoic。以 `clipbin/` 子包收录，并从其接续引擎**解耦**（不引入 `cache_manager` / `native_masked_av` / `fused_attention` / `rope_aligner`）。

MIT 代码可并入 GPLv3 作品，故整包按 GPLv3 分发。若再分发，请保留 `LICENSE` 与 `ATTRIBUTION.md`。详见 [ATTRIBUTION.md](ATTRIBUTION.md)。

---

## 故障排查

- **启动没报错，但跑接续时拒绝运行**：说明 ComfyUI 布局自检没通过（多半是 ComfyUI 太旧或 H3 锚定代码有改动）。看日志里的具体原因；0.33.4 及更旧请升 0.34+。
- **Picker 报「No clips found」**：该 `project_name` 库里还没有镜头。把 `mode` 设为 `Auto`（库空时自动作为首段），或确认 Saver 用的是同一个项目名。
- **接缝有电平跳 / 音频「像但不是同一条」**：在解码后、Trim 前插一个 **Seam Probe**（`clip_b_untrimmed` 接解码后的 audio、`trim_frames` 从 Motion Context 接过来、`clip_a_latent` 接你正在钉的那段 latent），读它输出的 `report`：`lag_ms`、`corr`、电平 step 能告诉你到底是真接续还是「模仿」。
- **画面分辨率不一致导致拒绝**：让 `context_latent` 与目标片段同分辨率。

---

## 目录结构

```
ComfyUI-H3-ClipStream/
├── __init__.py              # 顶层入口：importlib 载入两个子包，合并 MAPPINGS，WEB_DIRECTORY=./web
├── LICENSE                  # GPLv3（取自上游 B）
├── ATTRIBUTION.md           # 双上游致谢 + GPLv3 说明
├── requirements.txt
├── .gitignore
├── README.md
├── web/
│   ├── h3_motion_context.js      # B 前端（原样）
│   ├── clip_bin_picker.js        # A 前端（已去星级；import 已改为 2 级 ../../scripts/app.js）
│   └── clip_bin_picker.css       # A 前端样式（卡片可换行布局）
├── motion_context/
│   ├── __init__.py          # 注册 B 节点 + probe + chain 路由
│   ├── nodes.py             # B：MotionContext / Trim / Save / Load / Chain + register_chain_routes
│   ├── layout_contract.py   # B：布局自检
│   ├── csrf_guard.py        # B：CSRF 守卫
│   └── probe_node.py        # B：SeamProbe
├── clipbin/
│   ├── __init__.py          # 注册 A Saver/Picker + clip_bin 路由
│   ├── nodes.py             # A：Saver + Picker（重分类为 MiniMaxH3/ClipStream；已去星级，Picker 含 mode 三种运行模式）
│   ├── _shared.py           # 从 A 抽出的纯函数（供 Clip Bin 独立使用）
│   ├── clip_bin_manager.py  # A（原样，仅把 cache_manager 导入改为 _shared）
│   └── clip_bin_api.py      # A（原样）
└── examples/
    └── H3_reference_workflow.json   # 取自 B 的完整 H3+接续参考工作流
```
