"""Dual-variant Clip Bin nodes: Picker and Saver for 一采/二采 workflows.

These are NEW nodes that coexist with the existing MiniMaxClipBinPicker/Saver.
They manage clips containing two latent variants (一采 + 二采) in a single folder.

Usage:
  - DualSaver: receives latent from both 一采 and 二采 paths, saves to one card.
  - DualPicker: selects one card, outputs both latents for continuation.
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional

import torch

from ._shared import _unpack_latent, pack_av_latent, _standardize_image_tensor, _standardize_audio_dict
from .dual_manager import (
    save_dual_clip_asset,
    load_dual_clip_asset,
    create_dual_placeholder_card,
    list_projects,
    VARIANTS,
)
from .clip_bin_manager import (
    load_project_index,
    pil_to_tensor,
    create_placeholder_card,
)

logger = logging.getLogger("minimax_clip_bin_dual")


class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False
    def __eq__(self, __value: object) -> bool:
        return True


any_type = AnyType("*")


class MiniMaxClipBinDualSaverNode:
    """Saves dual-variant (一采 + 二采) latents into a single Clip Bin card.

    At least one variant must be provided. If only 一采 is connected,
    the card will be marked as '仅一采'. If both are connected, it shows
    '含一采+二采'.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent_一采": ("LATENT", {
                    "tooltip": "【一采 Latent】1次采样器输出的联合音画 Latent。首段可为空 (None)"
                }),
            },
            "optional": {
                "latent_二采": ("LATENT", {
                    "tooltip": "【二采 Latent】2次采样器 (upscale) 输出的联合音画 Latent。未跑二采时可不接"
                }),
                "images_一采": ("IMAGE", {
                    "tooltip": "【一采画面】一采路径解码后的帧序列 (来自 VAEDecode/Trim)"
                }),
                "images_二采": ("IMAGE", {
                    "tooltip": "【二采画面】二采路径解码后的帧序列 (来自 VAEDecode/Trim)"
                }),
                "audio_一采": ("AUDIO", {
                    "tooltip": "【一采音频】一采路径的音频流"
                }),
                "audio_二采": ("AUDIO", {
                    "tooltip": "【二采音频】二采路径的音频流"
                }),
                "project_name": ("STRING", {
                    "default": "Default_Project",
                    "tooltip": "【项目库名称】指定归档到哪个项目池"
                }),
                "shot_tag": ("STRING", {
                    "default": "Auto (自动编号)",
                    "tooltip": "【镜头标签】如 'Shot 1'、'男主回眸'。填 Auto 则自动递增"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "tooltip": "【本段提示词】正向提示词，存入 meta 供回顾"
                }),
                "parent_clip_id": ("STRING", {
                    "default": "",
                    "tooltip": "【父镜头ID】连接 DualPicker 输出的 clip_id，记录血缘"
                }),
                "video_file_一采": (any_type, {
                    "default": "",
                    "tooltip": "【一采视频文件】VHS_VideoCombine 的 Filenames 输出或手动路径"
                }),
                "video_file_二采": (any_type, {
                    "default": "",
                    "tooltip": "【二采视频文件】VHS_VideoCombine 的 Filenames 输出或手动路径"
                }),
                "save_video": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "【归档视频】是否将完整 MP4 存入卡片文件夹"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("clip_id", "preview_image", "project_name")
    OUTPUT_NODE = True
    FUNCTION = "save_clip"
    CATEGORY = "MiniMaxH3/ClipStream"

    def save_clip(
        self,
        latent_一采: Dict[str, Any],
        latent_二采: Optional[Dict[str, Any]] = None,
        images_一采: Optional[torch.Tensor] = None,
        images_二采: Optional[torch.Tensor] = None,
        audio_一采: Optional[Dict[str, Any]] = None,
        audio_二采: Optional[Dict[str, Any]] = None,
        project_name: str = "Default_Project",
        shot_tag: str = "Auto (自动编号)",
        prompt: str = "",
        parent_clip_id: str = "",
        video_file_一采: Any = "",
        video_file_二采: Any = "",
        save_video: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        meta_obj, clip_dir, preview_pil = save_dual_clip_asset(
            latent_a=latent_一采,
            latent_b=latent_二采,
            images_a=images_一采,
            images_b=images_二采,
            audio_a=audio_一采,
            audio_b=audio_二采,
            project_name=project_name,
            shot_tag=shot_tag,
            prompt=prompt,
            parent_clip_id=parent_clip_id,
            video_file_name_a=video_file_一采,
            video_file_name_b=video_file_二采,
            save_video=save_video,
        )

        preview_tensor = pil_to_tensor(preview_pil)

        try:
            import folder_paths
            base_dir = folder_paths.get_output_directory()
            subfolder = os.path.relpath(clip_dir, base_dir)
        except Exception:
            subfolder = ""

        ui_images = [{
            "filename": "preview.png",
            "subfolder": subfolder,
            "type": "output"
        }]

        variant_str = " + ".join(meta_obj.variant_labels)
        logger.info("[Dual Saver] Stored '%s' (%s) in '%s'", meta_obj.clip_id, variant_str, project_name)

        return {
            "ui": {"images": ui_images},
            "result": (meta_obj.clip_id, preview_tensor, project_name)
        }


class MiniMaxClipBinDualPickerNode:
    """Selects a dual-variant clip card and outputs both 一采 and 二采 latents.

    Modes:
      - Auto: empty bin → outputs empty latents (首段); non-empty → loads latest
      - Force Initial: always outputs empty latents (no continuation)
      - Strict Chaining: requires a clip, errors if bin is empty

    If the selected card only has 一采, the 二采 output will be empty (None).
    """

    @classmethod
    def INPUT_TYPES(cls):
        projects = list_projects()
        default_proj = projects[0] if projects else "Default_Project"
        return {
            "required": {
                "project_name": ("STRING", {
                    "default": default_proj,
                    "tooltip": "【项目库】要读取的 Clip Bin 项目文件夹名称"
                }),
                "mode": ([
                    "Auto (首段全新 / 后续自动接续)",
                    "Force Initial (强制首段，无上下文)",
                    "Strict Chaining (严格接续，空库报错)"
                ], {
                    "default": "Auto (首段全新 / 后续自动接续)",
                    "tooltip": "【运行模式】\n• Auto：空库自动首段；非空自动接续最新\n• Force Initial：强制首段\n• Strict：空库报错"
                }),
                "clip_selection": ("STRING", {
                    "default": "latest",
                    "tooltip": "【镜头定位】'latest' = 自动最新；或填 clip_id / shot 名称精确匹配"
                }),
            },
            "optional": {
                "custom_clip_path": ("STRING", {
                    "default": "",
                    "tooltip": "【自定义路径】直接指定磁盘上的卡片文件夹绝对路径"
                }),
            }
        }

    RETURN_TYPES = ("LATENT", "LATENT", "IMAGE", "IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("latent_一采", "latent_二采", "first_frame", "tail_frame", "clip_id", "project_name", "prompt")
    FUNCTION = "pick_clip"
    CATEGORY = "MiniMaxH3/ClipStream"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Force re-execution on every queued prompt: this node reads mutable disk state.
        # Without it, ComfyUI's RAM-pressure cache serves the stale output of a previous
        # run whenever the widget inputs are unchanged (e.g. Auto + 'latest'), which
        # silently breaks continuation. float('nan') never equals itself -> new key each run.
        return float("nan")

    def pick_clip(
        self,
        project_name: str = "Default_Project",
        mode: str = "Auto (首段全新 / 后续自动接续)",
        clip_selection: str = "latest",
        custom_clip_path: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        p_name = (project_name or "Default_Project").strip()
        custom_p = (custom_clip_path or "").strip().strip('"').strip("'")

        # --- Helper: find clips from index OR by scanning disk ---
        def _find_clips(proj: str) -> List[Dict[str, Any]]:
            """Returns list of clip dicts. Tries index first, falls back to disk scan."""
            # Try the project index
            try:
                idx = load_project_index(proj)
                clips = idx.get("clips", [])
                if clips:
                    logger.info("[Dual Picker] Found %d clip(s) in index for '%s'", len(clips), proj)
                    return clips
            except Exception as e:
                logger.warning("[Dual Picker] Index load failed for '%s': %s", proj, e)

            # Fallback: scan project directory for clip folders with latent files
            from .clip_bin_manager import get_project_dir
            try:
                proj_dir = get_project_dir(proj)
                scanned = []
                if os.path.isdir(proj_dir):
                    for entry in sorted(os.listdir(proj_dir), reverse=True):
                        entry_path = os.path.join(proj_dir, entry)
                        if not os.path.isdir(entry_path) or entry.startswith("."):
                            continue
                        # Check if this is a valid dual clip folder (has at least one variant latent)
                        if (os.path.isfile(os.path.join(entry_path, "latent_一采.safetensors")) or
                                os.path.isfile(os.path.join(entry_path, "latent_二采.safetensors")) or
                                os.path.isfile(os.path.join(entry_path, "latent.safetensors"))):
                            meta_path = os.path.join(entry_path, "meta.json")
                            meta = {"clip_id": entry, "shot_tag": entry}
                            if os.path.isfile(meta_path):
                                try:
                                    with open(meta_path, "r", encoding="utf-8") as f:
                                        meta = json.load(f)
                                except Exception:
                                    pass
                            scanned.append(meta)
                if scanned:
                    logger.info("[Dual Picker] Found %d clip(s) via disk scan for '%s'", len(scanned), proj)
                return scanned
            except Exception as e:
                logger.warning("[Dual Picker] Disk scan failed for '%s': %s", proj, e)
                return []

        # --- Initial / Force Initial mode ---
        is_initial = mode.startswith("Force Initial")
        if not is_initial and mode.startswith("Auto"):
            clips_check = _find_clips(p_name)
            if len(clips_check) == 0:
                is_initial = True

        if is_initial:
            logger.info("[Dual Picker] Initial generation for '%s' (no context).", p_name)
            card = create_placeholder_card("✨ 首段模式", f"Project: {p_name} | 无接续源，全新生成")
            placeholder = pil_to_tensor(card)
            return {
                "ui": {"images": []},
                "result": (None, None, placeholder, placeholder, "[INITIAL]", p_name, "")
            }

        # --- Strict mode with empty bin ---
        if mode.startswith("Strict"):
            if not _find_clips(p_name):
                raise ValueError(f"DualPicker: 项目 '{p_name}' 无卡片。请用 Auto 模式生成首段。")

        # --- Resolve target clip ---
        if custom_p and os.path.isdir(custom_p):
            target_clip_id = os.path.basename(custom_p)
            p_name = os.path.basename(os.path.dirname(custom_p)) or p_name
        else:
            clips = _find_clips(p_name)
            if not clips:
                raise ValueError(f"DualPicker: 项目 '{p_name}' 无卡片。")

            sel = (clip_selection or "latest").strip()
            if sel.lower() in ("latest", "", "0", "auto", "default"):
                target_clip_id = clips[0]["clip_id"]
            else:
                matched = [c for c in clips if sel in c.get("clip_id", "") or sel in c.get("shot_tag", "")]
                target_clip_id = matched[0]["clip_id"] if matched else sel
            logger.info("[Dual Picker] Resolved target: '%s' (from %d clips, sel='%s')", target_clip_id, len(clips), sel)

        # --- Load dual asset ---
        data = load_dual_clip_asset(p_name, target_clip_id)
        meta = data["meta"]
        variants = data["variants"]

        # Extract latents
        latent_a = variants.get("一采", {}).get("latent")
        latent_b = variants.get("二采", {}).get("latent")

        # Use first available variant's frames for display
        first_frame = None
        tail_frame = None
        for vname in ("一采", "二采"):
            v = variants.get(vname, {})
            if v.get("first_frame") is not None:
                first_frame = v["first_frame"]
                tail_frame = v.get("tail_frame")
                break

        if first_frame is None:
            card = create_placeholder_card(meta.get("shot_tag", "?"), f"{target_clip_id}")
            first_frame = pil_to_tensor(card)
            tail_frame = first_frame

        prompt_str = meta.get("prompt", "")
        variant_str = "+".join([v for v in ("一采", "二采") if variants.get(v, {}).get("has_latent", False)])
        logger.info("[Dual Picker] Loaded '%s' (%s) from '%s'", target_clip_id, variant_str, p_name)

        return {
            "ui": {"images": []},
            "result": (latent_a, latent_b, first_frame, tail_frame, target_clip_id, p_name, prompt_str)
        }


NODE_CLASS_MAPPINGS = {
    "MiniMaxClipBinDualSaver": MiniMaxClipBinDualSaverNode,
    "MiniMaxClipBinDualPicker": MiniMaxClipBinDualPickerNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxClipBinDualSaver": "MiniMax H3 Dual Clip Saver (一采+二采)",
    "MiniMaxClipBinDualPicker": "MiniMax H3 Dual Clip Picker (一采+二采)",
}
