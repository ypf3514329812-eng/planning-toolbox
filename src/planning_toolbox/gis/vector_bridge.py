"""Select the lightest available external vector conversion adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class VectorAdapterUnavailableError(RuntimeError):
    """Raised when neither ArcGIS Pro nor QGIS/GDAL is available."""


@dataclass(frozen=True)
class VectorAdapterInfo:
    adapter_id: str
    display_name: str
    executable: Path


def find_preferred_adapter() -> VectorAdapterInfo | None:
    from planning_toolbox.gis.arcgis_bridge import find_arcgis_python

    arcgis = find_arcgis_python()
    if arcgis is not None:
        return VectorAdapterInfo("arcgis", "ArcGIS Pro", arcgis)
    from planning_toolbox.gis.ogr_bridge import find_ogr2ogr

    ogr = find_ogr2ogr()
    if ogr is not None:
        return VectorAdapterInfo("ogr", "QGIS / GDAL", ogr)
    return None


def require_vector_adapter() -> VectorAdapterInfo:
    adapter = find_preferred_adapter()
    if adapter is None:
        raise VectorAdapterUnavailableError(
            "未检测到 ArcGIS Pro 或 QGIS/GDAL。基础 GeoJSON↔DXF 仍可使用；"
            "GPKG/SHP 扩展转换需要其中任意一个本机 GIS 组件。"
        )
    return adapter


def adapter_status_text() -> str:
    adapter = find_preferred_adapter()
    if adapter is None:
        return "⚠️ 未检测到 ArcGIS Pro 或 QGIS/GDAL；可继续使用基础 GeoJSON。"
    return f"✅ 已检测到 {adapter.display_name}，扩展 GIS 转换可以直接使用。"


def convert_vector_to_geojson(*args, adapter: str = "auto", **kwargs):
    selected = require_vector_adapter() if adapter == "auto" else None
    adapter_id = selected.adapter_id if selected else adapter
    if adapter_id == "arcgis":
        from planning_toolbox.gis.arcgis_bridge import convert_vector_to_geojson as convert

        kwargs.pop("source_crs", None)
        kwargs.pop("ogr2ogr_path", None)
        return convert(*args, **kwargs)
    if adapter_id == "ogr":
        from planning_toolbox.gis.ogr_bridge import convert_vector_to_geojson as convert

        return convert(*args, **kwargs)
    raise ValueError(f"不支持的 GIS 适配器：{adapter_id}")


def convert_geojson_to_gpkg(*args, adapter: str = "auto", **kwargs):
    selected = require_vector_adapter() if adapter == "auto" else None
    adapter_id = selected.adapter_id if selected else adapter
    if adapter_id == "arcgis":
        from planning_toolbox.gis.arcgis_bridge import convert_geojson_to_gpkg as convert

        kwargs.pop("ogr2ogr_path", None)
        return convert(*args, **kwargs)
    if adapter_id == "ogr":
        from planning_toolbox.gis.ogr_bridge import convert_geojson_to_gpkg as convert

        return convert(*args, **kwargs)
    raise ValueError(f"不支持的 GIS 适配器：{adapter_id}")


__all__ = [
    "VectorAdapterInfo",
    "VectorAdapterUnavailableError",
    "adapter_status_text",
    "convert_geojson_to_gpkg",
    "convert_vector_to_geojson",
    "find_preferred_adapter",
    "require_vector_adapter",
]
