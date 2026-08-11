"""Small, explicit planning-condition templates.

The templates are convenience starting points, not legal planning standards.
Local regulations must be entered and reviewed by the user.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RulePreset:
    """A named set of task parameters suitable for a guided workflow."""

    preset_id: str
    name: str
    description: str
    floors: Optional[int]
    setback_m: float
    parcel_layer: str = "PARCEL"
    building_layer: str = "BUILDING"
    green_layer: str = "GREEN"
    fallback_unit: Optional[str] = None

    def __post_init__(self):
        if not self.preset_id.strip():
            raise ValueError("preset_id must not be empty")
        if self.floors is not None and self.floors <= 0:
            raise ValueError("floors must be positive when provided")
        if self.setback_m < 0:
            raise ValueError("setback_m must not be negative")
        for field_name in ("parcel_layer", "building_layer", "green_layer"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")

    def to_task_params(self) -> dict:
        """Return parameters shared by the GUI task forms."""
        return {
            "floors": self.floors,
            "setback_m": self.setback_m,
            "parcel_layer": self.parcel_layer,
            "building_layer": self.building_layer,
            "green_layer": self.green_layer,
            "fallback_unit": self.fallback_unit,
        }


_PRESETS = (
    RulePreset(
        preset_id="custom",
        name="自定义参数",
        description="由用户自行填写规划条件。",
        floors=None,
        setback_m=5.0,
    ),
    RulePreset(
        preset_id="learning_example",
        name="教学示例（6层 / 5米退线，不代表法定规范）",
        description="用于 sample_data 和课堂演示的示例参数。",
        floors=6,
        setback_m=5.0,
    ),
)


def list_rule_presets() -> tuple[RulePreset, ...]:
    """Return all built-in presets in stable display order."""
    return _PRESETS


def get_rule_preset(preset_id: str) -> RulePreset:
    """Return a preset by ID or raise a clear error for unknown IDs."""
    for preset in _PRESETS:
        if preset.preset_id == preset_id:
            return preset
    known = ", ".join(p.preset_id for p in _PRESETS)
    raise KeyError(f"Unknown rule preset '{preset_id}'. Available: {known}")
