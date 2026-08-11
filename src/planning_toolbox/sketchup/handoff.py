"""Create a small, deterministic DXF-to-SketchUp handoff document.

The exporter intentionally does not bundle or automate SketchUp itself.  It
normalizes supported DXF linework to metres, applies the project's reversible
local-origin transform and writes JSON that the bundled SketchUp Ruby extension
turns into native editable groups, faces and building masses.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import ezdxf
from PIL import Image

from planning_toolbox.core.geometry.parser import points_from_dxf_polyline
from planning_toolbox.core.units.unit_manager import (
    get_dxf_unit_code,
    get_linear_scale_to_m,
    resolve_unit,
)
from planning_toolbox.project.chain_manifest import (
    ChainManifest,
    make_stable_object_id,
)
from planning_toolbox.project.semantic_scene import (
    is_presentation_fill_entity,
    load_semantic_scene_for_dxf,
)
from planning_toolbox.project.quality_baseline import (
    write_cad_to_sketchup_quality_baseline,
)
from planning_toolbox.knowledge.sketchup_modeling import (
    get_modeling_building_details,
    get_modeling_building_rule,
    get_modeling_detail_profile,
    get_modeling_road_facility_rule,
    get_modeling_site_surface,
    get_modeling_vegetation_rule,
    sketchup_modeling_knowledge_summary,
)
from planning_toolbox.knowledge.sketchup_components import (
    get_component_placement_rule,
    get_sketchup_component,
    load_sketchup_component_catalog,
    sketchup_component_catalog_summary,
)
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


HANDOFF_FORMAT = "planning-toolbox-sketchup-handoff"
HANDOFF_SCHEMA_VERSION = 7
_LINEWORK_TYPES = {
    "LWPOLYLINE",
    "POLYLINE",
    "LINE",
    "ARC",
    "CIRCLE",
    "ELLIPSE",
    "SPLINE",
}
_FACE_TYPES = {"3DFACE", "SOLID", "TRACE"}
_TEXT_TYPES = {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}
_SUPPORTED_TYPES = _LINEWORK_TYPES | _FACE_TYPES | _TEXT_TYPES
_MAX_BLOCK_DEPTH = 12
_MODEL_DETAIL_LEVELS = {"massing", "course", "presentation"}
_BUILDING_TYPES = {"auto", "generic", "residential", "office", "commercial", "campus"}
_ROOF_TYPES = {"flat", "gable", "hip"}
_ROAD_DESIGN_PRESETS = {"auto", "off", "basic", "complete"}
_CENTERLINE_CONFIDENCE_POLICIES = {"all", "trusted_only"}
_ROAD_CENTERLINE_TRUST_THRESHOLD = 0.65
_ROAD_CENTERLINE_LAYER_TOKENS = (
    "ROAD_CENTERLINE",
    "ROAD_CENTRELINE",
    "ROAD_AXIS",
    "ROUNDABOUT_CENTERLINE",
    "ROUNDABOUT_CENTRELINE",
    "ROUNDABOUT_AXIS",
    "CENTERLINE",
    "CENTRELINE",
    "CENTER_LINE",
    "道路中心线",
    "道路中线",
    "环岛中心线",
    "环岛中线",
)
_ROUNDABOUT_LAYER_TOKENS = (
    "ROUNDABOUT",
    "环岛",
    "转盘",
)

_ROLE_ALIASES = {
    "building": ("BUILDING", "CONCEPT_BUILDING", "AI_BUILDING", "BW_BUILDING", "建筑"),
    "parcel": ("PARCEL", "BOUNDARY", "REDLINE", "用地", "地块", "红线"),
    "green": (
        "GREEN",
        "LANDSCAPE",
        "TREE",
        "PT_TREE",
        "BW_TREE",
        "绿地",
        "景观",
    ),
    "road": ("ROAD", "ACCESS", "ROUNDABOUT", "道路", "车行", "人行", "环岛", "转盘"),
    "water": ("WATER", "水体", "水系"),
    "parking": ("PARKING", "停车"),
}

_ROLE_TAGS = {
    "building": "PT_BUILDING",
    "parcel": "PT_PARCEL",
    "green": "PT_GREEN",
    "road": "PT_ROAD",
    "water": "PT_WATER",
    "parking": "PT_PARKING",
    "underlay": "PT_UNDERLAY",
    "other": "PT_OTHER",
}


def _as_manifest(value: ChainManifest | Mapping[str, Any]) -> ChainManifest:
    if isinstance(value, ChainManifest):
        return value
    if isinstance(value, Mapping):
        return ChainManifest.from_dict(value)
    raise ValueError("SketchUp 交接缺少有效的全链路项目设置。")


def _normalized_layers(values: Sequence[str] | str | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = values.replace("；", ",").replace(";", ",").split(",")
    return tuple(str(item).strip().upper() for item in values if str(item).strip())


def _layer_role(layer_name: str, building_layers: tuple[str, ...]) -> str:
    normalized = str(layer_name or "0").strip().upper()
    if normalized in building_layers:
        return "building"
    for role, aliases in _ROLE_ALIASES.items():
        if any(alias.upper() in normalized for alias in aliases):
            return role
    return "other"


def _polyline_elevation(entity: Any) -> float:
    value = entity.dxf.get("elevation", 0.0)
    if hasattr(value, "z"):
        return float(value.z)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bounded_curve_vertices(
    vertices: Sequence[tuple[float, float, float]],
    *,
    closed: bool,
    maximum: int = 256,
) -> list[tuple[float, float, float]]:
    """Keep curve handoff geometry detailed but bounded in memory.

    ``ezdxf.path`` can return a very dense list for large-radius circles or
    high-resolution splines.  SketchUp only needs a stable editable proxy at
    this stage; the source DXF remains untouched and retains the authoritative
    curve.  Resampling is deterministic and preserves both ends of open curves.
    """
    values = [
        (float(point[0]), float(point[1]), float(point[2]))
        for point in vertices
        if all(math.isfinite(float(value)) for value in point[:3])
    ]
    if len(values) <= maximum:
        return values
    if closed and len(values) > 1 and math.dist(values[0], values[-1]) <= 1e-9:
        values = values[:-1]
    if len(values) <= maximum:
        return values
    target = maximum if not closed else max(12, maximum - 1)
    step = (len(values) - 1) / max(1, target - 1)
    sampled = [values[round(index * step)] for index in range(target)]
    return sampled


def _curve_points(entity: Any, flatten_distance: float) -> tuple[list[tuple[float, float, float]], bool]:
    path = ezdxf.path.make_path(entity)
    vertices = [
        (float(p.x), float(p.y), float(p.z))
        for p in path.flattening(distance=flatten_distance, segments=6)
    ]
    closed_value = getattr(entity, "closed", False)
    if callable(closed_value):
        closed_value = closed_value()
    closed = entity.dxftype() in {"CIRCLE"} or bool(closed_value)
    return _bounded_curve_vertices(vertices, closed=closed), closed


def _entity_points(entity: Any, flatten_distance: float) -> tuple[list[tuple[float, float, float]], bool]:
    entity_type = entity.dxftype()
    if entity_type in {"LWPOLYLINE", "POLYLINE"}:
        points, closed, _ = points_from_dxf_polyline(entity)
        elevation = _polyline_elevation(entity)
        return [(float(x), float(y), elevation) for x, y in points], bool(closed)
    if entity_type == "LINE":
        start = entity.dxf.start
        end = entity.dxf.end
        return [
            (float(start.x), float(start.y), float(start.z)),
            (float(end.x), float(end.y), float(end.z)),
        ], False
    if entity_type in {"ARC", "CIRCLE", "ELLIPSE", "SPLINE"}:
        return _curve_points(entity, flatten_distance)
    if entity_type in _FACE_TYPES:
        vertices = list(entity.wcs_vertices(close=False))
        if entity_type in {"SOLID", "TRACE"} and len(vertices) == 4:
            # DXF stores SOLID/TRACE corners as 0, 1, 2, 3 while their visible
            # perimeter is 0, 1, 3, 2.
            vertices = [vertices[0], vertices[1], vertices[3], vertices[2]]
        return [
            (float(point.x), float(point.y), float(point.z))
            for point in vertices
        ], True
    return [], False


def _is_closed_linework_candidate(entity: Any) -> bool:
    """Check closure without flattening curves into a large temporary point list."""
    entity_type = entity.dxftype()
    if entity_type == "CIRCLE":
        return True
    if entity_type == "ARC" or entity_type == "LINE":
        return False
    if entity_type == "ELLIPSE":
        start = float(entity.dxf.get("start_param", 0.0) or 0.0)
        end = float(entity.dxf.get("end_param", math.tau) or math.tau)
        return abs(abs(end - start) - math.tau) <= 1e-6
    closed_value = getattr(entity, "closed", False)
    if callable(closed_value):
        closed_value = closed_value()
    if not bool(closed_value):
        return False
    if entity_type == "LWPOLYLINE":
        return len(entity) >= 3
    if entity_type == "POLYLINE":
        return len(entity.vertices) >= 3
    return entity_type == "SPLINE"


def _text_content_and_location(entity: Any) -> tuple[str, tuple[float, float, float], float, float]:
    """Return plain annotation text and its WCS anchor without font rendering."""
    entity_type = entity.dxftype()
    text = str(entity.plain_text()).strip()
    if entity_type == "MTEXT":
        point = entity.dxf.insert
        height = float(entity.dxf.get("char_height", 1.0) or 1.0)
    else:
        _alignment, point, _second = entity.get_placement()
        point = entity.ocs().to_wcs(point)
        height = float(entity.dxf.get("height", 1.0) or 1.0)
    rotation = float(entity.dxf.get("rotation", 0.0) or 0.0)
    return (
        text[:1000],
        (float(point.x), float(point.y), float(point.z)),
        height,
        rotation,
    )


def _deduplicate_points(points: Iterable[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    cleaned: list[tuple[float, float, float]] = []
    for point in points:
        if not cleaned or math.dist(point, cleaned[-1]) > 1e-9:
            cleaned.append(point)
    if len(cleaned) > 2 and math.dist(cleaned[0], cleaned[-1]) <= 1e-9:
        cleaned.pop()
    return cleaned


def _is_road_centerline_layer(layer_name: str) -> bool:
    """Recognise explicit road-axis layers without guessing from every open line."""
    normalized = str(layer_name or "").strip().upper()
    return any(token.upper() in normalized for token in _ROAD_CENTERLINE_LAYER_TOKENS)


def _is_image_road_surface_layer(layer_name: str) -> bool:
    """Return true only for the image-derived road-area review layer."""
    return str(layer_name or "").strip().upper() == "BW_ROAD_CANDIDATE"


def _is_image_road_centerline_layer(layer_name: str) -> bool:
    """Return true only for the image-derived road-axis candidate layer."""
    return str(layer_name or "").strip().upper() == "BW_ROAD_CENTERLINE_CANDIDATE"


def _entity_xdata_float(entity: Any, appid: str, group_code: int = 1040) -> float | None:
    """Read one optional numeric DXF XDATA value without making it mandatory."""
    try:
        tags = entity.get_xdata(str(appid))
    except Exception:
        return None
    for tag in tags:
        try:
            if int(tag.code) == int(group_code):
                value = float(tag.value)
                return value if math.isfinite(value) and value > 0 else None
        except (TypeError, ValueError):
            continue
    return None


def _is_roundabout_layer(layer_name: str) -> bool:
    normalized = str(layer_name or "").strip().upper()
    return any(token.upper() in normalized for token in _ROUNDABOUT_LAYER_TOKENS)


def _canonical_axis_angle_deg(angle: float) -> float:
    """Return a stable undirected axis angle, avoiding -0° becoming 179.99°."""
    normalized = float(angle) % 180.0
    return 0.0 if normalized >= 179.5 else normalized


def _validate_chain_for_sketchup(manifest: ChainManifest) -> None:
    if manifest.crs.kind == "geographic":
        raise ValueError(
            "当前项目是经纬度坐标，不能直接生成 SketchUp 模型。请先在 ArcGIS Pro 中转换为合适的投影坐标。"
        )
    if manifest.crs.kind == "projected":
        if not manifest.crs.metric_ready:
            raise ValueError(
                "当前项目投影坐标不适合精确建模；请使用米制的本地投影坐标，不要使用 Web Mercator。"
            )
        if not manifest.local_origin.enabled:
            raise ValueError(
                "投影坐标进入 SketchUp 前必须启用近原点。请点击顶部“🧭 项目设置”，填写场地附近的东坐标和北坐标。"
            )


def _normalized_choice(value: str, allowed: set[str], label: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        choices = "、".join(sorted(allowed))
        raise ValueError(f"{label}不受支持：{normalized or '空值'}。可选值：{choices}。")
    return normalized


def _resolved_building_type(requested: str, project_type: str) -> str:
    if requested != "auto":
        return requested
    normalized = str(project_type or "").strip().lower()
    if any(token in normalized for token in ("residential", "housing", "居住", "住宅")):
        return "residential"
    if any(token in normalized for token in ("office", "办公")):
        return "office"
    if any(token in normalized for token in ("commercial", "retail", "商业")):
        return "commercial"
    if any(token in normalized for token in ("campus", "school", "校园", "学校")):
        return "campus"
    return "generic"


def _layer_token_present(layer_name: str, *tokens: str) -> bool:
    """Match an explicit underscore/dash/space-delimited English layer token."""
    normalized = str(layer_name or "").strip().upper()
    return any(
        re.search(
            rf"(?:^|[_\-\s]){re.escape(token.upper())}(?:$|[_\-\s])",
            normalized,
        )
        is not None
        for token in tokens
    )


def _explicit_building_layer_semantics(layer_name: str) -> dict[str, Any]:
    """Read only deliberately encoded building facts from a CAD layer name.

    Supported examples include ``BUILDING_RES_F6_FH3.2_FLAT``,
    ``BUILDING_OFFICE_F8_H32`` and ``住宅_6层_层高3.1_平屋顶``.  Bare
    numbers are intentionally ignored so drawing numbers cannot become heights.
    """
    normalized = str(layer_name or "").strip().upper()
    if not normalized:
        return {}
    semantics: dict[str, Any] = {}
    source_tokens: list[str] = []

    floor_height_match = re.search(
        r"(?:^|[_\-\s])FH[_\-\s]?(\d+(?:\.\d+)?)(?:M)?(?:$|[_\-\s])",
        normalized,
    ) or re.search(r"层高[_\-\s]?(\d+(?:\.\d+)?)(?:米|M)?", normalized)
    if floor_height_match:
        value = float(floor_height_match.group(1))
        if 0.5 <= value <= 20.0:
            semantics["floor_height_m"] = value
            source_tokens.append(floor_height_match.group(0).strip("_- "))

    floors_match = (
        re.search(
            r"(?:^|[_\-\s])F(?:LOORS?)?[_\-\s]?(\d{1,3})(?:$|[_\-\s])",
            normalized,
        )
        or re.search(
            r"(?:^|[_\-\s])(\d{1,3})F(?:LOORS?)?(?:$|[_\-\s])",
            normalized,
        )
        or re.search(r"(?:^|[_\-\s])(\d{1,3})层(?:$|[_\-\s])", normalized)
    )
    if floors_match:
        value = int(floors_match.group(1))
        if 1 <= value <= 200:
            semantics["floors"] = value
            source_tokens.append(floors_match.group(0).strip("_- "))

    height_match = re.search(
        r"(?:^|[_\-\s])H(?:EIGHT)?[_\-\s]?(\d+(?:\.\d+)?)(?:M)?(?:$|[_\-\s])",
        normalized,
    ) or re.search(
        r"(?<!层)(?:建筑)?高(?:度)?[_\-\s]?(\d+(?:\.\d+)?)(?:米|M)?",
        normalized,
    )
    if height_match:
        value = float(height_match.group(1))
        if 1.0 <= value <= 1000.0:
            semantics["total_height_m"] = value
            source_tokens.append(height_match.group(0).strip("_- "))

    building_type = None
    if any(token in normalized for token in ("住宅", "居住")) or _layer_token_present(
        normalized, "RES", "RESIDENTIAL", "HOUSING"
    ):
        building_type = "residential"
    elif "办公" in normalized or _layer_token_present(normalized, "OFFICE"):
        building_type = "office"
    elif any(token in normalized for token in ("商业", "商铺")) or _layer_token_present(
        normalized, "COMMERCIAL", "RETAIL", "SHOP"
    ):
        building_type = "commercial"
    elif any(token in normalized for token in ("学校", "校园", "教学")) or _layer_token_present(
        normalized, "CAMPUS", "SCHOOL", "EDU"
    ):
        building_type = "campus"
    if building_type:
        semantics["building_type"] = building_type
        source_tokens.append(building_type)

    roof_type = None
    if "平屋顶" in normalized or _layer_token_present(normalized, "FLAT"):
        roof_type = "flat"
    elif any(token in normalized for token in ("双坡", "人字坡")) or _layer_token_present(
        normalized, "GABLE"
    ):
        roof_type = "gable"
    elif "四坡" in normalized or _layer_token_present(normalized, "HIP"):
        roof_type = "hip"
    if roof_type:
        semantics["roof_type"] = roof_type
        source_tokens.append(roof_type)

    if semantics:
        semantics["source"] = "explicit_layer_name"
        semantics["source_layer"] = str(layer_name)
        semantics["source_tokens"] = source_tokens
    return semantics


def _with_geometry_fingerprint(object_data: dict[str, Any]) -> dict[str, Any]:
    """Attach a deterministic fingerprint used by incremental SketchUp imports."""
    object_data.pop("geometry_fingerprint", None)
    canonical = json.dumps(
        object_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    object_data["geometry_fingerprint"] = hashlib.sha256(canonical).hexdigest()
    return object_data


def _aggregate_semantic_underlay_objects(
    objects: Sequence[dict[str, Any]],
    project_id: str,
) -> tuple[list[dict[str, Any]], int]:
    """Bundle reference-only image linework into one lightweight SU object.

    The source paths remain independently editable inside the SketchUp group,
    but the Outliner and incremental importer only need to manage one stable
    top-level object instead of thousands of anonymous line groups.
    """
    retained: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    source_layers: set[str] = set()
    for item in objects:
        if (
            item.get("role") == "underlay"
            and item.get("geometry_type") in {"polyline", "polygon"}
            and isinstance(item.get("points_m"), list)
            and len(item["points_m"]) >= 2
        ):
            source_layers.add(str(item.get("source_layer", "")))
            paths.append(
                {
                    "source_handle": str(item.get("source_handle", "")),
                    "source_layer": str(item.get("source_layer", "")),
                    "source_type": str(item.get("source_type", "")),
                    "closed": bool(item.get("closed", False)),
                    "points_m": item["points_m"],
                }
            )
        else:
            retained.append(item)
    if not paths:
        return list(objects), 0

    bundle = _with_geometry_fingerprint(
        {
            "id": make_stable_object_id(
                project_id,
                "underlay",
                "IMAGE-REFERENCE-LINEWORK",
            ),
            "parent_id": None,
            "source_handle": "SEMANTIC-UNDERLAY",
            "source_type": "SEMANTIC_UNDERLAY",
            "source_layer": "PT_UNDERLAY",
            "source_layers": sorted(source_layers),
            "role": "underlay",
            "sketchup_tag": "PT_UNDERLAY",
            "geometry_type": "linework_bundle",
            "closed": False,
            "paths": paths,
            "path_count": len(paths),
            "extrusion_m": 0.0,
            "locked_by_default": True,
            "review_status": "reference_only",
        }
    )
    return [bundle, *retained], len(paths)


def _semantic_raster_underlay_object(
    semantic_scene: Mapping[str, Any] | None,
    project_id: str,
    origin_m: tuple[float, float, float],
) -> dict[str, Any] | None:
    """Build a source-bound raster underlay aligned with image-derived DXF.

    The vector DXF remains editable, while the original PNG/JPEG is the visual
    authority used to audit overlap in SketchUp.  A changed image is rejected
    instead of being silently stretched beneath geometry calibrated to another
    file.
    """
    source = dict((semantic_scene or {}).get("source", {}) or {})
    image_value = str(source.get("source_image_path", "")).strip()
    if not image_value:
        return None
    image_path = Path(image_value).resolve()
    if not image_path.is_file():
        return None
    expected_hash = str(source.get("source_image_sha256", "")).strip().lower()
    actual_hash = sha256_file(image_path)
    if expected_hash and actual_hash.lower() != expected_hash:
        raise ValueError(
            "SketchUp 底图已发生变化，无法保证与 CAD 坐标重合；"
            "请从当前图片重新执行图转 CAD。"
        )
    try:
        reference_width_m = float(source.get("reference_width_m"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(reference_width_m) or reference_width_m <= 0:
        return None
    with Image.open(image_path) as source_image:
        width_px, height_px = source_image.size
    if width_px <= 0 or height_px <= 0:
        return None
    reference_height_m = reference_width_m * float(height_px) / float(width_px)
    underlay_origin = (
        float(origin_m[0]),
        float(origin_m[1]),
        float(origin_m[2]) - 0.03,
    )
    return _with_geometry_fingerprint({
        "id": make_stable_object_id(project_id, "underlay", f"IMAGE:{actual_hash}"),
        "parent_id": None,
        "source_handle": "SEMANTIC-RASTER-UNDERLAY",
        "source_type": "SEMANTIC_RASTER_UNDERLAY",
        "source_layer": "PT_UNDERLAY_IMAGE",
        "role": "underlay",
        "sketchup_tag": "PT_UNDERLAY",
        "geometry_type": "image_underlay",
        "image_path": str(image_path),
        "image_sha256": actual_hash,
        "origin_m": [round(value, 9) for value in underlay_origin],
        "width_m": round(reference_width_m, 9),
        "height_m": round(reference_height_m, 9),
        "pixel_size": [int(width_px), int(height_px)],
        "closed": False,
        "extrusion_m": 0.0,
        "locked_by_default": True,
        "review_status": "reference_only",
    })


def _procedural_building_settings(
    points: Sequence[tuple[float, float, float]],
    *,
    floors: int,
    floor_height_m: float,
    detail_level: str,
    building_type: str,
    roof_type: str,
) -> tuple[dict[str, Any], int, int]:
    """Describe lightweight, deterministic planning-detail generation.

    Geometry remains generated natively by the SketchUp extension.  The JSON
    only carries explicit rules and counts, keeping the desktop package small.
    """
    detail_profile = get_modeling_detail_profile(detail_level)
    building_rule = get_modeling_building_rule(building_type)
    detail_rules = get_modeling_building_details()
    knowledge = sketchup_modeling_knowledge_summary()
    enabled = (
        floors > 0
        and floor_height_m > 0
        and bool(detail_profile.get("architectural_details_enabled"))
    )
    if not enabled:
        return {
            "enabled": False,
            "detail_level": detail_level,
            "building_type": building_type,
            "requested_roof_type": roof_type,
            "effective_roof_type": "flat",
            "floor_line_elevations_m": [],
            "facade": {"enabled": False},
            "architectural_details": {"enabled": False},
            "knowledge_rule": {
                "id": knowledge["id"],
                "version": knowledge["version"],
            },
        }, 0, 0

    effective_roof = roof_type if roof_type == "flat" or len(points) == 4 else "flat"
    floor_lines = [
        round(index * floor_height_m, 6)
        for index in range(1, floors)
    ]
    facade = dict(building_rule["facade"])
    facade.update(
        {
            "enabled": bool(detail_profile["facade_enabled"]),
            "margin_m": float(detail_profile["facade_margin_m"]),
            "depth_m": float(detail_profile["facade_depth_m"]),
            "max_instances": int(detail_profile["facade_max_instances_per_building"]),
        }
    )
    module_width = float(facade["module_width_m"])
    margin = float(facade["margin_m"])
    modules_per_floor = 0
    for point, next_point in zip(points, [*points[1:], points[0]]):
        edge_length = math.hypot(next_point[0] - point[0], next_point[1] - point[1])
        if edge_length <= margin * 2:
            continue
        modules_per_floor += max(1, int((edge_length - margin * 2) // module_width))
    estimated_modules = min(
        int(facade["max_instances"]),
        modules_per_floor * floors,
    )
    floor_guide_segments = len(floor_lines) * len(points)
    roof_rule = detail_rules["roof"]
    roof_height = 0.0
    if effective_roof in {"gable", "hip"}:
        roof_height = round(
            max(
                float(roof_rule["minimum_height_m"]),
                min(
                    float(roof_rule["maximum_height_m"]),
                    floor_height_m * float(roof_rule["height_floor_factor"]),
                ),
            ),
            3,
        )
    entrance_width = float(building_rule["entrance_width_m"])
    plinth_rule = detail_rules["plinth"]
    entrance_rule = detail_rules["entrance"]
    balcony_rule = detail_rules["balcony"]
    entrance_component_rule = get_component_placement_rule("entrance")
    entrance_asset_id = str(
        entrance_component_rule.get(
            building_type,
            entrance_component_rule.get("generic", "overhang_wide"),
        )
    )
    entrance_component = get_sketchup_component(entrance_asset_id)
    entrance_component_target = list(entrance_component["target_bounds_m"])
    entrance_component_target[0] = round(
        entrance_width + float(detail_profile["canopy_extra_width_m"]),
        3,
    )
    entrance_component_target[1] = float(detail_profile["canopy_depth_m"])
    architectural_details = {
        "enabled": True,
        "plinth": {
            "enabled": True,
            "height_m": round(
                max(
                    float(plinth_rule["minimum_height_m"]),
                    min(
                        float(plinth_rule["maximum_height_m"]),
                        floor_height_m * float(plinth_rule["height_floor_factor"]),
                    ),
                ),
                3,
            ),
            "offset_m": float(detail_profile["plinth_offset_m"]),
        },
        "entrance": {
            "enabled": True,
            "width_m": entrance_width,
            "height_m": round(
                max(
                    float(entrance_rule["minimum_height_m"]),
                    min(
                        float(entrance_rule["maximum_height_m"]),
                        floor_height_m * float(entrance_rule["height_floor_factor"]),
                    ),
                ),
                3,
            ),
            "depth_m": float(detail_profile["entrance_depth_m"]),
            "canopy_width_m": round(
                entrance_width + float(detail_profile["canopy_extra_width_m"]),
                3,
            ),
            "canopy_depth_m": float(detail_profile["canopy_depth_m"]),
            "canopy_thickness_m": float(entrance_rule["canopy_thickness_m"]),
            "component_library": _component_reference(
                entrance_asset_id,
                target_bounds_m=entrance_component_target,
            ),
        },
        "balcony": {
            "enabled": (
                bool(detail_profile["balcony_enabled"])
                and bool(building_rule["balcony_eligible"])
                and floors >= int(balcony_rule["minimum_floors"])
            ),
            "width_m": float(balcony_rule["width_m"]),
            "depth_m": float(balcony_rule["depth_m"]),
            "slab_thickness_m": float(balcony_rule["slab_thickness_m"]),
            "railing_height_m": float(balcony_rule["railing_height_m"]),
            "max_instances": int(balcony_rule["max_instances"]),
        },
        "rooftop_equipment": {
            "enabled": bool(detail_profile["rooftop_equipment_enabled"])
            and effective_roof == "flat",
            "height_m": float(roof_rule["rooftop_equipment_height_m"]),
        },
    }
    return {
        "enabled": True,
        "detail_level": detail_level,
        "building_type": building_type,
        "requested_roof_type": roof_type,
        "effective_roof_type": effective_roof,
        "roof_height_m": roof_height,
        "parapet_height_m": (
            float(roof_rule["flat_parapet_height_m"])
            if effective_roof == "flat"
            else 0.0
        ),
        "floor_count": floors,
        "floor_height_m": round(floor_height_m, 6),
        "floor_line_elevations_m": floor_lines,
        "facade": facade,
        "architectural_details": architectural_details,
        "material_rgb": list(building_rule["material_rgb"]),
        "knowledge_rule": {
            "id": knowledge["id"],
            "version": knowledge["version"],
        },
    }, estimated_modules, floor_guide_segments


def _site_surface_style(
    role: str,
    detail_level: str,
    road_design_preset: str = "auto",
) -> dict[str, Any] | None:
    """Return a restrained SketchUp site-surface treatment for a CAD role."""
    effective_level = (
        "presentation"
        if role == "road"
        and detail_level != "massing"
        and road_design_preset == "complete"
        else detail_level
    )
    result = get_modeling_site_surface(effective_level, role)
    if result is not None:
        result["enabled"] = True
        if role == "road" and road_design_preset == "off":
            result.get("road_design", {})["enabled"] = False
            result.get("lane_marking", {})["enabled"] = False
            result.get("edge_profile", {})["enabled"] = False
        elif role == "road" and road_design_preset == "basic":
            result.get("road_design", {}).get("sidewalk", {})["enabled"] = False
            result.get("road_design", {}).get("direction_arrow", {})["enabled"] = False
        if role == "road" and (
            detail_level == "presentation" or road_design_preset == "complete"
        ) and road_design_preset != "off":
            placement = get_component_placement_rule("road_street_lights")
            result["street_lights"] = {
                "enabled": True,
                "component_library": _component_reference(
                    str(placement["asset_id"]),
                ),
                "minimum_edge_length_m": float(placement["minimum_edge_length_m"]),
                "spacing_m": float(placement["spacing_m"]),
                "end_margin_m": float(placement["end_margin_m"]),
                "max_instances": int(placement["max_instances_per_surface"]),
            }
    return result


def _road_sidewalk_width(width_m: float, settings: Mapping[str, Any]) -> float:
    """Calculate the bounded sidewalk width shared by all road shape hints."""
    sidewalk = settings.get("sidewalk", {})
    if not isinstance(sidewalk, Mapping):
        return 0.0
    if not sidewalk.get("enabled"):
        return 0.0
    if width_m < float(sidewalk.get("minimum_total_road_width_m", 8.0)):
        return 0.0
    sidewalk_width_m = min(
        float(sidewalk.get("preferred_width_m", 1.5)),
        width_m * float(sidewalk.get("maximum_fraction_each_side", 0.22)),
    )
    minimum_carriageway_m = float(
        sidewalk.get("minimum_carriageway_width_m", 5.5)
    )
    if width_m - sidewalk_width_m * 2 < minimum_carriageway_m:
        sidewalk_width_m = (width_m - minimum_carriageway_m) / 2
    if sidewalk_width_m < float(sidewalk.get("minimum_width_m", 1.0)):
        return 0.0
    return max(0.0, sidewalk_width_m)


def _road_segment_record(
    first: Sequence[float],
    second: Sequence[float],
    index: int,
) -> dict[str, Any] | None:
    dx = float(second[0]) - float(first[0])
    dy = float(second[1]) - float(first[1])
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return None
    return {
        "index": index,
        "start": [float(first[0]), float(first[1])],
        "end": [float(second[0]), float(second[1])],
        "center": [
            (float(first[0]) + float(second[0])) / 2.0,
            (float(first[1]) + float(second[1])) / 2.0,
        ],
        "length_m": length,
        "axis_vector": [dx / length, dy / length],
        "axis_angle_deg": _canonical_axis_angle_deg(math.degrees(math.atan2(dy, dx))),
    }


def _roundabout_geometry_hint(
    points: Sequence[Sequence[float]],
    settings: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a bounded ring hint from an explicitly named circular road.

    A circle in a generic CAD layer is intentionally *not* treated as a
    road.  The caller gates this helper behind a ROUNDABOUT/环岛 layer.  The
    circle still does not contain a carriageway width, so the width is marked
    as conceptual and comes only from the audited modeling rule.
    """
    if len(points) < 12:
        return {}
    xy = [(float(point[0]), float(point[1])) for point in points]
    center = [
        sum(point[0] for point in xy) / len(xy),
        sum(point[1] for point in xy) / len(xy),
    ]
    radii = [math.dist(point, center) for point in xy]
    radius = sorted(radii)[len(radii) // 2]
    if not math.isfinite(radius) or radius <= 0:
        return {}
    radial_error = max(abs(value - radius) for value in radii)
    if radial_error > max(0.35, radius * 0.05):
        return {}

    minimum_width = float(settings.get("minimum_width_m", 4.0))
    width_m = max(
        minimum_width,
        float(settings.get("centerline_assumed_width_m", minimum_width)),
    )
    if radius <= width_m * 0.65:
        return {}
    circumference_m = math.tau * radius
    if circumference_m < float(settings.get("minimum_length_m", 8.0)):
        return {}

    # Keep the ring smooth enough for a planning model while bounding the
    # number of SketchUp faces and JSON frames.
    frame_count = min(64, max(16, math.ceil(circumference_m / 4.0)))
    first_radial = (xy[0][0] - center[0], xy[0][1] - center[1])
    second_radial = (xy[1][0] - center[0], xy[1][1] - center[1])
    orientation = 1.0 if (
        first_radial[0] * second_radial[1]
        - first_radial[1] * second_radial[0]
    ) >= 0 else -1.0
    start_angle = math.atan2(first_radial[1], first_radial[0])
    frames: list[dict[str, Any]] = []
    for index in range(frame_count):
        angle = start_angle + orientation * math.tau * index / frame_count
        radial = [math.cos(angle), math.sin(angle)]
        tangent = [
            -math.sin(angle) * orientation,
            math.cos(angle) * orientation,
        ]
        frames.append(
            {
                "index": index,
                "center_m": [
                    round(center[0] + radial[0] * radius, 6),
                    round(center[1] + radial[1] * radius, 6),
                ],
                "axis_vector": [round(tangent[0], 9), round(tangent[1], 9)],
                "axis_angle_deg": round(
                    _canonical_axis_angle_deg(math.degrees(math.atan2(tangent[1], tangent[0]))),
                    6,
                ),
                "width_m": round(width_m, 3),
                "half_width_m": round(width_m / 2.0, 3),
                "support_length_m": round(circumference_m / frame_count, 3),
                "station_m": round(circumference_m * index / frame_count, 3),
            }
        )
    sidewalk_width_m = _road_sidewalk_width(width_m, settings)
    tangent = frames[0]["axis_vector"]
    return {
        "eligible": True,
        "shape": "roundabout_ring",
        "classification": "roundabout_centerline_conceptual",
        "geometry_confidence": round(
            max(0.62, min(0.88, 0.88 - radial_error / max(radius, 1e-9))),
            6,
        ),
        "local_tangent_supported": True,
        "detail_geometry_supported": True,
        "detail_geometry": "roundabout_ring_local_frames",
        "width_source": "conceptual_roundabout_centerline_default",
        "center_m": [round(center[0], 6), round(center[1], 6)],
        "long_axis_angle_deg": round(
            _canonical_axis_angle_deg(math.degrees(math.atan2(tangent[1], tangent[0]))),
            6,
        ),
        "long_axis_vector": [round(float(tangent[0]), 9), round(float(tangent[1]), 9)],
        "length_m": round(circumference_m, 3),
        "width_m": round(width_m, 3),
        "sidewalk_width_each_side_m": round(sidewalk_width_m, 3),
        "carriageway_width_m": round(width_m - sidewalk_width_m * 2.0, 3),
        "centerline_radius_m": round(radius, 3),
        "roundabout_segment_count": frame_count,
        "radial_fit_error_m": round(radial_error, 6),
        "frames": frames,
        "curvature_angle_deg": 360.0,
        "sidewalk_band_count": 0,
        "edge_line_count": 0,
        "direction_arrow_count": 0,
        "center_dash_count": 0,
        "street_light_count": 0,
    }


def _road_local_tangent_frames(
    points: Sequence[Sequence[float]],
    settings: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Infer conservative local tangents from paired boundary segments.

    A road strip is accepted only when two non-adjacent boundary segments are
    nearly parallel and separated by a plausible carriageway width.  This is
    deliberately stricter than a generic polygon principal-axis estimate.
    """
    if len(points) < 6:
        return []
    if len(points) > 160:
        sample_step = (len(points) - 1) / 159.0
        points = [points[round(index * sample_step)] for index in range(160)]
    minimum_width = float(settings.get("minimum_width_m", 4.0))
    segments = [
        record
        for index, first in enumerate(points)
        for record in [
            _road_segment_record(first, points[(index + 1) % len(points)], index)
        ]
        if record is not None
    ]
    if len(segments) < 6:
        return []

    pair_frames: list[dict[str, Any]] = []
    segment_count = len(points)
    for first_index, first in enumerate(segments):
        for second in segments[first_index + 1 :]:
            second_index = int(second["index"])
            index_gap = abs(int(first["index"]) - second_index)
            if index_gap in {0, 1, segment_count - 1}:
                continue
            angle_difference = _axis_angle_difference_deg(
                float(first["axis_angle_deg"]),
                float(second["axis_angle_deg"]),
            )
            if angle_difference > 24.0:
                continue
            first_axis = list(first["axis_vector"])
            second_axis = list(second["axis_vector"])
            if first_axis[0] * second_axis[0] + first_axis[1] * second_axis[1] < 0:
                second_axis = [-second_axis[0], -second_axis[1]]
            axis = [
                first_axis[0] + second_axis[0],
                first_axis[1] + second_axis[1],
            ]
            axis_length = math.hypot(axis[0], axis[1])
            if axis_length <= 1e-9:
                continue
            axis = [axis[0] / axis_length, axis[1] / axis_length]
            normal = [-axis[1], axis[0]]
            delta = [
                float(second["center"][0]) - float(first["center"][0]),
                float(second["center"][1]) - float(first["center"][1]),
            ]
            separation = abs(delta[0] * normal[0] + delta[1] * normal[1])
            longitudinal_offset = abs(delta[0] * axis[0] + delta[1] * axis[1])
            if separation < minimum_width * 0.82:
                continue
            if longitudinal_offset > max(
                first["length_m"], second["length_m"]
            ) * 2.5 + 2.0:
                continue
            center = [
                (float(first["center"][0]) + float(second["center"][0])) / 2.0,
                (float(first["center"][1]) + float(second["center"][1])) / 2.0,
            ]
            pair_frames.append(
                {
                    "center_m": center,
                    "axis_vector": axis,
                    "axis_angle_deg": _canonical_axis_angle_deg(
                        math.degrees(math.atan2(axis[1], axis[0]))
                    ),
                    "width_m": separation,
                    "support_length_m": min(
                        float(first["length_m"]), float(second["length_m"])
                    ),
                    "edge_pair": [int(first["index"]), second_index],
                    "match_quality": angle_difference + longitudinal_offset / max(separation, 1e-9),
                }
            )

    if not pair_frames:
        return []

    # Keep the best frame per local position.  Dense DXF curve flattening can
    # otherwise create many nearly identical candidates and inflate the JSON.
    pair_frames.sort(key=lambda item: float(item["match_quality"]))
    frames: list[dict[str, Any]] = []
    for frame in pair_frames:
        duplicate = next(
            (
                existing
                for existing in frames
                if math.dist(existing["center_m"], frame["center_m"])
                <= min(1.25, max(0.5, float(frame["width_m"]) * 0.12))
                and _axis_angle_difference_deg(
                    float(existing["axis_angle_deg"]),
                    float(frame["axis_angle_deg"]),
                )
                <= 18.0
            ),
            None,
        )
        if duplicate is None:
            frames.append(frame)
    if len(frames) < 2:
        return []

    centroid = [
        sum(float(point[0]) for point in points) / len(points),
        sum(float(point[1]) for point in points) / len(points),
    ]
    # The farthest vertex pair gives a stable station axis without a large
    # dependency.  It is only used to order local frames and report a hint.
    farthest = (points[0], points[1], 0.0)
    for first_index, first in enumerate(points):
        for second in points[first_index + 1 :]:
            distance = math.dist(first[:2], second[:2])
            if distance > farthest[2]:
                farthest = (first, second, distance)
    axis_delta = [
        float(farthest[1][0]) - float(farthest[0][0]),
        float(farthest[1][1]) - float(farthest[0][1]),
    ]
    axis_length = math.hypot(axis_delta[0], axis_delta[1])
    if axis_length <= 1e-9:
        return []
    station_axis = [axis_delta[0] / axis_length, axis_delta[1] / axis_length]
    for frame in frames:
        delta = [
            float(frame["center_m"][0]) - centroid[0],
            float(frame["center_m"][1]) - centroid[1],
        ]
        frame["station_m"] = delta[0] * station_axis[0] + delta[1] * station_axis[1]
    frames.sort(key=lambda item: float(item["station_m"]))
    if len(frames) > 64:
        sample_step = (len(frames) - 1) / 63.0
        frames = [frames[round(index * sample_step)] for index in range(64)]

    widths = sorted(float(frame["width_m"]) for frame in frames)
    width_m = widths[len(widths) // 2]
    sidewalk_width_m = _road_sidewalk_width(width_m, settings)
    station_span = float(frames[-1]["station_m"]) - float(frames[0]["station_m"])
    length_m = station_span + sum(
        float(frame["support_length_m"]) for frame in frames
    ) / len(frames)
    if width_m < minimum_width or length_m < float(settings.get("minimum_length_m", 8.0)):
        return []
    if length_m / max(width_m, 1e-9) < 1.35:
        return []

    frame_centers = [frame["center_m"] for frame in frames]
    road_center = [
        sum(float(center[0]) for center in frame_centers) / len(frame_centers),
        sum(float(center[1]) for center in frame_centers) / len(frame_centers),
    ]
    global_angle = _canonical_axis_angle_deg(
        math.degrees(math.atan2(station_axis[1], station_axis[0]))
    )
    curvature = max(
        _axis_angle_difference_deg(global_angle, float(frame["axis_angle_deg"]))
        for frame in frames
    )
    shape = "curved_strip" if curvature >= 10.0 else "segmented_strip"
    confidence = min(0.90, 0.58 + min(len(frames), 8) * 0.04)
    for index, frame in enumerate(frames):
        frame["index"] = index
        frame.pop("match_quality", None)
        frame.pop("edge_pair", None)
        frame["center_m"] = [round(float(value), 6) for value in frame["center_m"]]
        frame["axis_vector"] = [round(float(value), 9) for value in frame["axis_vector"]]
        frame["axis_angle_deg"] = round(float(frame["axis_angle_deg"]), 6)
        frame["width_m"] = round(float(frame["width_m"]), 3)
        frame["half_width_m"] = round(float(frame["width_m"]) / 2.0, 3)
        frame["support_length_m"] = round(float(frame["support_length_m"]), 3)
        frame["station_m"] = round(float(frame["station_m"]), 3)

    return {
        "eligible": True,
        "shape": shape,
        "classification": "curved_local_tangent" if shape == "curved_strip" else "segmented_local_tangent",
        "geometry_confidence": round(confidence, 6),
        "local_tangent_supported": True,
        "detail_geometry_supported": True,
        "detail_geometry": "curved_local_frame_strips",
        "width_source": "paired_boundary_segments",
        "center_m": [round(float(value), 6) for value in road_center],
        "long_axis_angle_deg": round(global_angle, 6),
        "long_axis_vector": [round(float(value), 9) for value in station_axis],
        "length_m": round(length_m, 3),
        "width_m": round(width_m, 3),
        "sidewalk_width_each_side_m": round(sidewalk_width_m, 3),
        "carriageway_width_m": round(width_m - sidewalk_width_m * 2.0, 3),
        "frames": frames,
        "curvature_angle_deg": round(curvature, 3),
        "sidewalk_band_count": 0,
        "edge_line_count": 0,
        "direction_arrow_count": 0,
        "center_dash_count": 0,
        "street_light_count": 0,
    }


def _road_centerline_hint(
    points: Sequence[Sequence[float]],
    settings: Mapping[str, Any],
    *,
    corridor_enabled: bool = False,
    requested_width_m: float = 0.0,
    requested_width_source: str = "user_centerline_width",
    source_confidence: float | None = None,
) -> dict[str, Any]:
    """Describe an explicit road axis and, optionally, a conceptual corridor."""
    shape = "centerline_corridor" if corridor_enabled else "centerline"
    result = {
        "eligible": False,
        "shape": shape,
        "classification": "unclassified_centerline",
        "geometry_confidence": 0.0,
        "local_tangent_supported": False,
        "detail_geometry_supported": False,
        "detail_geometry": "orientation_only",
        "width_source": "not_available",
        "sidewalk_band_count": 0,
        "edge_line_count": 0,
        "direction_arrow_count": 0,
        "center_dash_count": 0,
        "street_light_count": 0,
    }
    if source_confidence is not None:
        result["source_confidence"] = round(float(source_confidence), 3)
        result["source_review_required"] = float(source_confidence) < 0.65
    if len(points) < 2:
        return result
    segments = [
        _road_segment_record(first, second, index)
        for index, (first, second) in enumerate(zip(points, points[1:]))
    ]
    segments = [segment for segment in segments if segment is not None]
    if not segments:
        return result
    total_length = sum(float(segment["length_m"]) for segment in segments)
    if total_length < float(settings.get("minimum_length_m", 8.0)):
        return result
    minimum_width_m = float(settings.get("minimum_width_m", 4.0))
    width_m = max(
        minimum_width_m,
        float(
            requested_width_m
            if requested_width_m > 0
            else settings.get("centerline_assumed_width_m", 6.0)
        ),
    )
    width_source = (
        requested_width_source
        if corridor_enabled and requested_width_m > 0
        else "conceptual_centerline_default"
    )
    sidewalk_width_m = _road_sidewalk_width(width_m, settings)
    weighted_center = [
        sum(float(segment["center"][axis]) * float(segment["length_m"]) for segment in segments)
        / total_length
        for axis in (0, 1)
    ]
    first = points[0]
    last = points[-1]
    dx = float(last[0]) - float(first[0])
    dy = float(last[1]) - float(first[1])
    direct_length = math.hypot(dx, dy)
    if direct_length <= 1e-9:
        dx, dy = segments[0]["axis_vector"]
        direct_length = 1.0
    global_axis = [dx / direct_length, dy / direct_length]
    # Sample the complete centerline instead of keeping only the first 64
    # source segments.  This guarantees that both endpoints reach SketchUp,
    # while retaining the existing bounded geometry budget for dense CAD
    # polylines and image-derived paths.
    maximum_frames = 64
    frame_count = min(maximum_frames, len(segments) + 1)
    frame_count = max(2, frame_count)
    target_stations = [
        total_length * index / (frame_count - 1)
        for index in range(frame_count)
    ]
    cumulative_starts = []
    cumulative = 0.0
    for segment in segments:
        cumulative_starts.append(cumulative)
        cumulative += float(segment["length_m"])

    frames = []
    segment_index = 0
    nominal_support_length = total_length / max(frame_count - 1, 1)
    for index, target_station in enumerate(target_stations):
        while (
            segment_index < len(segments) - 1
            and target_station
            > cumulative_starts[segment_index]
            + float(segments[segment_index]["length_m"])
        ):
            segment_index += 1
        segment = segments[segment_index]
        segment_start = cumulative_starts[segment_index]
        segment_length = float(segment["length_m"])
        ratio = min(
            1.0,
            max(0.0, (target_station - segment_start) / segment_length),
        )
        center = [
            float(segment["start"][axis])
            + (float(segment["end"][axis]) - float(segment["start"][axis]))
            * ratio
            for axis in (0, 1)
        ]
        axis_vector = [float(value) for value in segment["axis_vector"]]
        axis_angle = _canonical_axis_angle_deg(
            math.degrees(math.atan2(axis_vector[1], axis_vector[0]))
        )
        frames.append(
            {
                "index": index,
                "center_m": [round(float(value), 6) for value in center],
                "axis_vector": [round(float(value), 9) for value in axis_vector],
                "axis_angle_deg": round(float(axis_angle), 6),
                "width_m": round(width_m, 3),
                "half_width_m": round(width_m / 2.0, 3),
                "support_length_m": round(nominal_support_length, 3),
                "station_m": round(target_station - total_length / 2.0, 3),
            }
        )
    global_angle = _canonical_axis_angle_deg(
        math.degrees(math.atan2(global_axis[1], global_axis[0]))
    )
    curvature = max(
        _axis_angle_difference_deg(global_angle, float(segment["axis_angle_deg"]))
        for segment in segments
    )
    return {
        **result,
        "eligible": True,
        "classification": (
            "explicit_centerline_conceptual_corridor"
            if corridor_enabled
            else "explicit_centerline_assist"
        ),
        "geometry_confidence": 0.78,
        "local_tangent_supported": True,
        "detail_geometry_supported": bool(corridor_enabled),
        "detail_geometry": (
            "centerline_local_frame_strips"
            if corridor_enabled
            else "orientation_only"
        ),
        "width_source": width_source,
        "center_m": [round(float(value), 6) for value in weighted_center],
        "long_axis_angle_deg": round(global_angle, 6),
        "long_axis_vector": [round(float(value), 9) for value in global_axis],
        "length_m": round(total_length, 3),
        "width_m": round(width_m, 3),
        "sidewalk_width_each_side_m": round(sidewalk_width_m, 3),
        "carriageway_width_m": round(width_m - sidewalk_width_m * 2.0, 3),
        "sidewalk_band_count": (
            2 if corridor_enabled and sidewalk_width_m > 0 else 0
        ),
        "curvature_angle_deg": round(curvature, 3),
        "frames": frames,
        "source_vertex_count": len(points),
        "source_segment_count": len(segments),
        "frame_sampling_mode": "full_path_arc_length_resampled",
        "full_path_coverage_ratio": 1.0,
        "source_segments_truncated": 0,
    }


def _road_geometry_hint(
    points: Sequence[Sequence[float]],
    style: Mapping[str, Any],
    *,
    closed: bool = True,
    centerline_allowed: bool = False,
    centerline_corridor_enabled: bool = False,
    centerline_width_m: float = 0.0,
    centerline_width_source: str = "user_centerline_width",
    centerline_confidence: float | None = None,
    source_type: str = "",
    layer_name: str = "",
) -> dict[str, Any]:
    """Estimate bounded road details for UI/reporting without changing geometry."""
    result: dict[str, Any] = {
        "eligible": False,
        "shape": "irregular",
        "classification": "unclassified",
        "geometry_confidence": 0.0,
        "local_tangent_supported": False,
        "width_source": "not_available",
        "sidewalk_band_count": 0,
        "edge_line_count": 0,
        "direction_arrow_count": 0,
        "center_dash_count": 0,
        "street_light_count": 0,
        "end_curbs_suppressed": bool(
            style.get("edge_profile", {}).get("skip_short_ends")
        ),
    }
    settings = style.get("road_design", {})
    if not isinstance(settings, Mapping) or not settings.get("enabled"):
        return result
    if not closed:
        return (
            _road_centerline_hint(
                points,
                settings,
                corridor_enabled=centerline_corridor_enabled,
                requested_width_m=centerline_width_m,
                requested_width_source=centerline_width_source,
                source_confidence=centerline_confidence,
            )
            if centerline_allowed
            else result
        )
    if _is_roundabout_layer(layer_name) and source_type in {
        "CIRCLE",
        "ELLIPSE",
        "LWPOLYLINE",
        "POLYLINE",
        "SPLINE",
    }:
        roundabout_hint = _roundabout_geometry_hint(points, settings)
        if roundabout_hint:
            return {**result, **roundabout_hint}
    if len(points) != 4:
        if settings.get("curved_geometry_enabled", True) is not True:
            return result
        curved_hint = _road_local_tangent_frames(points, settings)
        if curved_hint:
            return {**result, **curved_hint}
        return result

    xy = [(float(point[0]), float(point[1])) for point in points]
    edges: list[tuple[float, int]] = []
    for index, first in enumerate(xy):
        second = xy[(index + 1) % 4]
        edges.append((math.hypot(second[0] - first[0], second[1] - first[1]), index))
    length, long_index = max(edges)
    opposite = edges[(long_index + 2) % 4][0]
    width_a = edges[(long_index + 1) % 4][0]
    width_b = edges[(long_index + 3) % 4][0]
    if min(length, opposite, width_a, width_b) <= 0:
        return result
    if min(length, opposite) / max(length, opposite) < 0.82:
        return result
    if min(width_a, width_b) / max(width_a, width_b) < 0.72:
        return result
    for index, point in enumerate(xy):
        previous = xy[(index - 1) % 4]
        following = xy[(index + 1) % 4]
        first_vector = (previous[0] - point[0], previous[1] - point[1])
        second_vector = (following[0] - point[0], following[1] - point[1])
        first_length = math.hypot(*first_vector)
        second_length = math.hypot(*second_vector)
        cosine = (
            first_vector[0] * second_vector[0]
            + first_vector[1] * second_vector[1]
        ) / (first_length * second_length)
        if abs(cosine) > 0.24:
            return result

    length_m = (length + opposite) / 2.0
    width_m = (width_a + width_b) / 2.0
    if length_m < float(settings.get("minimum_length_m", 8.0)):
        return result
    if width_m < float(settings.get("minimum_width_m", 4.0)):
        return result

    if width_m < 5.5:
        classification = "narrow_shared"
    elif width_m < 10.0:
        classification = "two_way_local"
    else:
        classification = "complete_street"

    long_first = xy[long_index]
    long_second = xy[(long_index + 1) % 4]
    long_axis_angle_deg = _canonical_axis_angle_deg(
        math.degrees(
            math.atan2(
                long_second[1] - long_first[1],
                long_second[0] - long_first[0],
            )
        )
    )
    long_axis_radians = math.radians(long_axis_angle_deg)
    road_center = (
        sum(point[0] for point in xy) / len(xy),
        sum(point[1] for point in xy) / len(xy),
    )

    sidewalk_width_m = _road_sidewalk_width(width_m, settings)

    marking = style.get("lane_marking", {})
    center_dash_count = 0
    if (
        isinstance(marking, Mapping)
        and marking.get("enabled")
        and width_m >= float(marking.get("minimum_road_width_m", 5.5))
    ):
        dash_m = float(marking.get("dash_length_m", 3.0))
        gap_m = float(marking.get("gap_length_m", 3.0))
        available_m = length_m - float(marking.get("margin_m", 2.0)) * 2
        if available_m >= dash_m:
            center_dash_count = max(
                1,
                math.floor((available_m + gap_m) / (dash_m + gap_m)),
            )
            center_dash_count = min(
                center_dash_count,
                int(marking.get("max_dashes", 80)),
            )

    edge = settings.get("edge_marking", {})
    edge_line_count = 2 if isinstance(edge, Mapping) and edge.get("enabled") else 0
    arrow = settings.get("direction_arrow", {})
    arrow_count = 0
    if (
        isinstance(arrow, Mapping)
        and arrow.get("enabled")
        and width_m >= float(arrow.get("minimum_road_width_m", 6.0))
        and length_m >= float(arrow.get("minimum_road_length_m", 20.0))
    ):
        available_m = length_m - float(arrow.get("end_margin_m", 8.0)) * 2
        if available_m > 0:
            max_total = min(
                int(arrow.get("max_per_surface", 6)),
                int(settings.get("geometry_budget", {}).get("max_arrows", 6)),
            )
            per_lane = min(
                max(1, math.floor(available_m / float(arrow.get("spacing_m", 30.0))) + 1),
                max_total // 2,
            )
            arrow_count = per_lane * 2

    street_light_count = 0
    street_lights = style.get("street_lights", {})
    if isinstance(street_lights, Mapping) and street_lights.get("enabled"):
        minimum_m = float(street_lights.get("minimum_edge_length_m", 24.0))
        if length_m >= minimum_m:
            available_m = length_m - float(street_lights.get("end_margin_m", 6.0)) * 2
            if available_m > 0:
                per_side = max(
                    1,
                    math.floor(available_m / float(street_lights.get("spacing_m", 18.0))) + 1,
                )
                street_light_count = min(
                    per_side * 2,
                    int(street_lights.get("max_instances", 12)),
                )

    return {
        **result,
        "eligible": True,
        "shape": "near_rectangular",
        "classification": classification,
        "geometry_confidence": 0.96,
        "local_tangent_supported": False,
        "width_source": "paired_rectangle_edges",
        "center_m": [round(road_center[0], 6), round(road_center[1], 6)],
        "long_axis_angle_deg": round(long_axis_angle_deg, 6),
        "long_axis_vector": [
            round(math.cos(long_axis_radians), 9),
            round(math.sin(long_axis_radians), 9),
        ],
        "length_m": round(length_m, 3),
        "width_m": round(width_m, 3),
        "sidewalk_width_each_side_m": round(sidewalk_width_m, 3),
        "carriageway_width_m": round(width_m - sidewalk_width_m * 2, 3),
        "sidewalk_band_count": 2 if sidewalk_width_m > 0 else 0,
        "edge_line_count": edge_line_count,
        "direction_arrow_count": arrow_count,
        "center_dash_count": center_dash_count,
        "street_light_count": street_light_count,
    }


def _component_reference(
    asset_id: str,
    *,
    target_bounds_m: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Return the small, auditable subset needed by the SketchUp extension."""
    component = get_sketchup_component(asset_id)
    source_bounds = [round(float(value), 6) for value in component["source_bounds_m"]]
    target_bounds = target_bounds_m or component["target_bounds_m"]
    result = {
        "asset_id": component["asset_id"],
        "skp_file": component["skp_file"],
        "source_id": component["source_id"],
        "license": "CC0-1.0",
        "source_bounds_m": source_bounds,
        "target_bounds_m": [round(float(value), 6) for value in target_bounds],
        "instance_budget": int(component["instance_budget"]),
    }
    if component.get("native_generator"):
        result["native_generator"] = str(component["native_generator"])
    if asset_id == "road_crossing":
        rule = get_modeling_road_facility_rule("crosswalk")
        result["facility_rendering"] = {
            "stripe_count": int(rule["stripe_count"]),
            "stripe_half_width_fraction": float(
                rule["stripe_half_width_fraction"]
            ),
            "stripe_half_length_fraction": float(
                rule["stripe_half_length_fraction"]
            ),
            "stripe_spacing_fraction": float(rule["stripe_spacing_fraction"]),
            "surface_offset_m": float(rule["surface_offset_m"]),
            "hide_source_mesh_edges": bool(rule["hide_source_mesh_edges"]),
            "mask_underlying_markings": bool(rule["mask_underlying_markings"]),
        }
    return result


def _is_tree_symbol_block(block_name: str) -> bool:
    """Recognise leaf tree symbols without promoting rows/clusters twice."""
    normalized = "".join(
        character if character.isalnum() else "_"
        for character in str(block_name or "").upper()
    )
    if any(token in normalized for token in ("CLUSTER", "GROUP", "ROW", "ARRAY")):
        return False
    return (
        normalized in {"TREE", "TREE_SYMBOL", "PT_TREE"}
        or normalized.startswith("PT_TREE_")
        or normalized.startswith("TREE_")
        or "_TREE_" in normalized
    )


def _object_geometry_points(objects: Sequence[Mapping[str, Any]]) -> Iterable[tuple[float, float, float]]:
    for item in objects:
        for point in item.get("points_m", []):
            if isinstance(point, Sequence) and len(point) >= 3:
                yield float(point[0]), float(point[1]), float(point[2])
        children = item.get("children", [])
        if isinstance(children, Sequence):
            yield from _object_geometry_points(children)


def _procedural_tree_settings(
    block_name: str,
    role: str,
    children: Sequence[Mapping[str, Any]],
    detail_level: str,
    stable_key: str,
) -> dict[str, Any] | None:
    """Describe a shared low-poly tree proxy inferred from a CAD symbol."""
    vegetation_rule = get_modeling_vegetation_rule(detail_level)
    if vegetation_rule is None or role != "green" or not _is_tree_symbol_block(block_name):
        return None
    points = list(_object_geometry_points(children))
    if len(points) < 3:
        return None
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_z = min(point[2] for point in points)
    inferred_radius = max((max_x - min_x) / 2.0, (max_y - min_y) / 2.0)
    if not math.isfinite(inferred_radius) or inferred_radius <= 0:
        return None

    # Quantising dimensions encourages component-definition reuse across a
    # tree row instead of producing one unique definition per noisy CAD block.
    quantization = float(vegetation_rule["radius_quantization_m"])
    canopy_radius = round(
        max(
            float(vegetation_rule["minimum_canopy_radius_m"]),
            min(float(vegetation_rule["maximum_canopy_radius_m"]), inferred_radius),
        )
        / quantization
    ) * quantization
    trunk_height = round(
        max(
            float(vegetation_rule["minimum_trunk_height_m"]),
            min(
                float(vegetation_rule["maximum_trunk_height_m"]),
                canopy_radius * float(vegetation_rule["trunk_height_factor"]),
            ),
        ),
        1,
    )
    canopy_height = round(
        max(
            float(vegetation_rule["minimum_canopy_height_m"]),
            min(
                float(vegetation_rule["maximum_canopy_height_m"]),
                canopy_radius * float(vegetation_rule["canopy_height_factor"]),
            ),
        ),
        1,
    )
    trunk_radius = round(
        max(
            float(vegetation_rule["minimum_trunk_radius_m"]),
            min(
                float(vegetation_rule["maximum_trunk_radius_m"]),
                canopy_radius * float(vegetation_rule["trunk_radius_factor"]),
            ),
        ),
        2,
    )
    variation = int(hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:8], 16)
    scale_min = float(vegetation_rule["variation_scale_min"])
    scale_max = float(vegetation_rule["variation_scale_max"])
    variation_steps = int(vegetation_rule["variation_steps"])
    scale_step = (scale_max - scale_min) / max(1, variation_steps - 1)
    knowledge = sketchup_modeling_knowledge_summary()
    component_rule = get_component_placement_rule("tree")
    tree_asset_id = str(
        component_rule["large_asset_id"]
        if canopy_radius >= float(component_rule["large_radius_threshold_m"])
        else component_rule["small_asset_id"]
    )
    return {
        "enabled": True,
        "type": "tree",
        "center_m": [round(center_x, 6), round(center_y, 6), round(center_z, 6)],
        "canopy_radius_m": canopy_radius,
        "trunk_radius_m": trunk_radius,
        "trunk_height_m": trunk_height,
        "canopy_height_m": canopy_height,
        "segments": int(vegetation_rule["segments"]),
        "canopy_tiers": int(vegetation_rule["canopy_tiers"]),
        "rotation_deg": variation % 360,
        "scale_factor": round(
            scale_min + ((variation >> 8) % variation_steps) * scale_step,
            2,
        ),
        "detail_level": detail_level,
        "component_library": _component_reference(
            tree_asset_id,
            target_bounds_m=[
                canopy_radius * 2.0,
                canopy_radius * 2.0,
                trunk_height + canopy_height,
            ],
        ),
        "knowledge_rule": {
            "id": knowledge["id"],
            "version": knowledge["version"],
        },
    }


def _library_symbol_settings(
    block_name: str,
    children: Sequence[Mapping[str, Any]],
    stable_key: str,
    insert_rotation_deg: float = 0.0,
) -> dict[str, Any] | None:
    """Map explicit CAD block aliases to curated reusable site components."""
    normalized = str(block_name or "").strip().upper()
    component = next(
        (
            item
            for item in load_sketchup_component_catalog()["components"]
            if normalized
            in {str(alias).strip().upper() for alias in item.get("block_aliases", [])}
        ),
        None,
    )
    if component is None:
        return None
    points = list(_object_geometry_points(children))
    if not points:
        return None
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    variation = int(hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:8], 16)
    component_role = str(component.get("role"))
    cad_rotation_deg = float(insert_rotation_deg) % 360.0
    rotation_deg = (
        cad_rotation_deg
        if component.get("preserve_cad_rotation")
        or component_role in {"road_crossing", "traffic_light"}
        else float(variation % 360)
    )
    result = {
        "enabled": True,
        "type": "library_component",
        "center_m": [
            round((min_x + max_x) / 2.0, 6),
            round((min_y + max_y) / 2.0, 6),
            round(min(point[2] for point in points), 6),
        ],
        "rotation_deg": round(rotation_deg % 360, 6),
        "component_library": _component_reference(str(component["asset_id"])),
    }
    if component_role == "road_crossing":
        crosswalk_rule = get_modeling_road_facility_rule("crosswalk")
        manual_tokens = {
            str(token).strip().upper()
            for token in crosswalk_rule["manual_rotation_block_tokens"]
        }
        manual = any(token in normalized for token in manual_tokens)
        result.update(
            {
                "cad_rotation_deg": round(cad_rotation_deg, 6),
                "orientation_mode": (
                    "manual_cad_rotation" if manual else "auto_nearest_road"
                ),
                "orientation_source": (
                    "cad_rotation_manual" if manual else "pending_road_match"
                ),
            }
        )
    return result


