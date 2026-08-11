"""Tests for the lightweight CAD-to-SketchUp handoff and RBZ package."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import math
import tracemalloc
import zipfile

import ezdxf
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from planning_toolbox import __version__
from planning_toolbox.project.chain_manifest import CRSDefinition, LocalOrigin, new_chain_manifest
from planning_toolbox.project.semantic_scene import (
    apply_semantic_candidate_reviews,
    build_semantic_scene_from_dxf,
    load_semantic_scene_for_dxf,
)
from planning_toolbox.sketchup import (
    build_sketchup_extension,
    export_sketchup_handoff,
    inspect_sketchup_buildings,
)
from planning_toolbox.utils.file_integrity import sha256_file


@pytest.fixture(scope="module")
def qapp():
    """Provide a local Qt application when this module runs by itself."""
    app = QApplication.instance() or QApplication([])
    yield app


def _projected_dxf(path: Path, *, units: int = 6) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = units
    for layer in ("PARCEL", "BUILDING", "GREEN", "ROAD"):
        doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(500000, 3400000), (500100, 3400000), (500100, 3400080), (500000, 3400080)],
        close=True,
        dxfattribs={"layer": "PARCEL"},
    )
    msp.add_lwpolyline(
        [(500010, 3400010), (500030, 3400010), (500030, 3400025), (500010, 3400025)],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    msp.add_circle((500060, 3400040), 8, dxfattribs={"layer": "GREEN"})
    msp.add_line((500000, 3400005), (500100, 3400005), dxfattribs={"layer": "ROAD"})
    msp.add_text("不自动交接", dxfattribs={"layer": "0"})
    doc.saveas(path)
    return path


def _two_building_dxf(path: Path) -> Path:
    _projected_dxf(path)
    doc = ezdxf.readfile(path)
    doc.modelspace().add_lwpolyline(
        [(500050, 3400010), (500075, 3400010), (500075, 3400030), (500050, 3400030)],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    doc.saveas(path)
    return path


def _complex_projected_dxf(path: Path) -> Path:
    """Create a compact but realistic mix of nested blocks, faces and labels."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    for layer in ("GREEN", "MASSING", "LABEL"):
        doc.layers.add(layer)

    tree = doc.blocks.new("TREE_SYMBOL")
    tree.add_circle((0, 0), 2, dxfattribs={"layer": "0"})
    tree.add_text(
        "TREE",
        dxfattribs={"layer": "0", "height": 0.5},
    ).set_placement((0, 0))

    cluster = doc.blocks.new("TREE_CLUSTER")
    cluster.add_blockref("TREE_SYMBOL", (1, 1), dxfattribs={"layer": "0"})
    cluster.add_line((0, 0), (4, 0), dxfattribs={"layer": "0"})

    modelspace = doc.modelspace()
    insert = modelspace.add_blockref(
        "TREE_CLUSTER",
        (500020, 3400030),
        dxfattribs={"layer": "GREEN"},
    )
    insert.dxf.rotation = 30
    insert.dxf.xscale = 2
    insert.dxf.yscale = 2
    modelspace.add_3dface(
        [
            (500050, 3400010, 0),
            (500060, 3400010, 0),
            (500060, 3400010, 3),
            (500050, 3400010, 3),
        ],
        dxfattribs={"layer": "MASSING"},
    )
    modelspace.add_solid(
        [
            (500070, 3400010, 0),
            (500080, 3400010, 0),
            (500070, 3400020, 0),
            (500080, 3400020, 0),
        ],
        dxfattribs={"layer": "MASSING"},
    )
    modelspace.add_line(
        (500090, 3400010, 0),
        (500100, 3400010, 0),
        dxfattribs={"layer": "MASSING"},
    )
    modelspace.add_text(
        "社区中心",
        dxfattribs={"layer": "LABEL", "height": 1.0},
    ).set_placement((500040, 3400040))
    modelspace.add_mtext(
        "公共\\P空间",
        dxfattribs={
            "insert": (500045, 3400045),
            "char_height": 1.2,
            "layer": "LABEL",
        },
    )
    doc.saveas(path)
    return path


def _walk_objects(objects):
    for item in objects:
        yield item
        yield from _walk_objects(item.get("children", []))


def _manifest(*, origin_enabled: bool = True):
    manifest = new_chain_manifest("居住区 SketchUp 交接", "residential")
    return manifest.with_updates(
        crs=CRSDefinition(
            code=4547,
            name="CGCS2000 / 3-degree Gauss-Kruger CM 114E",
            kind="projected",
        ).to_dict(),
        cad_unit="m",
        local_origin=LocalOrigin(
            enabled=origin_enabled,
            easting=500000.0,
            northing=3400000.0,
            elevation=0.0,
            rotation_deg=0.0,
        ).to_dict(),
    )


def _road_rectangle(
    center: tuple[float, float],
    angle_deg: float,
    *,
    length: float = 80.0,
    width: float = 12.0,
) -> list[tuple[float, float]]:
    radians = math.radians(angle_deg)
    axis = (math.cos(radians), math.sin(radians))
    normal = (-axis[1], axis[0])
    return [
        (
            center[0] + axis[0] * along + normal[0] * across,
            center[1] + axis[1] * along + normal[1] * across,
        )
        for along, across in (
            (-length / 2, -width / 2),
            (length / 2, -width / 2),
            (length / 2, width / 2),
            (-length / 2, width / 2),
        )
    ]


def _curved_road_strip(
    center: tuple[float, float],
    *,
    width: float = 12.0,
) -> list[tuple[float, float]]:
    """Create a simple bent road band with two sampled side boundaries."""
    centreline = [
        (0.0, 0.0),
        (20.0, 0.0),
        (38.0, 8.0),
        (52.0, 24.0),
    ]
    half_width = width / 2.0
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for index, (x, y) in enumerate(centreline):
        if index == 0:
            dx, dy = centreline[1][0] - x, centreline[1][1] - y
        elif index == len(centreline) - 1:
            dx, dy = x - centreline[index - 1][0], y - centreline[index - 1][1]
        else:
            dx = centreline[index + 1][0] - centreline[index - 1][0]
            dy = centreline[index + 1][1] - centreline[index - 1][1]
        length = math.hypot(dx, dy)
        normal = (-dy / length, dx / length)
        left.append((center[0] + x + normal[0] * half_width, center[1] + y + normal[1] * half_width))
        right.append((center[0] + x - normal[0] * half_width, center[1] + y - normal[1] * half_width))
    return left + list(reversed(right))


def _crosswalk_test_dxf(
    path: Path,
    *,
    road_angles: tuple[float, ...],
    block_name: str = "PT_CROSSWALK",
    crossing_rotation_deg: float = 0.0,
) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD")
    doc.layers.add("GREEN")
    center = (500050.0, 3400050.0)
    for angle in road_angles:
        doc.modelspace().add_lwpolyline(
            _road_rectangle(center, angle),
            close=True,
            dxfattribs={"layer": "ROAD"},
        )
    crossing = doc.blocks.new(block_name)
    crossing.add_lwpolyline(
        [(-1, -1), (1, -1), (1, 1), (-1, 1)],
        close=True,
    )
    insert = doc.modelspace().add_blockref(
        block_name,
        center,
        dxfattribs={"layer": "GREEN"},
    )
    insert.dxf.rotation = crossing_rotation_deg
    doc.saveas(path)
    return path


def test_handoff_preserves_source_and_applies_local_origin(tmp_path):
    source = _projected_dxf(tmp_path / "site.dxf")
    source_hash = sha256_file(source)
    output = tmp_path / "site_sketchup.ptsu.json"

    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        floors=6,
        floor_height_m=3.2,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result["zero_mutation_verified"] is True
    assert sha256_file(source) == source_hash
    assert result["object_count"] == 4
    assert result["building_count"] == 1
    assert result["extruded_building_count"] == 1
    assert result["skipped_count"] == 1
    assert payload["coordinate_contract"]["mode"] == "project_to_local"
    building = next(item for item in payload["objects"] if item["role"] == "building")
    assert building["points_m"][0] == pytest.approx([10.0, 10.0, 0.0])
    assert building["extrusion_m"] == pytest.approx(19.2)
    assert building["id"].startswith("PT-BUILDING-")
    assert len(building["geometry_fingerprint"]) == 64
    assert building["procedural_modeling"]["enabled"] is True
    assert building["procedural_modeling"]["building_type"] == "residential"
    assert building["procedural_modeling"]["effective_roof_type"] == "flat"
    assert building["procedural_modeling"]["floor_line_elevations_m"] == pytest.approx(
        [3.2, 6.4, 9.6, 12.8, 16.0]
    )
    assert result["procedural_building_count"] == 1
    assert result["estimated_facade_module_count"] > 0
    assert result["floor_guide_segment_count"] == 20
    assert payload["summary"]["skipped_reasons"]["text_disabled"] == 1
    quality_baseline = Path(result["quality_baseline_file"])
    assert quality_baseline.is_file()
    quality_payload = json.loads(quality_baseline.read_text(encoding="utf-8"))
    assert quality_payload["workflow"] == "cad_to_sketchup"
    assert quality_payload["inputs"]["source_sha256"] == source_hash
    assert quality_payload["outputs"]["handoff_sha256"] == sha256_file(output)
    assert quality_payload["summary"]["blocked_count"] == 0
    quality_review = Path(result["quality_baseline"]["review_path"])
    assert quality_review.is_file()
    review_text = quality_review.read_text(encoding="utf-8-sig")
    assert "CAD → SketchUp" in review_text
    assert "人工建模复核" in review_text
    assert result["output_files"][-2][1] == str(quality_review)
    assert result["output_files"][-1][1] == str(quality_baseline)


