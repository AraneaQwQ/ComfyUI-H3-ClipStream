"""Engine for MiniMax H3 Clip Bin - Media Pool and Visual Asset Management.

Provides:
- Self-contained clip asset packaging (Latent, First/Tail keyframes, Preview composite, Metadata).
- Project indexing with fast in-memory caching and thread-safe atomic writes.
- Rich search, filtering (star ratings, tags, timestamps), and lineage tracking.
- Zero-VAE-cost image frame loading and placeholder generation.
"""

import os
import json
import time
import glob
import logging
import shutil
import subprocess
import wave
import tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import torch
try:
    import numpy as np
except ImportError:
    np = None
from PIL import Image, ImageDraw, ImageFont


try:
    from safetensors.torch import load_file as st_load, save_file as st_save
except ImportError:
    st_load = None
    st_save = None

logger = logging.getLogger("minimax_clip_bin")


@dataclass
class ClipMeta:
    clip_id: str
    project_name: str = "Default_Project"
    shot_tag: str = "Shot 1"
    prompt: str = ""
    created_at: str = ""
    rating: int = 3
    frames: int = 124
    duration_seconds: float = 5.16
    resolution: List[int] = field(default_factory=lambda: [1280, 720])
    fps: float = 24.0
    video_shape: List[int] = field(default_factory=lambda: [1, 16, 32, 88, 160])
    audio_shape: Optional[List[int]] = None
    parent_clip_id: Optional[str] = None
    associated_video_path: Optional[str] = None
    has_video: bool = False
    video_file: Optional[str] = None
    notes: Optional[str] = None


def get_base_bin_dir() -> str:
    """Returns the base storage directory for all MiniMax Clip Bins."""
    try:
        import folder_paths
        base_dir = folder_paths.get_output_directory()
    except Exception:
        base_dir = "output"
    bin_dir = os.path.join(base_dir, "minimax_h3_bins")
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir


def get_project_dir(project_name: str) -> str:
    """Returns and ensures the path for a given project bin."""
    safe_name = "".join(c for c in (project_name or "Default_Project") if c.isalnum() or c in ("_", "-", " ")).strip()
    if not safe_name:
        safe_name = "Default_Project"
    p_dir = os.path.join(get_base_bin_dir(), safe_name)
    os.makedirs(p_dir, exist_ok=True)
    return p_dir


def list_projects() -> List[str]:
    """Lists all available project bin names."""
    base_dir = get_base_bin_dir()
    if not os.path.exists(base_dir):
        return ["Default_Project"]
    projects = []
    for item in sorted(os.listdir(base_dir)):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path) and not item.startswith("."):
            projects.append(item)
    if not projects:
        projects = ["Default_Project"]
    return projects


def _get_index_path(project_name: str) -> str:
    return os.path.join(get_project_dir(project_name), ".bin_index.json")


def load_project_index(project_name: str) -> Dict[str, Any]:
    """Loads the project index, auto-rebuilding if missing or corrupted."""
    idx_path = _get_index_path(project_name)
    if os.path.isfile(idx_path):
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "clips" in data:
                    return data
        except Exception as e:
            logger.warning("[Clip Bin] Corrupted index for '%s', rebuilding: %s", project_name, e)

    # Rebuild from clip directories
    return rebuild_project_index(project_name)


