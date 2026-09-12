"""Clip Bin nodes: a visual, searchable media pool of MiniMax H3 clips.

These nodes reuse the original PrefixStream Clip Bin (Saver + Picker) but are
decoupled from its continuation engine. They archive each generated clip's
joint AV latent plus preview card, shot tag and lineage, and load a
chosen clip back out as an H3 AV latent that the Motion-Context engine can
consume as ``context_latent``.
"""

import os
import logging
from typing import Any, Dict, Optional

import torch

from ._shared import (
    _unpack_latent,
    pack_av_latent,
    latent_steps_to_pixel_frames,
    _standardize_image_tensor,
    _standardize_audio_dict,
)
from .clip_bin_manager import (
    save_clip_asset,
    load_clip_asset,
    load_project_index,
    list_projects,
    pil_to_tensor,
    create_placeholder_card,
)

logger = logging.getLogger("minimax_clip_bin")


class AnyType(str):
    """Wildcard type for ComfyUI input slots to accept multiple types (STRING, VHS_FILENAMES, etc.)."""
    def __ne__(self, __value: object) -> bool:
        return False

    def __eq__(self, __value: object) -> bool:
        return True


any_type = AnyType("*")


class MiniMaxClipBinSaverNode:
    """Saves a unified MiniMax H3 AV Latent into the Clip Bin media pool with keyframes, preview card, and rich metadata."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT", {"tooltip": "【核心音画潜空间】采样器输出的原生联合音画 Latent (支持 MiniMax H3 官方 NestedTensor，包含完整视频与音频潜空间)"}),
                "project_name": ("STRING", {
                    "default": "Default_Project",
                    "tooltip": "【项目/分镜箱名称】指定当前镜头归档的项目库（例如：科幻短片、广告场景1）。不同项目之间素材完全隔离，方便多故事独立管理"
                }),
                "shot_tag": ("STRING", {
                    "default": "Auto (自动编号)",
                    "tooltip": "【镜头标签/备注】镜头的编号或简要动作描述（如：'Shot 1'、'男主回眸'、'远景空镜'）。填 'Auto (自动编号)' 时系统将根据项目内已有镜头数量自动顺延递增为 Shot 1, Shot 2..."
                }),
            },
            "optional": {
                "images": ("IMAGE", {"tooltip": "【渲染像素画面】连接当前片段解码后的画面 (来自 VAEDecode 或 Trim)。连接后系统将自动截取真实的首帧与尾帧，生成超高清并排缩略图卡片！"}),
                "audio": ("AUDIO", {"tooltip": "【音频流】连接当前片段的音频 (来自 Trim 或 VAEDecodeAudio)。当自动编码保存 MP4 视频时，将作为音轨同步封装"}),
                "prompt": ("STRING", {"default": "", "tooltip": "【本段正向提示词】连接输入文本 (Input Text/Prompt)。自动入库保存到 meta.json，以便后续回顾镜头剧情与接续参考"}),
                "parent_clip_id": ("STRING", {"default": "", "tooltip": "【父镜头血缘ID】连接上一段 Clip Bin Picker 输出的 clip_id。用于在元数据中清晰记录多版本分支历史与承接血缘"}),
                "video_file_name": (any_type, {"default": "", "tooltip": "【关联合成视频名】连接当前片段合成保存节点 (VHS_VideoCombine) 的 Filenames 输出，或手动输入关联的 MP4 文件名，系统将自动将该视频归档到资产包中"}),
                "save_video": ("BOOLEAN", {"default": True, "tooltip": "【归档完整视频】是否在资产包内归档或编码生成完整 MP4 视频文件。开启后 Clip Bin Picker 画廊将支持悬停实时微动播放与声画视听弹窗！"}),
            }
        }

    RETURN_TYPES = ("STRING", "IMAGE", "STRING")
    RETURN_NAMES = ("clip_id", "preview_image", "bin_path")
    OUTPUT_NODE = True
    FUNCTION = "save_clip"
    CATEGORY = "MiniMaxH3/ClipStream"

    def save_clip(
        self,
        latent: Dict[str, Any],
        project_name: str = "Default_Project",
        shot_tag: str = "Auto (自动编号)",
        images: Optional[torch.Tensor] = None,
        audio: Optional[Dict[str, Any]] = None,
        prompt: str = "",
        parent_clip_id: str = "",
        video_file_name: Any = "",
        save_video: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        if latent is None:
            raise ValueError("MiniMaxClipBinSaver: 'latent' input is required.")

        video, audio_lat = _unpack_latent(latent)
        if video is None:
            raise ValueError("MiniMaxClipBinSaver: latent contains no video samples.")

        images = _standardize_image_tensor(images)
        audio = _standardize_audio_dict(audio)

        actual_shot = (shot_tag or "").strip()
        if actual_shot.startswith("Auto") or not actual_shot:
            idx = load_project_index(project_name)
            actual_shot = f"Shot {len(idx.get('clips', [])) + 1}"

        # Handle video_file_name if passed as list/tuple from VHS_VideoCombine Filenames
        resolved_video_name = ""
        def _extract_filename(val: Any) -> str:
            if isinstance(val, (list, tuple)):
                if not val:
                    return ""
                # Prioritize video extensions in list/tuple
                for item in val:
                    if isinstance(item, (list, tuple)):
                        extracted = _extract_filename(item)
                        if extracted and any(extracted.lower().endswith(e) for e in (".mp4", ".webm", ".mov", ".mkv")):
                            return extracted
                    elif isinstance(item, str) and any(item.lower().endswith(e) for e in (".mp4", ".webm", ".mov", ".mkv")):
                        return item.strip()
                return _extract_filename(val[-1])
            s = str(val).strip()
            return s if s.lower() not in ("true", "false", "none") else ""

        if video_file_name is not None:
            resolved_video_name = _extract_filename(video_file_name)
            # If it's a full path, keep basename for friendly display
            if resolved_video_name:
                resolved_video_name = os.path.basename(resolved_video_name)

        meta_obj, clip_dir, preview_pil = save_clip_asset(
            video_tensor=video,
            audio_tensor=audio_lat,
            images=images,
            project_name=project_name,
            shot_tag=actual_shot,
            prompt=prompt if isinstance(prompt, str) else str(prompt),
            parent_clip_id=parent_clip_id if isinstance(parent_clip_id, str) else str(parent_clip_id),
            associated_video_path=resolved_video_name,
            raw_video_source=video_file_name,
            audio_dict=audio,
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

        logger.info("[Clip Bin Saver] Stored clip '%s' in '%s' (%s frames | tag: %s | video: '%s')",
                    meta_obj.clip_id, project_name, meta_obj.frames, actual_shot, resolved_video_name)

        return {
            "ui": {"images": ui_images},
            "result": (meta_obj.clip_id, preview_tensor, clip_dir)
        }


class MiniMaxClipBinPickerNode:
    """Visually browses and loads clips from the Clip Bin, with a three-mode switch (Auto / Force Initial / Strict Chaining)."""

    @classmethod
    def INPUT_TYPES(cls):
        projects = list_projects()
        default_proj = projects[0] if projects else "Default_Project"
        return {
            "required": {
                "project_name": ("STRING", {
                    "default": default_proj,
                    "tooltip": "【选择项目库】要读取素材的项目文件夹名称（如 Default_Project）。可在 ComfyUI 运行控制台查看已存在的项目名称列表"
                }),
                "mode": ([
                    "Auto (首段全新 / 后续自动接续)",
                    "Force Initial (强制新建首段，无上下文)",
                    "Strict Chaining (必须接续指定或最新镜头)"
                ], {
                    "default": "Auto (首段全新 / 后续自动接续)",
                    "tooltip": "【运行工作模式】\n• Auto（强烈推荐）：若项目库为空自动作为首段全新生成；后续运行时全自动接续上一段，无需任何拔线或手动操作！\n• Force Initial：强制开辟首段，忽略库内所有历史素材。\n• Strict Chaining：严格接续模式，库内无镜头时直接报错提示"
                }),
                "clip_selection": ("STRING", {
                    "default": "latest",
                    "tooltip": "【镜头定位】\n• 填 'latest'（默认）：自动调取最新生成的镜头进行无缝接续\n• 填 clip_id（如 clip_20260908...）：精确跳转或回溯到指定的历史镜头开启新分支\n• 填 shot 名称：按镜头标签名称匹配"
                }),
            },
            "optional": {
                "custom_clip_path": ("STRING", {
                    "default": "",
                    "tooltip": "【自定义物理路径覆盖】可选高级选项。填入绝对路径可直接载入任意磁盘目录下的 Clip Bin 镜头文件夹"
                }),
            }
        }

    RETURN_TYPES = ("LATENT", "IMAGE", "IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("latent", "tail_frame", "first_frame", "prompt", "clip_id", "project_name")
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

        if custom_p and os.path.isdir(custom_p):
            target_clip_dir = custom_p
            p_name = os.path.basename(os.path.dirname(custom_p)) or p_name
            target_clip_id = os.path.basename(custom_p)
        else:
            idx = load_project_index(p_name)
            clips = idx.get("clips", [])

            # Initial (no-context) generation: Force Initial, or Auto with an empty bin.
            is_initial_mode = mode.startswith("Force Initial") or (mode.startswith("Auto") and len(clips) == 0)

            if is_initial_mode:
                logger.info("[Clip Bin Picker] Initial generation for project '%s' (mode: %s).", p_name, mode)
                card = create_placeholder_card("✨ Initial Clip Mode", f"Project: {p_name} | Ready for First Clip (No Context)")
                placeholder_tensor = pil_to_tensor(card)
                return {
                    "ui": {"images": []},
                    "result": (None, placeholder_tensor, placeholder_tensor, "", "[INITIAL_GENERATION]", p_name)
                }

            # Strict Chaining with an empty bin -> loud failure.
            if not clips:
                raise ValueError(f"MiniMaxClipBinPicker: No clips found in project '{p_name}'. "
                                 f"Switch mode to 'Auto' to generate the first clip.")

            sel = (clip_selection or "latest").strip()
            if sel.lower() in ("latest", "", "0", "auto", "default"):
                target_clip = clips[0]
                target_clip_id = target_clip["clip_id"]
            else:
                # Substring / exact match
                matched = [c for c in clips if sel in c.get("clip_id", "") or sel in c.get("shot_tag", "")]
                if matched:
                    target_clip_id = matched[0]["clip_id"]
                else:
                    target_clip_id = sel

        video, audio, tail_tensor, first_tensor, meta_dict = load_clip_asset(p_name, target_clip_id)
        out_latent = pack_av_latent(video, audio)

        prompt_str = meta_dict.get("prompt", "")
        frames = meta_dict.get("frames", latent_steps_to_pixel_frames(video.shape[2]))
        logger.info("[Clip Bin Picker] Loaded clip '%s' (%s frames | tag: '%s')",
                    target_clip_id, frames, meta_dict.get("shot_tag", ""))

        return {
            "ui": {"images": []},
            "result": (out_latent, tail_tensor, first_tensor, prompt_str, target_clip_id, p_name)
        }


NODE_CLASS_MAPPINGS = {
    "MiniMaxClipBinSaver": MiniMaxClipBinSaverNode,
    "MiniMaxClipBinPicker": MiniMaxClipBinPickerNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MiniMaxClipBinSaver": "MiniMax H3 Clip Bin Saver (Media Pool)",
    "MiniMaxClipBinPicker": "MiniMax H3 Clip Bin Picker (Gallery Loader)",
}
