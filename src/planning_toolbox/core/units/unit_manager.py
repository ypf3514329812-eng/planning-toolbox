from typing import Optional

# AutoCAD DXF $INSUNITS mapping table
INSUNITS_MAP = {
    0: "Unspecified",
    1: "Inches",
    2: "Feet",
    4: "Millimeters",
    5: "Centimeters",
    6: "Meters",
    7: "Kilometers",
}

# Scale factor from linear unit to meters
LINEAR_TO_METER = {
    "Meters": 1.0,
    "m": 1.0,
    "Millimeters": 0.001,
    "mm": 0.001,
    "Centimeters": 0.01,
    "cm": 0.01,
    "Kilometers": 1000.0,
    "km": 1000.0,
    "Inches": 0.0254,
    "in": 0.0254,
    "Feet": 0.3048,
    "ft": 0.3048,
}

class UnitError(ValueError):
    """Raised when CAD unit is unknown or invalid."""
    pass

def get_dxf_unit_code(doc) -> int:
    """Read $INSUNITS header from ezdxf drawing document."""
    try:
        return doc.header.get("$INSUNITS", 0)
    except Exception:
        return 0

def resolve_unit(doc_unit_code: int, fallback_unit: Optional[str] = None, strict_check: bool = False) -> str:
    """
    Resolves the unit name for spatial calculation.
    If unit is 0 (Unspecified):
      - If strict_check is True, raise UnitError.
      - If fallback_unit is explicitly provided, return fallback_unit with warning flag.
      - Otherwise, raise UnitError.
    """
    unit_name = INSUNITS_MAP.get(doc_unit_code, "Unspecified")
    if unit_name == "Unspecified":
        if strict_check:
            raise UnitError("CAD document unit ($INSUNITS) is Unspecified (0). Strict unit checking is enabled.")
        if fallback_unit:
            return fallback_unit
        raise UnitError("CAD document unit is Unspecified and no fallback unit was provided. Cannot compute area safely.")
    return unit_name

def get_area_scale_to_m2(unit_name: str) -> float:
    """Return scaling multiplier to convert raw calculated polygon area into square meters (m²)."""
    if unit_name not in LINEAR_TO_METER:
        raise UnitError(f"Unsupported unit: {unit_name}")
    meter_factor = LINEAR_TO_METER[unit_name]
    return meter_factor * meter_factor
