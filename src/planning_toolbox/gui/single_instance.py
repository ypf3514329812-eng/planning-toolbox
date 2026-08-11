"""Acquire a lightweight Windows single-instance guard before GUI imports."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Optional


ERROR_ALREADY_EXISTS = 183
DEFAULT_MUTEX_NAME = "Local\\PlanningToolbox_Desktop_Workbench_v070"


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _create_mutex = _kernel32.CreateMutexW
    _create_mutex.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _create_mutex.restype = wintypes.HANDLE
    _close_handle = _kernel32.CloseHandle
    _close_handle.argtypes = [wintypes.HANDLE]
    _close_handle.restype = wintypes.BOOL


def acquire_single_instance(name: str = DEFAULT_MUTEX_NAME):
    """Return a mutex handle, or ``None`` when another instance owns it."""
    if os.name != "nt":
        return object()

    ctypes.set_last_error(0)
    handle = _create_mutex(None, False, name)
    error_code = ctypes.get_last_error()
    if not handle:
        raise OSError(error_code, "Unable to create the Planning Toolbox instance guard")
    if error_code == ERROR_ALREADY_EXISTS:
        _close_handle(handle)
        return None
    return handle


def release_single_instance(handle: Optional[object]) -> None:
    """Release a previously acquired single-instance guard."""
    if os.name == "nt" and handle:
        _close_handle(handle)