def _walk_handoff_objects(
    objects: Sequence[Mapping[str, Any]],
) -> Iterable[Mapping[str, Any]]:
    for item in objects:
        yield item
        children = item.get("children", [])
        if isinstance(children, list):
            yield from _walk_handoff_objects(children)


def _axis_angle_difference_deg(first: float, second: float) -> float:
    difference = abs((float(first) - float(second)) % 180.0)
    return min(difference, 180.0 - difference)


def _road_candidates_for_crosswalk(
    center: Sequence[float],
    roads: Sequence[Mapping[str, Any]],
    maximum_distance_m: float,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    center_x, center_y = float(center[0]), float(center[1])
    for road in roads:
        hint = road["hint"]
        frames = hint.get("frames", [])
        if hint.get("local_tangent_supported") is True and isinstance(frames, list):
            valid_frames: list[dict[str, Any]] = []
            for frame in frames:
                frame_center = frame.get("center_m", [])
                axis = frame.get("axis_vector", [])
                width_m = float(frame.get("width_m", hint.get("width_m", 0.0)))
                if len(frame_center) != 2 or len(axis) != 2 or width_m <= 0:
                    continue
                valid_frames.append(
                    {
                        "frame": frame,
                        "center": [float(frame_center[0]), float(frame_center[1])],
                        "axis": [float(axis[0]), float(axis[1])],
                        "width_m": width_m,
                    }
                )

            local_candidates: list[dict[str, Any]] = []
            for pair_index, (first_frame, second_frame) in enumerate(
                zip(valid_frames, valid_frames[1:])
            ):
                start_x, start_y = first_frame["center"]
                end_x, end_y = second_frame["center"]
                segment_x = end_x - start_x
                segment_y = end_y - start_y
                segment_length_squared = segment_x**2 + segment_y**2
                if segment_length_squared <= 1e-12:
                    continue
                ratio = min(
                    1.0,
                    max(
                        0.0,
                        (
                            (center_x - start_x) * segment_x
                            + (center_y - start_y) * segment_y
                        )
                        / segment_length_squared,
                    ),
                )
                closest_x = start_x + segment_x * ratio
                closest_y = start_y + segment_y * ratio
                distance_m = math.hypot(center_x - closest_x, center_y - closest_y)
                width_m = (
                    float(first_frame["width_m"]) * (1.0 - ratio)
                    + float(second_frame["width_m"]) * ratio
                )
                half_width_m = max(width_m / 2.0, 1e-6)
                outside_distance_m = max(0.0, distance_m - half_width_m)
                if outside_distance_m > maximum_distance_m:
                    continue
                normalized_lateral = distance_m / half_width_m
                # The segment projection supplies continuous spatial coverage,
                # while the nearest source frame retains the established local
                # road-axis orientation on paired curved-road boundaries.
                orientation_frame = min(
                    (first_frame, second_frame),
                    key=lambda item: math.dist(
                        [center_x, center_y], item["center"]
                    ),
                )
                tangent = orientation_frame["axis"]
                tangent_angle = _canonical_axis_angle_deg(
                    math.degrees(math.atan2(tangent[1], tangent[0]))
                )
                first_station = float(first_frame["frame"].get("station_m", 0.0))
                second_station = float(second_frame["frame"].get("station_m", 0.0))
                station_m = first_station + (second_station - first_station) * ratio
                local_candidates.append(
                    {
                        **road,
                        "inside": distance_m <= half_width_m,
                        "outside_distance_m": outside_distance_m,
                        "signed_longitudinal_m": station_m,
                        "signed_lateral_m": distance_m,
                        "normalized_lateral": normalized_lateral,
                        "normalized_longitudinal": 0.0,
                        "local_tangent_angle_deg": float(tangent_angle),
                        "local_frame_index": int(
                            orientation_frame["frame"].get("index", pair_index)
                        ),
                        "local_frame_segment_index": pair_index,
                        "road_width_source": hint.get("width_source", "unknown"),
                        "geometry_match": hint.get("shape", "unknown"),
                    }
                )

            # One candidate per road avoids adjacent frames of the same road
            # masking an actual intersection ambiguity.  Segment projection
            # also covers the complete span between sparse endpoint frames.
            if local_candidates:
                local_candidates.sort(
                    key=lambda item: (
                        0 if item["inside"] else 1,
                        round(float(item["outside_distance_m"]), 9),
                        round(float(item["normalized_lateral"]), 9),
                        abs(float(item["signed_longitudinal_m"])),
                        int(item["local_frame_segment_index"]),
                    )
                )
                candidates.append(local_candidates[0])
                continue

            # Degenerate one-frame hints retain the former point-distance
            # fallback.  Normal full-path centerlines always have >=2 frames.
            if valid_frames:
                frame_data = valid_frames[0]
                frame = frame_data["frame"]
                distance_m = math.dist(
                    [center_x, center_y], frame_data["center"]
                )
                half_width_m = max(float(frame_data["width_m"]) / 2.0, 1e-6)
                outside_distance_m = max(0.0, distance_m - half_width_m)
                if outside_distance_m <= maximum_distance_m:
                    candidates.append(
                        {
                            **road,
                            "inside": distance_m <= half_width_m,
                            "outside_distance_m": outside_distance_m,
                            "signed_longitudinal_m": float(
                                frame.get("station_m", 0.0)
                            ),
                            "signed_lateral_m": distance_m,
                            "normalized_lateral": distance_m / half_width_m,
                            "normalized_longitudinal": 0.0,
                            "local_tangent_angle_deg": float(
                                frame.get(
                                    "axis_angle_deg",
                                    hint.get("long_axis_angle_deg", 0.0),
                                )
                            ),
                            "local_frame_index": int(frame.get("index", 0)),
                            "road_width_source": hint.get(
                                "width_source", "unknown"
                            ),
                            "geometry_match": hint.get("shape", "unknown"),
                        }
                    )
            continue
        road_center = hint.get("center_m", [])
        axis = hint.get("long_axis_vector", [])
        if len(road_center) != 2 or len(axis) != 2:
            continue
        axis_x, axis_y = float(axis[0]), float(axis[1])
        normal_x, normal_y = -axis_y, axis_x
        delta_x = center_x - float(road_center[0])
        delta_y = center_y - float(road_center[1])
        signed_longitudinal_m = delta_x * axis_x + delta_y * axis_y
        signed_lateral_m = delta_x * normal_x + delta_y * normal_y
        longitudinal_m = abs(signed_longitudinal_m)
        lateral_m = abs(signed_lateral_m)
        half_length_m = float(hint["length_m"]) / 2.0
        half_width_m = float(hint["width_m"]) / 2.0
        outside_long_m = max(0.0, longitudinal_m - half_length_m)
        outside_lateral_m = max(0.0, lateral_m - half_width_m)
        outside_distance_m = math.hypot(outside_long_m, outside_lateral_m)
        if outside_distance_m > maximum_distance_m:
            continue
        inside = outside_distance_m <= 1e-9
        normalized_lateral = lateral_m / max(half_width_m, 1e-9)
        normalized_longitudinal = longitudinal_m / max(half_length_m, 1e-9)
        candidates.append(
            {
                **road,
                "inside": inside,
                "outside_distance_m": outside_distance_m,
                "signed_longitudinal_m": signed_longitudinal_m,
                "signed_lateral_m": signed_lateral_m,
                "normalized_lateral": normalized_lateral,
                "normalized_longitudinal": normalized_longitudinal,
                "road_width_source": hint.get("width_source", "unknown"),
                "geometry_match": hint.get("shape", "unknown"),
            }
        )
    candidates.sort(
        key=lambda item: (
            0 if item["inside"] else 1,
            round(float(item["outside_distance_m"]), 9),
            round(float(item["normalized_lateral"]), 9),
            round(float(item["normalized_longitudinal"]), 9),
            str(item["object"].get("id", "")),
        )
    )
    return candidates


def _crosswalk_match_is_ambiguous(candidates: Sequence[Mapping[str, Any]]) -> bool:
    if len(candidates) < 2:
        return False
    first, second = candidates[0], candidates[1]
    if first["object"].get("id") == second["object"].get("id"):
        return False
    if not first["inside"] or not second["inside"]:
        return False
    first_angle = float(first["hint"]["long_axis_angle_deg"])
    second_angle = float(second["hint"]["long_axis_angle_deg"])
    return (
        _axis_angle_difference_deg(first_angle, second_angle) >= 30.0
        and abs(
            float(first["normalized_lateral"])
            - float(second["normalized_lateral"])
        )
        <= 0.12
        and abs(
            float(first["normalized_longitudinal"])
            - float(second["normalized_longitudinal"])
        )
        <= 0.12
    )


def _refresh_handoff_fingerprints(objects: Sequence[dict[str, Any]]) -> None:
    for item in objects:
        children = item.get("children", [])
        if isinstance(children, list):
            _refresh_handoff_fingerprints(children)
        _with_geometry_fingerprint(item)


def _align_road_facility_symbols(objects: Sequence[dict[str, Any]]) -> Counter:
    """Align crosswalk bars to a trusted road axis and keep safe fallbacks."""
    counts = Counter()
    rule = get_modeling_road_facility_rule("crosswalk")
    roads: list[dict[str, Any]] = []
    all_objects = list(_walk_handoff_objects(objects))
    for item in all_objects:
        hint = item.get("surface_style", {}).get("geometry_hint", {})
        if item.get("role") == "road" and hint.get("eligible") is True:
            roads.append({"object": item, "hint": hint})

    for item in all_objects:
        symbol = item.get("procedural_symbol", {})
        component = symbol.get("component_library", {})
        if component.get("asset_id") != "road_crossing":
            continue
        counts["road_crossing_total"] += 1
        center = symbol.get("center_m", [])
        if not isinstance(center, (list, tuple)) or len(center) < 2:
            symbol["orientation_source"] = "cad_rotation_invalid_center_fallback"
            counts["road_crossing_fallback"] += 1
            continue

        candidates = _road_candidates_for_crosswalk(
            center,
            roads,
            float(rule["road_match_max_distance_m"]),
        )
        manual = symbol.get("orientation_mode") == "manual_cad_rotation"
        ambiguous = _crosswalk_match_is_ambiguous(candidates)
        if ambiguous and not manual:
            symbol["orientation_source"] = "cad_rotation_ambiguous_intersection_fallback"
            symbol["orientation_confidence"] = 0.0
            counts["road_crossing_ambiguous"] += 1
            counts["road_crossing_fallback"] += 1
            continue
        if not candidates:
            symbol["orientation_source"] = (
                "cad_rotation_manual" if manual else "cad_rotation_unmatched_fallback"
            )
            symbol["orientation_confidence"] = 0.0
            counts[
                "road_crossing_manual" if manual else "road_crossing_fallback"
            ] += 1
            counts["road_crossing_unmatched"] += int(not manual)
            continue

        matched = candidates[0]
        local_tangent = matched.get("local_tangent_angle_deg")
        if local_tangent is not None:
            geometry_confidence = float(
                matched["hint"].get("geometry_confidence", 0.0)
            )
            if matched["inside"]:
                confidence = max(
                    0.0,
                    geometry_confidence
                    - min(1.0, float(matched["normalized_lateral"])) * 0.15,
                )
            else:
                confidence = max(
                    0.0,
                    geometry_confidence
                    * (
                        1.0
                        - float(matched["outside_distance_m"])
                        / float(rule["road_match_max_distance_m"])
                    ),
                )
        elif matched["inside"]:
            confidence = max(
                0.0,
                1.0
                - min(1.0, float(matched["normalized_lateral"])) * 0.15
                - min(1.0, float(matched["normalized_longitudinal"])) * 0.05,
            )
        else:
            confidence = max(
                0.0,
                0.75
                * (
                    1.0
                    - float(matched["outside_distance_m"])
                    / float(rule["road_match_max_distance_m"])
                ),
            )
        if confidence < float(rule["road_match_minimum_confidence"]) and not manual:
            symbol["orientation_source"] = "cad_rotation_low_confidence_fallback"
            symbol["orientation_confidence"] = round(confidence, 6)
            counts["road_crossing_fallback"] += 1
            continue

        hint = matched["hint"]
        road_angle = float(
            local_tangent
            if local_tangent is not None
            else hint["long_axis_angle_deg"]
        )
        carriageway_span_m = min(
            float(rule["maximum_carriageway_span_m"]),
            max(
                float(rule["minimum_carriageway_span_m"]),
                float(hint["carriageway_width_m"])
                + float(rule["carriageway_span_margin_m"]) * 2.0,
            ),
        )
        crossing_width_m = min(
            float(rule["maximum_crossing_width_along_road_m"]),
            max(
                float(rule["minimum_crossing_width_along_road_m"]),
                float(rule["crossing_width_along_road_m"]),
            ),
        )
        component["target_bounds_m"] = [
            round(carriageway_span_m, 6),
            round(crossing_width_m, 6),
            round(float(rule["component_thickness_m"]), 6),
        ]
        symbol.update(
            {
                "matched_road_id": matched["object"].get("id"),
                "matched_road_axis_deg": round(road_angle, 6),
                "orientation_confidence": round(confidence, 6),
                "orientation_rule": rule["orientation_rule"],
                "matched_road_geometry": matched.get(
                    "geometry_match", hint.get("shape", "unknown")
                ),
                "matched_road_local_frame_index": matched.get("local_frame_index"),
                "road_width_source": matched.get(
                    "road_width_source", hint.get("width_source", "unknown")
                ),
            }
        )
        road_style = matched["object"].get("surface_style", {})
        road_design = road_style.get("road_design", {})
        if isinstance(road_design, dict):
            zones = road_design.setdefault("exclusion_zones", [])
            zones.append(
                {
                    "type": "crosswalk",
                    "source_object_id": item.get("id"),
                    "center_longitudinal_m": round(
                        float(matched["signed_longitudinal_m"]), 6
                    ),
                    "half_length_m": round(
                        crossing_width_m / 2.0
                        + float(rule["road_detail_clearance_m"]),
                        6,
                    ),
                }
            )
            counts["road_crossing_exclusion_zone"] += 1
        if manual:
            symbol["orientation_source"] = "cad_rotation_manual_with_road_fit"
            counts["road_crossing_manual"] += 1
            continue

        symbol["rotation_deg"] = round(
            (road_angle + float(rule["rotation_offset_from_road_axis_deg"]))
            % 360.0,
            6,
        )
        symbol["orientation_source"] = (
            "matched_road_local_tangent"
            if local_tangent is not None
            else "matched_road_long_axis"
        )
        counts["road_crossing_auto_aligned"] += 1
        counts["road_crossing_local_tangent"] += int(local_tangent is not None)

    _refresh_handoff_fingerprints(objects)
    return counts


def _rendered_site_surface_count(objects: Sequence[Mapping[str, Any]]) -> int:
    """Count styled faces that the plugin will render, excluding tree source symbols."""
    count = 0
    for item in objects:
        symbol = item.get("procedural_symbol", {})
        if isinstance(symbol, Mapping) and symbol.get("enabled"):
            continue
        style = item.get("surface_style", {})
        if isinstance(style, Mapping) and style.get("enabled"):
            count += 1
        children = item.get("children", [])
        if isinstance(children, Sequence):
            count += _rendered_site_surface_count(children)
    return count


def _course_model_readiness(
    objects: Sequence[Mapping[str, Any]],
    *,
    semantic_scene_validated: bool,
    semantic_review_required_count: int,
    skipped_count: int,
) -> dict[str, Any]:
    """Build a non-normative checklist for a course-model refinement pass."""
    flattened = list(_walk_handoff_objects(objects))
    buildings = [
        item
        for item in flattened
        if item.get("role") == "building"
        and isinstance(item.get("building_parameters"), Mapping)
    ]
    extruded_buildings = [
        item for item in buildings if float(item.get("extrusion_m", 0.0) or 0.0) > 0
    ]
    height_variants = sorted(
        {
            round(float(item["building_parameters"].get("total_height_m", 0.0)), 3)
            for item in extruded_buildings
            if float(item["building_parameters"].get("total_height_m", 0.0)) > 0
        }
    )
    type_variants = sorted(
        {
            str(item["building_parameters"].get("building_type", "generic"))
            for item in buildings
        }
    )
    explicit_buildings = [
        item
        for item in buildings
        if str(item["building_parameters"].get("source", "global_default"))
        != "global_default"
    ]
    # Count editable top-level semantic objects, not the source geometry inside
    # a reusable tree/parking block, so this matches the SketchUp Outliner.
    road_count = sum(1 for item in objects if item.get("role") == "road")
    green_count = sum(1 for item in objects if item.get("role") == "green")
    parking_count = sum(1 for item in objects if item.get("role") == "parking")

    items: list[dict[str, Any]] = []

    def add_item(key: str, label: str, status: str, detail: str) -> None:
        items.append(
            {"key": key, "label": label, "status": status, "detail": detail}
        )

    add_item(
        "building_geometry",
        "建筑轮廓",
        "pass" if buildings else "missing",
        f"识别 {len(buildings)} 栋建筑" if buildings else "未识别到建筑轮廓",
    )
    height_status = (
        "pass"
        if buildings and len(extruded_buildings) == len(buildings)
        else ("review" if extruded_buildings else "missing")
    )
    add_item(
        "building_height",
        "建筑高度",
        height_status,
        f"已建三维 {len(extruded_buildings)}/{len(buildings)} 栋",
    )
    variation_needed = len(buildings) >= 4
    variation_present = len(height_variants) > 1 or len(type_variants) > 1
    add_item(
        "building_variation",
        "建筑层次",
        "pass" if not variation_needed or variation_present else "review",
        (
            f"高度 {len(height_variants)} 类、用途 {len(type_variants)} 类；"
            f"明确逐栋/图层参数 {len(explicit_buildings)} 栋"
        ),
    )
    add_item(
        "road_system",
        "道路系统",
        "pass" if road_count else "missing",
        f"道路对象 {road_count} 个" if road_count else "未生成道路对象",
    )
    add_item(
        "green_system",
        "绿化与树木",
        "pass" if green_count else "review",
        f"绿化/树木对象 {green_count} 个" if green_count else "缺少绿化表达",
    )
    add_item(
        "parking_system",
        "停车表达",
        "pass" if parking_count else "review",
        f"停车对象 {parking_count} 个" if parking_count else "缺少停车对象",
    )
    add_item(
        "source_alignment",
        "底图与语义接力",
        "pass" if semantic_scene_validated else "review",
        "语义底图已校验" if semantic_scene_validated else "普通 CAD：请人工核对底图位置",
    )
    add_item(
        "candidate_review",
        "候选对象复核",
        "pass" if semantic_review_required_count == 0 else "review",
        f"待人工复核 {semantic_review_required_count} 个候选",
    )
    add_item(
        "unsupported_geometry",
        "未交接图元",
        "pass" if skipped_count == 0 else "review",
        f"未交接 {skipped_count} 个图元",
    )

    review_items = [item for item in items if item["status"] != "pass"]
    return {
        "scope": "course_model_refinement_assistance",
        "normative": False,
        "status": "review_required" if review_items else "refinement_ready",
        "passed_count": len(items) - len(review_items),
        "item_count": len(items),
        "review_count": len(review_items),
        "items": items,
        "review_labels": [str(item["label"]) for item in review_items],
        "building_height_variant_count": len(height_variants),
        "building_type_variant_count": len(type_variants),
        "building_explicit_parameter_count": len(explicit_buildings),
        "note": "仅检查基础模型资料完整度，不代表课程评分、规范符合或设计质量。",
    }


def _normalize_building_overrides(
    values: Mapping[str, Mapping[str, Any]] | None,
    manifest: ChainManifest,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Validate per-building settings and index them by stable ID and handle."""
    if values is None:
        return {}, {}
    if not isinstance(values, Mapping):
        raise ValueError("逐栋建筑参数必须是由建筑编号索引的设置表。")

    by_id: dict[str, dict[str, Any]] = {}
    by_handle: dict[str, dict[str, Any]] = {}
    for raw_key, raw_value in values.items():
        override_key = str(raw_key or "").strip()
        if not override_key or not isinstance(raw_value, Mapping):
            raise ValueError("逐栋建筑参数中存在无效的建筑编号或设置。")
        label = str(
            raw_value.get("display_name")
            or raw_value.get("source_handle")
            or override_key
        ).strip()
        try:
            item_floors = int(raw_value.get("floors", 0))
            item_floor_height = float(raw_value.get("floor_height_m", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"建筑 {label} 的楼层数或层高不是有效数字。") from exc
        if item_floors < 0 or item_floors > 200:
            raise ValueError(f"建筑 {label} 的楼层数必须在 0 到 200 之间。")
        if (
            not math.isfinite(item_floor_height)
            or item_floor_height < 0
            or item_floor_height > 20
        ):
            raise ValueError(f"建筑 {label} 的标准层高必须在 0 到 20 米之间。")
        if item_floors > 0 and item_floor_height <= 0:
            raise ValueError(
                f"建筑 {label} 已设置为 {item_floors} 层，但没有填写大于 0 的标准层高。"
            )

        requested_type = _normalized_choice(
            str(raw_value.get("building_type", "auto")),
            _BUILDING_TYPES,
            f"建筑 {label} 的建筑类型",
        )
        item = {
            "override_key": override_key,
            "object_id": str(raw_value.get("object_id") or override_key).strip(),
            "source_handle": str(raw_value.get("source_handle") or "").strip(),
            "source_layer": str(raw_value.get("source_layer") or "").strip(),
            "display_name": label,
            "floors": item_floors,
            "floor_height_m": item_floor_height,
            "requested_building_type": requested_type,
            "building_type": _resolved_building_type(
                requested_type, manifest.project_type
            ),
            "roof_type": _normalized_choice(
                str(raw_value.get("roof_type", "flat")),
                _ROOF_TYPES,
                f"建筑 {label} 的屋顶类型",
            ),
            "model_detail_level": _normalized_choice(
                str(raw_value.get("model_detail_level", "course")),
                _MODEL_DETAIL_LEVELS,
                f"建筑 {label} 的模型精度",
            ),
        }
        by_id[override_key] = item
        if item["object_id"]:
            by_id[item["object_id"]] = item
        if item["source_handle"]:
            by_handle[item["source_handle"].upper()] = item
    return by_id, by_handle


def inspect_sketchup_buildings(
    dxf_path: Path | str,
    chain_manifest: ChainManifest | Mapping[str, Any],
    building_layers: Sequence[str] | str | None = None,
) -> dict[str, Any]:
    """List top-level closed building footprints without modifying the DXF."""
    source = Path(dxf_path).resolve()
    if not source.is_file() or source.suffix.lower() != ".dxf":
        raise FileNotFoundError(f"找不到有效的 DXF 文件：{source}")
    manifest = _as_manifest(chain_manifest)
    normalized_layers = _normalized_layers(
        building_layers
        or ("BUILDING", "CONCEPT_BUILDING", "AI_BUILDING", "BW_BUILDING_CANDIDATE")
    )
    source_hash = sha256_file(source)
    semantic_scene = load_semantic_scene_for_dxf(source)
    semantic_layer_rules = {
        str(layer).strip().upper(): dict(rule)
        for layer, rule in (semantic_scene or {}).get("layer_rules", {}).items()
        if isinstance(rule, Mapping)
    }
    doc = ezdxf.readfile(source)
    buildings: list[dict[str, Any]] = []
    for index, entity in enumerate(doc.modelspace()):
        entity_type = entity.dxftype()
        if entity_type not in _LINEWORK_TYPES:
            continue
        layer = str(entity.dxf.get("layer", "0") or "0")
        if _layer_role(layer, normalized_layers) != "building":
            continue
        if not _is_closed_linework_candidate(entity):
            continue
        handle = str(entity.dxf.get("handle", "") or f"INDEX-{index}")
        buildings.append(
            {
                "object_id": make_stable_object_id(
                    manifest.project_id, "building", f"DXF:{handle}"
                ),
                "source_handle": handle,
                "source_layer": layer,
                "source_type": entity_type,
                "display_name": f"建筑 {len(buildings) + 1:03d}",
            }
        )
    assert_file_unchanged(source, source_hash)
    return {
        "source_file": str(source),
        "source_sha256": source_hash,
        "zero_mutation_verified": True,
        "buildings": buildings,
    }


def export_sketchup_handoff(
    dxf_path: Path | str,
    output_path: Path | str,
    chain_manifest: ChainManifest | Mapping[str, Any],
    *,
    floors: int = 0,
    floor_height_m: float = 0.0,
    building_layers: Sequence[str] | str | None = None,
    include_open_linework: bool = True,
    include_blocks: bool = True,
    include_faces: bool = True,
    include_text: bool = False,
    model_detail_level: str = "course",
    road_design_preset: str = "auto",
    building_type: str = "auto",
    roof_type: str = "flat",
    incremental_update: bool = True,
    building_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    centerline_corridor: bool = False,
    centerline_width_m: float = 0.0,
    centerline_confidence_policy: str = "all",
) -> dict[str, Any]:
    """Export supported DXF geometry as a local-metre SketchUp handoff.

    ``floors=0`` is an explicit two-dimensional mode.  Positive floors require
    a positive floor height; the software never guesses a building height.
    """
    source = Path(dxf_path).resolve()
    output = Path(output_path).resolve()
    try:
        centerline_width_m = float(centerline_width_m or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("中心线道路带宽度必须是数字。") from exc
    if not math.isfinite(centerline_width_m) or centerline_width_m < 0:
        raise ValueError("中心线道路带宽度不能为负数或无穷值。")
    if centerline_width_m and not 4.0 <= centerline_width_m <= 60.0:
        raise ValueError("中心线道路带宽度应为 4 至 60 米；填写 0 表示使用知识库默认值。")
    if not source.is_file() or source.suffix.lower() != ".dxf":
        raise FileNotFoundError(f"找不到有效的 DXF 文件：{source}")
    if source == output:
        raise ValueError("SketchUp 交接文件不能覆盖原始 DXF。")
    if output.suffix.lower() != ".json" or not output.name.lower().endswith(".ptsu.json"):
        raise ValueError("SketchUp 交接文件必须使用 .ptsu.json 扩展名。")

    floors = int(floors)
    floor_height_m = float(floor_height_m)
    if floors < 0:
        raise ValueError("建筑楼层不能小于 0。")
    if not math.isfinite(floor_height_m) or floor_height_m < 0:
        raise ValueError("标准层高必须是大于或等于 0 的有限数值。")
    if floors > 0 and floor_height_m <= 0:
        raise ValueError("需要生成三维建筑时，请明确填写大于 0 的标准层高；系统不会自动猜测。")

    manifest = _as_manifest(chain_manifest)
    _validate_chain_for_sketchup(manifest)
    model_detail_level = _normalized_choice(
        model_detail_level, _MODEL_DETAIL_LEVELS, "模型精度"
    )
    road_design_preset = _normalized_choice(
        road_design_preset, _ROAD_DESIGN_PRESETS, "道路建模预设"
    )
    centerline_confidence_policy = _normalized_choice(
        centerline_confidence_policy,
        _CENTERLINE_CONFIDENCE_POLICIES,
        "道路中心线可信度策略",
    )
    requested_building_type = _normalized_choice(
        building_type, _BUILDING_TYPES, "建筑类型"
    )
    resolved_building_type = _resolved_building_type(
        requested_building_type, manifest.project_type
    )
    roof_type = _normalized_choice(roof_type, _ROOF_TYPES, "屋顶类型")
    building_layers = _normalized_layers(
        building_layers or ("BUILDING", "CONCEPT_BUILDING", "AI_BUILDING", "BW_BUILDING_CANDIDATE")
    )
    overrides_by_id, overrides_by_handle = _normalize_building_overrides(
        building_overrides, manifest
    )
    requested_override_keys = {
        item["override_key"] for item in overrides_by_id.values()
    }
    matched_override_keys: set[str] = set()

    source_hash = sha256_file(source)
    semantic_scene = load_semantic_scene_for_dxf(source)
    semantic_layer_rules = {
        str(layer).strip().upper(): dict(rule)
        for layer, rule in (semantic_scene or {}).get("layer_rules", {}).items()
        if isinstance(rule, Mapping)
    }
    doc = ezdxf.readfile(source)
    unit_code = int(get_dxf_unit_code(doc) or 0)
    unit_name = resolve_unit(unit_code, strict_check=True)
    linear_to_m = get_linear_scale_to_m(unit_name)
    flatten_distance = max(0.01 / linear_to_m, 1e-6)

    objects: list[dict[str, Any]] = []
    skipped = Counter()
    role_counts = Counter()
    type_counts = Counter()
    block_definition_counts = Counter()
    stats = Counter()
    used_detail_levels: set[str] = set()
    modelspace = doc.modelspace()
    has_image_road_centerline_candidates = any(
        _is_image_road_centerline_layer(entity.dxf.get("layer", "0"))
        for entity in modelspace
    )

    def to_local_m(point: tuple[float, float, float]) -> tuple[float, float, float]:
        project_point = tuple(float(value) * linear_to_m for value in point)
        if manifest.local_origin.enabled:
            return manifest.local_origin.to_local(*project_point)
        return project_point

    def effective_layer(entity: Any, inherited_layer: str = "0") -> str:
        layer = str(entity.dxf.get("layer", "0") or "0")
        if layer == "0" and inherited_layer != "0":
            return inherited_layer
        return layer

    def resolved_layer_role(layer: str) -> str:
        normalized = str(layer or "0").strip().upper()
        if normalized in building_layers:
            return "building"
        semantic_rule = semantic_layer_rules.get(normalized, {})
        semantic_role = str(semantic_rule.get("role", "")).strip()
        if semantic_role in _ROLE_TAGS:
            return semantic_role
        return _layer_role(layer, building_layers)

    def make_primitive(
        entity: Any,
        stable_key: str,
        inherited_layer: str = "0",
        parent_id: str | None = None,
    ) -> dict[str, Any] | None:
        entity_type = entity.dxftype()
        layer = effective_layer(entity, inherited_layer)
        role = resolved_layer_role(layer)
        handle = str(entity.dxf.get("handle", "") or stable_key)

        if entity_type in _TEXT_TYPES:
            if not include_text:
                skipped["text_disabled"] += 1
                return None
            try:
                text, source_point, source_height, rotation = _text_content_and_location(entity)
            except Exception:
                skipped[f"parse_failed:{entity_type}"] += 1
                return None
            if not text:
                skipped["empty_text"] += 1
                return None
            object_id = make_stable_object_id(manifest.project_id, "text", stable_key)
            position_m = to_local_m(source_point)
            stats["text"] += 1
            stats["geometry"] += 1
            type_counts[entity_type] += 1
            return _with_geometry_fingerprint({
                "id": object_id,
                "parent_id": parent_id,
                "source_handle": handle,
                "source_type": entity_type,
                "source_layer": layer,
                "role": role,
                "sketchup_tag": "PT_TEXT",
                "geometry_type": "text",
                "text": text,
                "position_m": [round(value, 9) for value in position_m],
                "height_m": round(source_height * linear_to_m, 6),
                "rotation_deg": round(rotation, 6),
                "closed": False,
                "extrusion_m": 0.0,
            })

        if entity_type in _FACE_TYPES and not include_faces:
            skipped["faces_disabled"] += 1
            return None
        if entity_type not in _LINEWORK_TYPES | _FACE_TYPES:
            skipped[f"unsupported:{entity_type}"] += 1
            return None
        try:
            source_points, closed = _entity_points(entity, flatten_distance)
        except Exception:
            skipped[f"parse_failed:{entity_type}"] += 1
            return None
        local_points = _deduplicate_points(to_local_m(point) for point in source_points)
        minimum = 3 if closed else 2
        if len(local_points) < minimum:
            skipped[f"insufficient_points:{entity_type}"] += 1
            return None
        if not closed and not include_open_linework:
            skipped["open_linework_disabled"] += 1
            return None

        object_id = make_stable_object_id(manifest.project_id, role, stable_key)
        horizontal = max(point[2] for point in local_points) - min(
            point[2] for point in local_points
        ) <= 1e-6
        is_building_footprint = (
            closed
            and role == "building"
            and entity_type not in _FACE_TYPES
            and horizontal
        )
        item_floors = floors
        item_floor_height = floor_height_m
        item_detail_level = model_detail_level
        item_building_type = resolved_building_type
        item_requested_building_type = requested_building_type
        item_roof_type = roof_type
        item_total_height_m: float | None = None
        layer_semantics: dict[str, Any] = {}
        parameter_source = "global_default"
        matched_override = None
        if is_building_footprint:
            stats["building_footprint"] += 1
            layer_semantics = _explicit_building_layer_semantics(layer)
            if layer_semantics:
                parameter_source = "explicit_layer_semantics"
                stats["building_layer_semantics"] += 1
                if "floors" in layer_semantics:
                    item_floors = int(layer_semantics["floors"])
                    stats["building_layer_floor_semantics"] += 1
                if "floor_height_m" in layer_semantics:
                    item_floor_height = float(layer_semantics["floor_height_m"])
                    stats["building_layer_floor_height_semantics"] += 1
                if "total_height_m" in layer_semantics:
                    item_total_height_m = float(layer_semantics["total_height_m"])
                    stats["building_layer_total_height_semantics"] += 1
                if "building_type" in layer_semantics:
                    item_requested_building_type = str(
                        layer_semantics["building_type"]
                    )
                    item_building_type = item_requested_building_type
                    stats["building_layer_type_semantics"] += 1
                if "roof_type" in layer_semantics:
                    item_roof_type = str(layer_semantics["roof_type"])
                    stats["building_layer_roof_semantics"] += 1

                # An explicit total height is authoritative.  When a floor
                # count is also explicit (or globally supplied by the user),
                # derive only the mathematical floor height needed for guides.
                # With no floor count, SketchUp receives an exact simple mass
                # and no invented storey structure.
                if item_total_height_m is not None and item_floors > 0:
                    item_floor_height = item_total_height_m / item_floors
            matched_override = overrides_by_id.get(object_id) or overrides_by_handle.get(
                handle.upper()
            )
            if matched_override is not None:
                item_floors = int(matched_override["floors"])
                item_floor_height = float(matched_override["floor_height_m"])
                item_detail_level = str(matched_override["model_detail_level"])
                item_building_type = str(matched_override["building_type"])
                item_requested_building_type = str(
                    matched_override["requested_building_type"]
                )
                item_roof_type = str(matched_override["roof_type"])
                item_total_height_m = None
                parameter_source = "building_override"
                matched_override_keys.add(str(matched_override["override_key"]))
        extrusion_m = (
            (
                item_total_height_m
                if item_total_height_m is not None
                else item_floors * item_floor_height
            )
            if is_building_footprint
            else 0.0
        )
        procedural_modeling, facade_modules, floor_guide_segments = (
            _procedural_building_settings(
                local_points,
                floors=item_floors,
                floor_height_m=item_floor_height,
                detail_level=item_detail_level,
                building_type=item_building_type,
                roof_type=item_roof_type,
            )
            if extrusion_m > 0 and item_floors > 0 and item_floor_height > 0
            else ({"enabled": False}, 0, 0)
        )
        if procedural_modeling.get("enabled"):
            used_detail_levels.add(item_detail_level)
            stats["procedural_building"] += 1
            stats["estimated_facade_module"] += facade_modules
            stats["floor_guide_segment"] += floor_guide_segments
            details = procedural_modeling.get("architectural_details", {})
            entrance = details.get("entrance", {})
            balcony = details.get("balcony", {})
            rooftop = details.get("rooftop_equipment", {})
            stats["building_entrance"] += int(bool(entrance.get("enabled")))
            if balcony.get("enabled"):
                stats["estimated_balcony"] += min(
                    int(balcony.get("max_instances", 0)),
                    max(0, item_floors - 1),
                )
            stats["rooftop_equipment"] += int(bool(rooftop.get("enabled")))
        stats["geometry"] += 1
        stats["surface_face"] += int(entity_type in _FACE_TYPES)
        stats["extruded"] += int(extrusion_m > 0)
        role_counts[role] += 1
        type_counts[entity_type] += 1
        object_data = {
            "id": object_id,
            "parent_id": parent_id,
            "source_handle": handle,
            "source_type": entity_type,
            "source_layer": layer,
            "role": role,
            "sketchup_tag": _ROLE_TAGS[role],
            "geometry_type": "face" if entity_type in _FACE_TYPES else ("polygon" if closed else "polyline"),
            "closed": bool(closed),
            "points_m": [
                [round(value, 9) for value in point] for point in local_points
            ],
            "extrusion_m": round(extrusion_m, 6),
        }
        road_centerline_object = (
            role == "road"
            and not closed
            and horizontal
            and _is_road_centerline_layer(layer)
        )
        image_road_surface_suppressed = bool(
            role == "road"
            and closed
            and horizontal
            and _is_image_road_surface_layer(layer)
            and has_image_road_centerline_candidates
            and centerline_corridor
            and centerline_confidence_policy == "trusted_only"
        )
        if image_road_surface_suppressed:
            object_data["surface_generation_suppressed"] = True
            object_data["surface_suppression_reason"] = (
                "trusted_centerline_corridor_preferred"
            )
            stats["road_surface_generation_suppressed"] += 1
        entity_centerline_width_m = (
            _entity_xdata_float(entity, "PT_ROAD_WIDTH_M")
            if road_centerline_object
            else None
        )
        entity_centerline_confidence = (
            _entity_xdata_float(entity, "PT_ROAD_CONFIDENCE")
            if road_centerline_object
            else None
        )
        centerline_review_required = bool(
            road_centerline_object
            and entity_centerline_confidence is not None
            and float(entity_centerline_confidence)
            < _ROAD_CENTERLINE_TRUST_THRESHOLD
        )
        centerline_corridor_suppressed = bool(
            centerline_corridor
            and road_centerline_object
            and centerline_confidence_policy == "trusted_only"
            and centerline_review_required
        )
        centerline_corridor_for_object = bool(
            centerline_corridor
            and road_centerline_object
            and not centerline_corridor_suppressed
        )
        if centerline_review_required:
            stats["road_centerline_review_required"] += 1
        if centerline_corridor_suppressed:
            stats["road_centerline_corridor_suppressed"] += 1
        effective_centerline_width_m = (
            centerline_width_m
            if centerline_width_m > 0
            else float(entity_centerline_width_m or 0.0)
        )
        effective_centerline_width_source = (
            "user_centerline_width"
            if centerline_width_m > 0
            else (
                "image_detected_centerline_width"
                if entity_centerline_width_m
                else "conceptual_centerline_default"
            )
        )
        surface_style = (
            _site_surface_style(role, model_detail_level, road_design_preset)
            if (
                (closed or road_centerline_object)
                and horizontal
                and not is_building_footprint
                and entity_type not in _FACE_TYPES
                and not image_road_surface_suppressed
            )
            else None
        )
        if surface_style is not None:
            if role == "road":
                road_hint = _road_geometry_hint(
                    local_points,
                    surface_style,
                    closed=closed,
                    centerline_allowed=road_centerline_object,
                    centerline_corridor_enabled=centerline_corridor_for_object,
                    centerline_width_m=(
                        effective_centerline_width_m
                        if centerline_corridor_for_object
                        else 0.0
                    ),
                    centerline_width_source=effective_centerline_width_source,
                    centerline_confidence=entity_centerline_confidence,
                    source_type=entity_type,
                    layer_name=layer,
                )
                if centerline_corridor_suppressed:
                    road_hint["corridor_requested"] = True
                    road_hint["corridor_suppressed"] = True
                    road_hint["corridor_suppression_reason"] = (
                        "source_confidence_below_threshold"
                    )
                    road_hint["corridor_confidence_threshold"] = (
                        _ROAD_CENTERLINE_TRUST_THRESHOLD
                    )
                surface_style["geometry_hint"] = road_hint
                if road_hint["eligible"] and road_hint["shape"] == "near_rectangular":
                    stats["road_design_surface"] += 1
                    stats["road_sidewalk_band"] += int(
                        road_hint["sidewalk_band_count"]
                    )
                    stats["road_edge_line"] += int(road_hint["edge_line_count"])
                    stats["road_direction_arrow"] += int(
                        road_hint["direction_arrow_count"]
                    )
                    stats["road_center_dash"] += int(
                        road_hint["center_dash_count"]
                    )
                    stats["road_street_light"] += int(
                        road_hint["street_light_count"]
                    )
                elif road_hint["eligible"] and road_hint["shape"] in {
                    "curved_strip",
                    "segmented_strip",
                }:
                    stats["road_curved_hint"] += 1
                    stats["road_local_frame"] += len(road_hint.get("frames", []))
                elif road_hint["eligible"] and road_hint["shape"] == "roundabout_ring":
                    stats["road_roundabout_hint"] += 1
                    stats["road_local_frame"] += len(road_hint.get("frames", []))
                elif road_hint["eligible"] and road_hint["shape"] == "centerline":
                    stats["road_centerline_hint"] += 1
                    stats["road_local_frame"] += len(road_hint.get("frames", []))
                elif (
                    road_hint["eligible"]
                    and road_hint["shape"] == "centerline_corridor"
                ):
                    stats["road_centerline_corridor_hint"] += 1
                    stats["road_local_frame"] += len(road_hint.get("frames", []))
                    if (
                        road_hint.get("frame_sampling_mode")
                        == "full_path_arc_length_resampled"
                    ):
                        stats["road_centerline_full_path_resampled"] += 1
            object_data["surface_style"] = surface_style
            if road_centerline_object and entity_centerline_width_m:
                object_data["centerline_width_m"] = round(
                    float(entity_centerline_width_m), 3
                )
                object_data["centerline_width_source"] = (
                    "user_centerline_width"
                    if centerline_width_m > 0
                    else "image_detected_centerline_width"
                )
            if road_centerline_object and entity_centerline_confidence is not None:
                object_data["centerline_confidence"] = round(
                    float(entity_centerline_confidence), 3
                )
                object_data["centerline_review_required"] = (
                    float(entity_centerline_confidence) < 0.65
                )
            stats["styled_site_surface"] += 1
            if surface_style.get("edge_profile", {}).get("enabled"):
                stats["site_edge_segment"] += len(local_points)
        if is_building_footprint:
            object_data["building_parameters"] = {
                "source": parameter_source,
                "floors": item_floors,
                "floor_height_m": round(item_floor_height, 6),
                "total_height_m": round(extrusion_m, 6),
                "requested_building_type": item_requested_building_type,
                "building_type": item_building_type,
                "roof_type": item_roof_type,
                "detail_level": item_detail_level,
            }
            if layer_semantics:
                object_data["building_parameters"]["layer_semantics"] = dict(
                    layer_semantics
                )
        if procedural_modeling.get("enabled"):
            object_data["procedural_modeling"] = procedural_modeling
        return _with_geometry_fingerprint(object_data)

    def make_insert_group(
        entity: Any,
        stable_key: str,
        inherited_layer: str = "0",
        parent_id: str | None = None,
        depth: int = 0,
    ) -> dict[str, Any] | None:
        if not include_blocks:
            skipped["blocks_disabled"] += 1
            return None
        if depth >= _MAX_BLOCK_DEPTH:
            skipped["block_depth_limit"] += 1
            return None
        layer = effective_layer(entity, inherited_layer)
        role = resolved_layer_role(layer)
        block_name = str(entity.dxf.get("name", "UNNAMED") or "UNNAMED")
        handle = str(entity.dxf.get("handle", "") or stable_key)
        object_id = make_stable_object_id(manifest.project_id, "block", stable_key)
        children: list[dict[str, Any]] = []

        def skipped_virtual(_entity: Any, reason: str) -> None:
            reason_key = str(reason or "unknown").strip().replace(" ", "_")[:80]
            skipped[f"block_virtual:{reason_key}"] += 1

        try:
            virtual_entities = list(
                entity.virtual_entities(skipped_entity_callback=skipped_virtual)
            )
        except Exception:
            skipped["block_parse_failed"] += 1
            return None
        for child_index, child in enumerate(virtual_entities):
            child_key = f"{stable_key}:CHILD:{child_index}:{child.dxftype()}"
            if child.dxftype() == "INSERT":
                child_object = make_insert_group(
                    child,
                    child_key,
                    layer,
                    object_id,
                    depth + 1,
                )
            else:
                child_object = make_primitive(child, child_key, layer, object_id)
            if child_object is not None:
                children.append(child_object)
        if not children:
            skipped["empty_or_unsupported_block"] += 1
            return None
        procedural_symbol = _procedural_tree_settings(
            block_name,
            role,
            children,
            model_detail_level,
            stable_key,
        )
        if procedural_symbol is None:
            procedural_symbol = _library_symbol_settings(
                block_name,
                children,
                stable_key,
                float(entity.dxf.get("rotation", 0.0) or 0.0),
            )
        stats["block"] += 1
        type_counts["INSERT"] += 1
        block_definition_counts[block_name] += 1
        object_data = {
            "id": object_id,
            "parent_id": parent_id,
            "source_handle": handle,
            "source_type": "INSERT",
            "source_layer": layer,
            "role": role,
            "sketchup_tag": _ROLE_TAGS[role],
            "geometry_type": "group",
            "block_name": block_name,
            "closed": False,
            "extrusion_m": 0.0,
            "children": children,
        }
        if procedural_symbol is not None:
            object_data["procedural_symbol"] = procedural_symbol
            if procedural_symbol.get("type") == "tree":
                stats["procedural_tree"] += 1
            else:
                stats["library_symbol"] += 1
        return _with_geometry_fingerprint(object_data)

    for index, entity in enumerate(modelspace):
        entity_type = entity.dxftype()
        handle = str(entity.dxf.get("handle", "") or f"INDEX-{index}")
        stable_key = f"DXF:{handle}"
        if is_presentation_fill_entity(entity):
            stats["presentation_fill_ignored"] += 1
            object_data = None
        elif entity_type == "INSERT":
            object_data = make_insert_group(entity, stable_key)
        elif entity_type in _SUPPORTED_TYPES:
            object_data = make_primitive(entity, stable_key)
        else:
            skipped[f"unsupported:{entity_type}"] += 1
            object_data = None
        if object_data is not None:
            objects.append(object_data)

    underlay_source_entity_count = 0
    if semantic_scene is not None:
        objects, underlay_source_entity_count = _aggregate_semantic_underlay_objects(
            objects,
            manifest.project_id,
        )
        if underlay_source_entity_count:
            stats["underlay_bundle"] = 1
            stats["underlay_source_entity"] = underlay_source_entity_count
            role_counts["underlay"] = 1
        raster_underlay = _semantic_raster_underlay_object(
            semantic_scene,
            manifest.project_id,
            to_local_m((0.0, 0.0, 0.0)),
        )
        if raster_underlay is not None:
            objects.insert(0, raster_underlay)
            stats["raster_underlay"] = 1
            role_counts["underlay"] += 1

    facility_stats = _align_road_facility_symbols(objects)
    stats.update(facility_stats)
    assert_file_unchanged(source, source_hash)
    if not objects:
        raise ValueError("DXF 中没有可交接到 SketchUp 的有效线、多段线或曲线。")
    facade_instance_budget = max(
        [int(get_modeling_detail_profile(model_detail_level)["facade_instance_budget"])]
        + [
            int(get_modeling_detail_profile(level)["facade_instance_budget"])
            for level in used_detail_levels
        ]
    )
    facade_budget_policy = "detail_profile"
    semantic_role_counts = dict(
        ((semantic_scene or {}).get("summary", {}) or {}).get("role_counts", {})
    )
    image_candidate_building_count = int(semantic_role_counts.get("building", 0))
    if facade_instance_budget > 0 and image_candidate_building_count > 0:
        adaptive_image_budget = max(
            640,
            min(2400, image_candidate_building_count * 72),
        )
        if adaptive_image_budget < facade_instance_budget:
            facade_instance_budget = adaptive_image_budget
            facade_budget_policy = "adaptive_image_candidate"
    estimated_facade_modules = min(
        int(stats["estimated_facade_module"]), facade_instance_budget
    )

    building_footprint_count = int(stats["building_footprint"])
    extruded_building_count = int(stats["extruded"])
    if extruded_building_count == 0:
        building_mode = "two_dimensional"
    elif extruded_building_count < building_footprint_count:
        building_mode = "mixed"
    else:
        building_mode = "three_dimensional"
    unmatched_override_keys = requested_override_keys - matched_override_keys
    rendered_site_surface_count = _rendered_site_surface_count(objects)

    knowledge_summary = sketchup_modeling_knowledge_summary()
    component_catalog_summary = sketchup_component_catalog_summary()
    semantic_scene_summary = dict((semantic_scene or {}).get("summary", {}))
    semantic_review_required_count = int(
        semantic_scene_summary.get("review_required_count", 0)
    )
    course_model_readiness = _course_model_readiness(
        objects,
        semantic_scene_validated=semantic_scene is not None,
        semantic_review_required_count=semantic_review_required_count,
        skipped_count=sum(skipped.values()),
    )
    payload = {
        "format": HANDOFF_FORMAT,
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "Planning Toolbox",
        "project": {
            "project_id": manifest.project_id,
            "name": manifest.name,
            "project_type": manifest.project_type,
            "crs": manifest.crs.to_dict(),
            "local_origin": manifest.local_origin.to_dict(),
        },
        "source": {
            "path": str(source),
            "sha256": source_hash,
            "dxf_insunits": unit_code,
            "dxf_unit": unit_name,
            "source_unit_to_m": linear_to_m,
        },
        "semantic_scene": {
            "validated": semantic_scene is not None,
            "path": str((semantic_scene or {}).get("file_path", "")),
            "sha256": str((semantic_scene or {}).get("file_sha256", "")),
            "review_required_count": int(
                semantic_scene_summary.get("review_required_count", 0)
            ),
            "semantic_object_count": int(
                semantic_scene_summary.get("semantic_object_count", 0)
            ),
            "underlay_entity_count": int(underlay_source_entity_count),
            "raster_underlay_count": int(stats["raster_underlay"]),
        },
        "coordinate_contract": {
            "storage_unit": "m",
            "mode": "project_to_local" if manifest.local_origin.enabled else "cad_local_identity",
            "round_trip_supported": True,
        },
        "building_settings": {
            "mode": building_mode,
            "floors": floors,
            "floor_height_m": floor_height_m,
            "total_height_m": round(floors * floor_height_m, 6),
            "building_layers": list(building_layers),
            "building_override_count": len(requested_override_keys),
            "matched_building_override_count": len(matched_override_keys),
            "unmatched_building_override_count": len(unmatched_override_keys),
            "explicit_layer_semantics_count": int(
                stats["building_layer_semantics"]
            ),
        },
        "modeling_settings": {
            "detail_level": model_detail_level,
            "road_design_preset": road_design_preset,
            "requested_building_type": requested_building_type,
            "resolved_building_type": resolved_building_type,
            "roof_type": roof_type,
            "incremental_update": bool(incremental_update),
            "preserve_locked_objects": True,
            "facade_instance_budget": facade_instance_budget,
            "site_surface_styling": model_detail_level != "massing",
            "shared_tree_components": model_detail_level != "massing",
            "architectural_detail_generation": model_detail_level != "massing",
            "site_edge_detailing": model_detail_level != "massing",
            "road_cross_section_generation": model_detail_level != "massing",
            "centerline_corridor_generation": bool(centerline_corridor),
            "centerline_confidence_policy": centerline_confidence_policy,
            "centerline_confidence_threshold": _ROAD_CENTERLINE_TRUST_THRESHOLD,
            "centerline_corridor_width_m": (
                round(centerline_width_m, 3) if centerline_width_m > 0 else None
            ),
            "bounded_road_furniture": model_detail_level == "presentation",
            "deterministic_tree_variation": model_detail_level != "massing",
            "road_local_tangent_matching": True,
            "crosswalk_auto_orientation": True,
            "crosswalk_orientation_rule": get_modeling_road_facility_rule(
                "crosswalk"
            )["orientation_rule"],
            "knowledge_base": knowledge_summary,
            "component_library": component_catalog_summary,
        },
        "course_model_readiness": course_model_readiness,
        "compatibility_settings": {
            "include_open_linework": bool(include_open_linework),
            "include_blocks": bool(include_blocks),
            "include_faces": bool(include_faces),
            "include_text": bool(include_text),
            "max_block_depth": _MAX_BLOCK_DEPTH,
        },
        "objects": objects,
        "summary": {
            "object_count": int(stats["geometry"]),
            "top_level_object_count": len(objects),
            "underlay_bundle_count": int(stats["underlay_bundle"]),
            "underlay_source_entity_count": int(stats["underlay_source_entity"]),
            "raster_underlay_count": int(stats["raster_underlay"]),
            "semantic_scene_validated": semantic_scene is not None,
            "presentation_fill_ignored_count": int(stats["presentation_fill_ignored"]),
            "semantic_review_required_count": int(
                semantic_scene_summary.get("review_required_count", 0)
            ),
            "block_count": int(stats["block"]),
            "surface_face_count": int(stats["surface_face"]),
            "text_count": int(stats["text"]),
            "procedural_building_count": int(stats["procedural_building"]),
            "procedural_tree_count": int(stats["procedural_tree"]),
            "explicit_library_symbol_count": int(stats["library_symbol"]),
            "styled_site_surface_count": rendered_site_surface_count,
            "building_entrance_count": int(stats["building_entrance"]),
            "estimated_balcony_count": int(stats["estimated_balcony"]),
            "rooftop_equipment_count": int(stats["rooftop_equipment"]),
            "site_edge_segment_count": int(stats["site_edge_segment"]),
            "road_design_surface_count": int(stats["road_design_surface"]),
            "estimated_road_sidewalk_band_count": int(stats["road_sidewalk_band"]),
            "estimated_road_edge_line_count": int(stats["road_edge_line"]),
            "estimated_road_direction_arrow_count": int(stats["road_direction_arrow"]),
            "estimated_road_center_dash_count": int(stats["road_center_dash"]),
            "estimated_road_street_light_count": int(stats["road_street_light"]),
            "road_curved_hint_count": int(stats["road_curved_hint"]),
            "road_roundabout_hint_count": int(stats["road_roundabout_hint"]),
            "road_centerline_hint_count": int(stats["road_centerline_hint"]),
            "road_centerline_corridor_hint_count": int(
                stats["road_centerline_corridor_hint"]
            ),
            "road_centerline_full_path_resampled_count": int(
                stats["road_centerline_full_path_resampled"]
            ),
            "road_centerline_review_required_count": int(
                stats["road_centerline_review_required"]
            ),
            "road_centerline_corridor_suppressed_count": int(
                stats["road_centerline_corridor_suppressed"]
            ),
            "road_surface_generation_suppressed_count": int(
                stats["road_surface_generation_suppressed"]
            ),
            "road_local_frame_count": int(stats["road_local_frame"]),
            "road_crossing_total_count": int(stats["road_crossing_total"]),
            "road_crossing_auto_aligned_count": int(
                stats["road_crossing_auto_aligned"]
            ),
            "road_crossing_manual_count": int(stats["road_crossing_manual"]),
            "road_crossing_fallback_count": int(stats["road_crossing_fallback"]),
            "road_crossing_ambiguous_count": int(stats["road_crossing_ambiguous"]),
            "road_crossing_unmatched_count": int(stats["road_crossing_unmatched"]),
            "road_crossing_exclusion_zone_count": int(
                stats["road_crossing_exclusion_zone"]
            ),
            "road_crossing_local_tangent_count": int(
                stats["road_crossing_local_tangent"]
            ),
            "estimated_facade_module_count": estimated_facade_modules,
            "potential_facade_module_count": int(stats["estimated_facade_module"]),
            "floor_guide_segment_count": int(stats["floor_guide_segment"]),
            "building_footprint_count": building_footprint_count,
            "building_override_count": len(requested_override_keys),
            "matched_building_override_count": len(matched_override_keys),
            "unmatched_building_override_count": len(unmatched_override_keys),
            "unmatched_building_override_keys": sorted(unmatched_override_keys),
            "building_layer_semantics_count": int(
                stats["building_layer_semantics"]
            ),
            "building_layer_floor_semantics_count": int(
                stats["building_layer_floor_semantics"]
            ),
            "building_layer_floor_height_semantics_count": int(
                stats["building_layer_floor_height_semantics"]
            ),
            "building_layer_total_height_semantics_count": int(
                stats["building_layer_total_height_semantics"]
            ),
            "building_layer_type_semantics_count": int(
                stats["building_layer_type_semantics"]
            ),
            "building_layer_roof_semantics_count": int(
                stats["building_layer_roof_semantics"]
            ),
            "course_model_readiness_status": course_model_readiness["status"],
            "course_model_readiness_passed_count": course_model_readiness[
                "passed_count"
            ],
            "course_model_readiness_review_count": course_model_readiness[
                "review_count"
            ],
            "block_definition_counts": dict(sorted(block_definition_counts.items())),
            "role_counts": dict(sorted(role_counts.items())),
            "entity_type_counts": dict(sorted(type_counts.items())),
            "skipped_count": sum(skipped.values()),
            "skipped_reasons": dict(sorted(skipped.items())),
        },
    }
    if facade_budget_policy == "adaptive_image_candidate":
        payload["modeling_settings"]["facade_budget_policy"] = facade_budget_policy
        payload["modeling_settings"][
            "image_candidate_building_count"
        ] = image_candidate_building_count
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "task_type": "sketchup_export",
        "source_file": str(source),
        "source_sha256": source_hash,
        "zero_mutation_verified": True,
        "handoff_file": str(output),
        "object_count": int(stats["geometry"]),
        "top_level_object_count": len(objects),
        "underlay_bundle_count": int(stats["underlay_bundle"]),
        "underlay_source_entity_count": int(stats["underlay_source_entity"]),
        "raster_underlay_count": int(stats["raster_underlay"]),
        "semantic_scene_validated": semantic_scene is not None,
        "semantic_scene_file": str((semantic_scene or {}).get("file_path", "")),
        "presentation_fill_ignored_count": int(stats["presentation_fill_ignored"]),
        "semantic_review_required_count": int(
            semantic_scene_summary.get("review_required_count", 0)
        ),
        "block_count": int(stats["block"]),
        "surface_face_count": int(stats["surface_face"]),
        "text_count": int(stats["text"]),
        "procedural_building_count": int(stats["procedural_building"]),
        "procedural_tree_count": int(stats["procedural_tree"]),
        "explicit_library_symbol_count": int(stats["library_symbol"]),
        "styled_site_surface_count": rendered_site_surface_count,
        "building_entrance_count": int(stats["building_entrance"]),
        "estimated_balcony_count": int(stats["estimated_balcony"]),
        "rooftop_equipment_count": int(stats["rooftop_equipment"]),
        "site_edge_segment_count": int(stats["site_edge_segment"]),
        "road_design_surface_count": int(stats["road_design_surface"]),
        "estimated_road_sidewalk_band_count": int(stats["road_sidewalk_band"]),
        "estimated_road_edge_line_count": int(stats["road_edge_line"]),
        "estimated_road_direction_arrow_count": int(stats["road_direction_arrow"]),
        "estimated_road_center_dash_count": int(stats["road_center_dash"]),
        "estimated_road_street_light_count": int(stats["road_street_light"]),
        "road_curved_hint_count": int(stats["road_curved_hint"]),
        "road_roundabout_hint_count": int(stats["road_roundabout_hint"]),
        "road_centerline_hint_count": int(stats["road_centerline_hint"]),
        "road_centerline_corridor_hint_count": int(
            stats["road_centerline_corridor_hint"]
        ),
        "road_centerline_full_path_resampled_count": int(
            stats["road_centerline_full_path_resampled"]
        ),
        "road_centerline_review_required_count": int(
            stats["road_centerline_review_required"]
        ),
        "road_centerline_corridor_suppressed_count": int(
            stats["road_centerline_corridor_suppressed"]
        ),
        "road_surface_generation_suppressed_count": int(
            stats["road_surface_generation_suppressed"]
        ),
        "centerline_confidence_policy": centerline_confidence_policy,
        "centerline_confidence_threshold": _ROAD_CENTERLINE_TRUST_THRESHOLD,
        "centerline_corridor_width_m": (
            round(centerline_width_m, 3) if centerline_width_m > 0 else None
        ),
        "road_local_frame_count": int(stats["road_local_frame"]),
        "road_crossing_total_count": int(stats["road_crossing_total"]),
        "road_crossing_auto_aligned_count": int(stats["road_crossing_auto_aligned"]),
        "road_crossing_manual_count": int(stats["road_crossing_manual"]),
        "road_crossing_fallback_count": int(stats["road_crossing_fallback"]),
        "road_crossing_ambiguous_count": int(stats["road_crossing_ambiguous"]),
        "road_crossing_unmatched_count": int(stats["road_crossing_unmatched"]),
        "road_crossing_exclusion_zone_count": int(
            stats["road_crossing_exclusion_zone"]
        ),
        "road_crossing_local_tangent_count": int(
            stats["road_crossing_local_tangent"]
        ),
        "estimated_facade_module_count": estimated_facade_modules,
        "facade_instance_budget": facade_instance_budget,
        "facade_budget_policy": facade_budget_policy,
        "potential_facade_module_count": int(stats["estimated_facade_module"]),
        "floor_guide_segment_count": int(stats["floor_guide_segment"]),
        "block_definition_counts": dict(sorted(block_definition_counts.items())),
        "building_count": int(role_counts.get("building", 0)),
        "building_footprint_count": building_footprint_count,
        "extruded_building_count": extruded_building_count,
        "building_mode": building_mode,
        "building_override_count": len(requested_override_keys),
        "matched_building_override_count": len(matched_override_keys),
        "unmatched_building_override_count": len(unmatched_override_keys),
        "unmatched_building_override_keys": sorted(unmatched_override_keys),
        "building_layer_semantics_count": int(stats["building_layer_semantics"]),
        "building_layer_floor_semantics_count": int(
            stats["building_layer_floor_semantics"]
        ),
        "building_layer_floor_height_semantics_count": int(
            stats["building_layer_floor_height_semantics"]
        ),
        "building_layer_total_height_semantics_count": int(
            stats["building_layer_total_height_semantics"]
        ),
        "building_layer_type_semantics_count": int(
            stats["building_layer_type_semantics"]
        ),
        "building_layer_roof_semantics_count": int(
            stats["building_layer_roof_semantics"]
        ),
        "course_model_readiness": course_model_readiness,
        "course_model_readiness_status": course_model_readiness["status"],
        "course_model_readiness_passed_count": course_model_readiness["passed_count"],
        "course_model_readiness_review_count": course_model_readiness["review_count"],
        "skipped_count": sum(skipped.values()),
        "skipped_reasons": dict(sorted(skipped.items())),
        "floors": floors,
        "floor_height_m": floor_height_m,
        "model_detail_level": model_detail_level,
        "road_design_preset": road_design_preset,
        "building_type": resolved_building_type,
        "roof_type": roof_type,
        "modeling_knowledge_id": knowledge_summary["id"],
        "modeling_knowledge_version": knowledge_summary["version"],
        "modeling_knowledge_source_count": knowledge_summary["source_count"],
        "component_library_id": component_catalog_summary["id"],
        "component_library_version": component_catalog_summary["version"],
        "bundled_component_count": component_catalog_summary["component_count"],
        "bundled_component_total_bytes": component_catalog_summary["total_bytes"],
        "incremental_update": bool(incremental_update),
        "local_origin_enabled": manifest.local_origin.enabled,
        "project_crs": manifest.crs.identifier,
        "output_files": [
            ("SketchUp 模型交接文件", str(output)),
            *(
                [("全链路语义场景 JSON", str(semantic_scene["file_path"]))]
                if semantic_scene is not None
                else []
            ),
        ],
    }
    quality_baseline = write_cad_to_sketchup_quality_baseline(result)
    result["quality_baseline_file"] = quality_baseline["path"]
    result["quality_baseline"] = quality_baseline
    result["output_files"].append(("CAD 转 SketchUp 质量基线 JSON", quality_baseline["path"]))
    return result


__all__ = [
    "HANDOFF_FORMAT",
    "HANDOFF_SCHEMA_VERSION",
    "export_sketchup_handoff",
    "inspect_sketchup_buildings",
]
