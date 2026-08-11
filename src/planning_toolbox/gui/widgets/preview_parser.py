"""Background DXF preview parsing without importing a plotting framework."""

from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path
from typing import Optional

import ezdxf
from PySide6.QtCore import QThread, Signal

from planning_toolbox.cad.layers.manager import build_alias_map, load_layer_config
from planning_toolbox.core.geometry.parser import parse_parcel_geometry, points_from_dxf_polyline
from planning_toolbox.gui.utils.dxf_inspector import inspect_dxf_file


def empty_preview_geometry():
    return {
        "parcel": [],
        "building": [],
        "road": [],
        "green": [],
        "water": [],
        "parking": [],
        "linework": [],
        "curves": [],
        "inserts": [],
        "texts": [],
    }


_PREVIEW_ROLE_BY_LAYER = {
    "AI_BUILDING": "building",
    "BW_BUILDING_CANDIDATE": "building",
    "AI_ROAD": "road",
    "BW_ROAD_CANDIDATE": "road",
    "BW_ROAD_CENTERLINE_CANDIDATE": "road_centerline",
    "AI_GREEN": "green",
    "BW_TREE_CANDIDATE": "green",
    "BW_LANDSCAPE_CANDIDATE": "green",
    "AI_WATER": "water",
    "AI_PARKING": "parking",
    "BW_PARKING_CANDIDATE": "parking",
}


class DxfPreviewWorker(QThread):
    """Read and classify common 2D entities away from the GUI thread."""

    result_ready = Signal(dict, object)

    def __init__(self, dxf_path: Path | str, layer_config_path: Optional[Path | str] = None, parent=None):
        super().__init__(parent)
        self.dxf_path = Path(dxf_path)
        self.layer_config_path = layer_config_path

    def run(self):
        info = inspect_dxf_file(self.dxf_path, self.layer_config_path)
        if self.isInterruptionRequested():
            return
        if not info.get("valid_dxf"):
            self.result_ready.emit(info, empty_preview_geometry())
            return

        try:
            doc = ezdxf.readfile(self.dxf_path)
            try:
                layer_cfg = load_layer_config(self.layer_config_path)
                alias_map = build_alias_map(layer_cfg.get("layers", {}))
            except Exception:
                alias_map = {"PARCEL": "PARCEL", "BUILDING": "BUILDING", "GREEN": "GREEN"}
            geometry = empty_preview_geometry()

            for entity in doc.modelspace():
                if self.isInterruptionRequested():
                    return
                entity_type = entity.dxftype()
                layer_orig = str(entity.dxf.layer).upper()
                std_layer = alias_map.get(layer_orig, layer_orig)
                if entity_type in ("LWPOLYLINE", "POLYLINE"):
                    points, is_closed, _ = points_from_dxf_polyline(entity)
                    _, polygon, _ = parse_parcel_geometry(points, is_closed)
                    preview_role = _PREVIEW_ROLE_BY_LAYER.get(
                        layer_orig,
                        std_layer.lower()
                        if std_layer in {"PARCEL", "BUILDING", "GREEN"}
                        else "",
                    )
                    if (
                        polygon
                        and len(points) >= 3
                        and preview_role in {"parcel", "building", "road", "green", "water", "parking"}
                    ):
                        geometry[preview_role].append(points)
                    elif len(points) >= 2:
                        geometry["linework"].append({
                            "points": points,
                            "closed": bool(is_closed),
                            "layer": layer_orig,
                            "role": preview_role,
                        })
                elif entity_type == "LINE":
                    geometry["linework"].append({
                        "points": [
                            (float(entity.dxf.start.x), float(entity.dxf.start.y)),
                            (float(entity.dxf.end.x), float(entity.dxf.end.y)),
                        ],
                        "closed": False,
                        "layer": layer_orig,
                    })
                elif entity_type in {"ARC", "CIRCLE"}:
                    center = entity.dxf.center
                    geometry["curves"].append({
                        "type": entity_type,
                        "center": (float(center.x), float(center.y)),
                        "radius": float(entity.dxf.radius),
                        "start_angle": float(getattr(entity.dxf, "start_angle", 0.0)),
                        "end_angle": float(getattr(entity.dxf, "end_angle", 360.0)),
                        "layer": layer_orig,
                    })
                elif entity_type in {"ELLIPSE", "SPLINE"}:
                    try:
                        points = [(float(point.x), float(point.y)) for point in entity.flattening(0.25)]
                    except Exception:
                        points = []
                    if len(points) >= 2:
                        geometry["linework"].append({
                            "points": points,
                            "closed": entity_type == "ELLIPSE",
                            "layer": layer_orig,
                        })
                elif entity_type == "INSERT":
                    insert = entity.dxf.insert
                    block_name = str(entity.dxf.name)
                    if block_name.upper() == "PT_TREE":
                        radius = abs(float(getattr(entity.dxf, "xscale", 1.0) or 1.0))
                        geometry["curves"].append({
                            "type": "CIRCLE",
                            "center": (float(insert.x), float(insert.y)),
                            "radius": radius,
                            "start_angle": 0.0,
                            "end_angle": 360.0,
                            "layer": layer_orig,
                            "role": "green",
                        })
                    elif block_name.upper() == "PT_PARKING_STALL":
                        length = abs(float(getattr(entity.dxf, "xscale", 1.0) or 1.0))
                        width = abs(float(getattr(entity.dxf, "yscale", 1.0) or 1.0))
                        angle = radians(float(getattr(entity.dxf, "rotation", 0.0) or 0.0))
                        cosine = cos(angle)
                        sine = sin(angle)
                        points = []
                        for local_x, local_y in (
                            (-length / 2.0, -width / 2.0),
                            (length / 2.0, -width / 2.0),
                            (length / 2.0, width / 2.0),
                            (-length / 2.0, width / 2.0),
                        ):
                            points.append((
                                float(insert.x) + local_x * cosine - local_y * sine,
                                float(insert.y) + local_x * sine + local_y * cosine,
                            ))
                        geometry["parking"].append(points)
                    else:
                        geometry["inserts"].append({
                            "point": (float(insert.x), float(insert.y)),
                            "name": block_name,
                        })
                elif entity_type in {"TEXT", "MTEXT"}:
                    insert = getattr(entity.dxf, "insert", None)
                    if insert is not None:
                        text = getattr(entity, "text", "")
                        geometry["texts"].append({
                            "point": (float(insert.x), float(insert.y)),
                            "text": str(text)[:32],
                        })

            self.result_ready.emit(info, geometry)
        except Exception:
            self.result_ready.emit(
                {"exists": True, "valid_dxf": False, "error": "DXF 预览解析失败"},
                empty_preview_geometry(),
            )
