"""Stable paths for GUI resources in source and packaged builds."""

from __future__ import annotations

import sys
from pathlib import Path


def gui_asset_path(filename: str) -> Path:
    """Return a GUI asset path that also works inside a PyInstaller build."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "assets" / filename
    return Path(__file__).resolve().parents[3] / "assets" / filename
