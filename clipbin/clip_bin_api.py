"""HTTP API endpoints for MiniMax H3 Clip Bin web frontend integration."""

import os
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("minimax_clip_bin_api")

try:
    import folder_paths
except ImportError:
    folder_paths = None

from .clip_bin_manager import (
    get_project_dir,
    list_projects,
    load_project_index,
    save_project_index,
    rebuild_project_index,
    probe_video_duration,
    VIDEO_EXTENSIONS,
    resolve_source_video_path,
)


def _probe_and_fix_durations(project_name: str, clip_id: str, entry: Dict[str, Any], clip_dir: str) -> bool:
    """Lazily measures real video durations for clips saved before probing existed.

    Only probes entries whose duration_source is not yet 'probed'; the result is
    cached back into meta.json + index so each clip pays this cost exactly once."""
    fixed = False
    if not entry.get("variants"):
        vf = str(entry.get("video_file") or "")
        if vf and os.path.isfile(os.path.join(clip_dir, vf)) and entry.get("duration_source") != "probed":
            d = probe_video_duration(os.path.join(clip_dir, vf))
            if d is not None:
                entry["duration_seconds"] = round(d, 2)
                entry["duration_source"] = "probed"
                fixed = True
    else:
        for v in (entry.get("variants") or {}).values():
            if not isinstance(v, dict) or not v.get("has_latent"):
                continue
            vf = str(v.get("video_file") or "")
            if vf and os.path.isfile(os.path.join(clip_dir, vf)) and v.get("duration_source") != "probed":
                d = probe_video_duration(os.path.join(clip_dir, vf))
                if d is not None:
                    v["duration_seconds"] = round(d, 2)
                    v["duration_source"] = "probed"
                    fixed = True
    return fixed


_FRONTEND_ONLY_KEYS = {"thumbnail_file", "subfolder", "thumbnail_url", "video_url"}


def _persist_clip_entry(project_name: str, clip_id: str, entry: Dict[str, Any]) -> None:
    """Writes corrected fields back into both the project index and meta.json."""
    clean = {k: v for k, v in entry.items() if k not in _FRONTEND_ONLY_KEYS}
    idx = load_project_index(project_name)
    replaced = False
    clips = []
    for c in idx.get("clips", []):
        if c.get("clip_id") == clip_id:
            merged = dict(c)
            merged.update(clean)
            clips.append(merged)
            replaced = True
        else:
            clips.append(c)
    if not replaced:
        return
    idx["clips"] = clips
    save_project_index(project_name, idx)

    meta_path = os.path.join(get_project_dir(project_name), clip_id, "meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta.update(clean)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("[Clip Bin API] Failed to persist probed duration for '%s': %s", clip_id, e)

def get_project_clips_api(project_name: str) -> Dict[str, Any]:
    """Retrieves full clip metadata and relative thumbnail paths for the frontend."""
    p_name = (project_name or "Default_Project").strip()
    idx = load_project_index(p_name)
    clips = idx.get("clips", [])

    base_dir = folder_paths.get_output_directory() if folder_paths is not None else "output"
    project_dir = get_project_dir(p_name)

    enriched_clips = []
    for c in clips:
        clip_id = c.get("clip_id", "")
        clip_dir = os.path.join(project_dir, clip_id)

        # Determine relative subfolder for ComfyUI /view API
        try:
            subfolder = os.path.relpath(clip_dir, base_dir)
        except Exception:
            subfolder = os.path.join("h3-clipstream", p_name, clip_id)

        # Check existing preview files
        tail_path = os.path.join(clip_dir, "tail_frame.png")
        first_path = os.path.join(clip_dir, "first_frame.png")
        preview_path = os.path.join(clip_dir, "preview.png")

        preview_file = "preview.png" if os.path.isfile(preview_path) else (
            "tail_frame.png" if os.path.isfile(tail_path) else (
                "first_frame.png" if os.path.isfile(first_path) else ""
            )
        )

        # Check existing video file (must have valid video extension)
        video_file = c.get("video_file", "")
        if not video_file or not any(video_file.lower().endswith(e) for e in VIDEO_EXTENSIONS) or not os.path.isfile(os.path.join(clip_dir, video_file)):
            video_file = ""
            for v_cand in ["video.mp4", "video.webm"]:
                if os.path.isfile(os.path.join(clip_dir, v_cand)):
                    video_file = v_cand
                    break
            if not video_file and os.path.isdir(clip_dir):
                for fn in os.listdir(clip_dir):
                    if any(fn.lower().endswith(e) for e in VIDEO_EXTENSIONS):
                        video_file = fn
                        break

            # Auto-repair from associated_video_path if found in output
            if not video_file and c.get("associated_video_path"):
                src_v = resolve_source_video_path(c.get("associated_video_path"))
                if src_v and os.path.isfile(src_v):
                    ext = os.path.splitext(src_v)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        dest_v = os.path.join(clip_dir, f"video{ext}")
                        try:
                            import shutil
                            shutil.copy2(src_v, dest_v)
                            video_file = f"video{ext}"
                            # Also delete bogus video.png if present
                            bogus = os.path.join(clip_dir, "video.png")
                            if os.path.isfile(bogus):
                                os.remove(bogus)
                        except Exception:
                            pass

        has_video = bool(video_file and os.path.isfile(os.path.join(clip_dir, video_file)))
        video_url = f"/view?filename={video_file}&subfolder={subfolder}&type=output" if has_video else ""

        # Self-heal: measure real durations for clips saved before probing existed (one-time per clip)
        if _probe_and_fix_durations(p_name, clip_id, c, clip_dir):
            _persist_clip_entry(p_name, clip_id, c)

        enriched = dict(c)
        enriched["thumbnail_file"] = preview_file
        enriched["subfolder"] = subfolder
        enriched["thumbnail_url"] = f"/view?filename={preview_file}&subfolder={subfolder}&type=output" if preview_file else ""
        enriched["has_video"] = has_video
        enriched["video_file"] = video_file if has_video else ""
        enriched["video_url"] = video_url
        enriched_clips.append(enriched)

    return {
        "project_name": p_name,
        "total_clips": len(enriched_clips),
        "available_projects": list_projects(),
        "clips": enriched_clips,
    }


def register_clip_bin_routes() -> None:
    """Registers API routes into ComfyUI's PromptServer if running inside ComfyUI."""
    try:
        import server
        from aiohttp import web
    except ImportError:
        logger.debug("[Clip Bin API] ComfyUI server or aiohttp not available. Skipping route registration.")
        return

    prompt_server = getattr(server.PromptServer, "instance", None)
    if prompt_server is None or not hasattr(prompt_server, "routes"):
        logger.debug("[Clip Bin API] PromptServer routes not found.")
        return

    routes = prompt_server.routes

    @routes.get("/minimax/clip_bin/list")
    async def handle_list_clips(request):
        project = request.rel_url.query.get("project", "Default_Project")
        data = get_project_clips_api(project)
        return web.json_response(data)

    logger.info("[Clip Bin API] Successfully registered /minimax/clip_bin routes with PromptServer.")
