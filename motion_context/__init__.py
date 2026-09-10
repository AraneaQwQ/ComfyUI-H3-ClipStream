"""MiniMax H3 Motion-Context continuation engine.

Verbatim port of the nodes from NikoDemon80's ComfyUI-H3-Motion-Context
(https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context), GPLv3 licensed.
Nothing in ComfyUI is modified; the layout checks run on first use of a
Motion Context node.
"""
import logging

from .nodes import (
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
    register_chain_routes,
)
from .probe_node import (
    NODE_CLASS_MAPPINGS as _PROBE_CLASSES,
    NODE_DISPLAY_NAME_MAPPINGS as _PROBE_NAMES,
)

NODE_CLASS_MAPPINGS.update(_PROBE_CLASSES)
NODE_DISPLAY_NAME_MAPPINGS.update(_PROBE_NAMES)

try:
    register_chain_routes()
except Exception as exc:  # never block node registration on route wiring
    logging.getLogger("h3_motion_context").warning(
        "h3_motion_context: chain routes not registered: %s", exc)

logging.getLogger("h3_motion_context").info(
    "h3_motion_context: nodes registered. ComfyUI is not modified; the "
    "layout checks run on the first use of a Motion Context node.")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