def save_project_index(project_name: str, index_data: Dict[str, Any]) -> None:
    """Saves project index atomically to prevent corruption."""
    idx_path = _get_index_path(project_name)
    tmp_path = idx_path + f".tmp_{os.getpid()}_{int(time.time())}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)
        if os.path.exists(idx_path):
            try:
                os.replace(tmp_path, idx_path)
            except OSError:
                # Windows fallback
                os.remove(idx_path)
                os.rename(tmp_path, idx_path)
        else:
            os.rename(tmp_path, idx_path)
    except Exception as e:
        logger.error("[Clip Bin] Failed to save index for '%s': %s", project_name, e)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def rebuild_project_index(project_name: str) -> Dict[str, Any]:
    """Scans all subdirectories in a project directory and builds an updated index."""
    p_dir = get_project_dir(project_name)
    clips = []
    if os.path.exists(p_dir):
        for entry in os.listdir(p_dir):
            entry_path = os.path.join(p_dir, entry)
            if os.path.isdir(entry_path):
                meta_path = os.path.join(entry_path, "meta.json")
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        # Reject non-video extensions (e.g. video.png)
                        curr_v = str(meta.get("video_file", "")).lower()
                        if curr_v.endswith(NON_VIDEO_EXTENSIONS) or not curr_v.endswith(VIDEO_EXTENSIONS):
                            meta["has_video"] = False
                            meta["video_file"] = None

                        # Clean up bogus video.png if present
                        bogus_png = os.path.join(entry_path, "video.png")
                        if os.path.isfile(bogus_png):
                            try:
                                os.remove(bogus_png)
                            except Exception:
                                pass

                        # Check for existing video file
                        if not meta.get("has_video"):
                            for vid_candidate in ["video.mp4", "video.webm"]:
                                if os.path.isfile(os.path.join(entry_path, vid_candidate)):
                                    meta["has_video"] = True
                                    meta["video_file"] = vid_candidate
                                    break
                            if not meta.get("has_video"):
                                for f_name in os.listdir(entry_path):
                                    if f_name.lower().endswith(VIDEO_EXTENSIONS):
                                        meta["has_video"] = True
                                        meta["video_file"] = f_name
                                        break

                        # Auto-heal: if no video in clip dir, try to restore from associated_video_path
                        if not meta.get("has_video") and meta.get("associated_video_path"):
                            src_v = resolve_source_video_path(meta.get("associated_video_path"))
                            if src_v and os.path.isfile(src_v):
                                ext = os.path.splitext(src_v)[1].lower()
                                if ext in VIDEO_EXTENSIONS:
                                    dest_v = os.path.join(entry_path, f"video{ext}")
                                    try:
                                        shutil.copy2(src_v, dest_v)
                                        meta["has_video"] = True
                                        meta["video_file"] = f"video{ext}"
                                        meta["associated_video_path"] = os.path.basename(src_v)
                                        with open(meta_path, "w", encoding="utf-8") as mf:
                                            json.dump(meta, mf, indent=2, ensure_ascii=False)
                                    except Exception:
                                        pass

                        clips.append(meta)
                    except Exception:
                        pass
    # Sort descending by creation date and unique clip_id
    clips.sort(key=lambda c: (c.get("created_at", ""), c.get("clip_id", "")), reverse=True)
    index_data = {

        "project_name": project_name,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_clips": len(clips),
        "clips": clips
    }
    save_project_index(project_name, index_data)
    return index_data


def tensor_to_pil(tensor_img: torch.Tensor) -> Image.Image:
    """Converts a [H, W, C] or [1, H, W, C] float32 tensor (0.0~1.0) to PIL Image."""
    if tensor_img.ndim == 4:
        tensor_img = tensor_img[0]
    if tensor_img.ndim == 3 and tensor_img.shape[0] in (1, 3, 4) and tensor_img.shape[2] not in (1, 3, 4):
        tensor_img = tensor_img.permute(1, 2, 0)
    H, W = tensor_img.shape[0], tensor_img.shape[1]
    byte_tensor = tensor_img.detach().clamp(0, 1).mul(255).to(torch.uint8).contiguous().cpu()
    if np is not None:
        return Image.fromarray(byte_tensor.numpy())
    else:
        return Image.frombytes("RGB", (W, H), bytes(bytearray(byte_tensor.view(-1).tolist())))


def pil_to_tensor(pil_img: Image.Image) -> torch.Tensor:
    """Converts a PIL Image to [1, H, W, 3] float32 torch.Tensor in range 0.0~1.0."""
    rgb = pil_img.convert("RGB")
    raw_bytes = bytearray(rgb.tobytes())
    tensor = torch.frombuffer(raw_bytes, dtype=torch.uint8).clone().view(rgb.height, rgb.width, 3).to(torch.float32) / 255.0
    return tensor.unsqueeze(0)



def create_placeholder_card(title: str, subtitle: str, width: int = 640, height: int = 360) -> Image.Image:
    """Generates a clean visual card placeholder if no raw decoded images are provided."""
    img = Image.new("RGB", (width, height), color=(26, 28, 35))
    draw = ImageDraw.Draw(img)
    # Border
    draw.rectangle([4, 4, width - 5, height - 5], outline=(55, 65, 81), width=2)
    # Text
    draw.text((30, 40), "MiniMax H3 Clip Bin", fill=(147, 197, 253))
    draw.text((30, 80), title, fill=(243, 244, 246))
    draw.text((30, 130), subtitle, fill=(156, 163, 175))
    draw.text((30, height - 50), "Safe Native DiT Prefix State Preserved", fill=(75, 85, 99))
    return img