def test_handoff_stable_ids_repeat_and_two_dimensional_mode(tmp_path):
    source = _projected_dxf(tmp_path / "site.dxf")
    first = tmp_path / "first.ptsu.json"
    second = tmp_path / "second.ptsu.json"
    manifest = _manifest()

    export_sketchup_handoff(source, first, manifest, floors=0, floor_height_m=0)
    export_sketchup_handoff(source, second, manifest, floors=0, floor_height_m=0)
    first_data = json.loads(first.read_text(encoding="utf-8"))
    second_data = json.loads(second.read_text(encoding="utf-8"))

    assert [item["id"] for item in first_data["objects"]] == [
        item["id"] for item in second_data["objects"]
    ]
    assert [item["geometry_fingerprint"] for item in first_data["objects"]] == [
        item["geometry_fingerprint"] for item in second_data["objects"]
    ]
    assert all(item["extrusion_m"] == 0 for item in first_data["objects"])
    assert first_data["building_settings"]["mode"] == "two_dimensional"


def test_handoff_modeling_profiles_change_only_required_geometry(tmp_path):
    source = _projected_dxf(tmp_path / "site.dxf")
    course = tmp_path / "course.ptsu.json"
    presentation = tmp_path / "presentation.ptsu.json"
    manifest = _manifest()

    export_sketchup_handoff(
        source,
        course,
        manifest,
        floors=4,
        floor_height_m=3.0,
        model_detail_level="course",
        building_type="auto",
        roof_type="gable",
        incremental_update=True,
    )
    export_sketchup_handoff(
        source,
        presentation,
        manifest,
        floors=4,
        floor_height_m=3.0,
        model_detail_level="presentation",
        building_type="office",
        roof_type="hip",
        incremental_update=True,
    )
    course_data = json.loads(course.read_text(encoding="utf-8"))
    presentation_data = json.loads(presentation.read_text(encoding="utf-8"))
    course_building = next(item for item in course_data["objects"] if item["role"] == "building")
    presentation_building = next(
        item for item in presentation_data["objects"] if item["role"] == "building"
    )

    assert course_data["schema_version"] == 7
    course_settings = dict(course_data["modeling_settings"])
    knowledge = course_settings.pop("knowledge_base")
    component_library = course_settings.pop("component_library")
    assert course_settings == {
        "detail_level": "course",
        "road_design_preset": "auto",
        "requested_building_type": "auto",
        "resolved_building_type": "residential",
        "roof_type": "gable",
        "incremental_update": True,
        "preserve_locked_objects": True,
        "facade_instance_budget": 8000,
        "site_surface_styling": True,
        "shared_tree_components": True,
        "architectural_detail_generation": True,
        "site_edge_detailing": True,
        "road_cross_section_generation": True,
        "centerline_corridor_generation": False,
        "centerline_confidence_policy": "all",
        "centerline_confidence_threshold": 0.65,
        "centerline_corridor_width_m": None,
        "bounded_road_furniture": False,
        "deterministic_tree_variation": True,
        "road_local_tangent_matching": True,
        "crosswalk_auto_orientation": True,
        "crosswalk_orientation_rule": "longitudinal_bars_parallel_to_vehicle_travel",
    }
    assert knowledge == {
        "id": "planning-toolbox-lightweight-urban-modeling",
        "version": "2026.08.6",
        "schema_version": 1,
        "normative": False,
        "source_count": 10,
        "detail_profile_count": 3,
        "building_type_count": 5,
        "road_facility_rule_count": 3,
        "storage": "rules_only_no_images_or_models",
        "user_settings_take_priority": True,
    }
    assert component_library["id"] == "planning-toolbox-sketchup-component-library"
    assert component_library["version"] == "2026.08.10"
    assert component_library["component_count"] == 14
    assert component_library["total_bytes"] == 1_220_468
    assert component_library["network_required"] is False
    assert component_library["api_required"] is False
    assert course_building["procedural_modeling"]["effective_roof_type"] == "gable"
    assert course_building["procedural_modeling"]["material_rgb"] == [202, 184, 158]
    assert course_building["procedural_modeling"]["knowledge_rule"]["version"] == "2026.08.6"
    assert course_building["procedural_modeling"]["architectural_details"]["entrance"]["enabled"] is True
    entrance_component = course_building["procedural_modeling"]["architectural_details"]["entrance"]["component_library"]
    assert entrance_component["asset_id"] == "overhang_wide"
    assert entrance_component["license"] == "CC0-1.0"
    assert course_building["procedural_modeling"]["architectural_details"]["balcony"]["enabled"] is False
    assert presentation_building["procedural_modeling"]["effective_roof_type"] == "hip"
    assert course_building["geometry_fingerprint"] != presentation_building["geometry_fingerprint"]
    assert course_data["objects"][0]["geometry_fingerprint"] == presentation_data["objects"][0]["geometry_fingerprint"]


def test_handoff_styles_closed_site_surfaces_without_heavy_terrain(tmp_path):
    source = tmp_path / "site_surfaces.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    for layer in ("GREEN", "ROAD", "WATER", "PARKING"):
        doc.layers.add(layer)
    for index, layer in enumerate(("GREEN", "ROAD", "WATER", "PARKING")):
        x0 = 500000 + index * 15
        doc.modelspace().add_lwpolyline(
            [(x0, 3400000), (x0 + 10, 3400000), (x0 + 10, 3400008), (x0, 3400008)],
            close=True,
            dxfattribs={"layer": layer},
        )
    doc.saveas(source)

    course_output = tmp_path / "course.ptsu.json"
    massing_output = tmp_path / "massing.ptsu.json"
    presentation_output = tmp_path / "presentation.ptsu.json"
    course = export_sketchup_handoff(
        source,
        course_output,
        _manifest(),
        model_detail_level="course",
    )
    massing = export_sketchup_handoff(
        source,
        massing_output,
        _manifest(),
        model_detail_level="massing",
    )
    export_sketchup_handoff(
        source,
        presentation_output,
        _manifest(),
        model_detail_level="presentation",
    )
    course_objects = json.loads(course_output.read_text(encoding="utf-8"))["objects"]
    massing_objects = json.loads(massing_output.read_text(encoding="utf-8"))["objects"]
    presentation_objects = json.loads(
        presentation_output.read_text(encoding="utf-8")
    )["objects"]

    styles = {item["role"]: item["surface_style"] for item in course_objects}
    assert set(styles) == {"green", "road", "water", "parking"}
    assert styles["road"]["elevation_m"] > styles["green"]["elevation_m"]
    assert styles["water"]["elevation_m"] < 0
    assert styles["water"]["thickness_m"] == 0
    assert course["styled_site_surface_count"] == 4
    assert styles["road"]["edge_profile"]["treatment"] == "curb"
    assert styles["road"]["edge_profile"]["skip_short_ends"] is True
    assert styles["road"]["lane_marking"]["enabled"] is True
    assert styles["road"]["road_design"]["enabled"] is True
    assert styles["road"]["road_design"]["sidewalk"]["enabled"] is False
    assert styles["road"]["geometry_hint"]["eligible"] is True
    assert styles["road"]["geometry_hint"]["edge_line_count"] == 2
    assert styles["parking"]["edge_profile"]["treatment"] == "marking"
    assert "edge_profile" not in styles["green"]
    presentation_styles = {
        item["role"]: item["surface_style"] for item in presentation_objects
    }
    assert presentation_styles["green"]["edge_profile"]["treatment"] == "edging"
    assert presentation_styles["water"]["edge_profile"]["treatment"] == "bank"
    assert presentation_styles["road"]["street_lights"]["enabled"] is True
    assert presentation_styles["road"]["street_lights"]["component_library"]["asset_id"] == "street_light"
    assert presentation_styles["road"]["road_design"]["sidewalk"]["enabled"] is True
    assert presentation_styles["road"]["geometry_hint"]["sidewalk_band_count"] == 2
    assert presentation_styles["road"]["geometry_hint"]["end_curbs_suppressed"] is True
    assert massing["styled_site_surface_count"] == 0
    assert all("surface_style" not in item for item in massing_objects)


