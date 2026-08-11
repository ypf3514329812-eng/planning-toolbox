"""Tests for the lightweight semantic bridge between image, CAD and SU."""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
import pytest

from planning_toolbox.project.chain_manifest import CRSDefinition, new_chain_manifest
from planning_toolbox.project.semantic_scene import (
    SEMANTIC_SCENE_FORMAT,
    build_semantic_scene_from_dxf,
    load_semantic_scene_for_dxf,
    propagate_semantic_scene_to_derived_dxf,
)
from planning_toolbox.sketchup import export_sketchup_handoff
from planning_toolbox.utils.file_integrity import sha256_file


def _semantic_image_dxf(path: Path) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    for layer in (
        "BW_LINEWORK",
        "BW_CLOSED",
        "BW_BUILDING_CANDIDATE",
    ):
        doc.layers.add(layer)
    msp = doc.modelspace()
    for offset in (0.0, 8.0, 16.0):
        msp.add_line(
            (0.0, offset),
            (40.0, offset),
            dxfattribs={"layer": "BW_LINEWORK"},
        )
    msp.add_lwpolyline(
        [(2.0, 25.0), (12.0, 25.0), (12.0, 32.0), (2.0, 32.0)],
        close=True,
        dxfattribs={"layer": "BW_CLOSED"},
    )
    msp.add_lwpolyline(
        [(20.0, 24.0), (35.0, 24.0), (35.0, 34.0), (20.0, 34.0)],
        close=True,
        dxfattribs={"layer": "BW_BUILDING_CANDIDATE"},
    )
    doc.saveas(path)
    return path


def _local_manifest():
    return new_chain_manifest("图转 CAD 全链路语义测试", "residential").with_updates(
        crs=CRSDefinition(name="Local image calibration", kind="local").to_dict(),
        cad_unit="m",
    )


def test_semantic_scene_is_small_source_bound_and_reviewable(tmp_path):
    source = _semantic_image_dxf(tmp_path / "image_plan.dxf")
    source_hash = sha256_file(source)
    result = build_semantic_scene_from_dxf(
        source,
        source_image_path=tmp_path / "source.png",
        source_image_sha256="a" * 64,
        reference_width_m=120.0,
        conversion_mode="black_white_linework",
    )

    sidecar = Path(result["path"])
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["format"] == SEMANTIC_SCENE_FORMAT
    assert payload["source"]["dxf_sha256"] == source_hash
    assert payload["summary"]["source_entity_count"] == 5
    assert payload["summary"]["semantic_object_count"] == 1
    assert payload["summary"]["underlay_entity_count"] == 4
    assert payload["summary"]["review_required_count"] == 1
    assert payload["layer_rules"]["BW_BUILDING_CANDIDATE"]["role"] == "building"
    assert set(payload["underlay_layers"]) == {"BW_CLOSED", "BW_LINEWORK"}
    assert sidecar.stat().st_size < 20_000
    assert sha256_file(source) == source_hash
    assert load_semantic_scene_for_dxf(source) is not None


def test_black_white_road_candidate_is_reviewable_road_semantics(tmp_path):
    source = tmp_path / "road_candidate.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BW_ROAD_CANDIDATE")
    doc.modelspace().add_lwpolyline(
        [(0.0, 0.0), (40.0, 0.0), (40.0, 8.0), (0.0, 8.0)],
        close=True,
        dxfattribs={"layer": "BW_ROAD_CANDIDATE"},
    )
    doc.saveas(source)

    result = build_semantic_scene_from_dxf(source)
    payload = json.loads(Path(result["path"]).read_text(encoding="utf-8"))

    rule = payload["layer_rules"]["BW_ROAD_CANDIDATE"]
    assert rule["role"] == "road"
    assert rule["review_required"] is True
    assert rule["basis"] == "paired_line_corridor_candidate"
    assert payload["summary"]["role_counts"]["road"] == 1


def test_display_only_semantic_hatch_does_not_inflate_review_count(tmp_path):
    source = tmp_path / "presentation_fill.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BW_BUILDING_CANDIDATE")
    doc.appids.add("PT_PRESENTATION_FILL")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (0.0, 8.0)],
        close=True,
        dxfattribs={"layer": "BW_BUILDING_CANDIDATE"},
    )
    hatch = msp.add_hatch(dxfattribs={"layer": "BW_BUILDING_CANDIDATE"})
    hatch.paths.add_polyline_path(
        [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (0.0, 8.0)],
        is_closed=True,
    )
    hatch.set_xdata("PT_PRESENTATION_FILL", [(1000, "display_only_semantic_fill")])
    doc.saveas(source)

    scene = build_semantic_scene_from_dxf(source)
    payload = json.loads(Path(scene["path"]).read_text(encoding="utf-8"))
    assert payload["summary"]["source_entity_count"] == 2
    assert payload["summary"]["semantic_object_count"] == 1
    assert payload["summary"]["presentation_fill_count"] == 1
    assert payload["summary"]["review_required_count"] == 1

    output = tmp_path / "presentation_fill.ptsu.json"
    result = export_sketchup_handoff(source, output, _local_manifest())
    assert result["presentation_fill_ignored_count"] == 1
    assert result["skipped_count"] == 0


