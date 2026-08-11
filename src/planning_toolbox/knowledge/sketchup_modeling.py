"""Validated access to the lightweight SketchUp urban-modeling rule base.

The asset deliberately contains no images, model files or learned weights.  It
stores small deterministic rules with source and licence metadata so CAD-to-SU
generation stays reviewable, package-friendly and usable without an API.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from importlib import resources
import json
import math
from typing import Any, Mapping


MODELING_KNOWLEDGE_SCHEMA_VERSION = 1
_ASSET_NAME = "sketchup_modeling_rules.json"
_DETAIL_LEVELS = {"massing", "course", "presentation"}
_BUILDING_TYPES = {"generic", "residential", "office", "commercial", "campus"}
_SITE_ROLES = {"green", "road", "parking", "water"}


def _positive_number(value: Any, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"建模知识库字段 {label} 不是有效数值。")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"建模知识库字段 {label} 不是有效数值。") from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        condition = "非负" if allow_zero else "正数"
        raise ValueError(f"建模知识库字段 {label} 必须是{condition}。")
    return number


def _validate_knowledge(data: Mapping[str, Any]) -> None:
    if int(data.get("schema_version", 0)) != MODELING_KNOWLEDGE_SCHEMA_VERSION:
        raise ValueError("建模知识库版本不受当前 Planning Toolbox 支持。")
    if not str(data.get("knowledge_id", "")).strip() or not str(data.get("version", "")).strip():
        raise ValueError("建模知识库缺少编号或版本。")
    if data.get("normative") is not False:
        raise ValueError("建模知识库必须明确标记为非规范性学习辅助规则。")
    storage = data.get("storage_policy", {})
    if not isinstance(storage, Mapping) or any(
        bool(storage.get(key))
        for key in ("embedded_images", "embedded_models", "model_weights")
    ):
        raise ValueError("轻量建模知识库不得内嵌图片、模型或模型权重。")

    sources = data.get("sources", [])
    if not isinstance(sources, list) or len(sources) < 4:
        raise ValueError("建模知识库缺少足够的可追溯参考来源。")
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise ValueError(f"建模知识库来源 {index + 1} 格式无效。")
        for key in ("id", "title", "url", "license", "confidence"):
            if not str(source.get(key, "")).strip():
                raise ValueError(f"建模知识库来源 {index + 1} 缺少 {key}。")
        if source.get("code_copied") is not False:
            raise ValueError("当前规则库只允许记录参考思想，不允许未审计的代码复制。")

    rules = data.get("rules", {})
    if not isinstance(rules, Mapping):
        raise ValueError("建模知识库缺少规则主体。")
    profiles = rules.get("detail_profiles", {})
    buildings = rules.get("building_types", {})
    sites = rules.get("site_surfaces", {})
    road_facilities = rules.get("road_facilities", {})
    vegetation = rules.get("vegetation", {})
    if set(profiles) != _DETAIL_LEVELS:
        raise ValueError("建模知识库的细节层级不完整。")
    if set(buildings) != _BUILDING_TYPES:
        raise ValueError("建模知识库的建筑类型不完整。")
    if set(sites) != {"course", "presentation"}:
        raise ValueError("建模知识库的场地表达层级不完整。")
    if set(vegetation) != {"course", "presentation"}:
        raise ValueError("建模知识库的植被表达层级不完整。")
    if not isinstance(road_facilities, Mapping) or set(road_facilities) != {
        "crosswalk",
        "traffic_light",
        "quality_guards",
    }:
        raise ValueError("建模知识库的道路设施规则不完整。")

    crosswalk = road_facilities["crosswalk"]
    traffic_light = road_facilities["traffic_light"]
    quality_guards = road_facilities["quality_guards"]
    if not all(
        isinstance(value, Mapping)
        for value in (crosswalk, traffic_light, quality_guards)
    ):
        raise ValueError("建模知识库的道路设施子规则格式无效。")
    if crosswalk.get("auto_orientation_enabled") is not True:
        raise ValueError("斑马线自动定向规则必须明确启用。")
    if crosswalk.get("orientation_rule") != "longitudinal_bars_parallel_to_vehicle_travel":
        raise ValueError("斑马线方向语义不受当前版本支持。")
    if crosswalk.get("component_longitudinal_bar_axis") != "local_y":
        raise ValueError("斑马线组件纵向条带轴必须明确为 local_y。")
    rotation_offset = crosswalk.get("rotation_offset_from_road_axis_deg")
    if (
        isinstance(rotation_offset, bool)
        or not isinstance(rotation_offset, (int, float))
        or not math.isfinite(float(rotation_offset))
    ):
        raise ValueError("斑马线相对道路方向的旋转偏移无效。")
    for key in (
        "road_match_max_distance_m",
        "crossing_width_along_road_m",
        "minimum_crossing_width_along_road_m",
        "maximum_crossing_width_along_road_m",
        "road_detail_clearance_m",
        "minimum_carriageway_span_m",
        "maximum_carriageway_span_m",
        "component_thickness_m",
        "stripe_count",
        "stripe_spacing_fraction",
        "max_instances_per_model",
    ):
        _positive_number(crosswalk.get(key), f"road_facilities.crosswalk.{key}")
    for key in (
        "carriageway_span_margin_m",
        "surface_offset_m",
    ):
        _positive_number(
            crosswalk.get(key),
            f"road_facilities.crosswalk.{key}",
            allow_zero=True,
        )
    for key in ("stripe_half_width_fraction", "stripe_half_length_fraction"):
        fraction = _positive_number(
            crosswalk.get(key), f"road_facilities.crosswalk.{key}"
        )
        if fraction >= 0.5:
            raise ValueError(f"斑马线比例字段 {key} 必须小于 0.5。")
    confidence = _positive_number(
        crosswalk.get("road_match_minimum_confidence"),
        "road_facilities.crosswalk.road_match_minimum_confidence",
    )
    if confidence > 1.0:
        raise ValueError("斑马线道路匹配置信度不能大于 1。")
    manual_tokens = crosswalk.get("manual_rotation_block_tokens")
    if not isinstance(manual_tokens, list) or not manual_tokens or any(
        not str(token).strip() for token in manual_tokens
    ):
        raise ValueError("斑马线手动旋转块标记无效。")
    if not (
        float(crosswalk["minimum_crossing_width_along_road_m"])
        <= float(crosswalk["crossing_width_along_road_m"])
        <= float(crosswalk["maximum_crossing_width_along_road_m"])
    ):
        raise ValueError("斑马线沿道路宽度不在允许范围内。")
    if float(crosswalk["minimum_carriageway_span_m"]) > float(
        crosswalk["maximum_carriageway_span_m"]
    ):
        raise ValueError("斑马线横跨车行道范围上下限颠倒。")
    for key in ("target_height_m", "minimum_edge_clearance_m", "max_instances_per_model"):
        _positive_number(
            traffic_light.get(key), f"road_facilities.traffic_light.{key}"
        )
    if traffic_light.get("automatic_signal_control_inference") is not False:
        raise ValueError("交通灯规则不得自动推断信号控制。")
    if quality_guards.get("never_create_unrequested_signal_control") is not True:
        raise ValueError("道路设施规则必须禁止自动创造未请求的信号控制。")

    for level, profile in profiles.items():
        if not isinstance(profile, Mapping):
            raise ValueError(f"细节层级 {level} 的规则格式无效。")
        _positive_number(
            profile.get("facade_instance_budget"),
            f"detail_profiles.{level}.facade_instance_budget",
            allow_zero=True,
        )
    for building_type, rule in buildings.items():
        facade = rule.get("facade", {}) if isinstance(rule, Mapping) else {}
        for key in ("module_width_m", "window_width_m", "window_height_m", "sill_height_m"):
            _positive_number(facade.get(key), f"building_types.{building_type}.facade.{key}")
        _positive_number(rule.get("entrance_width_m"), f"building_types.{building_type}.entrance_width_m")
        rgb = rule.get("material_rgb")
        if (
            not isinstance(rgb, list)
            or len(rgb) != 3
            or any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255 for value in rgb)
        ):
            raise ValueError(f"建筑类型 {building_type} 的颜色必须是 3 个 0–255 整数。")
    for level, role_rules in sites.items():
        if set(role_rules) != _SITE_ROLES:
            raise ValueError(f"场地层级 {level} 缺少必要对象类型。")
        for role, rule in role_rules.items():
            _positive_number(rule.get("thickness_m"), f"site_surfaces.{level}.{role}.thickness_m", allow_zero=True)
            elevation = rule.get("elevation_m")
            if isinstance(elevation, bool) or not isinstance(elevation, (int, float)) or not math.isfinite(float(elevation)):
                raise ValueError(f"场地层级 {level} 的 {role} 标高无效。")
        road_design = role_rules["road"].get("road_design", {})
        if not isinstance(road_design, Mapping) or road_design.get("enabled") is not True:
            raise ValueError(f"场地层级 {level} 缺少启用的道路横断面规则。")
        for key in ("minimum_length_m", "minimum_width_m"):
            _positive_number(
                road_design.get(key),
                f"site_surfaces.{level}.road.road_design.{key}",
            )
        if road_design.get("curved_geometry_enabled") is not True:
            raise ValueError(
                f"鍦哄湴灞傜骇 {level} 鐨勯亾璺洸绾挎柟鍚戞帹鏂繀椤绘槑纭惎鐢ㄣ€?"
            )
        _positive_number(
            road_design.get("centerline_assumed_width_m"),
            f"site_surfaces.{level}.road.road_design.centerline_assumed_width_m",
        )
        sidewalk = road_design.get("sidewalk", {})
        edge_marking = road_design.get("edge_marking", {})
        arrow = road_design.get("direction_arrow", {})
        budget = road_design.get("geometry_budget", {})
        if not all(isinstance(value, Mapping) for value in (sidewalk, edge_marking, arrow, budget)):
            raise ValueError(f"场地层级 {level} 的道路横断面子规则格式无效。")
        for key in (
            "preferred_width_m",
            "minimum_width_m",
            "minimum_total_road_width_m",
            "minimum_carriageway_width_m",
            "height_m",
            "end_margin_m",
        ):
            _positive_number(
                sidewalk.get(key),
                f"site_surfaces.{level}.road.road_design.sidewalk.{key}",
                allow_zero=key == "end_margin_m",
            )
        sidewalk_fraction = _positive_number(
            sidewalk.get("maximum_fraction_each_side"),
            f"site_surfaces.{level}.road.road_design.sidewalk.maximum_fraction_each_side",
        )
        if sidewalk_fraction >= 0.45:
            raise ValueError(f"场地层级 {level} 的单侧人行道比例过大。")
        for key in ("width_m", "inset_m"):
            _positive_number(
                edge_marking.get(key),
                f"site_surfaces.{level}.road.road_design.edge_marking.{key}",
                allow_zero=key == "inset_m",
            )
        for key in (
            "minimum_road_width_m",
            "minimum_road_length_m",
            "spacing_m",
            "end_margin_m",
            "length_m",
            "width_m",
        ):
            _positive_number(
                arrow.get(key),
                f"site_surfaces.{level}.road.road_design.direction_arrow.{key}",
                allow_zero=key == "end_margin_m",
            )
        for key in ("max_sidewalk_bands", "max_edge_lines", "max_arrows"):
            _positive_number(
                budget.get(key),
                f"site_surfaces.{level}.road.road_design.geometry_budget.{key}",
            )
    for level, rule in vegetation.items():
        for key in (
            "minimum_canopy_radius_m",
            "maximum_canopy_radius_m",
            "radius_quantization_m",
            "segments",
            "canopy_tiers",
            "variation_steps",
        ):
            _positive_number(rule.get(key), f"vegetation.{level}.{key}")


@lru_cache(maxsize=1)
def _load_cached() -> dict[str, Any]:
    asset = resources.files("planning_toolbox.knowledge").joinpath(_ASSET_NAME)
    data = json.loads(asset.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("建模知识库根对象必须是 JSON 对象。")
    _validate_knowledge(data)
    return data


def load_sketchup_modeling_knowledge() -> dict[str, Any]:
    """Return a defensive copy so callers cannot mutate process-wide rules."""
    return deepcopy(_load_cached())


def get_modeling_detail_profile(detail_level: str) -> dict[str, Any]:
    level = str(detail_level or "").strip().lower()
    if level not in _DETAIL_LEVELS:
        raise ValueError(f"未知 SketchUp 建模细节层级：{level or '空值'}。")
    return deepcopy(_load_cached()["rules"]["detail_profiles"][level])


def get_modeling_building_rule(building_type: str) -> dict[str, Any]:
    category = str(building_type or "").strip().lower()
    if category not in _BUILDING_TYPES:
        raise ValueError(f"未知 SketchUp 建筑类型：{category or '空值'}。")
    return deepcopy(_load_cached()["rules"]["building_types"][category])


def get_modeling_building_details() -> dict[str, Any]:
    return deepcopy(_load_cached()["rules"]["building_details"])


def get_modeling_site_surface(detail_level: str, role: str) -> dict[str, Any] | None:
    level = str(detail_level or "").strip().lower()
    category = str(role or "").strip().lower()
    if level == "massing" or category not in _SITE_ROLES:
        return None
    return deepcopy(_load_cached()["rules"]["site_surfaces"][level][category])


def get_modeling_vegetation_rule(detail_level: str) -> dict[str, Any] | None:
    level = str(detail_level or "").strip().lower()
    if level == "massing":
        return None
    if level not in {"course", "presentation"}:
        raise ValueError(f"未知 SketchUp 植被细节层级：{level or '空值'}。")
    return deepcopy(_load_cached()["rules"]["vegetation"][level])


def get_modeling_road_facility_rule(facility: str) -> dict[str, Any]:
    category = str(facility or "").strip().lower()
    rules = _load_cached()["rules"]["road_facilities"]
    if category not in rules:
        raise ValueError(f"未知 SketchUp 道路设施类型：{category or '空值'}。")
    return deepcopy(rules[category])


def sketchup_modeling_knowledge_summary() -> dict[str, Any]:
    data = _load_cached()
    rules = data["rules"]
    return {
        "id": data["knowledge_id"],
        "version": data["version"],
        "schema_version": data["schema_version"],
        "normative": data["normative"],
        "source_count": len(data["sources"]),
        "detail_profile_count": len(rules["detail_profiles"]),
        "building_type_count": len(rules["building_types"]),
        "road_facility_rule_count": len(rules["road_facilities"]),
        "storage": "rules_only_no_images_or_models",
        "user_settings_take_priority": True,
    }


__all__ = [
    "MODELING_KNOWLEDGE_SCHEMA_VERSION",
    "get_modeling_building_details",
    "get_modeling_building_rule",
    "get_modeling_detail_profile",
    "get_modeling_site_surface",
    "get_modeling_road_facility_rule",
    "get_modeling_vegetation_rule",
    "load_sketchup_modeling_knowledge",
    "sketchup_modeling_knowledge_summary",
]
