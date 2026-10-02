"""HTTP API endpoints for MiniMax H3 Clip Bin web frontend integration."""

import os
import asyncio
from .asset_paths import preview_url
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
    project_locked,
    delete_clip_asset,
    atomic_write_json,
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
            atomic_write_json(meta_path, meta)
        except Exception as e:
            logger.warning("[Clip Bin API] Failed to persist probed duration for '%s': %s", clip_id, e)

@project_locked
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
        video_url = preview_url(os.path.join(clip_dir, video_file), subfolder) if has_video else ""

        # Self-heal: measure real durations for clips saved before probing existed (one-time per clip)
        if _probe_and_fix_durations(p_name, clip_id, c, clip_dir):
            _persist_clip_entry(p_name, clip_id, c)

        enriched = dict(c)
        enriched["thumbnail_file"] = preview_file
        enriched["subfolder"] = subfolder
        enriched["thumbnail_url"] = preview_url(os.path.join(clip_dir, preview_file), subfolder) if preview_file else ""
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


def _card_has_video(project_dir: str, clip_id: str, entry: Dict[str, Any]) -> bool:
    """Checks whether a card really has an archived video file on disk.

    Mirrors the list endpoint's lookup without its self-healing copy: the project
    picker only has to decide whether a bin is worth offering at all.
    """
    clip_dir = os.path.join(project_dir, str(clip_id))
    candidates = [str(entry.get("video_file") or "")]
    variants = entry.get("variants")
    if isinstance(variants, dict):
        for variant in variants.values():
            if isinstance(variant, dict):
                candidates.append(str(variant.get("video_file") or ""))
    for name in candidates:
        if name and any(name.lower().endswith(e) for e in VIDEO_EXTENSIONS) \
                and os.path.isfile(os.path.join(clip_dir, name)):
            return True
    if os.path.isdir(clip_dir):
        for file_name in os.listdir(clip_dir):
            if any(file_name.lower().endswith(e) for e in VIDEO_EXTENSIONS):
                return True
    return False


def list_video_projects_api() -> Dict[str, Any]:
    """Lists the bins that hold at least one archived video, with their card counts.

    The Long Builder panel offers these in a dropdown instead of asking for a project
    name to be typed by hand; a bin with no archived video can never become a film.
    """
    projects = []
    for name in list_projects():
        index = load_project_index(name)
        cards = [c for c in index.get("clips", []) if isinstance(c, dict) and c.get("clip_id")]
        project_dir = get_project_dir(name)
        videos = sum(1 for c in cards
                     if _card_has_video(project_dir, c.get("clip_id"), c))
        if videos:
            projects.append({"name": name, "clips": len(cards), "videos": videos})
    return {"projects": projects}

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
        data = await asyncio.to_thread(get_project_clips_api, project)
        return web.json_response(data, headers={"Cache-Control": "no-store"})


    @routes.get("/minimax/clip_bin/projects")
    async def handle_projects(request):
        data = await asyncio.to_thread(list_video_projects_api)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    @routes.post("/minimax/clip_bin/delete")
    async def handle_delete(request):
        from urllib.parse import urlsplit
        origin = request.headers.get("Origin") or request.headers.get("Referer", "")
        if (request.headers.get("Sec-Fetch-Site") == "cross-site" or
                not origin or urlsplit(origin).netloc.lower() != request.host.lower()):
            return web.json_response({"error": "Only same-origin requests are allowed"}, status=403)
        if request.content_type != "application/json":
            return web.json_response({"error": "Expected JSON"}, status=415)
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("project"), str) or not body["project"].strip():
                raise ValueError("A project name is required")
            project, asset_id = body["project"], body["clip_id"]
            removed = await asyncio.to_thread(delete_clip_asset, project, asset_id)
        except (ValueError, TypeError, KeyError):
            return web.json_response({"error": "Invalid project or clip_id"}, status=400)
        except OSError:
            logger.exception("Failed to delete saved asset")
            return web.json_response({"error": "删除失败：文件可能被占用或没有写入权限，请关闭预览后重试。"}, status=409)
        if not removed:
            return web.json_response({"error": "片段已不存在，请刷新列表。"}, status=404)
        prompt_server.send_sync("minimax/clip_bin/changed", {"project": project, "deleted_id": asset_id})
        return web.json_response({"deleted": asset_id})

    logger.info("[Clip Bin API] Successfully registered /minimax/clip_bin routes with PromptServer.")
