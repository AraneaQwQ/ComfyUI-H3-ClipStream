"""Safe local asset paths and versioned ComfyUI preview URLs."""
import os
from urllib.parse import urlencode


def checked_asset_dir(base, project_dir, asset_id):
    if not isinstance(asset_id, str) or not asset_id or asset_id in (".", "..") or any(c in asset_id for c in '/\\:\x00'):
        raise ValueError("Invalid asset ID")
    root = os.path.normcase(os.path.realpath(base))
    project = os.path.normcase(os.path.realpath(project_dir))
    expected_project = os.path.normcase(os.path.join(root, os.path.basename(os.path.abspath(project_dir))))
    target = os.path.abspath(os.path.join(project_dir, asset_id))
    if project != expected_project or os.path.dirname(project) != root:
        raise ValueError("Project must be directly inside the asset store (no links)")
    if os.path.normcase(os.path.realpath(target)) != os.path.normcase(os.path.join(project, asset_id)):
        raise ValueError("Asset directory must not be a symbolic link or junction")
    return target


def preview_url(path, subfolder):
    stat = os.stat(path)
    return "/view?" + urlencode({"filename": os.path.basename(path), "subfolder": subfolder,
        "type": "output", "v": f"{stat.st_mtime_ns}-{stat.st_size}"})