def test_complete_road_preset_is_bounded_and_width_aware(tmp_path):
    source = tmp_path / "road_cross_section.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD")
    modelspace = doc.modelspace()
    modelspace.add_lwpolyline(
        [(0, 0), (80, 0), (80, 12), (0, 12)],
        close=True,
        dxfattribs={"layer": "ROAD"},
    )
    modelspace.add_lwpolyline(
        [(0, 20), (30, 20), (30, 25), (0, 25)],
        close=True,
        dxfattribs={"layer": "ROAD"},
    )
    modelspace.add_lwpolyline(
        [(0, 32), (24, 32), (20, 38), (0, 39)],
        close=True,
        dxfattribs={"layer": "ROAD"},
    )
    doc.saveas(source)

    output = tmp_path / "road_cross_section.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="course",
        road_design_preset="complete",
    )
    roads = json.loads(output.read_text(encoding="utf-8"))["objects"]
    hints = [item["surface_style"]["geometry_hint"] for item in roads]
    wide = next(item for item in hints if item.get("width_m") == 12.0)
    narrow = next(item for item in hints if item.get("width_m") == 5.0)
    irregular = next(item for item in hints if item["eligible"] is False)

    assert wide["classification"] == "complete_street"
    assert wide["center_m"] == pytest.approx([-499960.0, -3399994.0])
    assert wide["long_axis_angle_deg"] == pytest.approx(0.0)
    assert wide["long_axis_vector"] == pytest.approx([1.0, 0.0])
    assert wide["sidewalk_width_each_side_m"] == 1.5
    assert wide["carriageway_width_m"] == 9.0
    assert wide["sidewalk_band_count"] == 2
    assert wide["edge_line_count"] == 2
    assert wide["direction_arrow_count"] == 4
    assert wide["center_dash_count"] > 0
    assert wide["street_light_count"] == 8
    assert narrow["classification"] == "narrow_shared"
    assert narrow["sidewalk_band_count"] == 0
    assert narrow["direction_arrow_count"] == 0
    assert narrow["center_dash_count"] == 0
    assert irregular["shape"] == "irregular"
    assert result["road_design_surface_count"] == 2
    assert result["estimated_road_sidewalk_band_count"] == 2
    assert result["estimated_road_edge_line_count"] == 4
    assert result["estimated_road_direction_arrow_count"] == 4
    assert result["estimated_road_street_light_count"] == 12
    assert result["road_design_preset"] == "complete"

    off_output = tmp_path / "road_cross_section_off.ptsu.json"
    off_result = export_sketchup_handoff(
        source,
        off_output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="off",
    )
    off_roads = json.loads(off_output.read_text(encoding="utf-8"))["objects"]
    assert off_result["road_design_surface_count"] == 0
    assert off_result["estimated_road_direction_arrow_count"] == 0
    assert all(
        item["surface_style"]["road_design"]["enabled"] is False
        for item in off_roads
        if item.get("role") == "road" and "surface_style" in item
    )


def test_presentation_residential_adds_bounded_architectural_details(tmp_path):
    source = _projected_dxf(tmp_path / "detailed_building.dxf")
    output = tmp_path / "detailed_building.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        floors=5,
        floor_height_m=3.0,
        model_detail_level="presentation",
        building_type="residential",
        roof_type="flat",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    building = next(item for item in payload["objects"] if item["role"] == "building")
    details = building["procedural_modeling"]["architectural_details"]

    assert details["plinth"]["enabled"] is True
    assert details["entrance"]["enabled"] is True
    assert details["balcony"]["enabled"] is True
    assert details["balcony"]["max_instances"] == 8
    assert details["rooftop_equipment"]["enabled"] is True
    assert result["building_entrance_count"] == 1
    assert result["estimated_balcony_count"] == 4
    assert result["rooftop_equipment_count"] == 1


def test_handoff_applies_independent_parameters_to_stable_building_ids(tmp_path):
    source = _two_building_dxf(tmp_path / "two_buildings.dxf")
    source_hash = sha256_file(source)
    manifest = _manifest()
    catalog = inspect_sketchup_buildings(source, manifest, "BUILDING")
    assert catalog["zero_mutation_verified"] is True
    assert len(catalog["buildings"]) == 2
    selected = catalog["buildings"][1]

    output = tmp_path / "independent.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        manifest,
        floors=3,
        floor_height_m=3.0,
        building_layers="BUILDING",
        model_detail_level="course",
        building_overrides={
            selected["object_id"]: {
                **selected,
                "floors": 10,
                "floor_height_m": 3.6,
                "building_type": "office",
                "roof_type": "gable",
                "model_detail_level": "presentation",
            }
        },
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    buildings = [item for item in payload["objects"] if item["role"] == "building"]
    by_handle = {item["source_handle"]: item for item in buildings}
    default = next(item for item in buildings if item["source_handle"] != selected["source_handle"])
    overridden = by_handle[selected["source_handle"]]

    assert sha256_file(source) == source_hash
    assert default["extrusion_m"] == pytest.approx(9.0)
    assert default["building_parameters"]["source"] == "global_default"
    assert overridden["extrusion_m"] == pytest.approx(36.0)
    assert overridden["building_parameters"] == {
        "source": "building_override",
        "floors": 10,
        "floor_height_m": 3.6,
        "total_height_m": 36.0,
        "requested_building_type": "office",
        "building_type": "office",
        "roof_type": "gable",
        "detail_level": "presentation",
    }
    assert overridden["procedural_modeling"]["building_type"] == "office"
    assert overridden["procedural_modeling"]["effective_roof_type"] == "gable"
    assert result["building_override_count"] == 1
    assert result["matched_building_override_count"] == 1
    assert result["unmatched_building_override_count"] == 0
    assert payload["modeling_settings"]["facade_instance_budget"] == 16_000


def test_handoff_reads_only_explicit_building_semantics_from_layer_names(tmp_path):
    source = tmp_path / "explicit_building_layers.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    layer_names = (
        "BUILDING_RES_6F_FH3.0_FLAT",
        "BUILDING_OFFICE_F8_H32_FLAT",
        "建筑_商业_3层_层高4.5_双坡",
        "BUILDING_H15",
    )
    for layer in layer_names:
        doc.layers.add(layer)
    for index, layer in enumerate(layer_names):
        x = float(index * 20)
        doc.modelspace().add_lwpolyline(
            [(x, 0), (x + 12, 0), (x + 12, 10), (x, 10)],
            close=True,
            dxfattribs={"layer": layer},
        )
    doc.saveas(source)

    output = tmp_path / "explicit_building_layers.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        floors=0,
        floor_height_m=0.0,
        model_detail_level="course",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    buildings = {
        item["source_layer"]: item
        for item in payload["objects"]
        if item.get("role") == "building"
    }

    residential = buildings["BUILDING_RES_6F_FH3.0_FLAT"]
    assert residential["extrusion_m"] == pytest.approx(18.0)
    assert residential["building_parameters"]["floors"] == 6
    assert residential["building_parameters"]["floor_height_m"] == pytest.approx(3.0)
    assert residential["building_parameters"]["building_type"] == "residential"
    assert residential["building_parameters"]["roof_type"] == "flat"

    office = buildings["BUILDING_OFFICE_F8_H32_FLAT"]
    assert office["extrusion_m"] == pytest.approx(32.0)
    assert office["building_parameters"]["floors"] == 8
    assert office["building_parameters"]["floor_height_m"] == pytest.approx(4.0)
    assert office["building_parameters"]["building_type"] == "office"

    commercial = buildings["建筑_商业_3层_层高4.5_双坡"]
    assert commercial["extrusion_m"] == pytest.approx(13.5)
    assert commercial["building_parameters"]["building_type"] == "commercial"
    assert commercial["building_parameters"]["roof_type"] == "gable"

    height_only = buildings["BUILDING_H15"]
    assert height_only["extrusion_m"] == pytest.approx(15.0)
    assert height_only["building_parameters"]["floors"] == 0
    assert "procedural_modeling" not in height_only
    assert all(
        item["building_parameters"]["source"] == "explicit_layer_semantics"
        for item in buildings.values()
    )
    assert result["building_layer_semantics_count"] == 4
    assert result["building_layer_floor_semantics_count"] == 3
    assert result["building_layer_total_height_semantics_count"] == 2
    assert result["building_layer_type_semantics_count"] == 3
    assert result["building_layer_roof_semantics_count"] == 3
    readiness = result["course_model_readiness"]
    assert readiness["normative"] is False
    assert readiness["building_height_variant_count"] == 4
    assert readiness["building_type_variant_count"] == 3
    assert readiness["building_explicit_parameter_count"] == 4
    assert "停车表达" in readiness["review_labels"]


