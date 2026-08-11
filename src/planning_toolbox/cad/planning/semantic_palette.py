"""Shared, dependency-free palette for semantic planning-guide images.

The image-to-CAD converter and the beginner-facing guide editor must agree on
these exact RGB values.  Keeping them in a small module avoids importing the
image-recognition stack merely to open the Qt editor.
"""

from __future__ import annotations

from typing import Final


SEMANTIC_GUIDE_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    "AI_BUILDING": (198, 119, 119),
    "AI_ROAD": (151, 151, 145),
    "AI_GREEN": (126, 165, 142),
    "AI_WATER": (118, 157, 184),
    "AI_PARKING": (204, 169, 113),
}

