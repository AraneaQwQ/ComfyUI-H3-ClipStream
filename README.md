# ComfyUI H3 ClipStream

**Current: ComfyUI V3 API + Nodes 2.0.** Requires ComfyUI ≥ 0.37.0. See [V3_MIGRATION.md](V3_MIGRATION.md) for details.
Card deletion supported on both single & dual pickers. See [CACHE_AND_DELETION.md](CACHE_AND_DELETION.md).
Long Builder stitches a project's archived shots into one film — pick the project, click cards out, and drag cards into the order you want. See [Long video assembly](#long-video-assembly).

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

[Long film]
  Clip Long Builder  (panel: choose project → click cards out, drag cards to reorder)
    → ffprobe pre-check per segment → ffmpeg concat
    → output/h3_long/<project>/<name>.mp4   (never written back into the card library)
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

Long films built by the Long Builder go to `output/h3_long/<project_name>/` and are **not** part of the card library.

---

### Nodes (14 total)

#### Clip Bin (`MiniMaxH3/ClipStream`)

| Node | What it does |
|------|-------------|
| **Clip Bin Saver** | Archives an H3 AV latent + preview card + shot tag + lineage into a project folder (real video duration is probed with ffprobe and shown on the card) |
| **Clip Bin Picker** | Visual card gallery. 3 modes: **Auto** / **Force Initial** / **Strict Chaining**. Outputs `latent`, `tail_frame`, `first_frame`, `prompt`, `clip_id`, `project_name` |
| **Dual Clip Saver** (一采+二采) | Archives the latents of both sampler passes (一采 required, 二采 optional) into **one card**, badged 「仅一采」 / 「含一采+二采」 |
| **Dual Clip Picker** (一采+二采) | Same 3 modes as the Picker. One card click outputs **both** `latent_一采` and `latent_二采` (a pass that didn't run outputs `None`), plus `first_frame` / `tail_frame` / `prompt` / `clip_id` / `project_name` |
| **Clip Long Builder** | Panel for choosing the project, clicking cards out and dragging them into order. Reads the MP4s already archived in a project's cards, orders them by the shot number on the card (or by the dragged card order), pre-checks every segment with ffprobe and joins them into one long video. Each card shows the resolution and duration measured from its archived video. One `video` output that previews inline; written to `output/h3_long/<project>/` — never into the card library |

#### Motion-Context (`conditioning/minimax`)

| Node | What it does |
|------|-------------|
| **H3 Motion Context** | Pins previous-clip frames as undenoised condition rows at the head of the new clip (audio + video) |
| **H3 Motion Context Trim** | Cuts the pinned head frames off the decoded output (audio & video synced) |
| **Save / Load Latent** | B's own cross-run persistence (alternative to Clip Bin) |
| **Chain** | Sequential execution control (approve / run / re-roll / auto-advance) |
| **Seam Probe** | In-canvas measurement: verifies the seam is a true continuation, not a "re-imagining" |
| **Refine Blend** (Experimental) | Keeps the first-pass frames that the pin established and takes the later frames from a refine pass, so a long chain stops drifting (faces ageing, detail building up). `use_refine = False` or no `refined` input = pass-through |
| **Join Match** (Experimental) | Measures the step at the join inside the sampled latent and shifts the whole new clip back so it starts where the previous clip ended; optional spread/detail matching, each capped at 10%. `context_latent` is optional - without it the previous clip is taken from `samples` |
| **Sigmas Tail** (Experimental) | Reshapes only the last few noise levels before the final zero, so the closing frames of a continuation do not come out crisper than the frames they were pinned from. Positive strength lifts the tail, negative does the opposite; `0.0` and too-short schedules pass through |

> The three Experimental nodes are upstream algorithms carried verbatim, and all three are optional - the chain works without them.
>
> They work on latents, never on decoded media: `sampler -> Refine Blend -> Join Match -> Save Latent / VAE Decode`, and `BasicScheduler -> Sigmas Tail -> SamplerCustomAdvanced`. Join Match goes after Refine Blend, not before it. Drive Join Match `context_length` from the Motion Context node `trim_frames` output (0 on the first clip = pass-through), and Refine Blend `clip_index` from the Chain node - put the node in the same chain group. Save Latent and both decodes must take the final output, or the mp4 will not match the latent the next clip continues from. Motion Context Trim stays after Decode.

---

### Picker modes

| Mode | Behaviour |
|------|-----------|
| **Auto** (default, recommended) | Empty bin → outputs `None` (first-clip mode). Non-empty bin → auto-continues latest clip. |
| **Force Initial** | Always outputs `None`. Forces a brand-new first clip regardless of bin contents. |
| **Strict Chaining** | Must have clips in the bin, otherwise raises an error. Continues the specified / latest clip. |

> When the Picker outputs `None` (first-clip), Motion Context detects the empty context and **passes conditioning through unchanged** (`trim_frames = 0`). Trim also passes through. The entire chain degrades gracefully into a normal first-clip workflow.

> The Dual Picker shares the same three modes; in first-clip mode **both** latents output `None`.

### Project menu

Both bin panels choose the project from a dropdown instead of a typed name:

- The **Clip Bin Picker** header menu lists every folder in the media pool with its card count (`科幻短片 01 (6 卡)`), and its first entry is `＋ 新建项目…`. Choosing it opens a name field inside the panel; **建立** creates the folder, writes an empty index, and switches the node to it. An existing name is selected rather than duplicated, and the name the node ends up holding is the sanitized folder name the server actually wrote.
- The last entry is `🗑 删除当前项目…`. It opens a confirm line that names the bin and says how many cards - and how many archived videos - would go with it, and the button repeats that name. The request has to send the same name back as `confirm`, so a panel left open in another tab cannot empty the wrong folder. Afterwards the node moves to `Default_Project` if it exists, otherwise to the next remaining bin.
- The **Clip Long Builder** menu offers only the folders that hold archived video, because a bin without video can never become a film.
- `project_name` is still an ordinary widget (behind the advanced toggle) and still works when typed by hand - the menu only removes the need to remember names.

Backed by `GET /minimax/clip_bin/projects` (every bin with its `clips` / `videos` counts; add `?videos_only=1` for the Long Builder), `POST /minimax/clip_bin/project` (creates a bin) and `POST /minimax/clip_bin/project/delete` (deletes a whole bin, `confirm` must repeat its name). All three write endpoints accept same-origin requests only.

---

### Long video assembly

`Clip Long Builder` (`MiniMaxClipBinLongBuilder`) reads the MP4s that the Savers already archived inside each card and joins them in shot order, so the manual stitching step is gone. It is a read-side node: it never writes into a card, never touches a latent, and only re-encodes when the segments cannot be joined as they are or slow-motion cuts are being restored to their original speed.

**Canonical wiring** — the one rule that keeps both the bin and the long film clean:

| Output | What to feed it |
|--------|-----------------|
| `latent_*` (Picker / Dual Picker) | the **full** sampler-output latent — continuation needs the pinned frames |
| `images_*` / `audio_*` / `video_file_*` (Saver / Dual Saver) | the **Trimmed** output — the delivered clip, without the overlap frames |

Feed it that way and every card's video is exactly what the viewer should see, so joins never repeat a beat. Cards saved before Trim still work; the node detects them (see pre-flight checks).

**The panel is the interface** — every widget on the node itself is hidden behind the advanced toggle:

- A **project dropdown** lists only the folders that hold archived video, with the number of usable segments next to each name. Nothing to type.
- A **card deck** shows every card in that project, ordered the way the film plays; hover a card to play its archived video.
- **The button on the card is the switch** — `⊘ 移出成片` takes that segment out of the film, the picture dims, the card moves to the back of the deck with an 已排除 badge, and the button becomes `↺ 加入成片`. This is how a rejected take or a branch is skipped. The card itself is not clickable, so pointing at a card can never change the film by accident.
- **Drag a card onto another to move it along the timeline** — the deck order *is* the film order, and the panel writes it into `clip_order`. Every joining card carries its position in the film (`#1`, `#2`, …), and `↺ 按镜头序号` puts the deck back on shot numbers.
- **Each card shows the resolution and duration of its archived video** (`1088×1920 · 6.21s`) — measured with ffprobe once per file and cached in the card, never estimated from the latent. The summary line adds the total length of the film.
- **Slow-motion cuts can be restored to their original speed** — choose the factor used when cutting and the Builder applies its reciprocal. The base frame rate is converted automatically (`24fps + 0.5x → 48fps`, `24fps + 0.75x → 32fps`) so restoring speed does not throw away rendered frames. Audio is retimed with `atempo` to preserve pitch.
- The summary line says exactly what will be joined (`将拼接 4 段 · 约 24.8 秒：Shot 1 → Shot 2 → Shot 4`), what is excluded, and what has no archived video. While cards are switched off, that line carries a `↺ 全部加回` button.
- **Card size is a 100%–400% zoom**, the same steps as the Clip Bin picker. It changes the cards only: the width you gave the node is never touched, and the rows you were looking at stay on screen. `⤢ 适应` sets the height to two rows at the current width and the rest scrolls.
- **The node keeps the size you gave it.** Refresh, re-ordering, switching project and a new run redraw the cards but never resize the node — only `⤢ 适应` and the zoom buttons change its height, and a node that has never been sized is fitted once when it first gets cards.
- After a run the finished film plays inline on the node and the panel prints where it was written. `▼ 收起成片` puts that preview away — the node becomes compact while the cards are being arranged — and `▶ 展开成片` gives the room back. Expanding goes back to exactly the height the node had before you collapsed it, so toggling never makes the node creep taller. Both the zoom and the preview choice are remembered in this browser.

**How the order is resolved**

- By default cards are ordered by the shot number on the card (`Shot 1`, `Shot 2`, …) — the order the film was generated in. A project whose early takes were deleted simply starts at `Shot 4`.
- **Dragging a card switches the deck to manual order**: `clip_order` then holds the `clip_id`s top to bottom and the film follows it. Cards the order does not mention are appended by shot number, so a segment generated after the last drag still joins the film instead of disappearing.
- `Shot 12` sorts after `Shot 2`, never between `Shot 1` and `Shot 2`.
- Tags with no number (a hand-written description) keep generation order and come after the numbered cards.
- Lineage (`parent_clip_id`) is **not** used for the timeline — it records which card a generation continued from, which is a different question. It stays on the card for the Pickers.
- A hole in the numbering (a take deleted from the bin) is named in the log; switching a card off in the panel is not a hole.
- A card with no archived video is skipped and named in the log. The panel greys it out and will not select it.

**Options** — the panel groups them into **Join & Speed / Project & Cards / Film Preview**, in that top-to-bottom order. It only hides the native widgets; their values stay in the original workflow positions.

| Option | Notes |
|--------|-------|
| `variant_policy` | **优先二采** (default: use the 二采 video when the card has one, otherwise fall back to 一采) / **仅一采** / **仅二采**. Cards that only hold one variant ignore the policy. |
| `join_mode` | **auto** (default): lossless `-c copy` when every segment matches, otherwise re-encode to unify. **copy**: hard error on any mismatch — for projects you have verified are uniform. **reencode**: always re-encode; this is how you force mixed-resolution history together. |
| `project_name` | Written by the panel's project dropdown. Filling it by hand works too — press 刷新 afterwards.
| `exclude_clips` | Written by the panel: the `clip_id`s switched off in the deck, comma separated. A shot-tag substring works here if you edit it by hand.
| `clip_order` | Written by the panel when a card is dragged: the `clip_id`s in the order the film should play, comma separated. Empty means follow the shot numbers; `↺ 按镜头序号` in the panel clears it. Cards it does not name are appended by shot number, and a `clip_id` whose card was deleted is reported and skipped.
| `fps` | **Base frame rate**: match the generation fps (24). Ordinary re-encoding uses it directly. Speed restoration divides it by the slow-motion factor, so `0.5x` at 24fps outputs 48fps and `0.75x` outputs 32fps instead of dropping rendered frames. |
| `output_name` | Optional. Default is `<project>_<n>shots_<timestamp>.mp4`. |
| `playback_speed` | The slow-motion factor used when the cuts were made: `1.0x` (default, no change), `0.75x`, `0.5x`, or `custom`. The Builder applies the reciprocal to restore original speed, so `0.5x` produces a `2x` film. Output fps is derived from the base fps automatically; video and audio are retimed together, and audio uses `atempo` to keep its pitch. Any restoration requires re-encoding and is rejected in `copy` mode. |
| `playback_speed_custom` | Custom slow-motion factor from `0.1` to `1.0`, step `0.1`; used only when `playback_speed` is `custom`. |

**Pre-flight checks** — every segment is measured with ffprobe *before* anything is written:

- Resolution / frame rate / audio presence / sample-rate mismatch → `auto` switches to re-encode and says which parameter differed; `copy` refuses and tells you to switch.
- **Untrimmed seam**: if a segment's measured video frame count is **not below** its latent frame count, the pinned overlap frames are still in that video and the film repeats a beat at the join. The log names the segment — re-archive it from the Trim output and rebuild. Two segments are never flagged: the first one in the film, and any card the Pickers marked as a no-context generation (`parent_clip_id` is `[INITIAL]` or `[INITIAL_GENERATION]`) - a first shot has nothing pinned at its head, so equal frame counts there are normal wherever it ends up in the order.
- Frame counts come from ffprobe, never from the card's `meta.frames` (that number is the latent count — see below).

> Card badges show the **latent** frame count, because that is what continuation consumes. Overlap frames are therefore *not* annotated on the card; they are only explained in the Long Builder's log.

Output lands in `output/h3_long/<project_name>/` — **not** the card library, so a long film can never be picked as a clip by accident. The node has a single `video` output: it plays inline on the node and can be wired straight into `SaveVideo` / `VHS_VideoCombine`. The per-segment audit — measured frames, duration, join mode and every warning — is written to the ComfyUI log instead of being exposed as sockets.

Requires `ffmpeg`/`ffprobe` on `PATH` (the Savers already need them to make preview cards).

---

### Key parameters

| Parameter | Notes |
|-----------|-------|
| `context_length` | Only **5 / 22 / 39 / 56** (integer latent steps). **22** = near-seamless, default recommended. 56 = strongest pin but eats 2.3s of your delivered clip. |
| `audio_context_length` | Independent audio tail window, END-aligned with the pinned picture window, so it only controls how far back the sound reaches. **0** = follow the picture window. Default **18**. Multiples of 3 land exactly on the 40 Hz audio grid; off-grid values are widened to the nearest whole step. A workflow saved earlier keeps whatever value it already stored. |
| `stock_format` (Load Latent) | Off (default) = Motion Context own format, accepted only by the Motion Context node `context_latent` input. On = a standard H3 video+audio latent that stock nodes (Separate AV Latent, Latent Cut, samplers) accept. |
| `folder` (Load Latent) | `output` (default) = a file or a chain folder under the ComfyUI output directory. `input` = one file under the input directory, e.g. uploaded over HTTP by an external tool. |
| Resolution | `context_latent` **must** match the target clip resolution. Mismatch = hard rejection. |

---

### Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| Layout check fails at runtime | ComfyUI too old or H3 anchor code changed. Upgrade to ≥ 0.34.0. |
| Picker: "No clips found" | No clips in that `project_name`. Use **Auto** mode or check the Saver's project name matches. |
| Audio seam jump / "sounds similar but isn't the same" | Insert a **Seam Probe** between Decode and Trim. Read the `report` output for `lag_ms`, `corr`, level step. |
| Resolution mismatch rejection | Ensure `context_latent` and target clip are the same resolution. |
| Long Builder: the film repeats a beat at a join | That segment was archived from the **untrimmed** output. Re-run the Saver with the Trim output on `images_*`/`audio_*`, then rebuild — the log names the segment. |
| Long Builder: parameters differ, `copy` mode refused | Segments differ in resolution, fps or audio. Use **auto** or **reencode**; `copy` is only for verified-uniform projects. |
| Long Builder: a shot has no archived video | That card was archived with `save_video` off. Re-archive the segment; the panel greys such cards out, skips them, and the log names them. |
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
├── VERSION.md               # Version rule: archive/<date>-<commit> snapshots + notes
├── requirements.txt
├── README.md
├── V3_MIGRATION.md          # V3 API migration notes
├── CACHE_AND_DELETION.md    # Index cache & card deletion behaviour
├── examples/
│   └── H3_Ref2VA_Contextual_LongVideo_ClipStream.json   # Ready-to-load example workflow
├── scripts/
│   └── sync_upstream.sh     # Helper: track upstream Motion-Context updates
├── tests/                   # unittest suite: python -m unittest discover -s tests -t .; JS: node tests/js/
│   ├── _support.py          # Loaders: ComfyUI on sys.path, clipbin without comfy_api
│   ├── test_node_schema.py  # Locks the 14 node ids, categories, inputs, outputs, options
│   ├── test_frame_grid.py   # Frame <-> latent-step grid invariants
│   ├── test_latent_codec.py # latent pack/unpack + image/audio standardising
│   ├── test_asset_paths.py  # Card path safety & preview URLs
│   ├── test_clip_bin_store.py # Single/dual card round-trip, index, deletion
│   ├── test_long_builder.py # Shot-number & dragged ordering, join classification, seam warnings
│   ├── test_projects_api.py # Project dropdown feed, card video probe cache
│   ├── test_experiment_nodes.py # Frame cycle math, refine blend, join match, sigmas tail, latent paths
│   └── js/long_builder_order.test.mjs # Deck order (node tests/js/long_builder_order.test.mjs)
├── web/
│   ├── h3_motion_context.js       # Motion-Context frontend
│   ├── clip_bin_picker.js         # Clip Bin gallery frontend (card wrap layout)
│   ├── dom_panel.js               # DOM panel used by the Pickers
│   ├── delete_button.js           # Card delete buttons + confirm flow
│   ├── long_builder_panel.js      # Long Builder panel: project dropdown + draggable deck
│   ├── long_builder_order.js      # Deck order = film order (pure, unit-tested)
│   ├── clip_bin_picker.css        # Card gallery styles (shared by both panels)
│   └── long_builder.css           # Long Builder panel chrome
├── motion_context/
│   ├── __init__.py
│   ├── nodes.py                   # MotionContext / Trim / Save / Load / Chain
│   ├── layout_contract.py         # Layout self-check
│   ├── csrf_guard.py
│   ├── probe_node.py              # SeamProbe
│   ├── refine_blend.py            # Refine Blend (upstream algorithm, V3 node class)
│   ├── join_match.py              # Join Match (upstream algorithm, V3 node class)
│   └── sigma_tools.py             # Sigmas Tail (upstream algorithm, V3 node class)
└── clipbin/
    ├── __init__.py
    ├── nodes.py                   # Saver + Picker (3 modes)
    ├── dual_nodes.py              # Dual Saver + Dual Picker (一采+二采)
    ├── dual_manager.py            # Dual-variant archive & load
    ├── _shared.py
    ├── clip_bin_manager.py
    ├── clip_bin_api.py
    ├── long_builder.py          # Long film assembly: shot order, ffprobe pre-check, concat
    └── long_nodes.py            # Clip Long Builder node
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

[长片]
  Clip Long Builder （面板：选项目 → 卡片上的按钮排除；顺序 = 卡片上的镜头序号）
    → 逐段 ffprobe 预检 → ffmpeg 拼接
    → output/h3_long/<项目>/<文件名>.mp4   （不写回卡片库）
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

Long Builder 拼出的长片在 `output/h3_long/<项目名>/`，**不属于卡片库**。

---

### 节点清单（共 14 个）

#### Clip Bin（类别 `MiniMaxH3/ClipStream`）

| 节点 | 作用 |
|------|------|
| **Clip Bin Saver** | 把一段 H3 音画 latent + 预览卡 + 镜头标签 + 血缘归档进项目素材库（卡片时长按 ffprobe 实测显示） |
| **Clip Bin Picker** | 可视化卡片画廊。三种模式：**Auto** / **Force Initial** / **Strict Chaining**。输出 `latent`、`tail_frame`、`first_frame`、`prompt`、`clip_id`、`project_name` |
| **Dual Clip Saver** (一采+二采) | 把两条采样器路的 latent（一采必填、二采可选）归档进**同一张卡片**，卡片标注「仅一采」/「含一采+二采」 |
| **Dual Clip Picker** (一采+二采) | 与 Picker 相同的三种模式。点一次卡片同时输出 `latent_一采` 与 `latent_二采`（没跑的那条路输出 `None`），另输出 `first_frame`/`tail_frame`/`prompt`/`clip_id`/`project_name` |
| **Clip Long Builder** | 面板里选项目、用卡片上的按钮排除、拖动卡片排序。读取项目卡片里已归档的 MP4，按卡片上的镜头序号（或你拖出来的顺序）排序，逐段 ffprobe 预检后拼成一个长视频。每张卡片显示它的归档视频实测分辨率与时长。只有一个 `video` 输出，节点上直接预览；成品写在 `output/h3_long/<项目>/`，不进卡片库 |

#### Motion-Context（类别 `conditioning/minimax`）

| 节点 | 作用 |
|------|------|
| **H3 Motion Context** | 把上一段的关键帧作为"永不降噪的条件行"钉在新片段头部，音画一起接续 |
| **H3 Motion Context Trim** | 裁掉解码后片段的 pinned 头部，音画同步裁 |
| **Save / Load Latent** | B 自带的跨段持久化方案（Clip Bin 的替代） |
| **Chain** | 顺序执行控制（审批/运行/重roll/自动推进） |
| **Seam Probe** | 画布内接缝测量：验证是真接续还是"模仿" |
| **Refine Blend**（实验性） | 保留被锚点钉住的首采帧，之后的帧改取 refine 二次采样的结果，用来止住长链漂移（脸变老、细节堆积）。`use_refine = False` 或不接 `refined` = 直通 |
| **Join Match**（实验性） | 在采样结果里量出接缝处的跳变，把整段新片段平移回去，让它从上一段结束的地方开始；可选再做幅度/细节匹配，各自上限 10%。`context_latent` 可选，不接时从 `samples` 里取上一段 |
| **Sigmas Tail**（实验性） | 只改终点 0 之前的最后几个噪声级别，让接续段的结尾不再比被锚定的开头更锐。正强度抬高尾部，负强度相反；`0.0` 或调度太短 = 直通 |

> 三个实验性节点是上游算法的原样移植，全部可选，不接也能跑。
>
> 它们只处理 latent，不处理解码后的画面/音频：`采样器 -> Refine Blend -> Join Match -> Save Latent / VAE Decode`，以及 `BasicScheduler -> Sigmas Tail -> SamplerCustomAdvanced`。Join Match 接在 Refine Blend **之后**而不是之前。Join Match 的 `context_length` 用 Motion Context 节点的 `trim_frames` 输出驱动（首段是 0 = 直通），Refine Blend 的 `clip_index` 由 Chain 节点驱动（把它放进同一个 chain 分组）。Save Latent 和两个解码都要接最终输出，否则下一段接续的 latent 和 mp4 会对不上。Motion Context Trim 仍在 Decode 之后。

---

### Picker 三种模式

| 模式 | 行为 |
|------|------|
| **Auto**（默认，推荐） | 库空 → 输出 `None`（首段模式）。库非空 → 自动接续最新镜头。 |
| **Force Initial** | 始终输出 `None`。强制开辟全新首段，忽略库内所有素材。 |
| **Strict Chaining** | 库内必须有镜头，否则报错。接续指定/最新镜头。 |

> **首段时 Picker 输出 `None`**：Motion Context 检测到空上下文后**原样透传 conditioning**（`trim_frames = 0`），Trim 也随之透传。整条链自然退化为普通首段工作流，无需拔线。

> Dual Picker 同样支持三种模式；首段时**两个** latent 均输出 `None`。

### 项目选单

两个素材库面板都改成从下拉菜单里选项目，不用再手输名字：

- **Clip Bin Picker** 标题栏的菜单列出素材库里的每一个文件夹并标出卡片数（`科幻短片 01 (6 卡)`），第一项是 `＋ 新建项目…`：选它就在面板里展开一个名字输入框，点**建立**即创建文件夹、写入空索引，并把节点切到这个项目。已有同名不会被重复创建，节点最终保存的是服务端真正写出的那个（已清洗过的）文件夹名。
- 最后一项是 `🗑 删除当前项目…`：选它展开一行确认，写明要删掉哪个项目、会连带删掉多少张卡片（其中多少个已归档视频），按钮上再重复一遍项目名。请求必须把同一个名字作为 `confirm` 送回，所以另一个标签页里停着的面板不会删错文件夹。删完后节点自动切到 `Default_Project`（存在的话），否则切到下一个剩余项目。
- **Clip Long Builder** 的菜单只列真正有归档视频的文件夹——没有视频的库拼不成片。
- `project_name` 仍是普通控件（收在高级开关后面），手输照样能用；菜单只是让人不必再记名字。

对应接口：`GET /minimax/clip_bin/projects`（列出全部项目及其 `clips` / `videos` 计数；Long Builder 用 `?videos_only=1`）、`POST /minimax/clip_bin/project`（新建项目）与 `POST /minimax/clip_bin/project/delete`（删除整个项目，`confirm` 必须重复项目名）。三个写接口都只接受同源请求。

---

### 长视频拼接

`Clip Long Builder`（`MiniMaxClipBinLongBuilder`）读取 Saver 已经归档进卡片的 MP4，按镜头顺序拼成一个长视频——手动拼接这一步没了。它和 Picker 一样是只读侧节点：不写卡片、不碰 latent；只有各段本身接不起来，或用户选择恢复慢放切片的原速时才重编码。

**规范接线**——让素材库和长片都保持干净的那一条规则：

| 输出 | 应该接什么 |
|------|-----------|
| `latent_*`（Picker / Dual Picker） | **完整**的采样器输出 latent——接续需要 pinned 帧 |
| `images_*` / `audio_*` / `video_file_*`（Saver / Dual Saver） | **Trim 之后**的输出——交付片段，不含重叠帧 |

按这个接，每张卡片的视频就是观众该看到的画面，接缝不会重复一小段。已经用未裁版本归档过的卡片照样能拼，节点会自己发现（见下面的预检）。

**面板就是操作界面**——从上到下按「拼接与速度 / 项目与卡片 / 成片预览」三区组织。原生控件只隐藏、不换位置，旧工作流保存的值不变：

- **项目下拉框**只列出真正有归档视频的文件夹，名字后面直接标可用段数。不用手输。
- **卡片墙**按影片播放顺序列出该项目全部卡片，鼠标停在卡片上就播放它归档的视频。
- **卡片上的按钮就是开关**——`⊘ 移出成片` 把这一段移出成片：画面变灰、卡片移到卡片墙最后并打上「已排除」，按钮同时变成 `↺ 加入成片`，点一下它就回来。废掉的条、分叉的线就是这样跳过的。卡片本身不再可点，鼠标划过卡片不会误改成片。
- **把卡片拖到另一张卡片旁边就是改时间轴**——卡片墙的顺序就是成片的顺序，面板会把它写进 `clip_order`。参与拼接的卡片左上角标着它在成片里的位置（`#1`、`#2`…），`↺ 按镜头序号` 一键恢复按序号排。
- **每张卡片显示归档视频的实测分辨率与时长**（`1088×1920 · 6.21s`）——每个文件只跑一次 ffprobe，结果缓存在卡片里，不是按 latent 估算的。摘要行还会给出成片总时长。
- **可恢复慢放切片的原速**：在「拼接与速度」里选择切片当初的慢放倍率即可，Builder 自动取倒数，不用自己算；`0.5x → 2x`、`0.75x → 约 1.333x`。基准帧率也会自动换算：`24fps + 0.5x → 48fps`、`24fps + 0.75x → 32fps`，恢复原速时不再丢弃渲染帧。视频和音频一起变速，音频用 `atempo` 保持音调。摘要会同时显示慢放时间轴与恢复后的成片时长。`1.0x` 完全保持旧行为；恢复速度必须重编码，因此不能与 `copy` 同时使用。
- 摘要行写清将要拼什么（`将拼接 4 段 · 约 24.8 秒：Shot 1 → Shot 2 → Shot 4`）、排除了什么、哪些没有归档视频；有卡片被排除时，这一行带一个 `↺ 全部加回` 按钮，一键把整批卡片放回成片。
- **卡片大小是 100%–400% 缩放**，与素材库选择器同一档位：只改卡片大小，不改你自己拖出来的节点宽度，并保持你正在看的那几行。`⤢ 适应` 按当前宽度显示两行，其余滚动。
- **节点保持你给它的大小**：刷新、拖卡片、换项目和重新运行都只重画卡片，不会改节点尺寸；只有 `⤢ 适应` 和缩放按钮会改高度，从没被布局过的新节点在第一次出现卡片时自动适配一次。
- 跑完之后成片在节点上直接播放，面板底部打印成品位置；`▼ 收起成片` 把这块预览收掉（节点立刻变小，方便调卡片墙），`▶ 展开成片` 再放回来。展开只会回到你收起之前的那个节点高度，反复收起/展开不会越变越长。缩放档位与是否收起都记在本机浏览器里。

**镜头顺序怎么定**

- 默认按卡片上的镜头序号升序（`Shot 1`、`Shot 2`…）——就是影片生成的顺序。前面几段被删掉的项目，自然从 `Shot 4` 开始。
- **拖动过任意一张卡片，卡片墙就改成手动顺序**：`clip_order` 按从上到下保存 `clip_id`，成片照这个顺序播。没被点名的卡片按镜头序号补在后面，所以「拖完之后又生成了新段」不会让新段凭空消失。
- `Shot 12` 排在 `Shot 2` 之后，不会插在 `Shot 1` 和 `Shot 2` 中间。
- 没有数字的标签（手写的描述）保持生成顺序，排在带序号的卡片之后。
- 血缘（`parent_clip_id`）**不**用来定时间轴——它记的是「这一代是从哪张卡片接续来的」，那是另一回事。它留在卡片上给 Picker 用。
- 序号出现缺口（某条被从库里删了）会写进日志；在面板上点掉一张卡不算缺口。
- 没有归档视频的卡片会被跳过并在日志里点名。面板把它置灰，也不允许选。

**选项**——面板分区控制，原生输入仍按原位置序列化

| 选项 | 说明 |
|------|------|
| `variant_policy` | **优先二采**（默认：卡片有二采视频就用二采，没有则退回一采）/ **仅一采** / **仅二采**。只归档了一个变体的卡片忽略该策略。 |
| `join_mode` | **auto**（默认）：各段参数一致时无损直拷 `-c copy`，不一致自动重编码统一。**copy**：只允许直拷，参数不一致直接报错——用于确认过参数一致的项目。**reencode**：一律重编码，把不同分辨率的历史片段强行接在一起就用它。 |
| `project_name` | 面板的项目下拉框写入。手动填写也可以，填完点「刷新」。 |
| `exclude_clips` | 面板写入：卡片上排除掉的 `clip_id`，逗号分隔。手动填写时写镜头标签的一部分也可以。 |
| `clip_order` | 拖动卡片时由面板写入：按成片播放顺序排列的 `clip_id`，逗号分隔。留空就是按镜头序号；面板上的 `↺ 按镜头序号` 会清掉它。没点名的卡片按序号补在后面；卡片已被删除的 `clip_id` 只告警并跳过。 |
| `fps` | **基准帧率**：填写切片生成时的帧率（默认 24）。普通重编码直接按此值输出；恢复原速时自动除以慢放倍率，例如 `24fps + 0.5x → 48fps`、`24fps + 0.75x → 32fps`，避免恢复时丢帧。 |
| `output_name` | 可选。默认 `<项目>_<段数>shots_<时间戳>.mp4`。 |
| `playback_speed` | 切片当初的慢放倍率：`1.0x`（默认，不恢复）/ `0.75x` / `0.5x` / `custom`。Builder 自动按倒数恢复原速，例如 `0.5x → 2x`；输出帧率由基准帧率自动换算，音视频同步，音频 `atempo` 保音调。恢复必须重编码，`copy` 模式会明确报错。 |
| `playback_speed_custom` | 自定义切片慢放倍率，范围 `0.1–1.0`、步进 `0.1`，只在上一项为 `custom` 时启用。 |

**预检**——写任何东西之前，每一段都先用 ffprobe 实测：

- 分辨率 / 帧率 / 有无音轨 / 采样率不一致 → `auto` 改用重编码并说明是哪一项不一致；`copy` 直接报错并提示改模式。
- **未裁的接缝**：某段实测视频帧数**没有少于**它的 latent 帧数，说明 pinned 重叠帧还留在视频里，长片在这个接缝处会重复一小段画面。日志会点名这一段——把 Trim 之后的输出重新归档一次再拼。两种段永不告警：成片的第一段（按定义没有重叠），以及被 Picker 标记为「首段生成」的卡片（`parent_clip_id` 是 `[INITIAL]` / `[INITIAL_GENERATION]`）——首段本来就没有 pinned 重叠帧，视频帧数等于 latent 帧数就是它的正常形态，被拖到成片中间也不需要裁。
- 帧数一律以 ffprobe 实测为准，不读卡片里的 `meta.frames`（那个是 latent 口径，见下）。

> 卡片上显示的帧数是 **latent 口径**，因为接续消费的就是它。因此重叠帧**不在卡片上加备注**（避免被误读成「当前保存的视频里有重叠」），只在 Long Builder 的日志里说明。

输出在 `output/h3_long/<项目名>/`，**不进卡片库**，所以长片不会被误当成一个镜头挑出来。节点只有一个 `video` 输出：节点上直接内联预览，也可以直接接 `SaveVideo` / `VHS_VideoCombine`。逐段核对结果——实测帧数、时长、拼接方式和全部告警——写进 ComfyUI 日志，不再做成接口。

需要 `PATH` 里有 `ffmpeg`/`ffprobe`（Saver 生成预览卡时本来就要用）。

---

### 关键参数

| 参数 | 说明 |
|------|------|
| `context_length` | 只有 **5 / 22 / 39 / 56**（整数 latent step）。**22** = 接近无缝，默认推荐。56 = 最强锚定但吃掉交付片段 2.3 秒。 |
| `audio_context_length` | 独立音频尾部窗口，与钉住的画面窗口**尾对齐**，所以它只决定声音往前伸多远。**0** = 跟随画面窗口。默认 **18**。3 的倍数正好落在 40 Hz 音频网格上，不在网格上的值会被放宽到最近的整 step。已保存的工作流保持它原来存的值。 |
| `stock_format`（Load Latent） | 关（默认）= Motion Context 自己的格式，只有 Motion Context 节点的 `context_latent` 能吃。开 = 标准 H3 音画 latent，原生节点（Separate AV Latent、Latent Cut、采样器）能吃。 |
| `folder`（Load Latent） | `output`（默认）= ComfyUI output 目录下的文件或 chain 文件夹。`input` = input 目录下的单个文件，例如外部工具通过 HTTP 上传的那个。 |
| 分辨率 | `context_latent` **必须**与目标片段同分辨率，否则硬拒绝。 |

---

### 故障排查

| 症状 | 原因 / 解决 |
|------|------------|
| 运行时布局自检失败 | ComfyUI 太旧或 H3 锚定代码有改动。升级到 ≥ 0.34.0。 |
| Picker 报"No clips found" | 该 `project_name` 库里没有镜头。用 **Auto** 模式或确认 Saver 项目名一致。 |
| 音频接缝跳变 / "像但不是同一条" | 在 Decode 和 Trim 之间插 **Seam Probe**，读 `report` 输出的 `lag_ms`、`corr`、电平 step。 |
| 分辨率不匹配被拒绝 | 确保 `context_latent` 与目标片段同分辨率。 |
| Long Builder：长片在某个接缝处重复一小段画面 | 那一段是用**未裁**的输出归档的。把 Trim 之后的输出接回 Saver 的 `images_*`/`audio_*` 重新归档，再拼一次——日志会点名这一段。 |
| Long Builder：`copy` 模式报「各段参数不一致」 | 各段分辨率、帧率或音频不同。改用 **auto** 或 **reencode**；`copy` 只用于确认过参数一致的项目。 |
| Long Builder：某段没有归档视频 | 该卡片归档时 `save_video` 是关的。重新归档这一段；面板会把这种卡片置灰并跳过，日志里会点名。 |
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
├── VERSION.md               # 版本铁规：archive/<日期>-<commit> 快照 + 说明
├── requirements.txt
├── README.md
├── V3_MIGRATION.md          # V3 API 迁移说明
├── CACHE_AND_DELETION.md    # 索引缓存与卡片删除行为
├── examples/
│   └── H3_Ref2VA_Contextual_LongVideo_ClipStream.json   # 现成示例工作流
├── scripts/
│   └── sync_upstream.sh     # 辅助脚本：跟踪上游 Motion-Context 更新
├── tests/                   # unittest 套件：python -m unittest discover -s tests -t .；JS：node tests/js/
│   ├── _support.py          # 装载助手：ComfyUI 进 sys.path、clipbin 不依赖 comfy_api
│   ├── test_node_schema.py  # 锁定 14 个节点的 id、category、输入输出与选项
│   ├── test_frame_grid.py   # 帧 ↔ latent step 网格不变量
│   ├── test_latent_codec.py # latent 打包/解包与图像/音频标准化
│   ├── test_asset_paths.py  # 卡片路径安全与预览 URL
│   ├── test_clip_bin_store.py # 单卡/双卡往返、索引与删除
│   ├── test_long_builder.py # 镜头序号与手动顺序、拼接方式判定、接缝告警
│   ├── test_projects_api.py # 项目下拉框数据源、卡片视频参数缓存
│   ├── test_experiment_nodes.py # 帧数 cycle、Refine Blend、Join Match、Sigmas Tail、latent 路径
│   ├── js/long_builder_order.test.mjs # 卡片墙顺序（node tests/js/long_builder_order.test.mjs）
│   └── js/long_builder_fit.test.mjs   # 卡片大小与区域高度（node tests/js/long_builder_fit.test.mjs）
├── web/
│   ├── h3_motion_context.js       # Motion-Context 前端
│   ├── clip_bin_picker.js         # Clip Bin 画廊前端（卡片换行布局）
│   ├── dom_panel.js               # Picker 使用的 DOM 面板
│   ├── delete_button.js           # 卡片删除按钮与确认流程
│   ├── long_builder_panel.js      # Long Builder 面板：项目下拉框 + 可拖拽卡片墙
│   ├── long_builder_order.js      # 卡片墙顺序 = 成片顺序（纯函数，有测试）
│   ├── long_builder_fit.js        # 卡片档位与卡片墙高度（纯函数，有测试）
│   ├── clip_bin_picker.css        # 卡片画廊样式（两个面板共用）
│   └── long_builder.css           # Long Builder 面板外观
├── motion_context/
│   ├── __init__.py
│   ├── nodes.py                   # MotionContext / Trim / Save / Load / Chain
│   ├── layout_contract.py         # 布局自检
│   ├── csrf_guard.py
│   ├── probe_node.py              # SeamProbe
│   ├── refine_blend.py            # Refine Blend（上游算法原样，节点类是 V3）
│   ├── join_match.py              # Join Match（上游算法原样，节点类是 V3）
│   └── sigma_tools.py             # Sigmas Tail（上游算法原样，节点类是 V3）
└── clipbin/
    ├── __init__.py
    ├── nodes.py                   # Saver + Picker（3 模式）
    ├── dual_nodes.py              # Dual Saver + Dual Picker（一采+二采）
    ├── dual_manager.py            # 双变体归档与读取
    ├── _shared.py
    ├── clip_bin_manager.py
    ├── clip_bin_api.py
    ├── long_builder.py          # 长视频拼接：镜头顺序、ffprobe 预检、concat
    └── long_nodes.py            # Clip Long Builder 节点
```