def test_individual_override_has_priority_over_explicit_layer_semantics(tmp_path):
    source = tmp_path / "layer_semantics_override.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BUILDING_RES_6F_FH3_FLAT")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (12, 0), (12, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "BUILDING_RES_6F_FH3_FLAT"},
    )
    doc.saveas(source)
    manifest = _manifest()
    building = inspect_sketchup_buildings(source, manifest)["buildings"][0]

    output = tmp_path / "layer_semantics_override.ptsu.json"
    export_sketchup_handoff(
        source,
        output,
        manifest,
        floors=4,
        floor_height_m=3.0,
        building_overrides={
            building["object_id"]: {
                **building,
                "floors": 2,
                "floor_height_m": 3.5,
                "building_type": "office",
                "roof_type": "hip",
                "model_detail_level": "course",
            }
        },
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    generated = next(
        item for item in payload["objects"] if item.get("role") == "building"
    )

    assert generated["extrusion_m"] == pytest.approx(7.0)
    assert generated["building_parameters"]["source"] == "building_override"
    assert generated["building_parameters"]["building_type"] == "office"
    assert generated["building_parameters"]["roof_type"] == "hip"


def test_handoff_rejects_incomplete_individual_height(tmp_path):
    source = _projected_dxf(tmp_path / "site.dxf")
    building = inspect_sketchup_buildings(source, _manifest(), "BUILDING")["buildings"][0]
    with pytest.raises(ValueError, match="没有填写大于 0"):
        export_sketchup_handoff(
            source,
            tmp_path / "invalid.ptsu.json",
            _manifest(),
            building_overrides={
                building["object_id"]: {
                    **building,
                    "floors": 6,
                    "floor_height_m": 0,
                }
            },
        )


def test_handoff_blocks_unknown_units_height_guess_and_unshifted_projected_coordinates(tmp_path):
    unknown = _projected_dxf(tmp_path / "unknown.dxf", units=0)
    known = _projected_dxf(tmp_path / "known.dxf", units=6)

    with pytest.raises(ValueError, match="近原点"):
        export_sketchup_handoff(
            known,
            tmp_path / "no_origin.ptsu.json",
            _manifest(origin_enabled=False),
        )
    with pytest.raises(ValueError, match="标准层高"):
        export_sketchup_handoff(
            known,
            tmp_path / "height.ptsu.json",
            _manifest(),
            floors=6,
            floor_height_m=0,
        )
    with pytest.raises(ValueError):
        export_sketchup_handoff(
            unknown,
            tmp_path / "unknown.ptsu.json",
            _manifest(),
        )


def test_image_semantic_handoff_includes_source_bound_raster_underlay(tmp_path):
    image_path = tmp_path / "selected_underlay.png"
    Image.new("RGB", (200, 300), (248, 248, 246)).save(image_path)
    image_hash = sha256_file(image_path)

    source = tmp_path / "image_plan.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    for layer in ("BW_BUILDING_CANDIDATE", "BW_LINEWORK"):
        doc.layers.add(layer)
    doc.modelspace().add_lwpolyline(
        [(20.0, 30.0), (45.0, 30.0), (45.0, 50.0), (20.0, 50.0)],
        close=True,
        dxfattribs={"layer": "BW_BUILDING_CANDIDATE"},
    )
    doc.modelspace().add_line(
        (0.0, 0.0),
        (100.0, 0.0),
        dxfattribs={"layer": "BW_LINEWORK"},
    )
    doc.saveas(source)
    build_semantic_scene_from_dxf(
        source,
        source_image_path=image_path,
        source_image_sha256=image_hash,
        reference_width_m=100.0,
        conversion_mode="black_white_linework",
    )
    manifest = new_chain_manifest("图片底图交接", "residential").with_updates(
        crs=CRSDefinition(
            name="Local image calibration",
            kind="local",
            linear_unit="m",
        ).to_dict(),
        cad_unit="m",
    )
    output = tmp_path / "image_plan.ptsu.json"

    result = export_sketchup_handoff(
        source,
        output,
        manifest,
        floors=4,
        floor_height_m=3.0,
        building_layers="BW_BUILDING_CANDIDATE",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    underlay = next(
        item for item in payload["objects"]
        if item.get("geometry_type") == "image_underlay"
    )

    assert result["raster_underlay_count"] == 1
    assert payload["schema_version"] == 7
    assert underlay["image_path"] == str(image_path.resolve())
    assert underlay["image_sha256"] == image_hash
    assert underlay["origin_m"] == pytest.approx([0.0, 0.0, -0.03])
    assert underlay["width_m"] == pytest.approx(100.0)
    assert underlay["height_m"] == pytest.approx(150.0)
    assert underlay["pixel_size"] == [200, 300]
    assert underlay["locked_by_default"] is True

    Image.new("RGB", (200, 300), (250, 240, 230)).save(image_path)
    with pytest.raises(ValueError, match="底图已发生变化"):
        export_sketchup_handoff(
            source,
            tmp_path / "stale_image.ptsu.json",
            manifest,
        )


def test_rbz_has_official_loader_structure_and_native_geometry_calls(tmp_path):
    rbz = tmp_path / "PlanningToolbox_SketchUp_Importer.rbz"
    result = build_sketchup_extension(rbz)

    assert result["size_bytes"] < 2_000_000
    with zipfile.ZipFile(rbz) as archive:
        names = archive.namelist()
        assert "planning_toolbox_sketchup.rb" in names
        assert "planning_toolbox_sketchup/main.rb" in names
        assert "planning_toolbox_sketchup/mcp_bridge.rb" in names
        loader = archive.read("planning_toolbox_sketchup.rb").decode("utf-8")
        ruby = archive.read("planning_toolbox_sketchup/main.rb").decode("utf-8")
        bridge = archive.read("planning_toolbox_sketchup/mcp_bridge.rb").decode("utf-8")
    component_names = [name for name in names if name.endswith(".skp")]
    assert len(component_names) == 14
    assert "planning_toolbox_sketchup/components/pt_parked_car.skp" in names
    assert "planning_toolbox_sketchup/components/pt_bus_shelter.skp" in names
    assert "planning_toolbox_sketchup/components/pt_road_crossing.skp" in component_names
    assert "planning_toolbox_sketchup/components/pt_traffic_light.skp" in component_names
    assert not any(name.lower().endswith((".glb", ".skb")) for name in names)
    assert f"EXTENSION.version = '{__version__}'" in loader
    assert f"VERSION = '{__version__}'" in bridge
    assert "WATCHDOG_INTERVAL" in bridge
    assert "def bridge_alive?" in bridge
    assert "def delete_config_if_owned" in bridge
    assert "process_id" in bridge
    assert "instance_id" in bridge
    assert "Socket.tcp" in bridge
    assert "TCPServer.new(HOST, 0)" in bridge
    assert "request['command'].to_s == 'health'" in bridge
    assert "Sketchup::AppObserver" in bridge
    assert "def onQuit" in bridge
    assert "Sketchup.add_observer" in bridge
    assert "model.start_operation" in ruby
    assert "group.entities.add_face" in ruby
    assert "face.pushpull" in ruby
    assert "entity.set_attribute" in ruby
    assert "SUPPORTED_SCHEMA_VERSIONS = [1, 2, 3, 4, 5, 6, 7]" in ruby
    assert "object['geometry_type'] == 'linework_bundle'" in ruby
    assert "object['geometry_type'] == 'image_underlay'" in ruby
    assert "group.entities.add_image" in ruby
    assert "Digest::SHA256.file" in ruby
    assert "underlay_source_entity_count" in ruby
    assert "group.locked = true" in ruby
    assert "object['geometry_type'] == 'group'" in ruby
    assert "group.entities.add_text" in ruby
    assert "entities.add_instance" in ruby
    assert "geometry_fingerprint" in ruby
    assert "manual_lock" in ruby
    assert "incremental_update" in ruby
    assert "facade_per_building_limit" in ruby
    assert "add_gable_roof" in ruby
    assert "UI.openpanel" in ruby
    assert "definition.entities.length.positive?" in ruby
    assert "definition.entities.empty?" not in ruby
    assert "def tree_definition" in ruby
    assert "component_role', 'site_tree'" in ruby
    assert "surface_style" in ruby
    assert "site_surface_slabs" in ruby
    assert "surface_generation_suppressed" in ruby
    assert "road_review_outlines" in ruby
    assert "def add_architectural_details" in ruby
    assert "def door_definition" in ruby
    assert "def balcony_definition" in ruby
    assert "def add_surface_edge_details" in ruby
    assert "def road_frame" in ruby
    assert "def curved_road_records" in ruby
    assert "def add_curved_road_details" in ruby
    assert "def add_curved_road_street_lights" in ruby
    assert "def roundabout_road_records" in ruby
    assert "def add_roundabout_road_details" in ruby
    assert "roundabout_ring" in ruby
    assert "road_roundabout_detail_faces" in ruby
    assert "curved_local_tangent" in ruby
    assert "def curved_road_sample" in ruby
    assert "road_curved_sidewalk_faces" in ruby
    assert "road_curved_street_lights" in ruby
    assert "centerline_corridor" in ruby
    assert "road_centerline_corridor_faces" in ruby
    assert "def road_cross_section" in ruby
    assert "def add_road_cross_section" in ruby
    assert "def add_road_direction_arrow" in ruby
    assert "def add_road_lane_markings" in ruby
    assert "def building_type_material" in ruby
    assert "def bundled_component_definition" in ruby
    assert "def add_bundled_component_instance" in ruby
    assert "[bounds.width, bounds.height, bounds.depth]" in ruby
    assert "root_bounds.depth" in ruby
    assert "def add_road_crossing_markings" in ruby
    assert "def road_detail_excluded?" in ruby
    assert "road_lane_markings_avoided" in ruby
    assert "road_street_lights_avoided" in ruby
    assert "def add_road_street_lights" in ruby
    assert "USER_COMPONENT_DIR" in ruby
    assert "component_origin" in ruby
    assert "USER-PROVIDED" in ruby
    assert "user-provided" in ruby
    assert "def open_user_component_folder" in ruby


def test_handoff_preserves_nested_blocks_faces_and_opt_in_text(tmp_path):
    source = _complex_projected_dxf(tmp_path / "complex.dxf")
    source_hash = sha256_file(source)
    output = tmp_path / "complex.ptsu.json"

    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        include_blocks=True,
        include_faces=True,
        include_text=True,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    all_objects = list(_walk_objects(payload["objects"]))

    assert sha256_file(source) == source_hash
    assert result["zero_mutation_verified"] is True
    assert payload["schema_version"] == 7
    assert result["block_count"] == 2
    assert result["surface_face_count"] == 2
    assert result["text_count"] == 3
    assert result["block_definition_counts"] == {
        "TREE_CLUSTER": 1,
        "TREE_SYMBOL": 1,
    }
    assert any(item["geometry_type"] == "face" for item in all_objects)
    assert any(item["geometry_type"] == "text" for item in all_objects)
    assert any(item.get("text") == "社区中心" for item in all_objects)
    assert any(item.get("text") == "公共\n空间" for item in all_objects)

    outer = next(item for item in payload["objects"] if item["source_type"] == "INSERT")
    inner = next(item for item in outer["children"] if item["geometry_type"] == "group")
    assert outer["id"].startswith("PT-BLOCK-")
    assert inner["parent_id"] == outer["id"]
    assert "procedural_symbol" not in outer
    assert inner["procedural_symbol"]["type"] == "tree"
    assert inner["procedural_symbol"]["detail_level"] == "course"
    assert inner["procedural_symbol"]["canopy_radius_m"] == pytest.approx(4.0)
    assert inner["procedural_symbol"]["component_library"]["asset_id"] == "tree_large"
    assert inner["procedural_symbol"]["component_library"]["target_bounds_m"] == pytest.approx([8.0, 8.0, 12.0])
    assert 0 <= inner["procedural_symbol"]["rotation_deg"] < 360
    assert 0.92 <= inner["procedural_symbol"]["scale_factor"] <= 1.08
    assert result["procedural_tree_count"] == 1
    assert all(
        item["source_layer"] == "GREEN"
        for item in _walk_objects([outer])
        if item["source_type"] != "INSERT"
    )


def test_handoff_complex_entity_switches_are_explicit(tmp_path):
    source = _complex_projected_dxf(tmp_path / "complex.dxf")
    output = tmp_path / "simple_only.ptsu.json"

    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        include_blocks=False,
        include_faces=False,
        include_text=False,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result["block_count"] == 0
    assert result["surface_face_count"] == 0
    assert result["text_count"] == 0
    assert result["skipped_reasons"] == {
        "blocks_disabled": 1,
        "faces_disabled": 2,
        "text_disabled": 2,
    }
    assert [item["source_type"] for item in payload["objects"]] == ["LINE"]


def test_explicit_site_blocks_map_to_curated_library_components(tmp_path):
    source = tmp_path / "library_symbols.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("GREEN")
    planter = doc.blocks.new("PT_PLANTER")
    planter.add_circle((0, 0), radius=0.5)
    parasol = doc.blocks.new("PT_PARASOL")
    parasol.add_circle((0, 0), radius=1.0)
    crossing = doc.blocks.new("PT_CROSSWALK")
    crossing.add_lwpolyline([(-1, -1), (1, -1), (1, 1), (-1, 1)], close=True)
    traffic_light = doc.blocks.new("PT_TRAFFIC_LIGHT")
    traffic_light.add_circle((0, 0), radius=0.25)
    doc.modelspace().add_blockref("PT_PLANTER", (500010, 3400010), dxfattribs={"layer": "GREEN"})
    doc.modelspace().add_blockref("PT_PARASOL", (500020, 3400010), dxfattribs={"layer": "GREEN"})
    doc.modelspace().add_blockref("PT_CROSSWALK", (500030, 3400010), dxfattribs={"layer": "GREEN"})
    doc.modelspace().add_blockref("PT_TRAFFIC_LIGHT", (500040, 3400010), dxfattribs={"layer": "GREEN"})
    doc.saveas(source)

    output = tmp_path / "library_symbols.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    symbols = {
        item["block_name"]: item["procedural_symbol"]
        for item in payload["objects"]
    }

    assert result["explicit_library_symbol_count"] == 4
    assert symbols["PT_PLANTER"]["type"] == "library_component"
    assert symbols["PT_PLANTER"]["component_library"]["asset_id"] == "planter"
    assert symbols["PT_PARASOL"]["component_library"]["asset_id"] == "parasol"
    assert symbols["PT_CROSSWALK"]["component_library"]["asset_id"] == "road_crossing"
    assert symbols["PT_CROSSWALK"]["component_library"]["facility_rendering"] == {
        "stripe_count": 7,
        "stripe_half_width_fraction": 0.045,
        "stripe_half_length_fraction": 0.45,
        "stripe_spacing_fraction": 0.13,
        "surface_offset_m": 0.01,
        "hide_source_mesh_edges": True,
        "mask_underlying_markings": True,
    }
    assert symbols["PT_TRAFFIC_LIGHT"]["component_library"]["asset_id"] == "traffic_light"
    assert symbols["PT_CROSSWALK"]["rotation_deg"] == 0.0
    assert symbols["PT_CROSSWALK"]["orientation_source"] == "cad_rotation_unmatched_fallback"
    assert result["road_crossing_total_count"] == 1
    assert result["road_crossing_auto_aligned_count"] == 0
    assert result["road_crossing_fallback_count"] == 1
    assert result["road_crossing_unmatched_count"] == 1
    assert symbols["PT_TRAFFIC_LIGHT"]["rotation_deg"] == 0.0
    assert all(symbol["component_library"]["license"] == "CC0-1.0" for symbol in symbols.values())


def test_native_planning_components_are_explicit_and_reusable(tmp_path):
    source = tmp_path / "native_symbols.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("GREEN")
    definitions = {
        "PT_PARKED_CAR": ("rect", 2.4, 1.0),
        "PT_BENCH": ("rect", 0.9, 0.35),
        "PT_SHRUB_CLUSTER": ("circle", 1.2, 0.0),
        "PT_BOLLARD": ("circle", 0.2, 0.0),
        "PT_BUS_SHELTER": ("rect", 2.0, 0.8),
    }
    for name, (kind, major, minor) in definitions.items():
        block = doc.blocks.new(name)
        if kind == "circle":
            block.add_circle((0, 0), radius=major)
        else:
            block.add_lwpolyline(
                [(-major, -minor), (major, -minor), (major, minor), (-major, minor)],
                close=True,
            )
    for index, name in enumerate(definitions):
        doc.modelspace().add_blockref(
            name,
            (500010 + index * 8, 3400010),
            dxfattribs={"layer": "GREEN"},
        )
    doc.saveas(source)

    output = tmp_path / "native_symbols.ptsu.json"
    result = export_sketchup_handoff(source, output, _manifest(), model_detail_level="presentation")
    payload = json.loads(output.read_text(encoding="utf-8"))
    symbols = {
        item["block_name"]: item["procedural_symbol"]
        for item in payload["objects"]
        if "procedural_symbol" in item
    }

    assert result["explicit_library_symbol_count"] == 5
    assert {
        symbols[name]["component_library"]["asset_id"]
        for name in definitions
    } == {"parked_car", "bench", "shrub_cluster", "bollard", "bus_shelter"}
    assert all(symbols[name]["type"] == "library_component" for name in definitions)


@pytest.mark.parametrize(
    ("road_angle_deg", "expected_rotation_deg"),
    ((0.0, 270.0), (90.0, 0.0), (30.0, 300.0)),
)
def test_crosswalk_auto_aligns_longitudinal_bars_to_trusted_road_axis(
    tmp_path,
    road_angle_deg,
    expected_rotation_deg,
):
    source = _crosswalk_test_dxf(
        tmp_path / f"crosswalk_{road_angle_deg}.dxf",
        road_angles=(road_angle_deg,),
    )
    output = tmp_path / f"crosswalk_{road_angle_deg}.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    crossing_object = next(
        item
        for item in payload["objects"]
        if item.get("block_name") == "PT_CROSSWALK"
    )
    crossing = crossing_object["procedural_symbol"]
    road = next(item for item in payload["objects"] if item.get("role") == "road")

    assert crossing["rotation_deg"] == pytest.approx(expected_rotation_deg)
    assert crossing["matched_road_axis_deg"] == pytest.approx(road_angle_deg)
    assert crossing["orientation_source"] == "matched_road_long_axis"
    assert crossing["orientation_rule"] == "longitudinal_bars_parallel_to_vehicle_travel"
    assert crossing["orientation_confidence"] >= 0.65
    assert crossing["component_library"]["target_bounds_m"] == pytest.approx(
        [9.3, 4.0, 0.08]
    )
    assert road["surface_style"]["road_design"]["exclusion_zones"] == [
        {
            "type": "crosswalk",
            "source_object_id": crossing_object["id"],
            "center_longitudinal_m": pytest.approx(0.0),
            "half_length_m": pytest.approx(2.75),
        }
    ]
    assert result["road_crossing_total_count"] == 1
    assert result["road_crossing_auto_aligned_count"] == 1
    assert result["road_crossing_fallback_count"] == 0
    assert result["road_crossing_exclusion_zone_count"] == 1


