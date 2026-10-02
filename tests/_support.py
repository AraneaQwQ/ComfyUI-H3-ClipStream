"""Shared helpers for the ClipStream test suite.

Two environment constraints shape this file:

* The node modules import comfy_api / comfy.utils / folder_paths, so a ComfyUI
  install has to be on sys.path. COMFYUI_ROOT points at it; when the suite runs
  from inside custom_nodes the root is inferred from the plugin location.
* The manager modules use relative imports, so they load through a synthetic
  package whose __path__ is the clipbin directory. That keeps the storage tests
  independent of clipbin/__init__.py, which pulls in comfy_api.
* tempfile.mkdtemp creates 0700 directories that a restricted sandbox refuses to
  create subdirectories in, so temp stores are made with plain os.mkdir.
"""

import importlib
import importlib.util
import os
import shutil
import sys
import tempfile
import types
import uuid

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def comfy_roots():
    """Yields plausible ComfyUI install roots, COMFYUI_ROOT first."""
    env_root = os.environ.get("COMFYUI_ROOT")
    if env_root:
        yield env_root
    custom_nodes = os.path.dirname(REPO)
    if os.path.basename(custom_nodes) == "custom_nodes":
        yield os.path.dirname(custom_nodes)


def ensure_comfy_on_path() -> bool:
    """Puts the first existing ComfyUI root on sys.path. Returns whether one was found."""
    found = False
    for root in comfy_roots():
        if os.path.isdir(root):
            found = True
            if root not in sys.path:
                sys.path.insert(0, root)
    return found


def try_import(module_name: str):
    """Imports a ComfyUI-dependent module, returning (module, error)."""
    if not ensure_comfy_on_path():
        return None, RuntimeError("COMFYUI_ROOT is not set and the plugin is not inside custom_nodes")
    try:
        return importlib.import_module(module_name), None
    except Exception as exc:  # ImportError, but also a broken host install
        return None, exc


def load_standalone(rel_path: str, module_name: str):
    """Loads a module that has no relative imports, without importing its package."""
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(REPO, rel_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_clipbin_package():
    """Loads clipbin as a package without running clipbin/__init__.py."""
    name = "clipbin_under_test"
    if name in sys.modules:
        return sys.modules[name]
    pkg = types.ModuleType(name)
    pkg.__path__ = [os.path.join(REPO, "clipbin")]
    sys.modules[name] = pkg
    return pkg


def load_clipbin_module(submodule: str):
    """Loads clipbin/<submodule>.py through the synthetic package."""
    return importlib.import_module("clipbin_under_test." + submodule)


def make_temp_dir(prefix: str) -> str:
    """Creates a temp directory that a restricted sandbox can write inside."""
    parent = tempfile.gettempdir()
    for _ in range(20):
        path = os.path.join(parent, "%s_%s" % (prefix, uuid.uuid4().hex[:8]))
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            continue
    raise RuntimeError("could not create a temp directory under %s" % parent)


def remove_temp_dir(path: str) -> None:
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def load_plugin_package():
    """Imports the plugin root (__init__.py) as a package. Returns (package, error)."""
    name = "h3_clipstream"
    if name in sys.modules:
        return sys.modules[name], None
    if not ensure_comfy_on_path():
        return None, RuntimeError("COMFYUI_ROOT is not set and the plugin is not inside custom_nodes")
    try:
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(REPO, "__init__.py"), submodule_search_locations=[REPO])
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        spec.loader.exec_module(package)
        return package, None
    except Exception as exc:
        sys.modules.pop(name, None)
        return None, exc