def create_side_by_side_preview(first_img: Image.Image, tail_img: Image.Image) -> Image.Image:
    """Combines first and tail keyframes into a stylish side-by-side composite preview."""
    target_h = 360
    # Resize keeping aspect ratio
    w1 = int(first_img.width * (target_h / first_img.height))
    w2 = int(tail_img.width * (target_h / tail_img.height))
    im1 = first_img.resize((w1, target_h), Image.Resampling.BILINEAR)
    im2 = tail_img.resize((w2, target_h), Image.Resampling.BILINEAR)

    composite = Image.new("RGB", (w1 + w2 + 8, target_h + 36), color=(20, 22, 28))
    composite.paste(im1, (0, 0))
    composite.paste(im2, (w1 + 8, 0))

    draw = ImageDraw.Draw(composite)
    # Separator line
    draw.line([(w1 + 4, 0), (w1 + 4, target_h)], fill=(40, 45, 55), width=2)
    # Bottom labels
    draw.text((12, target_h + 8), "Start / Anchor Frame", fill=(147, 197, 253))
    draw.text((w1 + 16, target_h + 8), "Next Handover Tail Frame", fill=(167, 243, 208))
    return composite


VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".flv", ".gif")
NON_VIDEO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".json", ".txt", ".safetensors")


def resolve_source_video_path(val: Any) -> Optional[str]:
    """Resolves an existing video file path from VHS format, direct path, or ComfyUI output directory."""
    if val is None:
        return None

    output_dir = "output"
    temp_dir = "temp"
    try:
        import folder_paths
        if hasattr(folder_paths, "get_output_directory"):
            output_dir = folder_paths.get_output_directory()
        if hasattr(folder_paths, "get_temp_directory"):
            temp_dir = folder_paths.get_temp_directory()
    except Exception:
        pass

    raw_candidates = []

    def _collect(v: Any, prefix: str = ""):
        if v is None:
            return
        if isinstance(v, (list, tuple)):
            # Check for VHS pair: [subfolder, [files...]]
            if len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], (list, tuple)):
                sub = v[0].strip()
                for item in v[1]:
                    _collect(item, prefix=sub)
            else:
                for item in v:
                    _collect(item, prefix=prefix)
        else:
            s = str(v).strip().strip('"').strip("'")
            if s and s.lower() not in ("true", "false", "none"):
                if prefix:
                    raw_candidates.append(os.path.join(prefix, s))
                raw_candidates.append(s)

    _collect(val)

    # Separate candidates: prioritized video files vs derived candidates from image stems
    video_candidates = []
    derived_candidates = []

    for c in raw_candidates:
        c_lower = c.lower()
        if c_lower.endswith(VIDEO_EXTENSIONS):
            video_candidates.append(c)
        elif c_lower.endswith(NON_VIDEO_EXTENSIONS):
            # VHS sometimes outputs companion image first: e.g. h3_00024.png -> search h3_00024.mp4 / h3_00024-audio.mp4
            stem, _ = os.path.splitext(c)
            for ext in [".mp4", "-audio.mp4", ".webm", ".mov"]:
                derived_candidates.append(stem + ext)
        else:
            for ext in [".mp4", "-audio.mp4", ".webm"]:
                derived_candidates.append(c + ext)

    search_list = video_candidates + derived_candidates

    for c in search_list:
        # 1. Direct path
        if os.path.isfile(c) and c.lower().endswith(VIDEO_EXTENSIONS):
            return os.path.abspath(c)
        # 2. Under ComfyUI output directory
        p = os.path.join(output_dir, c)
        if os.path.isfile(p) and p.lower().endswith(VIDEO_EXTENSIONS):
            return os.path.abspath(p)
        # 3. Under ComfyUI temp directory
        p = os.path.join(temp_dir, c)
        if os.path.isfile(p) and p.lower().endswith(VIDEO_EXTENSIONS):
            return os.path.abspath(p)
        # 4. Under common dirs
        for base in ["output", "temp", "."]:
            p = os.path.join(base, c)
            if os.path.isfile(p) and p.lower().endswith(VIDEO_EXTENSIONS):
                return os.path.abspath(p)

    return None


