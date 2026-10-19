# Attribution

`ComfyUI-H3-ClipStream` is a single ComfyUI plugin that combines two
independent, open-source upstream projects. Both are bundled here with credit;
the combined work is distributed under the stricter of their licenses, **GPLv3**.

## 1. Motion-Context continuation engine
* Upstream: [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)
* Author: NikoDemon80
* License: **GPLv3** (see `LICENSE`)
* Upstream baseline used here: `518c083` ("Release 0.7.1"). The previous
  vendored baseline was `5335715` (0.6.2). `scripts/sync_upstream.sh` tracks the
  delta and classifies every upstream file as VERBATIM / PORTED / LOCAL_ONLY.
* Bundled here as the `motion_context/` sub-package, verbatim:
  `nodes.py`, `layout_contract.py`, `csrf_guard.py`, `probe_node.py`,
  and `web/h3_motion_context.js`.
* Ported from the same upstream on 2026-10-18 - the algorithm and the docstrings
  are verbatim; only the node class is rewritten for the ComfyUI V3 API and the
  node id carries a `ClipStream` suffix so an independently installed upstream
  plugin cannot clash: `refine_blend.py` (Refine Blend), `join_match.py`
  (Join Match), `sigma_tools.py` (Sigmas Tail).

## 2. Clip Bin visual media pool
* Upstream: [knoic/ComfyUI-MiniMaxH3-PrefixStream](https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream)
* Author: knoic
* License: **MIT**
* Bundled here as the `clipbin/` sub-package:
  `clip_bin_manager.py`, `clip_bin_api.py`, the Clip Bin Saver/Picker nodes
  (`clipbin/nodes.py`), shared helpers (`clipbin/_shared.py`), and
  `web/clip_bin_picker.js` + `web/clip_bin_picker.css`.

The Clip Bin was extracted from PrefixStream and **decoupled from its
continuation engine** (the PrefixStream "Native Masked AV / Safe Native"
nodes and their `cache_manager` / `native_masked_av` / `fused_attention` /
`rope_aligner` dependencies are intentionally *not* included). Continuation is
provided by Motion-Context instead.

The Dual Saver/Picker pair (`clipbin/dual_nodes.py`, `clipbin/dual_manager.py`)
is **original work of the ClipStream author** (AraneaQwQ), not taken from
either upstream.

---

MIT code may be incorporated into a GPLv3 work, so the whole plugin is
distributed as GPLv3. If you redistribute, keep this attribution and the
`LICENSE` file intact.
