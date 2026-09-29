"""ComfyUI H3 ClipStream. V3 migration by RAFOLIE, 2026-09-28.

Based on AraneaQwQ/ComfyUI-H3-ClipStream, incorporating
NikoDemon80/ComfyUI-H3-Motion-Context (GPLv3) and
knoic/ComfyUI-MiniMaxH3-PrefixStream (MIT). See LICENSE and ATTRIBUTION.md.
"""
from comfy_api.latest import ComfyExtension
from .clipbin import NODE_LIST as CLIP_NODES
from .clipbin.clip_bin_api import register_clip_bin_routes
from .motion_context import NODE_LIST as CONTEXT_NODES
from .motion_context.nodes import register_chain_routes

WEB_DIRECTORY = "./web"


class H3ClipStreamExtension(ComfyExtension):
    async def get_node_list(self):
        return [*CONTEXT_NODES, *CLIP_NODES]


async def comfy_entrypoint():
    register_clip_bin_routes()
    register_chain_routes()
    return H3ClipStreamExtension()