def test_crosswalk_uses_local_tangent_on_conservative_curved_road_strip(tmp_path):
    source = tmp_path / "crosswalk_curved.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD")
    doc.layers.add("GREEN")
    base = (500050.0, 3400050.0)
    doc.modelspace().add_lwpolyline(
        _curved_road_strip(base),
        close=True,
        dxfattribs={"layer": "ROAD"},
    )
    crossing = doc.blocks.new("PT_CROSSWALK")
    crossing.add_lwpolyline(
        [(-1, -1), (1, -1), (1, 1), (-1, 1)],
        close=True,
    )
    insert = doc.modelspace().add_blockref(
        "PT_CROSSWALK",
        (base[0] + 10.0, base[1]),
        dxfattribs={"layer": "GREEN"},
    )
    insert.dxf.rotation = 11.0
    doc.saveas(source)

    output = tmp_path / "crosswalk_curved.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    road = next(item for item in payload["objects"] if item.get("role") == "road")
    crossing_data = next(
        item["procedural_symbol"]
        for item in payload["objects"]
        if item.get("block_name") == "PT_CROSSWALK"
    )

    assert road["surface_style"]["geometry_hint"]["shape"] == "curved_strip"
    assert road["surface_style"]["geometry_hint"]["local_tangent_supported"] is True
    assert road["surface_style"]["geometry_hint"]["detail_geometry_supported"] is True
    assert road["surface_style"]["geometry_hint"]["detail_geometry"] == "curved_local_frame_strips"
    assert len(road["surface_style"]["geometry_hint"]["frames"]) >= 2
    assert crossing_data["orientation_source"] == "matched_road_local_tangent"
    assert crossing_data["matched_road_geometry"] == "curved_strip"
    assert crossing_data["matched_road_local_frame_index"] is not None
    assert crossing_data["road_width_source"] == "paired_boundary_segments"
    assert crossing_data["rotation_deg"] == pytest.approx(270.0)
    assert result["road_curved_hint_count"] == 1
    assert result["road_crossing_local_tangent_count"] == 1


