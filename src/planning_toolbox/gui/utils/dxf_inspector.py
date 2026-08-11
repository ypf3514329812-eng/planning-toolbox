"""DXF 预检工具模块 (前置扫描单位、图层结构、实体闭合性与嵌套关系)."""
from pathlib import Path
from typing import Dict, Any, List, Optional
import ezdxf

from planning_toolbox.core.units.unit_manager import get_dxf_unit_code, INSUNITS_MAP
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry
from planning_toolbox.cad.layers.manager import load_layer_config, build_alias_map

def inspect_dxf_file(dxf_path: Path | str, layer_config_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """
    快速只读预检 DXF 文件结构，返回供 UI 数据检查区展示的摘要字典。
    """
    path = Path(dxf_path)
    if not path.exists():
        return {
            "exists": False,
            "error": f"文件不存在: {path}"
        }

    try:
        doc = ezdxf.readfile(path)
    except Exception as e:
        return {
            "exists": True,
            "valid_dxf": False,
            "error": f"DXF 文件无法解析: {str(e)}"
        }

    # 1. 检查单位 ($INSUNITS)
    unit_code = get_dxf_unit_code(doc)
    unit_name_en = INSUNITS_MAP.get(unit_code, "Unspecified")
    
    unit_display_cn = {
        "Unspecified": "未知 (Unspecified)",
        "Meters": "米 (Meters)",
        "Centimeters": "厘米 (Centimeters)",
        "Millimeters": "毫米 (Millimeters)",
        "Kilometers": "千米 (Kilometers)",
        "Feet": "英尺 (Feet)",
        "Inches": "英寸 (Inches)",
        "Miles": "英里 (Miles)",
    }.get(unit_name_en, f"未知 ({unit_name_en})")

    unit_known = (unit_code != 0 and unit_name_en != "Unspecified")

    # 2. 检查图层结构 (通过 layers.yaml 的别名表映射)
    try:
        layer_cfg = load_layer_config(layer_config_path)
        alias_map = build_alias_map(layer_cfg.get("layers", {}))
    except Exception:
        alias_map = {
            "PARCEL": "PARCEL", "地块": "PARCEL", "地块红线": "PARCEL",
            "BUILDING": "BUILDING", "建筑": "BUILDING", "建筑轮廓": "BUILDING",
            "GREEN": "GREEN", "绿地": "GREEN", "绿化": "GREEN"
        }

    msp = doc.modelspace()
    
    found_std_layers = set()
    layer_counts = {"PARCEL": 0, "BUILDING": 0, "GREEN": 0}
    total_polylines = 0
    open_polylines = 0
    valid_closed = 0
    invalid_geom = 0

    valid_geoms = []

    for entity in msp:
        if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            total_polylines += 1
            layer_orig = str(entity.dxf.layer).upper()
            std_layer = alias_map.get(layer_orig)
            
            if std_layer:
                found_std_layers.add(std_layer)
                if std_layer in layer_counts:
                    layer_counts[std_layer] += 1

            # 采样检查闭合性
            pts, is_closed, _ = points_from_dxf_polyline(entity)
            status, poly, _ = parse_parcel_geometry(pts, is_closed)
            if status == "OPEN":
                open_polylines += 1
            elif status == "INVALID_GEOMETRY":
                invalid_geom += 1
            elif status == "VALID" and poly:
                valid_closed += 1
                # Nested-ring semantics apply to parcel boundaries only.
                # Buildings and green areas commonly sit inside parcels and
                # must not create false hole warnings in the inspection UI.
                if std_layer == "PARCEL":
                    valid_geoms.append(poly)

    # 3. 前置检测嵌套环
    nested_ring_count = 0
    for i, outer in enumerate(valid_geoms):
        o_bounds = outer.bounds
        for j, inner in enumerate(valid_geoms):
            if i == j:
                continue
            i_bounds = inner.bounds
            if (i_bounds[0] >= o_bounds[0] and i_bounds[1] >= o_bounds[1] and
                    i_bounds[2] <= o_bounds[2] and i_bounds[3] <= o_bounds[3]):
                if outer.contains(inner) and not outer.touches(inner) and outer.area > inner.area:
                    nested_ring_count += 1
                    break

    return {
        "exists": True,
        "valid_dxf": True,
        "filename": path.name,
        "filepath": str(path.resolve()),
        "unit_code": unit_code,
        "unit_name_en": unit_name_en,
        "unit_display_cn": unit_display_cn,
        "unit_known": unit_known,
        "has_parcel_layer": "PARCEL" in found_std_layers,
        "has_building_layer": "BUILDING" in found_std_layers,
        "has_green_layer": "GREEN" in found_std_layers,
        "detected_layers": sorted(list(found_std_layers)),
        "layer_counts": layer_counts,
        "total_polylines": total_polylines,
        "valid_closed": valid_closed,
        "open_polylines": open_polylines,
        "invalid_geom": invalid_geom,
        "nested_ring_count": nested_ring_count,
    }
