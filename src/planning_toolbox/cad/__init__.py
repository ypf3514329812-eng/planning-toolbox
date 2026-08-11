"""CAD automation tools for urban planning."""

from __future__ import annotations

from importlib import import_module

_LAZY_EXPORTS = {
    "process_parcels": ("planning_toolbox.cad.parcels.calculator", "process_parcels"),
    "detect_nested_rings": ("planning_toolbox.cad.parcels.calculator", "detect_nested_rings"),
    "read_dxf_parcels": ("planning_toolbox.cad.io.dxf_reader", "read_dxf_parcels"),
    "DXFReadError": ("planning_toolbox.cad.io.dxf_reader", "DXFReadError"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
from planning_toolbox.cad.annotation.dxf_writer import export_labeled_dxf
