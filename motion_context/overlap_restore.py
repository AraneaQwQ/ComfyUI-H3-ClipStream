"""Restore the previous clip's original video tokens after final sampling."""

import logging

import torch
from comfy_api.latest import io

from .nodes import _steps_for_frames


_LOG = logging.getLogger("h3_motion_context")
WINDOWS = (5, 22, 39, 56)


def video_stream(latent, label):
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError(f"H3 Overlap Restore: {label} must be a LATENT.")
    samples = latent["samples"]
    if isinstance(samples, torch.Tensor):
        parts = [samples]
    elif isinstance(samples, (list, tuple)):
        parts = list(samples)
    elif getattr(samples, "is_nested", False) and hasattr(samples, "unbind"):
        parts = list(samples.unbind())
    else:
        raise ValueError(f"H3 Overlap Restore: unsupported {label} samples container.")
    if not parts or not isinstance(parts[0], torch.Tensor):
        raise ValueError(f"H3 Overlap Restore: {label} has no video tensor.")
    raw = parts[0]
    video = raw.unsqueeze(0) if raw.ndim == 4 else raw
    if video.ndim != 5 or video.shape[1] != 24:
        raise ValueError(
            f"H3 Overlap Restore: {label} must contain H3 video [B,24,T,H,W]; "
            f"got {tuple(raw.shape)}."
        )
    if not video.is_floating_point():
        raise ValueError(f"H3 Overlap Restore: {label} video must be floating point.")
    return video, raw.ndim, parts


def restore_overlap(samples, trim_frames, enabled=True, context_latent=None):
    """Copy only an aligned parent suffix; never mutate either input."""
    if not enabled or trim_frames == 0:
        return samples
    if trim_frames not in WINDOWS:
        raise ValueError(
            "H3 Overlap Restore: trim_frames must be 0, 5, 22, 39 or 56. "
            "Connect Motion Context.trim_frames; do not use audio context length."
        )
    if context_latent is None:
        raise ValueError(
            "H3 Overlap Restore: trim_frames is nonzero but context_latent is empty. "
            "Connect the previous clip's original pass-2 latent."
        )
    current, raw_ndim, parts = video_stream(samples, "samples")
    previous, _, _ = video_stream(context_latent, "context_latent")
    steps = _steps_for_frames(trim_frames)
    if previous.shape[2] < steps or current.shape[2] <= steps:
        raise ValueError(
            "H3 Overlap Restore: parent must cover the overlap and current clip "
            "must contain new content after it."
        )
    start = previous.shape[2] - steps
    if start % 5:
        raise ValueError(
            f"H3 Overlap Restore: parent tail starts at temporal cycle {start % 5}, "
            "expected 0. Refusing a shifted overlap."
        )
    if any(previous.shape[d] != current.shape[d] for d in (0, 1, 3, 4)):
        raise ValueError(
            "H3 Overlap Restore: batch, channels and spatial resolution must match. "
            "Use the previous pass-2 latent, not pass-1 or an upscaled substitute."
        )
    if previous.dtype != current.dtype:
        raise ValueError(
            f"H3 Overlap Restore: dtype mismatch ({previous.dtype}, {current.dtype}). "
            "Use matching latent precision; exact restoration does not cast tokens."
        )
    video = current.clone()
    video[:, :, :steps].copy_(previous[:, :, start:].to(device=current.device))
    if raw_ndim == 4:
        video = video.squeeze(0)
    # Keep the current audio and all other streams by reference, in their container.
    original_container = samples["samples"]
    if isinstance(original_container, torch.Tensor):
        packed = video
    else:
        parts[0] = video
        if isinstance(original_container, list):
            packed = parts
        elif isinstance(original_container, tuple):
            packed = tuple(parts)
        else:
            packed = type(original_container)(parts)
    result = dict(samples)
    result["samples"] = packed
    _LOG.info(
        "H3 Overlap Restore: restored %d video steps (%d frames) from parent "
        "tail; new video steps, current audio and latent metadata unchanged.",
        steps, trim_frames,
    )
    return result


class MiniMaxH3OverlapRestoreClipStream(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3OverlapRestoreClipStream",
            display_name="H3 Overlap Restore / 原始重叠恢复 (ClipStream)",
            category="latent/minimax",
            description=(
                "二采后恢复上一段原始视频重叠 token。接在最终采样器之后、"
                "视频解码和 latent 保存之前。只替换重叠区，不调色、不加噪、不修改音频。"
            ),
            inputs=[
                io.Latent.Input("samples", tooltip="当前段二采最终输出，尚未解码或裁切。"),
                io.Int.Input(
                    "trim_frames", default=0, min=0, max=56, force_input=True,
                    tooltip="连接本段 Motion Context 的 trim_frames；首段 0 自动透传。",
                ),
                io.Boolean.Input("enabled", default=True, tooltip="关闭后原样透传，便于对比。"),
                io.Latent.Input(
                    "context_latent", optional=True,
                    tooltip="上一段原始二采 latent，接 Dual Picker.latent_二采。"
                            "若使用上下文加噪，必须从加噪之前分支接入这里。",
                ),
            ],
            outputs=[io.Latent.Output(display_name="latent")],
        )

    @classmethod
    def execute(cls, samples, trim_frames, enabled=True, context_latent=None):
        return io.NodeOutput(restore_overlap(samples, trim_frames, enabled, context_latent))


NODE_LIST = [MiniMaxH3OverlapRestoreClipStream]
NODE_CLASS_MAPPINGS = {"MiniMaxH3OverlapRestoreClipStream": MiniMaxH3OverlapRestoreClipStream}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxH3OverlapRestoreClipStream": "H3 Overlap Restore / 原始重叠恢复 (ClipStream)",
}
