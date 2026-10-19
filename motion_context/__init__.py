"""Motion-Context from NikoDemon80/ComfyUI-H3-Motion-Context (GPLv3).

Integrated by AraneaQwQ; V3 migration by RAFOLIE, 2026-09-28.
The layout checks run on first use; no host patches are installed.

Upstream 0.7.1 adds the three experimental drift nodes (Refine Blend, Join
Match, Sigmas Tail). Their algorithms are carried verbatim; the node classes
are V3, and every node id carries the ClipStream suffix.
"""
from .nodes import NODE_LIST as CONTEXT_NODES
from .probe_node import NODE_LIST as PROBE_NODES
from .refine_blend import NODE_LIST as REFINE_NODES
from .join_match import NODE_LIST as JOIN_NODES
from .sigma_tools import NODE_LIST as SIGMA_NODES

NODE_LIST = [*CONTEXT_NODES, *PROBE_NODES, *REFINE_NODES, *JOIN_NODES,
             *SIGMA_NODES]
