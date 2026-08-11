"""Lightweight CRS safety checks for the optional GIS vector bridge.

The desktop application deliberately does not bundle an EPSG database.  A
saved project manifest is the primary coordinate contract.  When ``pyproj``
is installed for source-code workflows it is consulted lazily for an
additional authoritative check, so importing the GUI remains lightweight.
"""

from __future__ import annotations

import importlib
import re
from typing import Any, Mapping

from planning_toolbox.project.chain_manifest import CRSDefinition, ChainManifest


_KNOWN_GEOGRAPHIC_EPSG = {4326, 4490, 4610}


class CRSValidationError(ValueError):
    """Raised when coordinates are unsafe for distance or area workflows."""


def normalize_crs_identifier(value: str | int) -> str:
    """Return a conservative ``AUTHORITY:CODE`` identifier.

    Only authority/code identifiers are accepted for external conversion.
    This prevents free-form names from being silently interpreted as the wrong
    coordinate reference system by different GIS installations.
    """

    text = str(value).strip().upper()
    if text.isdigit():
        text = f"EPSG:{text}"
    match = re.fullmatch(r"([A-Z][A-Z0-9_]*)\s*:\s*([1-9][0-9]*)", text)
    if not match:
        raise CRSValidationError(
            "坐标系必须使用明确的编号，例如 EPSG:4547；系统不会根据名称猜测坐标系。"
        )
    return f"{match.group(1)}:{int(match.group(2))}"


def _coerce_definition(value: ChainManifest | CRSDefinition | Mapping[str, Any]) -> CRSDefinition:
    if isinstance(value, ChainManifest):
        return value.crs
    if isinstance(value, CRSDefinition):
        return value
    data = dict(value)
    if "crs" in data and isinstance(data["crs"], Mapping):
        return CRSDefinition.from_dict(data["crs"])
    return CRSDefinition.from_dict(data)


def _validate_with_optional_pyproj(identifier: str) -> None:
    """Use pyproj when available without making it a desktop dependency."""

    try:
        pyproj = importlib.import_module("pyproj")
    except (ImportError, ModuleNotFoundError):
        return
    try:
        crs = pyproj.CRS.from_user_input(identifier)
    except Exception as exc:  # pyproj exposes several version-specific errors
        raise CRSValidationError(f"无法识别项目坐标系 {identifier}：{exc}") from exc
    if bool(crs.is_geographic):
        raise CRSValidationError(
            f"{identifier} 是经纬度坐标，不能直接用于 CAD 距离、面积或退线计算。"
        )
    axis_info = tuple(getattr(crs, "axis_info", ()) or ())
    units = {str(getattr(axis, "unit_name", "")).lower() for axis in axis_info}
    if units and not any(unit in {"metre", "meter", "m"} for unit in units):
        raise CRSValidationError(
            f"{identifier} 不是米制投影坐标，当前全链路转换只接受米制项目坐标。"
        )


def require_projected_metric_crs(
    value: ChainManifest | CRSDefinition | Mapping[str, Any],
) -> str:
    """Validate and return the CRS identifier required by GIS conversion."""

    definition = _coerce_definition(value)
    if definition.code is None:
        raise CRSValidationError(
            "尚未设置项目 EPSG 编号。请点击顶部“🧭”填写经确认的 CGCS2000 投影坐标。"
        )
    identifier = normalize_crs_identifier(f"{definition.authority}:{definition.code}")
    if definition.kind != "projected":
        raise CRSValidationError(
            "GPKG/SHP 全链路转换要求项目坐标类型为“投影坐标”；本地坐标或经纬度不能自动对齐。"
        )
    if definition.linear_unit != "m":
        raise CRSValidationError("全链路 GIS 转换当前只接受米制项目坐标。")
    if definition.code == 3857:
        raise CRSValidationError(
            "EPSG:3857 只适合网络地图显示，不用于精确规划面积、距离或退线计算。"
        )
    if definition.code in _KNOWN_GEOGRAPHIC_EPSG:
        raise CRSValidationError(
            f"{identifier} 是经纬度坐标，请改用项目所在地适用的 CGCS2000 投影坐标。"
        )
    _validate_with_optional_pyproj(identifier)
    return identifier


__all__ = [
    "CRSValidationError",
    "normalize_crs_identifier",
    "require_projected_metric_crs",
]
