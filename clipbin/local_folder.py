"""Open a project folder on the Windows host running ComfyUI."""
from __future__ import annotations

import logging
import os
import platform
import time

logger = logging.getLogger(__name__)


def _explorer_windows():
    """Return visible Explorer folder windows as (handle, title)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    windows = []

    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        class_name = ctypes.create_unicode_buffer(64)
        if not user32.GetClassNameW(hwnd, class_name, 64) or class_name.value != "CabinetWClass":
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        windows.append((hwnd, title.value))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(visit), 0)
    return windows


def _raise_explorer(folder: str, previous, timeout: float = 2.0) -> bool:
    import ctypes
    from ctypes import wintypes

    name = os.path.basename(folder.rstrip("\\/"))
    deadline = time.monotonic() + timeout
    while True:
        windows = _explorer_windows()
        fresh = [hwnd for hwnd, _ in windows if hwnd not in previous]
        if fresh:
            hwnd = fresh[-1]
            break
        if name:
            matched = [hwnd for hwnd, title in windows if name in title]
            if matched:
                hwnd = matched[-1]
                break
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)

    user32 = ctypes.windll.user32
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow(hwnd, 9)
    user32.BringWindowToTop(hwnd)
    if user32.SetForegroundWindow(hwnd):
        return True
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 0x0002, 0)
    if user32.SetForegroundWindow(hwnd):
        return True
    user32.SwitchToThisWindow(hwnd, True)
    return True


def open_local_folder(path: str) -> None:
    """Open a folder in Explorer and attempt to raise its window."""
    if platform.system() != "Windows":
        raise RuntimeError("打开本地目录目前仅支持 Windows。")
    target = os.path.realpath(path)
    previous = set()
    try:
        previous = {hwnd for hwnd, _ in _explorer_windows()}
    except Exception:
        logger.warning("[Clip Bin] Could not list the open Explorer windows", exc_info=True)
    os.startfile(target)
    try:
        if not _raise_explorer(target, previous):
            logger.debug("[Clip Bin] Explorer window for %s was not found in time", target)
    except Exception:
        logger.warning("[Clip Bin] Could not bring the opened folder to the front", exc_info=True)


__all__ = ["open_local_folder"]