def test_crosswalk_can_use_explicit_road_centerline_for_direction_assistance(tmp_path):
    source = tmp_path / "crosswalk_centerline.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD_CENTERLINE")
    doc.layers.add("GREEN")
    base = (500050.0, 3400050.0)
    doc.modelspace().add_lwpolyline(
        [(base[0], base[1]), (base[0] + 35.0, base[1] + 12.0)],
        close=False,
        dxfattribs={"layer": "ROAD_CENTERLINE"},
    )
    crossing = doc.blocks.new("PT_CROSSWALK")
    crossing.add_lwpolyline(
        [(-1, -1), (1, -1), (1, 1), (-1, 1)],
        close=True,
    )
    insert = doc.modelspace().add_blockref(
        "PT_CROSSWALK",
        (base[0] + 17.5, base[1] + 6.0),
        dxfattribs={"layer": "GREEN"},
    )
    doc.saveas(source)

    output = tmp_path / "crosswalk_centerline.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    crossing_data = next(
        item["procedural_symbol"]
        for item in payload["objects"]
        if item.get("block_name") == "PT_CROSSWALK"
    )

    assert crossing_data["orientation_source"] == "matched_road_local_tangent"
    assert crossing_data["matched_road_geometry"] == "centerline"
    assert crossing_data["road_width_source"] == "conceptual_centerline_default"
    assert crossing_data["orientation_confidence"] >= 0.65
    assert result["road_centerline_hint_count"] == 1
    assert result["road_crossing_local_tangent_count"] == 1


def test_black_white_road_centerline_candidate_reaches_sketchup_corridor_hint(tmp_path):
    source = tmp_path / "black_white_road_centerline_candidate.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BW_ROAD_CENTERLINE_CANDIDATE")
    doc.appids.add("PT_ROAD_WIDTH_M")
    doc.appids.add("PT_ROAD_CONFIDENCE")
    base = (500050.0, 3400050.0)
    centerline_entity = doc.modelspace().add_lwpolyline(
        [
            (base[0], base[1]),
            (base[0] + 24.0, base[1] + 8.0),
            (base[0] + 52.0, base[1] + 6.0),
        ],
        close=False,
        dxfattribs={"layer": "BW_ROAD_CENTERLINE_CANDIDATE"},
    )
    centerline_entity.set_xdata("PT_ROAD_WIDTH_M", [(1040, 10.0)])
    centerline_entity.set_xdata("PT_ROAD_CONFIDENCE", [(1040, 0.82)])
    doc.saveas(source)

    output = tmp_path / "black_white_road_centerline_candidate.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
        centerline_corridor=True,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    road = next(item for item in payload["objects"] if item.get("role") == "road")

    assert road["source_layer"] == "BW_ROAD_CENTERLINE_CANDIDATE"
    assert road["surface_style"]["geometry_hint"]["shape"] == "centerline_corridor"
    assert road["surface_style"]["geometry_hint"]["width_source"] == "image_detected_centerline_width"
    assert road["surface_style"]["geometry_hint"]["width_m"] == pytest.approx(10.0)
    assert road["surface_style"]["geometry_hint"]["source_confidence"] == pytest.approx(0.82)
    assert road["surface_style"]["geometry_hint"]["source_review_required"] is False
    assert road["centerline_width_source"] == "image_detected_centerline_width"
    assert road["centerline_confidence"] == pytest.approx(0.82)
    assert result["road_centerline_corridor_hint_count"] == 1


def test_trusted_only_centerline_policy_keeps_low_confidence_candidate_as_review_line(
    tmp_path,
):
    source = tmp_path / "mixed_confidence_centerlines.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BW_ROAD_CENTERLINE_CANDIDATE")
    doc.appids.add("PT_ROAD_WIDTH_M")
    doc.appids.add("PT_ROAD_CONFIDENCE")
    base = (500050.0, 3400050.0)
    for index, confidence in enumerate((0.84, 0.42)):
        entity = doc.modelspace().add_lwpolyline(
            [
                (base[0], base[1] + index * 18.0),
                (base[0] + 60.0, base[1] + index * 18.0),
            ],
            close=False,
            dxfattribs={"layer": "BW_ROAD_CENTERLINE_CANDIDATE"},
        )
        entity.set_xdata("PT_ROAD_WIDTH_M", [(1040, 10.0)])
        entity.set_xdata("PT_ROAD_CONFIDENCE", [(1040, confidence)])
    doc.saveas(source)

    output = tmp_path / "mixed_confidence_centerlines.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
        centerline_corridor=True,
        centerline_confidence_policy="trusted_only",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    roads = sorted(
        (item for item in payload["objects"] if item.get("role") == "road"),
        key=lambda item: item["centerline_confidence"],
        reverse=True,
    )

    assert roads[0]["surface_style"]["geometry_hint"]["shape"] == "centerline_corridor"
    low_hint = roads[1]["surface_style"]["geometry_hint"]
    assert low_hint["shape"] == "centerline"
    assert low_hint["corridor_requested"] is True
    assert low_hint["corridor_suppressed"] is True
    assert low_hint["corridor_suppression_reason"] == "source_confidence_below_threshold"
    assert roads[1]["centerline_review_required"] is True
    assert result["road_centerline_corridor_hint_count"] == 1
    assert result["road_centerline_hint_count"] == 1
    assert result["road_centerline_review_required_count"] == 1
    assert result["road_centerline_corridor_suppressed_count"] == 1
    assert result["centerline_confidence_policy"] == "trusted_only"
    assert payload["modeling_settings"]["centerline_confidence_policy"] == "trusted_only"

    all_output = tmp_path / "mixed_confidence_centerlines_all.ptsu.json"
    all_result = export_sketchup_handoff(
        source,
        all_output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
        centerline_corridor=True,
        centerline_confidence_policy="all",
    )
    assert all_result["road_centerline_corridor_hint_count"] == 2
    assert all_result["road_centerline_corridor_suppressed_count"] == 0

    with pytest.raises(ValueError, match="道路中心线可信度策略"):
        export_sketchup_handoff(
            source,
            tmp_path / "invalid_policy.ptsu.json",
            _manifest(),
            centerline_confidence_policy="unknown",
        )


def test_explicitly_accepted_low_confidence_centerline_can_generate_corridor(tmp_path):
    source = tmp_path / "accepted_low_confidence_centerline.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BW_ROAD_CENTERLINE_CANDIDATE")
    doc.appids.add("PT_ROAD_WIDTH_M")
    doc.appids.add("PT_ROAD_CONFIDENCE")
    entity = doc.modelspace().add_lwpolyline(
        [(500000.0, 3400000.0), (500080.0, 3400000.0)],
        dxfattribs={"layer": "BW_ROAD_CENTERLINE_CANDIDATE"},
    )
    entity.set_xdata("PT_ROAD_WIDTH_M", [(1040, 12.0)])
    entity.set_xdata("PT_ROAD_CONFIDENCE", [(1040, 0.42)])
    doc.saveas(source)
    scene = build_semantic_scene_from_dxf(source)
    candidate = load_semantic_scene_for_dxf(source)["object_registry"][0]
    assert candidate["confidence"] == pytest.approx(0.42)
    reviewed = apply_semantic_candidate_reviews(
        source,
        {candidate["id"]: "accepted"},
        expected_scene_sha256=scene["sha256"],
    )

    result = export_sketchup_handoff(
        source,
        tmp_path / "accepted_low_confidence_centerline.ptsu.json",
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
        centerline_corridor=True,
        centerline_confidence_policy="trusted_only",
    )

    assert reviewed["summary"]["accepted_count"] == 1
    assert result["road_centerline_corridor_hint_count"] == 1
    assert result["road_centerline_corridor_suppressed_count"] == 0
    assert result["semantic_accepted_count"] == 1


