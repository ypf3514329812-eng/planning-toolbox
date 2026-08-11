from pathlib import Path

import ezdxf
import pytest

from planning_toolbox.cad.planning.concept_generator import generate_concept_plan
from planning_toolbox.core.units.unit_manager import UnitError
from planning_toolbox.utils.file_integrity import sha256_file


def test_concept_plan_generates_new_dxf_and_preserves_source(tmp_path):
    source = Path("sample_data/sample_parcels.dxf")
    before = sha256_file(source)

    result = generate_concept_plan(
        source,
        output_dir=tmp_path,
        building_count=2,
        coverage_ratio=0.25,
        setback_m=5.0,
        floors=6,
        parking_ratio=1.0,
        building_gap_m=6.0,
        access_width_m=6.0,
        standards_profile_id="residential_national_framework",
    )

    output_dxf = Path(result["output_files"][0][1])
    report = Path(result["output_files"][1][1])
    assert output_dxf.exists()
    assert report.exists()
    assert result["parcels_count"] == 3
    assert result["building_footprints"] > 0
    assert sha256_file(source) == before

    doc = ezdxf.readfile(output_dxf)
    layers = {layer.dxf.name for layer in doc.layers}
    assert {
        "CONCEPT_SETBACK",
        "CONCEPT_BUILDING",
        "CONCEPT_PARKING",
        "CONCEPT_GREEN",
        "CONCEPT_LABEL",
        "CONCEPT_DIMENSION",
        "CONCEPT_ROAD",
    } <= layers
    concept_entities = [
        entity for entity in doc.modelspace()
        if str(entity.dxf.layer).startswith("CONCEPT_")
    ]
    assert concept_entities
    assert "not a regulatory" in report.read_text(encoding="utf-8").lower()
    assert result["estimated_gfa_m2"] > 0
    assert result["parking_required"] > 0
    assert result["parking_generated"] > 0
    assert result["actual_coverage_ratio"] <= 0.25
    assert result["minimum_setback_m"] >= 5.0
    assert result["minimum_building_gap_m"] >= 6.0
    assert result["access_corridor_m2"] > 0
    assert result["standards_profile_id"] == "residential_national_framework"
    assert "GB 50180-2018" in report.read_text(encoding="utf-8")
    schedule = Path(result["output_files"][2][1])
    assert schedule.exists()
    assert "feature_id" in schedule.read_text(encoding="utf-8-sig")


def test_concept_plan_blocks_unknown_units(tmp_path):
    source = tmp_path / "unknown_units.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    parcel = doc.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        dxfattribs={"layer": "PARCEL"},
    )
    parcel.close(True)
    doc.saveas(source)

    with pytest.raises(UnitError):
        generate_concept_plan(source, output_dir=tmp_path)


def test_concept_plan_accepts_explicit_fallback_unit(tmp_path):
    source = tmp_path / "unknown_units_with_fallback.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    parcel = doc.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        dxfattribs={"layer": "PARCEL"},
    )
    parcel.close(True)
    doc.saveas(source)

    result = generate_concept_plan(
        source,
        output_dir=tmp_path,
        fallback_unit="m",
    )

    assert Path(result["output_files"][0][1]).exists()
    assert result["unit_name"] == "m"


def test_concept_plan_requires_floors_for_parking_estimate(tmp_path):
    source = Path("sample_data/sample_parcels.dxf")

    with pytest.raises(ValueError, match="楼层"):
        generate_concept_plan(
            source,
            output_dir=tmp_path,
            parking_ratio=1.0,
        )


def test_concept_plan_organic_layout_exports_curved_like_geometry(tmp_path):
    """The recommended style should create rounded footprints and curved guides."""
    source = Path("sample_data/sample_parcels.dxf")

    result = generate_concept_plan(
        source,
        output_dir=tmp_path,
        building_count=2,
        coverage_ratio=0.25,
        setback_m=5.0,
        building_gap_m=6.0,
        access_width_m=6.0,
        layout_style="organic",
    )

    assert result["layout_style"] == "organic"
    doc = ezdxf.readfile(result["output_files"][0][1])
    building_polylines = [
        entity for entity in doc.modelspace()
        if entity.dxf.layer == "CONCEPT_BUILDING"
        and entity.dxftype() == "LWPOLYLINE"
    ]
    road_polylines = [
        entity for entity in doc.modelspace()
        if entity.dxf.layer == "CONCEPT_ROAD"
        and entity.dxftype() == "LWPOLYLINE"
    ]

    assert building_polylines
    assert road_polylines
    assert all(len(list(entity.get_points())) > 8 for entity in building_polylines)
    assert any(len(list(entity.get_points())) > 8 for entity in road_polylines)


def test_concept_plan_rejects_unknown_layout_style(tmp_path):
    with pytest.raises(ValueError, match="layout_style"):
        generate_concept_plan(
            Path("sample_data/sample_parcels.dxf"),
            output_dir=tmp_path,
            layout_style="unknown",
        )