def encode_images_to_mp4(
    images: torch.Tensor,
    output_mp4_path: str,
    fps: float = 24.0,
    audio_dict: Optional[Dict[str, Any]] = None,
) -> bool:
    """Encodes a [N, H, W, 3] float32 image batch into MP4 with optional audio using ffmpeg."""
    if images is None or not isinstance(images, torch.Tensor) or images.ndim != 4 or len(images) == 0:
        return False

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.warning("[Clip Bin] ffmpeg executable not found in PATH; skipping video encoding.")
        return False

    N, H, W = images.shape[0], images.shape[1], images.shape[2]
    # ffmpeg requires even dimensions for H.264
    if W % 2 != 0 or H % 2 != 0:
        W = W - (W % 2)
        H = H - (H % 2)
        images = images[:, :H, :W, :]

    try:
        raw_bytes = bytes(images.detach().clamp(0, 1).mul(255).to(torch.uint8).contiguous().cpu().untyped_storage())
    except Exception as e:
        logger.warning("[Clip Bin] Failed to extract raw image bytes for video encoding: %s", e)
        return False

    temp_wav_path = None
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
    ]

    if audio_dict is not None and isinstance(audio_dict, dict) and "waveform" in audio_dict:
        try:
            wf = audio_dict["waveform"]
            sr = int(audio_dict.get("sample_rate", 32000))
            if isinstance(wf, torch.Tensor) and wf.ndim >= 2:
                if wf.ndim == 3:
                    wf = wf[0]
                channels = wf.shape[0]
                wf_pcm = wf.clamp(-1, 1).mul(32767).to(torch.int16).t().contiguous().cpu()
                audio_bytes = bytes(wf_pcm.untyped_storage())

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                    temp_wav_path = tmp_f.name
                with wave.open(temp_wav_path, "wb") as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sr)
                    wav_file.writeframes(audio_bytes)

                cmd.extend(["-i", temp_wav_path, "-c:a", "aac", "-b:a", "192k", "-shortest"])
        except Exception as e:
            logger.warning("[Clip Bin] Audio preparation failed for video encoding: %s", e)
            if temp_wav_path and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except Exception:
                    pass
            temp_wav_path = None

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_mp4_path
    ])

    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.communicate(input=raw_bytes)
        success = proc.returncode == 0 and os.path.isfile(output_mp4_path) and os.path.getsize(output_mp4_path) > 0
        if success:
            logger.info("[Clip Bin] Successfully encoded video asset to '%s' (%s frames, %.2fs)",
                        output_mp4_path, N, N / float(fps))
        else:
            logger.warning("[Clip Bin] ffmpeg video encoding returned code %s", proc.returncode)
        return success
    except Exception as e:
        logger.warning("[Clip Bin] Exception during ffmpeg encoding: %s", e)
        return False
    finally:
        if temp_wav_path and os.path.exists(temp_wav_path):
            try:
                os.remove(temp_wav_path)
            except Exception:
                pass


