"""Check that ComfyUI's H3 layout still means what this pack thinks it means.

Nothing here modifies ComfyUI. The pack used to wrap
`PackedLayout.__init__` because stock rejected any keyframe anchor other
than the first or last frame. ComfyUI 0.34.0 lifted that restriction, so the
node now just builds keyframe dicts and hands them over. No wrapper, no
ownership of a constructor, and no argument with other packs that patch
the same place.

What is left is a dependency on meaning rather than on structure. Stock
positions a keyframe at

    cond_t = cursor + FRAME_RESCALE * kf["resolved_frame_index"]

where `cursor` is the target timeline's origin, already advanced past any
reference blocks. Two properties of that line matter to this pack and
neither is guaranteed by anything upstream:

  fractional  the audio window has to END at the join, so its index is
              end_frame - rt / FRAME_RESCALE, which is not a whole number
  negative    that index is usually below zero, because the pinned audio
              is a tail that played before this clip starts

Stock's own Add Guide node validates `frame_idx` to a non-negative integer
before it ever reaches the layout, so upstream has no test covering either
property. An int cast or a bounds check added later would not fail loudly
on its own: it would quietly move the pinned audio and put the join in the
wrong place.

So this runs once, before the first render, and proves the arithmetic
still holds. If it does not, the node refuses and says what moved. Same
policy as the patch self-test it replaces, without touching anything.
"""

import logging

import comfy.ldm.minimax.model as mm

_LOG = logging.getLogger("h3_motion_context")

_checked = None  # None not yet run, True passed, str the failure


class _Stub:
    """Stands in for a latent. The layout reads only the shape."""

    def __init__(self, shape):
        self.shape = shape


def _origin(layout):
    """The coordinate the target clip starts at, read off the built layout.

    The target video rows are always the last segment and their first row
    sits exactly on the cursor, so this reads the origin rather than
    recomputing stock's reference arithmetic. Everything else here is
    expressed as a distance from it.
    """
    a, b, kind = layout.segments[-1]
    if kind != "video" or b <= a:
        raise RuntimeError(
            "expected the target video rows to be the last layout segment, "
            "found %r spanning %d rows" % (kind, b - a))
    return float(layout.position_ids[a, 0])


def _seg(layout, kind):
    return [(a, b) for a, b, k in layout.segments if k == kind]


def _check():
    text_len, latent_t, lh, lw, audio_t = 7, 7, 22, 38, 16
    fr = mm.FRAME_RESCALE

    if hasattr(mm.PackedLayout.__init__, "__wrapped__"):
        pass  # reported by ensure(); the checks below decide either way

    def build(keyframes=None, refs=None):
        return mm.PackedLayout(text_len, latent_t, lh, lw, audio_t,
                               keyframes=keyframes, refs=refs)

    video = _Stub((1, 24, 1, lh, lw))

    # 1. a whole-number anchor lands FRAME_RESCALE per pixel frame past the
    # target origin. This is the line the whole pack is built on.
    lay = build(keyframes=[{"resolved_frame_index": p, "latent": video}
                           for p in (0, 3)])
    o = _origin(lay)
    got = [float(lay.position_ids[a, 0]) - o for a, _ in _seg(lay, "cond")]
    want = [0.0, fr * 3]
    if len(got) != 2 or any(abs(g - w) > 1e-9 for g, w in zip(got, want)):
        raise RuntimeError(
            "keyframe anchors no longer sit at FRAME_RESCALE per pixel "
            "frame past the target origin: got %s, expected %s" % (got, want))

    # 2. a reference must not move an anchor relative to the target. Stock
    # advances its cursor past the references before placing anchors, so
    # the anchor-to-origin distance is unchanged.
    lay = build(keyframes=[{"resolved_frame_index": 3, "latent": video}],
                refs=[{"kind": "audio", "ref_audio_t": 8}])
    a, _ = _seg(lay, "cond")[0]
    gap = float(lay.position_ids[a, 0]) - _origin(lay)
    if abs(gap - fr * 3) > 1e-9:
        raise RuntimeError(
            "a reference moved the anchors relative to the target: anchor "
            "sits %.6f past the origin, expected %.6f. Stock no longer "
            "compensates keyframes for reference blocks." % (gap, fr * 3))

    # 3. the audio window: fractional AND negative index, window ending at
    # a chosen target frame. This is the property with no upstream test.
    # The numbers matter. An index is end_frame - rt / FRAME_RESCALE, and
    # the node snaps end_frame so that FRAME_RESCALE * end_frame is a whole
    # audio coordinate, which leaves the index whole whenever that
    # coordinate and rt differ by a multiple of 5. Picking such a pair here
    # would let an integer cast slip through the check, so this pair is
    # deliberately not one of them.
    rt, end_coord = 40, 8
    end_frame = end_coord / fr
    idx = end_frame - rt / fr
    if idx >= 0 or idx == int(idx):
        raise RuntimeError("the audio check is not exercising a fractional "
                           "negative index; its own numbers are wrong")
    lay = build(keyframes=[{"resolved_frame_index": idx,
                            "audio_latent": _Stub((1, 32, 2, rt))}])
    spans = _seg(lay, "cond_audio")
    if len(spans) != 1:
        raise RuntimeError(
            "a keyframe carrying an audio latent produced %d cond_audio "
            "segments, expected 1" % len(spans))
    a, b = spans[0]
    if b - a != 2 * rt:
        raise RuntimeError(
            "the pinned audio window has %d rows for %d latent steps, "
            "expected %d (stereo, channel-major)" % (b - a, rt, 2 * rt))
    o = _origin(lay)
    t = lay.position_ids[a:b, 0]
    start = float(t.min()) - o
    end = start + float(rt)
    if abs(end - fr * end_frame) > 1e-9:
        raise RuntimeError(
            "the pinned audio window ends %.6f past the target origin, "
            "expected %.6f. A fractional or negative resolved_frame_index "
            "is no longer taken literally, so pinned audio would land at "
            "the wrong instant." % (end, fr * end_frame))

    # 4. and it must reach BACKWARDS from there, not forwards. If upstream
    # ever flips the window's anchor end this stays silent otherwise.
    if start >= 0.0:
        raise RuntimeError(
            "the pinned audio window starts %.6f past the target origin; it "
            "should start before it and end at the join" % start)


