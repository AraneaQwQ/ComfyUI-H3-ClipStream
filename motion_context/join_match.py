"""Remove the step at the join from a freshly sampled clip.

EXPERIMENTAL

WHAT IT CORRECTS

When a clip continues from a pin, the new frames do not start exactly
where the previous clip ended. Measured in the latent, on a locked-off
shot, the first new frames sit about 2.8 times further from the previous
clip's last frames than the picture normally moves over the same stretch
of time. That step repeats at every join and builds up, which is the
slow darkening and graying people see on long static chains.

The step comes mostly from channels the model sets on its own in the new
frames, so nothing done to the pin before sampling can reach it. This
node works on the result instead: after the sampler, it measures the
step for this join and moves the whole new clip back by that much, so it
starts where the previous clip ended. The next clip then chains from the
corrected one, so steps can't pile up.

HOW

H3 packs frames into latent steps in a cycle of five, and each position
in the cycle has its own character, so the step is measured like with
like: the previous clip's last latent step against the first new step in
this clip at the same cycle position. The difference per channel is the
step. The whole clip, pinned rows included, is shifted by the opposite,
times strength. With match_spread on, each channel's spread (how far it
swings around its average, which is where contrast and fine texture
live) is measured the same way and the clip is scaled so it matches
too, never by more than 10 percent. With match_detail on, each frame
is split into its smooth part and its fine part (what a 3x3 blur takes
away, where grain, skin texture and wrinkles live), and only the fine
part is scaled to match, also capped at 10 percent. That is done first,
since it moves the averages and spread slightly. Shifting the pinned
rows too keeps the clip continuous inside itself; they are trimmed from
what you see anyway.

The same comparison is made inside this clip, between that step and the
same cycle position five steps on, which is how much the picture
normally moves over a similar stretch. If the join moves no more than
min_excess times that, the join is already seamless or the scene is
moving too much to tell a step from motion, and that part is left alone.
Averages and spread are judged separately, each with its own guard:
min_excess for the averages and min_excess_spread for the spread, which
changes less from step to step and so needs a lower bar.

Audio is untouched. Strength 0 is a byte-identical no-op.

AUTO TUNING

The right guards depend on the shot. A locked-off shot can take 1.0 on
spread and detail, so they are corrected at every join. Anything that
moves wants 1.5 on all three. With tuning on auto (the default), the
node reads the shot from this clip's own new frames and picks for you,
so nobody has to know which kind of shot they made:

    how much each latent step changes against the same cycle position
    five steps later, as a share of how much that step varies across
    the frame. A still camera on a still scene barely changes; a moving
    camera or a busy scene changes a lot.

At or under STILL_MAX it is read as locked-off, above it as moving. The
log names the reading and the number on every clip. STILL_MAX was set
from three five-clip test chains of the same subject: a locked-off shot
of someone playing guitar read 0.37 to 0.40, a tracking shot walking
toward the camera 0.58 to 0.63, and a slow orbit around the seated
player 0.82 to 0.87. A person moving on a still camera stays well under
it; any camera move tested so far lands well over it.

On manual, the three min_excess widgets are used as set, exactly as
before. On auto they are ignored. The match_spread and match_detail
switches and strength are honored either way.

LIMITS

Made for shots where the camera and the scene hold still. On a shot that
moves, the change inside each clip is mostly new scenery and the model's
own drift, the guards see that, and the clip is mostly left alone, which
measured better than every attempt to correct moving shots anyway. Keep
the guards at 1.5 for anything that moves.

Only the step at the join is removed. Anything that drifts inside a clip
still drifts. On moving shots, real motion over the measured stretch
looks like a step; min_excess is the guard against correcting it.

USING IT

    sampler -> H3 Join Match -> Save Latent and VAE Decode
    the context latent loaded for this clip -> H3 Join Match, context_latent
    Motion Context trim_frames -> H3 Join Match, context_length

context_length MUST match the Motion Context node. Driving it from
Motion Context's trim_frames output keeps the two from drifting apart:
that output is the pinned length on a chained clip and 0 on the first,
and 0 passes the clip through. With no context latent wired, as on the
first clip of a chain, it also passes through.
"""

from comfy_api.latest import io

import logging

_LOG = logging.getLogger("h3_motion_context")

FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
GAIN_MIN, GAIN_MAX = 0.9, 1.1   # spread is never scaled more than 10%
DETAIL_MIN, DETAIL_MAX = 0.9, 1.1   # nor is fine detail

# Auto tuning. STILL_MAX sits in the gap between locked-off (0.37 to
# 0.40) and every camera move tested (0.58 and up). See AUTO TUNING above.
STILL_MAX = 0.48
AUTO_STILL = {"min_excess": 1.5, "min_excess_spread": 1.0,
              "min_excess_detail": 1.0}