def test_semantic_scene_blocks_stale_dxf_meaning(tmp_path):
    source = _semantic_image_dxf(tmp_path / "stale.dxf")
    build_semantic_scene_from_dxf(source)
    doc = ezdxf.readfile(source)
    doc.modelspace().add_line(
        (0.0, 40.0),
        (40.0, 40.0),
        dxfattribs={"layer": "BW_LINEWORK"},
    )
    doc.saveas(source)

    with pytest.raises(ValueError, match="语义场景与当前 DXF 不匹配"):
        load_semantic_scene_for_dxf(source)


def test_semantic_scene_propagates_to_derived_dxf_with_lineage(tmp_path):
    source = _semantic_image_dxf(tmp_path / "source.dxf")
    image_path = tmp_path / "source.png"
    image_hash = "b" * 64
    guide_path = tmp_path / "semantic_guide.png"
    guide_path.write_bytes(b"semantic-guide-fixture")
    guide_hash = sha256_file(guide_path)
    parent = build_semantic_scene_from_dxf(
        source,
        source_image_path=image_path,
        source_image_sha256=image_hash,
        semantic_guide_path=guide_path,
        semantic_guide_sha256=guide_hash,
        reference_width_m=96.0,
        conversion_mode="semantic_guide",
    )
    source_hash = sha256_file(source)

    derived = tmp_path / "source_repaired.dxf"
    ezdxf.readfile(source).saveas(derived)
    result = propagate_semantic_scene_to_derived_dxf(source, derived)
    payload = load_semantic_scene_for_dxf(derived)

    assert result is not None
    assert payload is not None
    assert payload["source"]["dxf_path"] == str(derived.resolve())
    assert payload["source"]["source_image_path"] == str(image_path.resolve())
    assert payload["source"]["source_image_sha256"] == image_hash
    assert payload["source"]["semantic_guide_path"] == str(guide_path.resolve())
    assert payload["source"]["semantic_guide_sha256"] == guide_hash
    assert payload["source"]["conversion_mode"] == "semantic_guide"
    assert payload["source"]["reference_width_m"] == 96.0
    assert payload["lineage"]["parent_scene_path"] == parent["path"]
    assert payload["lineage"]["parent_dxf_sha256"] == source_hash
    assert payload["summary"]["source_entity_count"] == 5
    assert sha256_file(source) == source_hash


def test_sketchup_handoff_bundles_semantic_underlay(tmp_path):
    source = _semantic_image_dxf(tmp_path / "bundle.dxf")
    source_hash = sha256_file(source)
    scene = build_semantic_scene_from_dxf(
        source,
        reference_width_m=120.0,
        conversion_mode="black_white_linework",
    )
    output = tmp_path / "bundle.ptsu.json"

    result = export_sketchup_handoff(
        source,
        output,
        _local_manifest(),
        floors=6,
        floor_height_m=3.0,
        include_open_linework=True,
        building_layers="BW_BUILDING_CANDIDATE",
        model_detail_level="massing",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    bundle = next(
        item for item in payload["objects"] if item["geometry_type"] == "linework_bundle"
    )

    assert sha256_file(source) == source_hash
    assert payload["schema_version"] == 7
    assert payload["semantic_scene"]["validated"] is True
    assert payload["semantic_scene"]["path"] == scene["path"]
    assert payload["summary"]["underlay_bundle_count"] == 1
    assert payload["summary"]["underlay_source_entity_count"] == 4
    assert payload["summary"]["role_counts"]["underlay"] == 1
    assert result["object_count"] == 5
    assert result["top_level_object_count"] == 2
    assert result["building_count"] == 1
    assert result["semantic_scene_validated"] is True
    assert result["underlay_bundle_count"] == 1
    assert result["underlay_source_entity_count"] == 4
    assert bundle["sketchup_tag"] == "PT_UNDERLAY"
    assert bundle["locked_by_default"] is True
    assert bundle["path_count"] == 4
    assert len(bundle["paths"]) == 4


def test_image_semantic_handoff_adapts_facade_budget_without_dropping_buildings(tmp_path):
    source = _semantic_image_dxf(tmp_path / "adaptive_budget.dxf")
    build_semantic_scene_from_dxf(
        source,
        reference_width_m=120.0,
        conversion_mode="black_white_linework",
    )
    output = tmp_path / "adaptive_budget.ptsu.json"

    result = export_sketchup_handoff(
        source,
        output,
        _local_manifest(),
        floors=6,
        floor_height_m=3.0,
        building_layers="BW_BUILDING_CANDIDATE",
        model_detail_level="course",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result["building_count"] == 1
    assert payload["summary"]["procedural_building_count"] == 1
    assert payload["modeling_settings"]["facade_instance_budget"] == 640
    assert (
        payload["modeling_settings"]["facade_budget_policy"]
        == "adaptive_image_candidate"
    )