def _wrapper_origin():
    """Who wrapped PackedLayout.__init__, if anyone. None if nobody has.

    This matters because a wrapper's signature is not ComfyUI's. Every
    known wrapper of this constructor is a copy of this pack's old layout
    patch, vendored into another pack or left behind in a second folder,
    and its signature carries `frame_count` on every ComfyUI version. Read
    naively that looks exactly like ComfyUI 0.32, which is a confusing
    thing to tell someone running 0.33.

    So a wrapper is reported rather than interpreted, and the behavioural
    checks below decide whether the layout still works. Usually it does:
    the old patch passes anything without this pack's markers straight
    through, and nothing built here carries them any more.
    """
    init = getattr(mm.PackedLayout, "__init__", None)
    if init is None:
        return None
    if getattr(init, "_h3_motion_context_layout_patch", False):
        return "an older copy of this pack's layout patch"
    if getattr(init, "__name__", "") == "_patched_init":
        return "a copy of this pack's layout patch (a fork, or an older version)"
    if hasattr(init, "__wrapped__"):
        return "another pack (%s)" % getattr(init, "__module__", "unknown")
    home = getattr(mm.PackedLayout, "__module__", None)
    where = getattr(init, "__module__", None)
    if home and where and where != home:
        return "another pack (%s)" % where
    return None


def ensure(context=""):
    """Run the checks once. Raises with a usable message if they fail."""
    global _checked
    if _checked is True:
        return
    if isinstance(_checked, str):
        raise RuntimeError(_checked)

    if not hasattr(mm, "PackedLayout") or not hasattr(mm, "FRAME_RESCALE"):
        _checked = ("h3_motion_context: ComfyUI's MiniMax H3 model module is "
                    "missing PackedLayout or FRAME_RESCALE. This pack cannot "
                    "run against it.")
        raise RuntimeError(_checked)

    import inspect
    try:
        params = inspect.signature(mm.PackedLayout.__init__).parameters
    except (TypeError, ValueError):
        params = {}
    wrapped = _wrapper_origin()
    if wrapped:
        _LOG.warning(
            "h3_motion_context: H3's layout constructor has been wrapped by "
            "%s. This pack does not patch it and does not need it patched. "
            "Checking whether anchors still land correctly; if they do, "
            "nothing needs doing, but keeping only one H3 chaining pack "
            "installed avoids surprises.", wrapped)
    elif "frame_count" in params:
        _checked = (
            "h3_motion_context: this ComfyUI still has the older H3 layout, "
            "which rejects keyframe anchors other than the first and last "
            "frame. This version of the pack no longer works around that. "
            "Update ComfyUI, or use pack version 0.3.1, which runs on both "
            "layouts. (Detected from PackedLayout.__init__ still taking "
            "frame_count, not from a version number.)")
        raise RuntimeError(_checked)

    try:
        _check()
    except Exception as exc:
        _checked = (
            "h3_motion_context: ComfyUI's H3 layout does not behave the way "
            "this pack needs%s. %s. Refusing to run rather than rendering a "
            "join at the wrong instant.%s"
            % (" (%s)" % context if context else "", exc,
               (" H3's layout constructor is wrapped by %s, which is the "
                "first thing to rule out: disable it and try again."
                % wrapped) if wrapped else
               " This is an upstream ComfyUI change; please open an issue "
               "with your ComfyUI version."))
        raise RuntimeError(_checked) from exc

    _checked = True
    _LOG.info("h3_motion_context: ComfyUI H3 layout checks passed, anchors "
              "and pinned audio will land where intended")


def is_checked():
    return _checked is True