def save_clip_asset(
    video_tensor: torch.Tensor,
    audio_tensor: Optional[torch.Tensor],
    images: Optional[torch.Tensor],
    project_name: str = "Default_Project",
    shot_tag: str = "Shot 1",
    prompt: str = "",
    rating: int = 3,
    parent_clip_id: Optional[str] = None,
    associated_video_path: Optional[str] = None,
    raw_video_source: Any = None,
    audio_dict: Optional[Dict[str, Any]] = None,
    save_video: bool = True,
    fps: float = 24.0,
) -> Tuple[ClipMeta, str, Image.Image]:
    """Packages and persists a complete MiniMax Clip Bin asset.
    
    Returns:
        (ClipMeta, clip_dir_path, preview_pil_image)
    """
    now_dt = datetime.now()
    timestamp_str = now_dt.strftime("%Y%m%d_%H%M%S_%f")
    time_display = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    # Clean shot_tag for directory slug
    tag_slug = "".join(c for c in shot_tag if c.isalnum() or c in ("_", "-")).strip() or "Shot"
    clip_id = f"clip_{timestamp_str}_{tag_slug}"

    project_dir = get_project_dir(project_name)
    clip_dir = os.path.join(project_dir, clip_id)
    os.makedirs(clip_dir, exist_ok=True)

    # 1. Save unified AV Latent
    latent_file = os.path.join(clip_dir, "latent.safetensors")
    video_cpu = video_tensor.detach().cpu().contiguous()
    audio_cpu = audio_tensor.detach().cpu().contiguous() if audio_tensor is not None else None

    # Frame count calculation (MiniMax H3 VAE temporal grid: steps to frames)
    from ._shared import latent_steps_to_pixel_frames
    frame_count = latent_steps_to_pixel_frames(video_cpu.shape[2])
    duration = round(frame_count / float(fps), 2)

    tensors = {"video": video_cpu}
    if audio_cpu is not None:
        tensors["audio"] = audio_cpu

    meta_obj = ClipMeta(
        clip_id=clip_id,
        project_name=project_name,
        shot_tag=shot_tag,
        prompt=prompt,
        created_at=time_display,
        rating=max(1, min(5, int(rating))),
        frames=frame_count,
        duration_seconds=duration,
        resolution=[video_cpu.shape[4] * 8, video_cpu.shape[3] * 8],  # Approximate pixel WxH
        fps=fps,
        video_shape=list(video_cpu.shape),
        audio_shape=list(audio_cpu.shape) if audio_cpu is not None else None,
        parent_clip_id=parent_clip_id if parent_clip_id else None,
        associated_video_path=associated_video_path
    )

    if st_save is not None:
        st_save(
            tensors,
            latent_file,
            metadata={
                "clip_id": clip_id,
                "project_name": project_name,
                "shot_tag": shot_tag,
                "frame_count": str(frame_count),
                "created_at": time_display,
            }
        )
    else:
        torch.save(tensors, latent_file)

    # 2. Extract and save First Frame & Tail Frame
    first_path = os.path.join(clip_dir, "first_frame.png")
    tail_path = os.path.join(clip_dir, "tail_frame.png")
    preview_path = os.path.join(clip_dir, "preview.png")

    if images is not None and isinstance(images, torch.Tensor) and images.ndim == 4 and len(images) > 0:
        first_pil = tensor_to_pil(images[0])
        tail_pil = tensor_to_pil(images[-1])
        first_pil.save(first_path, "PNG")
        tail_pil.save(tail_path, "PNG")
        preview_pil = create_side_by_side_preview(first_pil, tail_pil)
        preview_pil.save(preview_path, "PNG")
    else:
        first_pil = create_placeholder_card(f"Start Frame: {shot_tag}", f"{frame_count} frames | {duration}s")
        tail_pil = create_placeholder_card(f"Tail Frame: {shot_tag}", f"Ready for Next Clip Handover")
        first_pil.save(first_path, "PNG")
        tail_pil.save(tail_path, "PNG")
        preview_pil = create_side_by_side_preview(first_pil, tail_pil)
        preview_pil.save(preview_path, "PNG")

    # 3. Video Asset Archiving
    video_saved = False
    saved_video_filename = None

    if save_video:
        # Check source video provided (e.g. from VHS_VideoCombine or path)
        video_src_input = raw_video_source if raw_video_source is not None and str(raw_video_source).strip() else associated_video_path
        src_video = resolve_source_video_path(video_src_input)
        if src_video and os.path.isfile(src_video):
            ext = os.path.splitext(src_video)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                dest_video = os.path.join(clip_dir, f"video{ext}")
                try:
                    shutil.copy2(src_video, dest_video)
                    video_saved = True
                    saved_video_filename = f"video{ext}"
                    meta_obj.associated_video_path = os.path.basename(src_video)
                    logger.info("[Clip Bin] Archived source video from '%s' into '%s'", src_video, dest_video)
                except Exception as e:
                    logger.warning("[Clip Bin] Failed to copy source video from '%s': %s", src_video, e)

        # If no source video, but images provided, auto-encode with ffmpeg
        if not video_saved and images is not None:
            dest_video = os.path.join(clip_dir, "video.mp4")
            if encode_images_to_mp4(images, dest_video, fps=fps, audio_dict=audio_dict):
                video_saved = True
                saved_video_filename = "video.mp4"

        # Remove any lingering invalid video.png from clip_dir if present
        bogus_png = os.path.join(clip_dir, "video.png")
        if os.path.isfile(bogus_png):
            try:
                os.remove(bogus_png)
            except Exception:
                pass

    meta_obj.has_video = video_saved
    meta_obj.video_file = saved_video_filename

    # 4. Save meta.json
    meta_json_path = os.path.join(clip_dir, "meta.json")
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(meta_obj), f, indent=2, ensure_ascii=False)

    # 4. Update project index
    idx = load_project_index(project_name)
    existing_clips = [c for c in idx.get("clips", []) if c.get("clip_id") != clip_id]
    existing_clips.insert(0, asdict(meta_obj))
    idx["clips"] = existing_clips
    idx["total_clips"] = len(existing_clips)
    idx["last_updated"] = time_display
    save_project_index(project_name, idx)

    logger.info("[Clip Bin] Successfully stored asset '%s' in project '%s' (⭐%s, %s frames)",
                clip_id, project_name, meta_obj.rating, frame_count)
    return meta_obj, clip_dir, preview_pil


