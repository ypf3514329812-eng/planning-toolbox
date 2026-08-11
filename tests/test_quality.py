"""Tests for read-only CAD quality diagnostics."""

from pathlib import Path

import ezdxf
import pytest

from planning_toolbox.cad.quality import scan_dxf_quality, repair_dxf_quality
from planning_toolbox.utils.file_integrity import sha256_file


def test_quality_scan_detects_duplicates_open_lines_and_complex_entities(tmp_path):
    dxf_path = tmp_path / "quality.dxf"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for _ in range(2):
        polyline = msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], dxfattribs={"layer": "PARCEL"})
        polyline.close(True)
    msp.add_lwpolyline([(20, 0), (30, 0), (30, 10)], dxfattribs={"layer": "PARCEL"})
    msp.add_arc((20, 20), 3, 0, 90, dxfattribs={"layer": "SYMBOL"})
    doc.saveas(dxf_path)

    result = scan_dxf_quality(dxf_path)

    assert result["duplicate_count"] == 1
    assert result["open_count"] == 1
    assert result["complex_entity_counts"]["ARC"] == 1
    assert "PARCEL" in result["layer_counts"]


def test_quality_repair_is_written_to_a_new_file(tmp_path):
    dxf_path = tmp_path / "repair.dxf"
    doc = ezdxf.new("R2010")
    polyline = doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 0.005)], dxfattribs={"layer": "PARCEL"})
    doc.saveas(dxf_path)
    before = dxf_path.read_bytes()

    result = repair_dxf_quality(dxf_path, tmp_path / "out", near_closed_tolerance=0.01)

    assert result["closed_polylines"] == 1
    assert result["output_file"] != str(dxf_path.resolve())
    assert dxf_path.read_bytes() == before


def test_minimum_manual_repair_merges_fragments_and_tracks_every_change(tmp_path):
    dxf_path = tmp_path / "fragmented_plan.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("建筑")
    msp = doc.modelspace()
    msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "建筑"})
    msp.add_line((5.02, 0.001), (10, 0), dxfattribs={"layer": "建筑"})
    msp.add_lwpolyline(
        [(10.01, 0), (10.012, 0), (15, 0), (20, 0)],
        dxfattribs={"layer": "建筑"},
    )
    for _ in range(2):
        msp.add_line((0, 10), (5, 10), dxfattribs={"layer": "建筑"})
    doc.saveas(dxf_path)
    before = sha256_file(dxf_path)

    result = repair_dxf_quality(
        dxf_path,
        tmp_path / "out",
        remove_duplicates=True,
        close_near_closed=True,
        remove_duplicate_lines=True,
        merge_connected_fragments=True,
        join_tolerance=0.05,
        simplify_collinear_vertices=True,
        collinear_tolerance=0.01,
        remove_short_vertices=True,
        min_segment_length=0.01,
        standardize_layers=True,
        require_known_units=True,
    )

    assert result["removed_duplicate_lines"] == 1
    assert result["merged_fragment_groups"] == 1
    assert result["merged_source_entities"] == 3
    assert result["fragment_entity_reduction"] == 2
    assert result["removed_collinear_vertices"] >= 2
    assert result["standardized_layer_count"] == 5
    assert result["change_count"] >= 5
    assert result["max_endpoint_snap_distance"] <= 0.05
    assert Path(result["change_log_file"]).is_file()
    assert sha256_file(dxf_path) == before

    repaired = ezdxf.readfile(result["output_file"])
    building_entities = [
        entity
        for entity in repaired.modelspace()
        if entity.dxf.layer == "BUILDING"
    ]
    assert len(building_entities) == 2
    merged = next(entity for entity in building_entities if entity.dxftype() == "LWPOLYLINE")
    assert len(list(merged.get_points("xy"))) == 2


def test_fragment_merging_stops_at_branching_junctions(tmp_path):
    dxf_path = tmp_path / "branching_lines.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "ROAD_CENTER"})
    msp.add_line((5, 0), (10, 0), dxfattribs={"layer": "ROAD_CENTER"})
    msp.add_line((5, 0), (5, 5), dxfattribs={"layer": "ROAD_CENTER"})
    doc.saveas(dxf_path)

    result = repair_dxf_quality(
        dxf_path,
        tmp_path / "out",
        merge_connected_fragments=True,
        join_tolerance=0.01,
        require_known_units=True,
    )

    assert result["merged_fragment_groups"] == 0
    assert result["branching_components_skipped"] == 1
    repaired = ezdxf.readfile(result["output_file"])
    assert len(repaired.modelspace().query("LINE")) == 3


def test_deep_distance_repair_blocks_unknown_dxf_units(tmp_path):
    dxf_path = tmp_path / "unknown_units.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.modelspace().add_line((0, 0), (5, 0))
    doc.modelspace().add_line((5.01, 0), (10, 0))
    doc.saveas(dxf_path)

    with pytest.raises(ValueError, match="INSUNITS=0"):
        repair_dxf_quality(
            dxf_path,
            tmp_path / "out",
            merge_connected_fragments=True,
            join_tolerance=0.05,
            require_known_units=True,
        )