def test_trusted_image_centerline_corridor_turns_duplicate_road_area_into_review_outline(
    tmp_path,
):
    source = tmp_path / "image_road_area_and_centerline.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BW_ROAD_CANDIDATE")
    doc.layers.add("BW_ROAD_CENTERLINE_CANDIDATE")
    doc.appids.add("PT_ROAD_WIDTH_M")
    doc.appids.add("PT_ROAD_CONFIDENCE")
    base = (500050.0, 3400050.0)
    doc.modelspace().add_lwpolyline(
        [
            (base[0], base[1] - 5.0),
            (base[0] + 60.0, base[1] - 5.0),
            (base[0] + 60.0, base[1] + 5.0),
            (base[0], base[1] + 5.0),
        ],
        close=True,
        dxfattribs={"layer": "BW_ROAD_CANDIDATE"},
    )
    centerline = doc.modelspace().add_lwpolyline(
        [(base[0], base[1]), (base[0] + 60.0, base[1])],
        close=False,
        dxfattribs={"layer": "BW_ROAD_CENTERLINE_CANDIDATE"},
    )
    centerline.set_xdata("PT_ROAD_WIDTH_M", [(1040, 10.0)])
    centerline.set_xdata("PT_ROAD_CONFIDENCE", [(1040, 0.84)])
    doc.saveas(source)

    output = tmp_path / "trusted_only.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
        centerline_corridor=True,
        centerline_confidence_policy="trusted_only",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    road_area = next(
        item
        for item in payload["objects"]
        if item.get("source_layer") == "BW_ROAD_CANDIDATE"
    )
    road_axis = next(
        item
        for item in payload["objects"]
        if item.get("source_layer") == "BW_ROAD_CENTERLINE_CANDIDATE"
    )

    assert road_area["surface_generation_suppressed"] is True
    assert road_area["surface_suppression_reason"] == (
        "trusted_centerline_corridor_preferred"
    )
    assert "surface_style" not in road_area
    assert road_axis["surface_style"]["geometry_hint"]["shape"] == (
        "centerline_corridor"
    )
    assert result["road_surface_generation_suppressed_count"] == 1
    assert payload["summary"]["road_surface_generation_suppressed_count"] == 1

    all_output = tmp_path / "all_candidates.ptsu.json"
    all_result = export_sketchup_handoff(
        source,
        all_output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
        centerline_corridor=True,
        centerline_confidence_policy="all",
    )
    all_payload = json.loads(all_output.read_text(encoding="utf-8"))
    all_road_area = next(
        item
        for item in all_payload["objects"]
        if item.get("source_layer") == "BW_ROAD_CANDIDATE"
    )
    assert "surface_generation_suppressed" not in all_road_area
    assert all_road_area["surface_style"]["enabled"] is True
    assert all_result["road_surface_generation_suppressed_count"] == 0


def test_arc_and_spline_centerlines_are_sampled_and_kept_bounded(tmp_path):
    source = tmp_path / "curved_centerlines.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD_CENTERLINE")
    base = (500050.0, 3400050.0)
    doc.modelspace().add_arc(
        (base[0] + 24.0, base[1]),
        18.0,
        20.0,
        160.0,
        dxfattribs={"layer": "ROAD_CENTERLINE"},
    )
    doc.modelspace().add_spline(
        [
            (base[0], base[1] + 35.0),
            (base[0] + 14.0, base[1] + 45.0),
            (base[0] + 34.0, base[1] + 38.0),
            (base[0] + 48.0, base[1] + 52.0),
        ],
        dxfattribs={"layer": "ROAD_CENTERLINE"},
    )
    doc.saveas(source)

    output = tmp_path / "curved_centerlines.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    roads = [item for item in payload["objects"] if item.get("role") == "road"]

    assert {item["source_type"] for item in roads} == {"ARC", "SPLINE"}
    assert all(len(item["points_m"]) <= 256 for item in roads)
    assert all(
        item["surface_style"]["geometry_hint"]["shape"] == "centerline"
        for item in roads
    )
    assert all(
        item["surface_style"]["geometry_hint"]["local_tangent_supported"] is True
        for item in roads
    )
    assert result["road_centerline_hint_count"] == 2


def test_explicit_centerline_corridor_opt_in_generates_bounded_detail_hint(tmp_path):
    source = tmp_path / "centerline_corridor.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD_AXIS")
    base = (500080.0, 3400080.0)
    doc.modelspace().add_arc(
        (base[0] + 28.0, base[1]),
        22.0,
        15.0,
        165.0,
        dxfattribs={"layer": "ROAD_AXIS"},
    )
    doc.modelspace().add_spline(
        [
            (base[0], base[1] + 45.0),
            (base[0] + 16.0, base[1] + 57.0),
            (base[0] + 36.0, base[1] + 50.0),
            (base[0] + 52.0, base[1] + 66.0),
        ],
        dxfattribs={"layer": "ROAD_AXIS"},
    )
    doc.saveas(source)

    output = tmp_path / "centerline_corridor.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
        centerline_corridor=True,
        centerline_width_m=12.0,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    roads = [item for item in payload["objects"] if item.get("role") == "road"]

    assert {item["source_type"] for item in roads} == {"ARC", "SPLINE"}
    assert all(
        item["surface_style"]["geometry_hint"]["shape"] == "centerline_corridor"
        for item in roads
    )
    assert all(
        item["surface_style"]["geometry_hint"]["detail_geometry_supported"] is True
        for item in roads
    )
    assert all(
        item["surface_style"]["geometry_hint"]["width_source"]
        == "user_centerline_width"
        for item in roads
    )
    assert all(
        item["surface_style"]["geometry_hint"]["width_m"] == pytest.approx(12.0)
        for item in roads
    )
    assert all(
        item["surface_style"]["geometry_hint"]["sidewalk_width_each_side_m"]
        == pytest.approx(1.5)
        for item in roads
    )
    assert all(
        len(item["surface_style"]["geometry_hint"]["frames"]) >= 2
        for item in roads
    )
    assert result["road_centerline_corridor_hint_count"] == 2
    assert result["centerline_corridor_width_m"] == pytest.approx(12.0)
    assert payload["modeling_settings"]["centerline_corridor_generation"] is True
    assert payload["modeling_settings"]["centerline_corridor_width_m"] == pytest.approx(12.0)


def test_dense_centerline_corridor_resamples_the_complete_path_without_truncation(
    tmp_path,
):
    source = tmp_path / "dense_centerline.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD_CENTERLINE")
    points = [
        (
            500000.0 + float(index),
            3400000.0 + math.sin(index / 18.0) * 6.0,
        )
        for index in range(201)
    ]
    doc.modelspace().add_lwpolyline(
        points,
        dxfattribs={"layer": "ROAD_CENTERLINE"},
    )
    doc.saveas(source)

    output = tmp_path / "dense_centerline.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        floors=0,
        floor_height_m=0,
        centerline_corridor=True,
        centerline_width_m=10.0,
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    road = next(item for item in payload["objects"] if item["role"] == "road")
    hint = road["surface_style"]["geometry_hint"]

    assert hint["shape"] == "centerline_corridor"
    assert hint["frame_sampling_mode"] == "full_path_arc_length_resampled"
    assert hint["source_vertex_count"] == 201
    assert hint["source_segment_count"] == 200
    assert hint["source_segments_truncated"] == 0
    assert hint["full_path_coverage_ratio"] == pytest.approx(1.0)
    assert len(hint["frames"]) == 64
    assert hint["frames"][0]["center_m"] == pytest.approx([0.0, 0.0])
    assert hint["frames"][-1]["center_m"] == pytest.approx(
        [200.0, math.sin(200.0 / 18.0) * 6.0]
    )
    assert result["road_centerline_full_path_resampled_count"] == 1


def test_two_point_centerline_corridor_produces_two_endpoint_frames(tmp_path):
    source = tmp_path / "two_point_centerline.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROAD_CENTERLINE")
    doc.modelspace().add_line(
        (500010.0, 3400020.0),
        (500090.0, 3400020.0),
        dxfattribs={"layer": "ROAD_CENTERLINE"},
    )
    doc.saveas(source)

    output = tmp_path / "two_point_centerline.ptsu.json"
    export_sketchup_handoff(
        source,
        output,
        _manifest(),
        floors=0,
        floor_height_m=0,
        centerline_corridor=True,
        centerline_width_m=8.0,
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    road = next(item for item in payload["objects"] if item["role"] == "road")
    frames = road["surface_style"]["geometry_hint"]["frames"]
    assert frames[0]["center_m"] == pytest.approx([10.0, 20.0])
    assert frames[1]["center_m"] == pytest.approx([90.0, 20.0])

    with pytest.raises(ValueError, match="4 至 60"):
        export_sketchup_handoff(
            source,
            tmp_path / "centerline_corridor_invalid.ptsu.json",
            _manifest(),
            model_detail_level="presentation",
            road_design_preset="complete",
            centerline_corridor=True,
            centerline_width_m=61.0,
        )


def test_named_roundabout_circle_exports_a_ring_hint_without_filling_the_island(tmp_path):
    source = tmp_path / "roundabout.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("ROUNDABOUT")
    doc.modelspace().add_circle(
        (500050.0, 3400050.0),
        15.0,
        dxfattribs={"layer": "ROUNDABOUT"},
    )
    doc.saveas(source)

    output = tmp_path / "roundabout.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    road = next(item for item in payload["objects"] if item.get("role") == "road")
    hint = road["surface_style"]["geometry_hint"]

    assert road["source_type"] == "CIRCLE"
    assert hint["shape"] == "roundabout_ring"
    assert hint["detail_geometry"] == "roundabout_ring_local_frames"
    assert hint["width_source"] == "conceptual_roundabout_centerline_default"
    assert hint["centerline_radius_m"] == pytest.approx(15.0, abs=0.1)
    assert 12 <= len(hint["frames"]) <= 64
    assert result["road_roundabout_hint_count"] == 1


def test_crosswalk_manual_alias_preserves_cad_rotation_and_uses_road_width(tmp_path):
    source = _crosswalk_test_dxf(
        tmp_path / "crosswalk_manual.dxf",
        road_angles=(0.0,),
        block_name="PT_CROSSWALK_FIXED",
        crossing_rotation_deg=17.0,
    )
    output = tmp_path / "crosswalk_manual.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    crossing = next(
        item["procedural_symbol"]
        for item in payload["objects"]
        if item.get("block_name") == "PT_CROSSWALK_FIXED"
    )

    assert crossing["rotation_deg"] == pytest.approx(17.0)
    assert crossing["cad_rotation_deg"] == pytest.approx(17.0)
    assert crossing["orientation_source"] == "cad_rotation_manual_with_road_fit"
    assert crossing["component_library"]["target_bounds_m"] == pytest.approx(
        [9.3, 4.0, 0.08]
    )
    assert result["road_crossing_manual_count"] == 1
    assert result["road_crossing_auto_aligned_count"] == 0