def load_clip_asset(project_name: str, clip_id: str) -> Tuple[torch.Tensor, Optional[torch.Tensor], torch.Tensor, torch.Tensor, Dict[str, Any]]:
    """Loads a clip asset completely from disk.
    
    Returns:
        (video_tensor, audio_tensor, tail_frame_tensor, first_frame_tensor, meta_dict)
    """
    project_dir = get_project_dir(project_name)
    clip_dir = os.path.join(project_dir, clip_id)
    if not os.path.isdir(clip_dir):
        raise FileNotFoundError(f"[Clip Bin] Asset directory not found: '{clip_dir}'")

    latent_file = os.path.join(clip_dir, "latent.safetensors")
    if not os.path.isfile(latent_file):
        raise FileNotFoundError(f"[Clip Bin] Latent file not found: '{latent_file}'")

    if st_load is not None:
        tensors = st_load(latent_file, device="cpu")
    else:
        try:
            tensors = torch.load(latent_file, map_location="cpu")
        except RuntimeError as exc:
            if "safetensors is not installed" in str(exc):
                with open(latent_file, "rb") as f:
                    tensors = torch.load(f, map_location="cpu")
            else:
                raise


    if "video" not in tensors:
        raise ValueError(f"[Clip Bin] '{latent_file}' does not contain 'video' tensor.")

    video = tensors["video"]
    audio = tensors.get("audio", None)

    # Load images
    first_path = os.path.join(clip_dir, "first_frame.png")
    tail_path = os.path.join(clip_dir, "tail_frame.png")

    if os.path.isfile(tail_path):
        tail_pil = Image.open(tail_path)
    else:
        tail_pil = create_placeholder_card("Tail Frame", clip_id)
    tail_tensor = pil_to_tensor(tail_pil)

    if os.path.isfile(first_path):
        first_pil = Image.open(first_path)
    else:
        first_pil = create_placeholder_card("First Frame", clip_id)
    first_tensor = pil_to_tensor(first_pil)

    # Load meta
    meta_json_path = os.path.join(clip_dir, "meta.json")
    meta_dict = {}
    if os.path.isfile(meta_json_path):
        try:
            with open(meta_json_path, "r", encoding="utf-8") as f:
                meta_dict = json.load(f)
        except Exception:
            pass

    return video, audio, tail_tensor, first_tensor, meta_dict


def format_clip_label(meta: Dict[str, Any]) -> str:
    """Creates a rich, user-friendly label for ComfyUI combo dropdowns."""
    stars = "⭐" * meta.get("rating", 3)
    created = meta.get("created_at", "")[:16]  # "YYYY-MM-DD HH:MM"
    shot = meta.get("shot_tag", "Shot")
    frames = meta.get("frames", 124)
    duration = meta.get("duration_seconds", 5.2)
    clip_id = meta.get("clip_id", "")
    return f"[{stars}] {created} | {shot} ({frames}f, {duration}s) #{clip_id}"


def get_clips_for_selection(project_name: str, min_rating: int = 1) -> List[Tuple[str, str]]:
    """Returns a list of (display_label, clip_id) tuples matching criteria."""
    idx = load_project_index(project_name)
    clips = idx.get("clips", [])
    results = []
    for c in clips:
        if c.get("rating", 3) >= min_rating:
            results.append((format_clip_label(c), c.get("clip_id", "")))
    return results
