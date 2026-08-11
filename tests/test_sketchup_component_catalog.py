from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from planning_toolbox.knowledge.sketchup_components import (
    get_component_placement_rule,
    get_sketchup_reference_pattern,
    get_sketchup_component,
    load_sketchup_component_catalog,
    load_sketchup_reference_patterns,
    sketchup_component_catalog_summary,
)


def test_component_catalog_is_tiny_offline_cc0_and_integrity_checked():
    catalog = load_sketchup_component_catalog()
    summary = sketchup_component_catalog_summary()

    assert summary == {
        "id": "planning-toolbox-sketchup-component-library",
        "version": "2026.08.10",
        "schema_version": 1,
        "component_count": 14,
        "automatic_component_count": 5,
        "source_count": 7,
        "license": "CC0-1.0 + PT-NATIVE-1.0",
        "total_bytes": 1_220_468,
        "budget_bytes": 100_000_000,
        "load_mode": "lazy_shared_component_definition",
        "network_required": False,
        "api_required": False,
        "fallback": "procedural_native_geometry",
        "native_component_count": 5,
        "resource_budget_bytes": 100_000_000,
        "reference_index_version": "2026.08.10",
        "reference_pattern_count": 22,
    }
    assert all(source["license"] == "CC0-1.0" for source in catalog["sources"])
    assert sum(item["skp_size_bytes"] for item in catalog["components"]) == 1_220_468
    assert all(item["skp_size_bytes"] < 8_000_000 for item in catalog["components"])
    native = [item for item in catalog["components"] if item.get("native_generator")]
    assert {item["asset_id"] for item in native} == {
        "parked_car",
        "bench",
        "shrub_cluster",
        "bollard",
        "bus_shelter",
    }


def test_component_catalog_returns_defensive_copies_and_semantic_rules():
    tree = get_sketchup_component("tree_large")
    tree["target_bounds_m"][0] = 999
    assert get_sketchup_component("tree_large")["target_bounds_m"][0] == 4.8

    entrance = get_component_placement_rule("entrance")
    assert entrance["residential"] == "overhang_wide"
    assert entrance["commercial"] == "awning_wide"
    assert get_component_placement_rule("tree")["large_radius_threshold_m"] == 1.8
    assert get_component_placement_rule("road_street_lights")["max_instances_per_surface"] == 12
    assert "PT_CROSSWALK" in get_sketchup_component("road_crossing")["block_aliases"]
    assert "PT_CROSSWALK_FIXED" in get_sketchup_component("road_crossing")["block_aliases"]
    assert "PT_TRAFFIC_LIGHT" in get_sketchup_component("traffic_light")["block_aliases"]


def test_reference_patterns_are_indexed_without_bundling_images():
    data = load_sketchup_reference_patterns()
    assert len(data["patterns"]) == 22
    assert data["storage_policy"]["embedded_images"] is False
    assert get_sketchup_reference_pattern("parking-row-with-cars")["visual_type"] == "parking_layout"


def test_kaykit_sources_are_self_contained_glb_with_catalogued_hashes():
    source_dir = (
        Path(__file__).resolve().parent.parent
        / "assets"
        / "sketchup_component_sources"
        / "kaykit_cc0"
    )
    for asset_id in ("road_crossing", "traffic_light"):
        component = get_sketchup_component(asset_id)
        raw = (source_dir / component["source_file"]).read_bytes()
        magic, version, total_length = struct.unpack("<4sII", raw[:12])
        assert magic == b"glTF"
        assert version == 2
        assert total_length == len(raw)
        assert hashlib.sha256(raw).hexdigest().upper() == component["source_sha256"]