def test_crosswalk_at_ambiguous_intersection_keeps_cad_rotation_for_review(tmp_path):
    source = _crosswalk_test_dxf(
        tmp_path / "crosswalk_ambiguous.dxf",
        road_angles=(0.0, 90.0),
        crossing_rotation_deg=23.0,
    )
    output = tmp_path / "crosswalk_ambiguous.ptsu.json"
    result = export_sketchup_handoff(
        source,
        output,
        _manifest(),
        model_detail_level="presentation",
        road_design_preset="complete",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    crossing = next(
        item["procedural_symbol"]
        for item in payload["objects"]
        if item.get("block_name") == "PT_CROSSWALK"
    )

    assert crossing["rotation_deg"] == pytest.approx(23.0)
    assert crossing["orientation_source"] == "cad_rotation_ambiguous_intersection_fallback"
    assert result["road_crossing_ambiguous_count"] == 1
    assert result["road_crossing_fallback_count"] == 1
    assert result["road_crossing_auto_aligned_count"] == 0


def test_sketchup_worker_generates_both_user_files(qapp, tmp_path):
    from planning_toolbox.gui.workers.task_worker import TaskWorker

    source = _projected_dxf(tmp_path / "site.dxf")
    finished = []
    worker = TaskWorker(
        "sketchup_export",
        {
            "dxf_path": str(source),
            "output_dir": str(tmp_path / "output"),
            "chain_manifest": _manifest().to_dict(),
            "floors": 5,
            "floor_height_m": 3.0,
            "building_layers": "BUILDING",
            "include_open_linework": True,
            "model_detail_level": "presentation",
            "building_type": "residential",
            "roof_type": "hip",
            "incremental_update": True,
            "centerline_confidence_policy": "trusted_only",
        },
    )
    worker.finished_signal.connect(finished.append)
    worker._run_sketchup_export_task()

    assert finished
    assert Path(finished[0]["handoff_file"]).is_file()
    assert Path(finished[0]["plugin_file"]).is_file()
    assert finished[0]["extruded_building_count"] == 1
    assert finished[0]["procedural_building_count"] == 1
    assert finished[0]["model_detail_level"] == "presentation"
    assert finished[0]["roof_type"] == "hip"
    assert finished[0]["centerline_confidence_policy"] == "trusted_only"


def test_sketchup_gui_page_emits_explicit_settings(qapp):
    from planning_toolbox.gui.widgets.task_zone import TaskZoneWidget

    widget = TaskZoneWidget()
    assert widget.tabs.count() == 10
    assert "SketchUp" in widget.tabs.tabText(9)
    assert widget.sketchup_floors.value() == 0
    assert widget.sketchup_floor_height.value() == pytest.approx(0.0)
    assert widget.sketchup_model_detail.currentData() == "course"
    assert widget.sketchup_building_type.currentData() == "auto"
    assert widget.sketchup_roof_type.currentData() == "flat"
    assert widget.sketchup_incremental_update.isChecked() is True
    assert widget.sketchup_centerline_corridor.isChecked() is False
    assert widget.sketchup_centerline_confidence_policy.currentData() == "trusted_only"
    assert widget.sketchup_centerline_confidence_policy.isEnabled() is False
    assert widget.sketchup_centerline_width.value() == pytest.approx(0.0)
    assert widget.sketchup_centerline_width.isEnabled() is False
    assert widget.sketchup_include_blocks.isChecked() is True
    assert widget.sketchup_include_faces.isChecked() is True
    assert widget.sketchup_include_text.isChecked() is False

    captured = []
    widget.run_task_signal.connect(lambda task, params: captured.append((task, params)))
    widget.tabs.setCurrentIndex(9)
    widget.sketchup_floors.setValue(8)
    widget.sketchup_floor_height.setValue(3.15)
    widget.sketchup_model_detail.setCurrentIndex(
        widget.sketchup_model_detail.findData("presentation")
    )
    widget.sketchup_building_type.setCurrentIndex(
        widget.sketchup_building_type.findData("office")
    )
    widget.sketchup_roof_type.setCurrentIndex(widget.sketchup_roof_type.findData("gable"))
    widget.sketchup_centerline_corridor.setChecked(True)
    widget.sketchup_centerline_confidence_policy.setCurrentIndex(
        widget.sketchup_centerline_confidence_policy.findData("all")
    )
    widget.sketchup_centerline_width.setValue(12.0)
    widget.sketchup_include_text.setChecked(True)
    widget.set_sketchup_building_overrides(
        {
            "PT-BUILDING-TEST": {
                "floors": 6,
                "floor_height_m": 3.1,
                "building_type": "residential",
                "roof_type": "flat",
                "model_detail_level": "course",
            }
        }
    )
    widget._on_run_clicked()

    assert captured[-1][0] == "sketchup_export"
    assert captured[-1][1]["floors"] == 8
    assert captured[-1][1]["floor_height_m"] == pytest.approx(3.15)
    assert captured[-1][1]["model_detail_level"] == "presentation"
    assert captured[-1][1]["building_type"] == "office"
    assert captured[-1][1]["roof_type"] == "gable"
    assert captured[-1][1]["incremental_update"] is True
    assert captured[-1][1]["centerline_corridor"] is True
    assert captured[-1][1]["centerline_confidence_policy"] == "all"
    assert captured[-1][1]["centerline_width_m"] == pytest.approx(12.0)
    assert captured[-1][1]["include_blocks"] is True
    assert captured[-1][1]["include_faces"] is True
    assert captured[-1][1]["include_text"] is True
    assert captured[-1][1]["building_overrides"]["PT-BUILDING-TEST"]["floors"] == 6

    saved_state = widget.get_project_state()
    restored = TaskZoneWidget()
    restored.apply_project_state(saved_state)
    assert restored.sketchup_model_detail.currentData() == "presentation"
    assert restored.sketchup_building_type.currentData() == "office"
    assert restored.sketchup_roof_type.currentData() == "gable"
    assert restored.sketchup_incremental_update.isChecked() is True
    assert restored.sketchup_centerline_corridor.isChecked() is True
    assert restored.sketchup_centerline_confidence_policy.currentData() == "all"
    assert restored.sketchup_centerline_width.value() == pytest.approx(12.0)
    assert restored.sketchup_centerline_width.isEnabled() is True
    assert restored.get_sketchup_building_overrides()["PT-BUILDING-TEST"]["floors"] == 6


def test_building_schedule_dialog_scans_and_saves_without_mutation(qapp, tmp_path):
    from planning_toolbox.gui.building_schedule_dialog import BuildingScheduleDialog

    source = _two_building_dxf(tmp_path / "schedule.dxf")
    source_hash = sha256_file(source)
    dialog = BuildingScheduleDialog(
        source,
        _manifest(),
        "BUILDING",
        global_defaults={
            "floors": 4,
            "floor_height_m": 3.0,
            "building_type": "auto",
            "roof_type": "flat",
            "model_detail_level": "course",
        },
    )
    assert dialog.table.rowCount() == 2
    dialog.table.selectRow(1)
    dialog.floors.setValue(12)
    dialog.floor_height.setValue(3.3)
    dialog._set_combo(dialog.building_type, "office")
    dialog._set_combo(dialog.roof_type, "hip")
    dialog._set_combo(dialog.detail_level, "presentation")
    dialog._apply_to_selected()

    overrides = dialog.building_overrides()
    assert len(overrides) == 1
    value = next(iter(overrides.values()))
    assert value["floors"] == 12
    assert value["floor_height_m"] == pytest.approx(3.3)
    assert value["building_type"] == "office"
    assert value["roof_type"] == "hip"
    assert value["model_detail_level"] == "presentation"
    assert sha256_file(source) == source_hash


def test_large_building_schedule_keeps_memory_bounded_and_cleans_artifacts():
    with TemporaryDirectory(prefix=".pt_building_stress_", dir=Path.cwd()) as temp_dir:
        root = Path(temp_dir)
        source = root / "large_site.dxf"
        output = root / "large_site.ptsu.json"
        doc = ezdxf.new("R2010")
        doc.header["$INSUNITS"] = 6
        doc.layers.add("BUILDING")
        modelspace = doc.modelspace()
        for index in range(750):
            x = 500000 + (index % 30) * 18
            y = 3400000 + (index // 30) * 14
            modelspace.add_lwpolyline(
                [(x, y), (x + 12, y), (x + 12, y + 8), (x, y + 8)],
                close=True,
                dxfattribs={"layer": "BUILDING"},
            )
        doc.saveas(source)

        tracemalloc.start()
        catalog = inspect_sketchup_buildings(source, _manifest(), "BUILDING")
        overrides = {
            item["object_id"]: {
                **item,
                "floors": 8,
                "floor_height_m": 3.2,
                "building_type": "residential",
                "roof_type": "flat",
                "model_detail_level": "presentation",
            }
            for item in catalog["buildings"][::25]
        }
        result = export_sketchup_handoff(
            source,
            output,
            _manifest(),
            floors=4,
            floor_height_m=3.0,
            building_layers="BUILDING",
            building_overrides=overrides,
        )
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert len(catalog["buildings"]) == 750
        assert result["building_count"] == 750
        assert result["matched_building_override_count"] == 30
        assert result["estimated_facade_module_count"] <= 16_000
        assert peak < 128 * 1024 * 1024
