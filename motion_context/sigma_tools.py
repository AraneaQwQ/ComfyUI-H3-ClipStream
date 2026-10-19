"""Reshape the last noise levels of the sampler's schedule.

EXPERIMENTAL

Every chained clip comes out a few percent crisper than the frames it was
pinned from, at every join, and on a face that reads as aging. FastH3's
schedule makes one large final step, from about 0.63 straight to zero,
and that last step settles nearly all of the fine detail. Starting it
from a slightly noisier point removes the extra crispness.

H3 Sigmas Tail reshapes only the last few noise levels before zero. The
first level, every level before the tail, and the final zero stay where
they are. Within the tail, each level is moved as a fraction of the
level just before the tail:

    new = anchor * (old / anchor) ** (1 / (1 + strength))

Positive strength lifts the tail toward the anchor, so less of the
schedule is spent at the lowest noise and the last step to zero is
larger. Negative strength does the opposite. Order is always kept, and
0.0 returns the schedule unchanged. The console shows the levels before
and after.

Tested: tail_steps 3, strength 0.5 stopped the per-join sharpening on
locked-off chains with a calm background, and kept faces from aging over
six clips. A busy, high-contrast background still crisps up slowly.

USING IT

    BasicScheduler -> H3 Sigmas Tail -> SamplerCustomAdvanced, sigmas
"""

from comfy_api.latest import io

import logging

_LOG = logging.getLogger("h3_motion_context")


def values_of(sigmas):
    return [float(v) for v in sigmas]


def same_kind(values, ref):
    """A schedule tensor like the one that came in."""
    if hasattr(ref, "new_tensor"):
        return ref.new_tensor(values)
    return values


def describe(values):
    return ", ".join("%.4f" % v for v in values)


# Adapted from NikoDemon80/ComfyUI-H3-Motion-Context v0.7.1 (GPLv3) on 2026-10-18.
# The upstream algorithm and its docstrings are kept verbatim; only the node
# class is rewritten for the ComfyUI V3 API, and the node id carries the
# ClipStream suffix so an independently installed Motion Context cannot clash.
class MiniMaxH3SigmasTailClipStream(io.ComfyNode):
    """Reshape only the lowest noise levels before the final zero."""
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id='MiniMaxH3SigmasTailClipStream',
            display_name='H3 Sigmas Tail (ClipStream)',
            category='sampling/custom_sampling/sigmas',
            description="Experimental. Reshapes only the last few noise levels before zero; the start, the levels above the tail and the final zero stay put.",
            inputs=[
                io.Sigmas.Input('sigmas', tooltip="The finished schedule from BasicScheduler, before any other sigma node touches it."),
                io.Int.Input('tail_steps', default=3, min=1, max=20, step=1, tooltip='How many of the lowest levels before zero to reshape. Everything above them is kept.'),
                io.Float.Input('strength', default=0.5, min=-0.9, max=3.0, step=0.05, round=False, tooltip='Above 0 lifts the tail, spending less time at the lowest noise, which is expected to add less fine detail. Below 0 does the opposite. 0 leaves the schedule unchanged.'),
            ],
            outputs=[
                io.Sigmas.Output(display_name='sigmas'),
            ],
        )

    @classmethod
    def execute(cls, sigmas, tail_steps, strength):
        v = values_of(sigmas)
        if abs(strength) < 1e-9:
            return io.NodeOutput(sigmas)
        # The levels to reshape: the last tail_steps above zero. The final
        # level is normally exactly 0 and is never touched.
        end = len(v) - 1 if v and v[-1] == 0.0 else len(v)
        start = max(1, end - int(tail_steps))
        if start >= end:
            _LOG.warning("h3_motion_context: sigmas tail: schedule too short "
                         "to reshape, passing it through")
            return io.NodeOutput(sigmas)
        anchor = v[start - 1]
        if anchor <= 0:
            return io.NodeOutput(sigmas)
        p = 1.0 / (1.0 + float(strength))
        out = list(v)
        for i in range(start, end):
            r = max(v[i], 0.0) / anchor
            out[i] = anchor * (r ** p)
        # keep strictly decreasing, in case of a flat stretch
        for i in range(start, end):
            if out[i] >= out[i - 1]:
                out[i] = out[i - 1] * 0.999
        _LOG.info("h3_motion_context: sigmas tail: reshaped the last %d "
                  "levels before zero at strength %.2f: %s -> %s",
                  end - start, strength, describe(v[start:end]),
                  describe(out[start:end]))
        return io.NodeOutput(same_kind(out, sigmas))

NODE_LIST = [MiniMaxH3SigmasTailClipStream]
NODE_CLASS_MAPPINGS = {
    "MiniMaxH3SigmasTailClipStream": MiniMaxH3SigmasTailClipStream,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3SigmasTailClipStream": "H3 Sigmas Tail (ClipStream)",
}
