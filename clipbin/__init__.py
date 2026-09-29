"""Clip Bin from knoic/ComfyUI-MiniMaxH3-PrefixStream (MIT).

Decoupled and extended by AraneaQwQ; V3 migration by RAFOLIE, 2026-09-28.
See ../ATTRIBUTION.md for the full component provenance.
"""
from .nodes import NODE_LIST as SINGLE_NODES
from .dual_nodes import NODE_LIST as DUAL_NODES

NODE_LIST = [*SINGLE_NODES, *DUAL_NODES]
