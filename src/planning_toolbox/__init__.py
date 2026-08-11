"""Planning Toolbox (城乡规划 CAD–GIS 自动化辅助工具箱)"""

from __future__ import annotations

from importlib import import_module

__version__ = "0.59.0"

# Keep the established public API while avoiding the CAD/GIS geometry stack at
# package import time.  Each symbol is resolved once, on first use.
_LAZY_EXPORTS = {
    "process_parcels": ("planning_toolbox.cad.parcels.calculator", "process_parcels"),
    "detect_nested_rings": ("planning_toolbox.cad.parcels.calculator", "detect_nested_rings"),
    "calculate_parcel_indicators": (
        "planning_toolbox.indicators.calculator",
        "calculate_parcel_indicators",
    ),
    "process_dxf_indicators": (
        "planning_toolbox.indicators.calculator",
        "process_dxf_indicators",
    ),
    "export_parcels_to_geojson": (
        "planning_toolbox.gis.io.exporter",
        "export_parcels_to_geojson",
    ),
    "import_geojson_to_dxf": (
        "planning_toolbox.gis.io.importer",
        "import_geojson_to_dxf",
    ),
    "validate_polyline_topology": (
        "planning_toolbox.validators.topology",
        "validate_polyline_topology",
    ),
    "check_building_setback": (
        "planning_toolbox.validators.setback",
        "check_building_setback",
    ),
}

__all__ = ["__version__", *_LAZY_EXPORTS]


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
