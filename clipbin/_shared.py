"""Shared helpers for the Clip Bin subsystem.

Pure functions extracted from the original PrefixStream engine so the Clip
Bin media pool can be reused without dragging in its (unused) continuation
engine. No ComfyUI imports are required at module load time, which keeps
standalone testing possible.
"""

from typing import Any, Dict, Optional, Tuple

import torch

# MiniMax H3 VAE temporal grid: each latent step spans this many pixel frames.
FRAME_PER_TOKEN = (1, 4, 4, 4, 4)


def pixel_frames_to_latent_steps(pixel_frames: int) -> int:
    """Converts pixel frames to the minimum MiniMax H3 latent steps covering them."""
    if pixel_frames <= 0:
        return 0
    k, covered = 0, 0
    while covered < pixel_frames:
        covered += FRAME_PER_TOKEN[k % 5]
        k += 1
    return max(1, k)


def latent_steps_to_pixel_frames(latent_steps: int) -> int:
    """Calculates exact pixel frames spanned by MiniMax H3 latent steps."""
    if latent_steps <= 0:
        return 0
    return sum(FRAME_PER_TOKEN[k % 5] for k in range(latent_steps))


def _unpack_latent(latent_dict: Optional[Dict[str, Any]]) -> Tuple[Optional[torch.Tensor], Optional[torch.Tensor]]:
    """Unpacks video and audio tensors from an H3 latent dict, handling NestedTensor."""
    if latent_dict is None:
        return None, None
    samples = latent_dict.get("samples")
    if samples is None:
        return None, None
    if hasattr(samples, "unbind"):
        parts = list(samples.unbind())
        v = parts[0]
        a = parts[1] if len(parts) > 1 else None
    elif hasattr(samples, "tensors"):
        parts = samples.tensors
        v = parts[0]
        a = parts[1] if len(parts) > 1 else None
    elif isinstance(samples, (tuple, list)):
        v = samples[0]
        a = samples[1] if len(samples) > 1 else None
    elif isinstance(samples, torch.Tensor):
        v = samples
        a = None
    else:
        return None, None
    if v is not None and v.ndim == 4:
        v = v.unsqueeze(0)
    if a is not None and a.ndim == 3:
        a = a.unsqueeze(0)
    return v, a


def pack_av_latent(
    video: torch.Tensor,
    audio: Optional[torch.Tensor] = None,
    original_dict: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Packs video and audio tensors back into an H3 latent dict matching ComfyUI conventions."""
    out = dict(original_dict) if original_dict is not None else {}
    if audio is None:
        out["samples"] = video
        return out

    try:
        import comfy.nested_tensor
        out["samples"] = comfy.nested_tensor.NestedTensor([video, audio])
    except (ImportError, AttributeError):
        out["samples"] = (video, audio)
    return out


def _pack_nested_streams(video: torch.Tensor, audio: torch.Tensor):
    """Pack two H3 streams without importing ComfyUI during standalone tests."""
    try:
        import comfy.nested_tensor
        return comfy.nested_tensor.NestedTensor((video, audio))
    except (ImportError, AttributeError):
        return (video, audio)


def _standardize_image_tensor(images: Optional[torch.Tensor]) -> Optional[torch.Tensor]:
    """Standardizes video image tensor to canonical ComfyUI 4D shape: [F, H, W, 3/4].

    Gracefully handles:
    - 5D tensors: [1, F, H, W, C], [B, C, F, H, W], [1, C, F, H, W]
    - 3D tensors: [H, W, C] -> [1, H, W, C]
    - Channel-first vs channel-last conventions.
    """
    if images is None or not isinstance(images, torch.Tensor):
        return images

    t = images
    if t.ndim == 5:
        # Case 1: [1, F, H, W, C] where last dim is color channels (1, 3, 4)
        if t.shape[0] == 1 and t.shape[-1] in (1, 3, 4):
            t = t.squeeze(0)
        # Case 2: [1, C, F, H, W] where channel dim is at index 1
        elif t.shape[0] == 1 and t.shape[1] in (1, 3, 4):
            t = t.squeeze(0).permute(1, 2, 3, 0)
        # Case 3: [B, C, F, H, W] where B > 1
        elif t.shape[1] in (1, 3, 4):
            t = t.permute(0, 2, 3, 4, 1).flatten(0, 1)
        else:
            t = t.flatten(0, 1)
    elif t.ndim == 3:
        t = t.unsqueeze(0)

    return t


def _standardize_audio_dict(audio: Any, default_sr: int = 32000) -> Optional[Dict[str, Any]]:
    """Safely normalizes AUDIO input to standard ComfyUI dict {'waveform': Tensor, 'sample_rate': int}.

    Prevents crash when upstream node outputs bare Tensor or tuple/list instead of dictionary.
    """
    if audio is None:
        return None
    if isinstance(audio, dict) and "waveform" in audio:
        return audio
    if isinstance(audio, torch.Tensor):
        t = audio
        if t.ndim == 1:
            t = t.unsqueeze(0).unsqueeze(0)
        elif t.ndim == 2:
            t = t.unsqueeze(0)
        return {"waveform": t, "sample_rate": default_sr}
    if isinstance(audio, (list, tuple)) and len(audio) > 0:
        return _standardize_audio_dict(audio[0], default_sr=default_sr)
    return None
