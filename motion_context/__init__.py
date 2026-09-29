"""Motion-Context from NikoDemon80/ComfyUI-H3-Motion-Context (GPLv3).

Integrated by AraneaQwQ; V3 migration by RAFOLIE, 2026-09-28.
The layout checks run on first use; no host patches are installed.
"""
from .nodes import NODE_LIST as CONTEXT_NODES
from .probe_node import NODE_LIST as PROBE_NODES

NODE_LIST = [*CONTEXT_NODES, *PROBE_NODES]
