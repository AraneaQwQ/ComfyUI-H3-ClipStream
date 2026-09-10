"""Clip Bin visual media pool for MiniMax H3 clips.

Reused from ComfyUI-MiniMaxH3-PrefixStream
(https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream), MIT licensed, and
decoupled from its continuation engine. It archives each generated clip's
joint AV latent plus a preview card, shot tag and lineage, and loads
a chosen clip back out as an H3 AV latent ready to feed Motion Context.
"""
import logging

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .clip_bin_api import register_clip_bin_routes

try:
    register_clip_bin_routes()
except Exception as exc:
    logging.getLogger("minimax_clip_bin").warning(
        "clipbin: clip bin routes not registered: %s", exc)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