AUTO_MOVING = {"min_excess": 1.5, "min_excess_spread": 1.5,
               "min_excess_detail": 1.5}


def pixel_frames(t):
    return sum(FRAME_PER_TOKEN[k % 5] for k in range(int(t)))


def steps_for_frames(frames):
    t = 0
    while pixel_frames(t) < frames:
        t += 1
        if t > 4096:
            return None
    return t if pixel_frames(t) == frames else None


def repack(samples, video, sound):
    """Hand back the same kind of container that came in."""
    if isinstance(samples, (list, tuple)):
        return [video, sound]
    try:
        import comfy.nested_tensor
        return comfy.nested_tensor.NestedTensor((video, sound))
    except ImportError:
        return [video, sound]


def streams_of(latent):
    """The video and audio halves of an H3 AV latent."""
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError("h3_motion_context: expected a latent, got %r"
                         % type(latent))
    samples = latent["samples"]
    if hasattr(samples, "unbind"):
        parts = list(samples.unbind())
    elif isinstance(samples, (tuple, list)):
        parts = list(samples)
    else:
        raise ValueError(
            "h3_motion_context: expected a MiniMax H3 AV latent (a nested "
            "video/audio pair), got %r" % type(samples))
    if len(parts) < 2:
        raise ValueError("h3_motion_context: AV latent needs a video and an "
                         "audio stream, found %d" % len(parts))
    return parts[0], parts[1]


def as5(video):
    return video.unsqueeze(0) if video.ndim == 4 else video


def step_means(video5, t):
    """Per channel average of one latent step, as a [C] tensor."""
    return video5[0, :, t].mean(dim=(-2, -1))


def blur(video5):
    """3x3 box blur over each frame, edges repeated. The smooth part."""
    import torch.nn.functional as F
    p = F.pad(video5, (1, 1, 1, 1, 0, 0), mode="replicate")
    h, w = video5.shape[-2], video5.shape[-1]
    out = 0
    for i in range(3):
        for j in range(3):
            out = out + p[..., i:i + h, j:j + w]
    return out / 9.0


def step_detail(fine5, t):
    """Per channel strength (rms) of the fine part of one latent step."""
    f = fine5[0, :, t]
    return (f * f).mean(dim=(-2, -1)).sqrt()


def step_spreads(video5, t):
    """Per channel spread (standard deviation) of one latent step, [C]."""
    return video5[0, :, t].std(dim=(-2, -1))


def rms(v):
    return float((v * v).mean().sqrt())


def shot_motion(video5, start):
    """How much the shot moves, from this clip's own new frames.

    Each latent step from `start` on is compared with the step five
    later, the same position in the cycle, so like is compared with
    like. The change is taken as a share of how much the step varies
    across the frame, which keeps the number independent of how bright
    or busy the scene is. Averaged over every pair. None when the clip
    is too short to have a pair.
    """
    vals = []
    for t in range(int(start), int(video5.shape[2]) - 5):
        x = video5[0, :, t]
        y = video5[0, :, t + 5]
        centred = x - x.mean(dim=(-2, -1), keepdim=True)
        vals.append(rms(y - x) / max(rms(centred), 1e-9))
    if not vals:
        return None
    return sum(vals) / len(vals)


def measure_diff(feat, a, b, ta, tb):
    """The join as a difference per channel, and normal change to judge it:
    clip A's last step against this clip's first new step at the same cycle
    position, and that step against the same position five steps on."""
    step = feat(b, tb) - feat(a, ta)
    normal = feat(b, tb + 5) - feat(b, tb)
    return step, normal


def measure_ratio(feat, a, b, ta, tb):
    """The join as a per channel ratio: the gain that would bring this clip
    back to clip A, and the normal ratio to judge it."""
    ratio = feat(a, ta) / feat(b, tb).clamp(min=1e-6)
    normal = feat(b, tb + 5) / feat(b, tb).clamp(min=1e-6)
    return ratio, normal


