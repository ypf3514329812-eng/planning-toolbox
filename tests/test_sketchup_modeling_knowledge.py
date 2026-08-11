import json
from importlib import resources

from planning_toolbox.knowledge.sketchup_modeling import (
    get_modeling_building_rule,
    get_modeling_detail_profile,
    get_modeling_road_facility_rule,
    get_modeling_site_surface,
    get_modeling_vegetation_rule,
    load_sketchup_modeling_knowledge,
    sketchup_modeling_knowledge_summary,
)


def test_sketchup_modeling_knowledge_is_small_traceable_and_rules_only():
    asset = resources.files("planning_toolbox.knowledge").joinpath(
        "sketchup_modeling_rules.json"
    )
    raw = asset.read_bytes()
    data = json.loads(raw.decode("utf-8"))

    assert len(raw) < 30_000
    assert data["normative"] is False
    assert data["storage_policy"] == {
        "embedded_images": False,
        "embedded_models": False,
        "model_weights": False,
        "description": "仅保存可审计的规则、参数范围、来源和许可证信息。",
    }
    assert len(data["sources"]) == 10
    assert all(source["url"].startswith("https://") for source in data["sources"])
    assert all(source["license"] for source in data["sources"])
    assert all(source["code_copied"] is False for source in data["sources"])
    lowered = raw.lower()
    assert b".skp" not in lowered
    assert b".png" not in lowered
    assert b"base64" not in lowered


def test_sketchup_modeling_knowledge_returns_defensive_copies():
    first = load_sketchup_modeling_knowledge()
    first["rules"]["building_types"]["residential"]["facade"]["module_width_m"] = 999

    second = load_sketchup_modeling_knowledge()
    assert second["rules"]["building_types"]["residential"]["facade"]["module_width_m"] == 3.3

    residential = get_modeling_building_rule("residential")
    residential["material_rgb"][0] = 0
    assert get_modeling_building_rule("residential")["material_rgb"] == [202, 184, 158]


def test_sketchup_modeling_rules_cover_generation_profiles():
    summary = sketchup_modeling_knowledge_summary()
    assert summary["source_count"] == 10
    assert summary["road_facility_rule_count"] == 3
    assert summary["storage"] == "rules_only_no_images_or_models"
    assert get_modeling_detail_profile("massing")["facade_instance_budget"] == 0
    assert get_modeling_detail_profile("presentation")["facade_instance_budget"] == 16_000
    assert get_modeling_site_surface("course", "road")["edge_profile"]["treatment"] == "curb"
    assert get_modeling_site_surface("course", "road")["road_design"]["sidewalk"]["enabled"] is False
    assert get_modeling_site_surface("course", "road")["road_design"]["curved_geometry_enabled"] is True
    assert get_modeling_site_surface("presentation", "road")["road_design"]["centerline_assumed_width_m"] == 6.0
    presentation_road = get_modeling_site_surface("presentation", "road")
    assert presentation_road["road_design"]["sidewalk"]["enabled"] is True
    assert presentation_road["road_design"]["direction_arrow"]["max_per_surface"] == 4
    assert get_modeling_site_surface("presentation", "green")["edge_profile"]["treatment"] == "edging"
    assert get_modeling_site_surface("massing", "road") is None
    assert get_modeling_vegetation_rule("course")["segments"] == 8
    assert get_modeling_vegetation_rule("presentation")["segments"] == 12
    assert get_modeling_vegetation_rule("massing") is None
    crosswalk = get_modeling_road_facility_rule("crosswalk")
    assert crosswalk["orientation_rule"] == "longitudinal_bars_parallel_to_vehicle_travel"
    assert crosswalk["rotation_offset_from_road_axis_deg"] == -90.0
    assert crosswalk["stripe_count"] == 7
    assert crosswalk["road_detail_clearance_m"] == 0.75
    assert crosswalk["manual_rotation_block_tokens"] == ["FIXED", "MANUAL"]
    assert get_modeling_road_facility_rule("traffic_light")[
        "automatic_signal_control_inference"
    ] is False
