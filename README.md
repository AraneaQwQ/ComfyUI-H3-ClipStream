# ComfyUI H3 ClipStream

**[English](#english)** | **[简体中文](#简体中文)**

---

## English

> **One plugin, two jobs:** a **visual, searchable Clip Bin** for MiniMax H3, plus **seamless audio-video continuation** (Motion-Context) between shots.

| Component | Source | Role |
|-----------|--------|------|
| **Clip Bin** (Saver + Picker) | [knoic/ComfyUI-MiniMaxH3-PrefixStream](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream) | Visual gallery — archive & retrieve any past shot as a full AV latent |
| **Clip Bin Dual** (Dual Saver + Dual Picker) | Original to this project | One card holds **both** 一采 + 二采 latents — one click gives you both |
| **Motion-Context** (continuation engine) | [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) | Frame-anchored chaining — audio & video both carry over |

We **kept** PrefixStream's visual Clip Bin but **removed** its continuation engine entirely. Continuation is handled 100% by Motion-Context. The Dual pair is our own addition for shots produced by two sampler passes (一采 + 二采).

**The key wiring:** `Picker.latent` → `Motion Context.context_latent` — that's it. No decode/re-encode round-trip, no audio "restarting from scratch".

---

### How it works

MiniMax H3 is a **joint audio-video** model — video and audio live in the same `NestedTensor([video, audio])` latent.

1. **Clip Bin Saver** archives the full AV latent from the sampler output.
2. **Clip Bin Picker** loads any past clip back out as `{"samples": NestedTensor([video, audio])}`.
3. **Motion Context**'s `context_latent` input expects exactly that — the previous clip's sampler-output AV latent. The two formats are **natively compatible**.

So `Picker.latent` plugs directly into `context_latent` with zero adapters.

---

### Wiring diagram

```
[First clip]
  H3 workflow (I2V / Ref2V / T2V) → Sampler → Decode
    → Clip Bin Saver  (archive: full AV latent + preview card + shot tag)

[Continuation]
  Clip Bin Picker  (pick any shot → outputs latent / first_frame / tail_frame / prompt / clip_id)
    │
    │  Picker.latent ──────────► Motion Context . context_latent
    │  native conditioning ────► Motion Context . conditioning
    │  target latent ──────────► Motion Context . latent
    │  VAE ────────────────────► Motion Context . vae
    │
    ▼
  Motion Context outputs conditioning → guider → Sampler → Decode
    → Trim  (cut pinned head frames; audio & video trimmed together)
    → Clip Bin Saver  (re-archive for the next continuation)
```

**Dual path (one shot = two sampler passes):**

```
一采: H3 workflow → Sampler → Decode ─┐
二采: H3 workflow → Sampler → Decode ─┼→ Dual Clip Saver   (one card: latent_一采 + latent_二采)

Dual Clip Picker ──► latent_一采 ─► Motion Context (一采 path) . context_latent
                 └► latent_二采 ─► Motion Context (二采 path) . context_latent
```

---

### Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/AraneaQwQ/ComfyUI-H3-ClipStream.git
pip install -r ComfyUI-H3-ClipStream/requirements.txt   # optional; ComfyUI usually ships torch/safetensors
```

Restart ComfyUI, hard-refresh the browser (`Ctrl+F5`).

> **Requires ComfyUI ≥ 0.34.0** — H3 arbitrary-frame anchoring landed in 0.34. Older versions will get a clear error message.

---

### Storage

Clips live in `ComfyUI/output/h3-clipstream/<project_name>/`. If you have an older install with `output/minimax_h3_bins`, it is **auto-migrated** (renamed) on first run. A ready-to-load example workflow is in `examples/`.

---

### Nodes (10 total)

#### Clip Bin (`MiniMaxH3/ClipStream`)

| Node | What it does |
|------|-------------|
| **Clip Bin Saver** | Archives an H3 AV latent + preview card + shot tag + lineage into a project folder (real video duration is probed with ffprobe and shown on the card) |
| **Clip Bin Picker** | Visual card gallery. 3 modes: **Auto** / **Force Initial** / **Strict Chaining**. Outputs `latent`, `tail_frame`, `first_frame`, `prompt`, `clip_id`, `project_name` |
| **Dual Clip Saver** (一采+二采) | Archives the latents of both sampler passes (一采 required, 二采 optional) into **one card**, badged 「仅一采」 / 「含一采+二采」 |
| **Dual Clip Picker** (一采+二采) | Same 3 modes as the Picker. One card click outputs **both** `latent_一采` and `latent_二采` (a pass that didn't run outputs `None`), plus `first_frame` / `tail_frame` / `prompt` / `clip_id` / `project_name` |

#### Motion-Context (`conditioning/minimax`)

| Node | What it does |
|------|-------------|
| **H3 Motion Context** | Pins previous-clip frames as undenoised condition rows at the head of the new clip (audio + video) |
| **H3 Motion Context Trim** | Cuts the pinned head frames off the decoded output (audio & video synced) |
| **Save / Load Latent** | B's own cross-run persistence (alternative to Clip Bin) |
| **Chain** | Sequential execution control (approve / run / re-roll / auto-advance) |
| **Seam Probe** | In-canvas measurement: verifies the seam is a true continuation, not a "re-imagining" |

---

### Picker modes

| Mode | Behaviour |
|------|-----------|
| **Auto** (default, recommended) | Empty bin → outputs `None` (first-clip mode). Non-empty bin → auto-continues latest clip. |
| **Force Initial** | Always outputs `None`. Forces a brand-new first clip regardless of bin contents. |
| **Strict Chaining** | Must have clips in the bin, otherwise raises an error. Continues the specified / latest clip. |

> When the Picker outputs `None` (first-clip), Motion Context detects the empty context and **passes conditioning through unchanged** (`trim_frames = 0`). Trim also passes through. The entire chain degrades gracefully into a normal first-clip workflow.

> The Dual Picker shares the same three modes; in first-clip mode **both** latents output `None`.

---

### Key parameters

| Parameter | Notes |
|-----------|-------|
| `context_length` | Only **5 / 22 / 39 / 56** (integer latent steps). **22** = near-seamless, default recommended. 56 = strongest pin but eats 2.3s of your delivered clip. |
| `audio_context_length` | Independent audio tail window. **Multiple of 24** = whole seconds (24 = 1s, default). 0 = follow video window. |
| Resolution | `context_latent` **must** match the target clip resolution. Mismatch = hard rejection. |

---

### Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| Layout check fails at runtime | ComfyUI too old or H3 anchor code changed. Upgrade to ≥ 0.34.0. |
| Picker: "No clips found" | No clips in that `project_name`. Use **Auto** mode or check the Saver's project name matches. |
| Audio seam jump / "sounds similar but isn't the same" | Insert a **Seam Probe** between Decode and Trim. Read the `report` output for `lag_ms`, `corr`, level step. |
| Resolution mismatch rejection | Ensure `context_latent` and target clip are the same resolution. |
| Dual Picker: 二采 latent is empty | That card was archived with only 一采 (二采 pass never ran). Expected — the 一采 path still works. |

---

### License & Attribution

Distributed under **GPLv3** (the stricter of the two upstream licenses).

- **Motion-Context** (GPLv3): [NikoDemon80](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) — included verbatim in `motion_context/`.
- **Clip Bin** (MIT): [knoic](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream) — included in `clipbin/`, decoupled from its continuation engine.

See [ATTRIBUTION.md](ATTRIBUTION.md) for full details.

---

### Project structure

```
ComfyUI-H3-ClipStream/
├── __init__.py              # Entry point: loads both sub-packages, merges MAPPINGS
├── LICENSE                  # GPLv3
├── ATTRIBUTION.md
├── requirements.txt
├── README.md
├── examples/
│   └── H3_Ref2VA_Contextual_LongVideo_ClipStream.json   # Ready-to-load example workflow
├── scripts/
│   └── sync_upstream.sh     # Helper: track upstream Motion-Context updates
├── web/
│   ├── h3_motion_context.js       # Motion-Context frontend
│   ├── clip_bin_picker.js         # Clip Bin gallery frontend (card wrap layout)
│   └── clip_bin_picker.css
├── motion_context/
│   ├── __init__.py
│   ├── nodes.py                   # MotionContext / Trim / Save / Load / Chain
│   ├── layout_contract.py         # Layout self-check
│   ├── csrf_guard.py
│   └── probe_node.py              # SeamProbe
└── clipbin/
    ├── __init__.py
    ├── nodes.py                   # Saver + Picker (3 modes)
    ├── dual_nodes.py              # Dual Saver + Dual Picker (一采+二采)
    ├── dual_manager.py            # Dual-variant archive & load
    ├── _shared.py
    ├── clip_bin_manager.py
    └── clip_bin_api.py
```

---
---

## 简体中文

> **一个插件，两件事：** 给 MiniMax H3 一个**可视化、可搜索的镜头素材库（Clip Bin）**，并让镜头之间**音画无缝接续（Motion-Context）**。

| 组件 | 来源 | 作用 |
|------|------|------|
| **Clip Bin**（Saver + Picker） | [knoic/ComfyUI-MiniMaxH3-PrefixStream](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream) | 可视化画廊——归档 & 取回任意历史镜头的完整音画 latent |
| **Clip Bin Dual**（Dual Saver + Dual Picker） | 本项目原创 | 一张卡片同时保存 **一采 + 二采** 两个 latent——点一次，两个都拿到 |
| **Motion-Context**（接续引擎） | [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) | 关键帧锚定链式接续——音画都带着走 |

我们**保留**了 PrefixStream 的可视化 Clip Bin，但**完全移除**了它自带的接续引擎。接续 100% 由 Motion-Context 负责。Dual Saver/Picker 是我们为「一个镜头经两次采样器生成（一采 + 二采）」新增的原创节点。

**核心接线：** `Picker.latent` → `Motion Context.context_latent`——就这一根线。不做解码/重编码往返，不让音频"听起来像"地重新起步。

---

### 工作原理

MiniMax H3 是**音视频一体**模型——视频和音频活在同一个 `NestedTensor([video, audio])` 的 latent 里。

1. **Clip Bin Saver** 把采样器输出的完整音画 latent 归档进素材库。
2. **Clip Bin Picker** 把任意历史片段以 `{"samples": NestedTensor([video, audio])}` 的形式原样吐回。
3. **Motion Context** 的 `context_latent` 输入恰好要的就是这个——上一段的采样器输出音画 latent。两种格式**天然兼容**。

所以 `Picker.latent` 直接插进 `context_latent`，零适配器。

---

### 接线图

```
[首段]
  H3 工作流 (I2V / Ref2V / T2V) → 采样器 → 解码
    → Clip Bin Saver  （归档：完整音画 latent + 预览卡 + 镜头标签）

[续写]
  Clip Bin Picker  （挑镜头 → 输出 latent / first_frame / tail_frame / prompt / clip_id）
    │
    │  Picker.latent ──────────► Motion Context . context_latent
    │  原生 conditioning ──────► Motion Context . conditioning
    │  目标 latent ────────────► Motion Context . latent
    │  VAE ────────────────────► Motion Context . vae
    │
    ▼
  Motion Context 输出 conditioning → guider → 采样器 → 解码
    → Trim  （裁掉 pinned 头部帧，音画同步裁）
    → Clip Bin Saver  （再归档，形成下一段可接续的素材）
```

**双路（一个镜头 = 两次采样器）：**

```
一采: H3 工作流 → 采样器 → 解码 ─┐
二采: H3 工作流 → 采样器 → 解码 ─┼→ Dual Clip Saver   （一张卡片：latent_一采 + latent_二采）

Dual Clip Picker ──► latent_一采 ─► Motion Context（一采路）. context_latent
                 └► latent_二采 ─► Motion Context（二采路）. context_latent
```

---

### 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/AraneaQwQ/ComfyUI-H3-ClipStream.git
pip install -r ComfyUI-H3-ClipStream/requirements.txt   # 可选；ComfyUI 通常已自带 torch/safetensors
```

重启 ComfyUI，浏览器 `Ctrl+F5` 硬刷新。

> **要求 ComfyUI ≥ 0.34.0**——H3 任意关键帧锚定从 0.34 起才支持。更旧版本会明确报错提示。

---

### 存储位置

素材存放在 `ComfyUI/output/h3-clipstream/<项目名>/`。若旧版本存在 `output/minimax_h3_bins`，首次运行会**自动迁移**（改名）。现成可载入的示例工作流见 `examples/` 目录。

---

### 节点清单（共 10 个）

#### Clip Bin（类别 `MiniMaxH3/ClipStream`）

| 节点 | 作用 |
|------|------|
| **Clip Bin Saver** | 把一段 H3 音画 latent + 预览卡 + 镜头标签 + 血缘归档进项目素材库（卡片时长按 ffprobe 实测显示） |
| **Clip Bin Picker** | 可视化卡片画廊。三种模式：**Auto** / **Force Initial** / **Strict Chaining**。输出 `latent`、`tail_frame`、`first_frame`、`prompt`、`clip_id`、`project_name` |
| **Dual Clip Saver** (一采+二采) | 把两条采样器路的 latent（一采必填、二采可选）归档进**同一张卡片**，卡片标注「仅一采」/「含一采+二采」 |
| **Dual Clip Picker** (一采+二采) | 与 Picker 相同的三种模式。点一次卡片同时输出 `latent_一采` 与 `latent_二采`（没跑的那条路输出 `None`），另输出 `first_frame`/`tail_frame`/`prompt`/`clip_id`/`project_name` |

#### Motion-Context（类别 `conditioning/minimax`）

| 节点 | 作用 |
|------|------|
| **H3 Motion Context** | 把上一段的关键帧作为"永不降噪的条件行"钉在新片段头部，音画一起接续 |
| **H3 Motion Context Trim** | 裁掉解码后片段的 pinned 头部，音画同步裁 |
| **Save / Load Latent** | B 自带的跨段持久化方案（Clip Bin 的替代） |
| **Chain** | 顺序执行控制（审批/运行/重roll/自动推进） |
| **Seam Probe** | 画布内接缝测量：验证是真接续还是"模仿" |

---

### Picker 三种模式

| 模式 | 行为 |
|------|------|
| **Auto**（默认，推荐） | 库空 → 输出 `None`（首段模式）。库非空 → 自动接续最新镜头。 |
| **Force Initial** | 始终输出 `None`。强制开辟全新首段，忽略库内所有素材。 |
| **Strict Chaining** | 库内必须有镜头，否则报错。接续指定/最新镜头。 |

> **首段时 Picker 输出 `None`**：Motion Context 检测到空上下文后**原样透传 conditioning**（`trim_frames = 0`），Trim 也随之透传。整条链自然退化为普通首段工作流，无需拔线。

> Dual Picker 同样支持三种模式；首段时**两个** latent 均输出 `None`。

---

### 关键参数

| 参数 | 说明 |
|------|------|
| `context_length` | 只有 **5 / 22 / 39 / 56**（整数 latent step）。**22** = 接近无缝，默认推荐。56 = 最强锚定但吃掉交付片段 2.3 秒。 |
| `audio_context_length` | 独立音频尾部窗口。**24 的倍数** = 整秒（24 = 1 秒，默认）。0 = 跟随画面窗口。 |
| 分辨率 | `context_latent` **必须**与目标片段同分辨率，否则硬拒绝。 |

---

### 故障排查

| 症状 | 原因 / 解决 |
|------|------------|
| 运行时布局自检失败 | ComfyUI 太旧或 H3 锚定代码有改动。升级到 ≥ 0.34.0。 |
| Picker 报"No clips found" | 该 `project_name` 库里没有镜头。用 **Auto** 模式或确认 Saver 项目名一致。 |
| 音频接缝跳变 / "像但不是同一条" | 在 Decode 和 Trim 之间插 **Seam Probe**，读 `report` 输出的 `lag_ms`、`corr`、电平 step。 |
| 分辨率不匹配被拒绝 | 确保 `context_latent` 与目标片段同分辨率。 |
| Dual Picker 的 二采 latent 为空 | 该卡片归档时只有一采（二采路没跑过），属正常现象；一采路照常可用。 |

---

### 许可与来源

按**更严格的一方**分发：**GPLv3**。

- **Motion-Context**（GPLv3）：[NikoDemon80](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)——以 `motion_context/` 子包**原样**收录。
- **Clip Bin**（MIT）：[knoic](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream)——以 `clipbin/` 子包收录，已从接续引擎**解耦**。

详见 [ATTRIBUTION.md](ATTRIBUTION.md)。

---

### 目录结构

```
ComfyUI-H3-ClipStream/
├── __init__.py              # 入口：载入两个子包，合并 MAPPINGS
├── LICENSE                  # GPLv3
├── ATTRIBUTION.md
├── requirements.txt
├── README.md
├── examples/
│   └── H3_Ref2VA_Contextual_LongVideo_ClipStream.json   # 现成示例工作流
├── scripts/
│   └── sync_upstream.sh     # 辅助脚本：跟踪上游 Motion-Context 更新
├── web/
│   ├── h3_motion_context.js       # Motion-Context 前端
│   ├── clip_bin_picker.js         # Clip Bin 画廊前端（卡片换行布局）
│   └── clip_bin_picker.css
├── motion_context/
│   ├── __init__.py
│   ├── nodes.py                   # MotionContext / Trim / Save / Load / Chain
│   ├── layout_contract.py         # 布局自检
│   ├── csrf_guard.py
│   └── probe_node.py              # SeamProbe
└── clipbin/
    ├── __init__.py
    ├── nodes.py                   # Saver + Picker（3 模式）
    ├── dual_nodes.py              # Dual Saver + Dual Picker（一采+二采）
    ├── dual_manager.py            # 双变体归档与读取
    ├── _shared.py
    ├── clip_bin_manager.py
    └── clip_bin_api.py
```