# Adapted from NikoDemon80/ComfyUI-H3-Motion-Context v0.7.1 (GPLv3) on 2026-10-18.
# The upstream algorithm and its docstrings are kept verbatim; only the node
# class is rewritten for the ComfyUI V3 API, and the node id carries the
# ClipStream suffix so an independently installed Motion Context cannot clash.
class MiniMaxH3JoinMatchClipStream(io.ComfyNode):
    """Move a new clip so it starts where the previous clip ended."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id='MiniMaxH3JoinMatchClipStream',
            display_name='H3 Join Match (ClipStream)',
            category='latent/minimax',
            description="Experimental. After sampling, measures the step between the previous clip's last frames and this clip's first new frames, and moves this clip so it starts where the last one ended.",
            inputs=[
                io.Latent.Input('samples', tooltip='The clip the sampler just made.'),
                io.Float.Input('strength', default=1.0, min=0.0, max=1.5, step=0.05, round=False, tooltip='How much of the measured step to remove. 1.0 removes all of it, 0.0 turns it off.'),
                io.Int.Input('context_length', default=22, min=0, max=4096, step=1, tooltip="Frames pinned by Motion Context. Wire Motion Context's trim_frames here so the two always agree. 0 passes the clip through. Has to be a whole number of latent steps (5, 22, 39, 56)."),
                io.Float.Input('min_excess', default=1.5, min=1.0, max=5.0, step=0.1, round=False, tooltip='Manual tuning only. Averages: only correct when the join moves more than this many times what the picture normally moves over the same stretch inside the clip. Guards against treating motion as a step.'),
                io.Boolean.Input('match_spread', default=True, tooltip='Also match how far each channel swings around its average, which is where contrast and fine texture live. Off matches the averages only.'),
                io.Float.Input('min_excess_spread', default=1.5, min=1.0, max=5.0, step=0.1, round=False, tooltip='Manual tuning only. Spread: only correct when it changes more than this many times its normal change inside the clip. 1.5 is the safe default for any shot. On a locked-off shot, 1.0 lets it correct at every join. The correction is capped at 10% either way.'),
                io.Boolean.Input('match_detail', default=True, tooltip='Also match the fine, pixel-to-pixel part of each channel, where grain, skin texture and wrinkles live. It builds up at every join even when the averages and spread hold.'),
                io.Float.Input('min_excess_detail', default=1.5, min=1.0, max=5.0, step=0.1, round=False, tooltip="Manual tuning only. Fine detail: only correct when it changes more than this many times its normal change inside the clip. 1.5 is the safe default; 1.0 suits a locked-off shot. Capped at 10% either way."),
                io.Combo.Input('tuning', options=['auto', 'manual'], default='auto', tooltip='Auto reads the shot from this clip (still camera or moving) and sets the three min_excess guards itself. Manual uses them as set.'),
                io.Latent.Input('context_latent', optional=True, tooltip='The previous clip, the same latent loaded for Motion Context. Leave it unwired on the first clip.'),
            ],
            outputs=[
                io.Latent.Output(display_name='samples'),
            ],
        )

    @classmethod
    def execute(cls, samples, strength, context_length, min_excess,
              match_spread=True, min_excess_spread=1.5,
              match_detail=True, min_excess_detail=1.5,
              tuning="auto", context_latent=None):
        if context_latent is None or abs(strength) < 1e-9:
            if context_latent is None:
                _LOG.info("h3_motion_context: join match: no previous clip "
                          "wired, passing this one through unchanged")
            return io.NodeOutput(samples)

        # Saved graphs from the dropdown version store the value as text
        frames = int(str(context_length).strip())
        if frames <= 0:
            _LOG.info("h3_motion_context: join match: context_length is 0 "
                      "(first clip, nothing pinned), passing this one "
                      "through unchanged")
            return io.NodeOutput(samples)
        steps = steps_for_frames(frames)
        if steps is None:
            raise ValueError(
                "h3_motion_context: join match: %d frames is not a whole "
                "number of latent steps. Use the length Motion Context "
                "pins (5, 22, 39 or 56), ideally by wiring its trim_frames "
                "output here." % frames)
        if tuning not in ("auto", "manual"):
            raise ValueError(
                "h3_motion_context: join match: tuning is %r, expected "
                "auto or manual" % (tuning,))

        video, audio = streams_of(samples)
        prev, _ = streams_of(context_latent)
        raw_ndim = video.ndim
        b = as5(video)
        a = as5(prev).to(device=b.device, dtype=b.dtype)
        if a.shape[1] != b.shape[1] or a.shape[3:] != b.shape[3:]:
            raise ValueError(
                "h3_motion_context: join match: the previous clip is %s and "
                "this one is %s. They have to share channels and frame size "
                "to be compared." % (tuple(a.shape), tuple(b.shape)))

        # Like with like: the previous clip's last step against the first
        # new step here at the same position in the five-step cycle.
        ta = a.shape[2] - 1
        pos = ta % 5
        tb = steps
        while tb % 5 != pos:
            tb += 1
        if tb + 5 >= b.shape[2]:
            _LOG.warning("h3_motion_context: join match: this clip is too "
                         "short to measure the join, passing it through")
            return io.NodeOutput(samples)

        if tuning == "auto":
            # Read from the new frames only: the pinned rows are the
            # previous clip's motion, not this one's.
            motion = shot_motion(b, steps)
            still = motion is not None and motion <= STILL_MAX
            picks = AUTO_STILL if still else AUTO_MOVING
            min_excess = picks["min_excess"]
            min_excess_spread = picks["min_excess_spread"]
            min_excess_detail = picks["min_excess_detail"]
            _LOG.info("h3_motion_context: join match: auto, motion %.3f "
                      "(locked-off at or under %.2f), read as %s, guards "
                      "%.1f / %.1f / %.1f",
                      motion if motion is not None else float("nan"),
                      STILL_MAX, "locked-off" if still else "moving",
                      min_excess, min_excess_spread, min_excess_detail)

        s_ = float(strength)

        # Fine detail first: split each frame into its smooth part and what
        # a 3x3 blur takes away, compare the strength of that fine part like
        # with like, and scale only it. Done before the spread and averages
        # are measured, since it changes both a little.
        detail_note = "detail not matched"
        detail_done = False
        if match_detail:
            smooth_a, smooth_b = blur(a), blur(b)
            fine_a, fine_b = a - smooth_a, b - smooth_b

            def fine_feat(v, t):
                return step_detail(fine_a if v is a else fine_b, t)
            d_ratio, d_normal = measure_ratio(fine_feat, a, b, ta, tb)
            d_excess = rms(d_ratio - 1.0) / max(rms(d_normal - 1.0), 1e-9)
            summary = ("fine detail off by %.2f%% against %.2f%% inside the "
                       "clip (%.1fx)" % (100 * rms(d_ratio - 1.0),
                                         100 * rms(d_normal - 1.0), d_excess))
            if d_excess >= min_excess_detail:
                d_gain = (1.0 + s_ * (d_ratio - 1.0)).clamp(min=DETAIL_MIN,
                                                            max=DETAIL_MAX)
                b = smooth_b + fine_b * d_gain.view(1, -1, 1, 1, 1)
                detail_note = summary + ", matched"
                detail_done = True
            else:
                detail_note = summary + ", left alone"

        step, normal = measure_diff(step_means, a, b, ta, tb)
        m_b = step_means(b, tb)
        excess = rms(step) / max(rms(normal), 1e-9)
        fix_mean = excess >= min_excess

        # Spread, as a ratio: how much wider or narrower each channel swings
        # here than at the end of the previous clip. Compared, like the
        # averages, with how much it normally changes inside this clip.
        gain = None
        spread_note = "spread not matched"
        if match_spread:
            ratio, normal_ratio = measure_ratio(step_spreads, a, b, ta, tb)
            s_excess = rms(ratio - 1.0) / max(rms(normal_ratio - 1.0), 1e-9)
            if s_excess >= min_excess_spread:
                gain = (1.0 + s_ * (ratio - 1.0)).clamp(min=GAIN_MIN,
                                                        max=GAIN_MAX)
                spread_note = ("spread off by %.2f%% against %.2f%% inside "
                               "the clip (%.1fx), matched"
                               % (100 * rms(ratio - 1.0),
                                  100 * rms(normal_ratio - 1.0), s_excess))
            else:
                spread_note = ("spread off by %.2f%% against %.2f%% inside "
                               "the clip (%.1fx), left alone"
                               % (100 * rms(ratio - 1.0),
                                  100 * rms(normal_ratio - 1.0), s_excess))

        if not fix_mean and gain is None and not detail_done:
            _LOG.info("h3_motion_context: join match: the join moves %.4f "
                      "against %.4f inside the clip (%.1fx, under %.1fx), "
                      "%s and %s, so the clip is left alone", rms(step),
                      rms(normal), excess, min_excess, spread_note,
                      detail_note)
            return io.NodeOutput(samples)

        # Each channel is scaled about its own average at the measured step,
        # then moved, so the step ends up with clip A's average and spread.
        view = lambda v: v.view(1, -1, 1, 1, 1)
        target = m_b - s_ * step if fix_mean else m_b
        out = b
        if gain is not None:
            out = (out - view(m_b)) * view(gain) + view(m_b)
        out = out - view(m_b - target)

        top = sorted(range(step.shape[0]),
                     key=lambda c: -abs(float(step[c])))[:5]
        _LOG.info("h3_motion_context: join match: averages moved %.4f "
                  "against %.4f inside the clip (%.1fx, %s), %s, %s. Biggest "
                  "average steps: %s",
                  rms(step), rms(normal), excess,
                  "matched" if fix_mean else "left alone", spread_note,
                  detail_note,
                  ", ".join("ch %d %+.4f" % (c, float(step[c])) for c in top))

        if raw_ndim == 4:
            out = out.squeeze(0)
        result = dict(samples)
        result["samples"] = repack(samples["samples"], out, audio)
        return io.NodeOutput(result)

NODE_LIST = [MiniMaxH3JoinMatchClipStream]
NODE_CLASS_MAPPINGS = {
    "MiniMaxH3JoinMatchClipStream": MiniMaxH3JoinMatchClipStream,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3JoinMatchClipStream": "H3 Join Match (ClipStream)",
}
