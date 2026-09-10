"""ComfyUI H3 ClipStream.

One plugin, two jobs:

* a **visual, searchable Clip Bin** media pool -- archive every generated
  clip (joint AV latent + preview card + shot tag + lineage), then
  pick any historical clip from a gallery; and
* **MiniMax H3 Motion-Context** seamless continuation -- latent-sliced,
  keyframe-anchored chaining that carries both motion and sound across the
  cut (no decode/re-encode round trip, no "sounds similar" audio restart).

Wire the Clip Bin Picker's ``latent`` into Motion Context's ``context_latent``
and you can continue *any* saved clip, not just the latest one. See README.md.

Bundled engines:
  * Motion-Context (GPLv3):   https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context
  * PrefixStream Clip Bin (MIT): https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream

The combined plugin is distributed under the stricter license, GPLv3
(see LICENSE and ATTRIBUTION.md).
"""
import importlib.util
import os
import sys

_PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))


def _import_subpackage(pkg_name):
    """Load a sub-package by path, giving it a proper ``__path__`` so its
    internal relative imports (``from .nodes import ...``) resolve, without
    adding the plugin root to the global ``sys.path``."""
    init = os.path.join(_PLUGIN_ROOT, pkg_name, "__init__.py")
    pkg_dir = os.path.join(_PLUGIN_ROOT, pkg_name)
    spec = importlib.util.spec_from_file_location(
        pkg_name, init, submodule_search_locations=[pkg_dir])
    module = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = module
    spec.loader.exec_module(module)
    return module


_motion_context = _import_subpackage("motion_context")
_clipbin = _import_subpackage("clipbin")

NODE_CLASS_MAPPINGS = {
    **_motion_context.NODE_CLASS_MAPPINGS,
    **_clipbin.NODE_CLASS_MAPPINGS,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    **_motion_context.NODE_DISPLAY_NAME_MAPPINGS,
    **_clipbin.NODE_DISPLAY_NAME_MAPPINGS,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
