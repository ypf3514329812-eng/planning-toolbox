import csv
import time
from pathlib import Path
import pytest
import ezdxf
from planning_toolbox.core.geometry.parser import parse_parcel_geometry
from planning_toolbox.cad.parcels.calculator import process_parcels
from planning_toolbox.config import load_config
from tests.fixtures.gold_standards import (
    GS_001_SQUARE, GS_002_RECTANGLE, GS_003_SETBACK, GS_004_FAR, GS_005_DENSITY
)

def test_t01_square_parcel():
    """T01: 100m x 100m square geometry area = 10,000 m²."""
    status, poly, err = parse_parcel_geometry(GS_001_SQUARE.vertices, is_closed=True)
    assert status == "VALID"
    assert poly is not None
    assert pytest.approx(poly.area, rel=1e-5) == GS_001_SQUARE.expected_area_m2

def test_t02_rectangle_parcel():
    """T02: 200m x 50m rectangle geometry area = 10,000 m²."""
    status, poly, err = parse_parcel_geometry(GS_002_RECTANGLE.vertices, is_closed=True)
    assert status == "VALID"
    assert poly is not None
    assert pytest.approx(poly.area, rel=1e-5) == GS_002_RECTANGLE.expected_area_m2

def test_t03_open_polyline():
    """T03: Unclosed polyline must be rejected with status OPEN."""
    unclosed_pts = [(0, 0), (100, 0), (100, 100)]
    status, poly, err = parse_parcel_geometry(unclosed_pts, is_closed=False)
    assert status == "OPEN"
    assert poly is None
    assert "not closed" in err.lower()

def test_t04_self_intersecting_polyline():
    """T04: Self-intersecting geometry must be rejected with status INVALID_GEOMETRY."""
    figure_8_pts = [(0, 0), (100, 100), (100, 0), (0, 100)]
    status, poly, err = parse_parcel_geometry(figure_8_pts, is_closed=True)
    assert status == "INVALID_GEOMETRY"
    assert poly is None
    assert "self-intersecting" in err.lower() or "invalid geometry" in err.lower()

def test_gs_003_setback():
    """GS-003: 5m Setback region inside 100x100 square gives 8,100 m²."""
    status, poly, err = parse_parcel_geometry(GS_003_SETBACK.vertices, is_closed=True)
    assert status == "VALID"
    assert pytest.approx(poly.area, rel=1e-5) == GS_003_SETBACK.expected_area_m2

def test_end_to_end_dxf_processing(tmp_path):
    """
    Tests T05, T06, T07 end-to-end using a temporary DXF file:
    - Unique deterministic parcel numbering (T05)
    - Correct CSV export (T06)
    - Labeled DXF export without touching original DXF file (T07)
    """
    original_dxf = tmp_path / "test_site.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # Meters
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    # Add 2 valid parcels and 1 unclosed polyline
    p1 = msp.add_lwpolyline([(0, 100), (100, 100), (100, 0), (0, 0)], dxfattribs={"layer": "PARCEL"})
    p1.close(True)

    p2 = msp.add_lwpolyline([(150, 50), (350, 50), (350, 0), (150, 0)], dxfattribs={"layer": "PARCEL"})
    p2.close(True)

    p3 = msp.add_lwpolyline([(0, -50), (50, -50), (50, -100)], dxfattribs={"layer": "PARCEL"})
    p3.close(False)

    doc.saveas(original_dxf)

    # Record original mtime and size
    orig_stat_before = original_dxf.stat()

    config = {
        "parcel": {
            "input_layers": ["PARCEL"],
            "fallback_unit": "m",
            "strict_unit_check": False,
            "id_prefix": "P",
            "id_digits": 3,
            "annotation": {"layer_name": "PARCEL_LABEL", "show_ha": True}
        },
        "output": {"dir": str(tmp_path / "out")}
    }

    time.sleep(0.05)
    parcels, labeled_dxf, csv_file, report_file = process_parcels(original_dxf, config, tmp_path / "out")

    # T07: Check original DXF was NOT modified
    orig_stat_after = original_dxf.stat()
    assert orig_stat_before.st_mtime == orig_stat_after.st_mtime
    assert orig_stat_before.st_size == orig_stat_after.st_size
    assert labeled_dxf.exists()
    assert labeled_dxf.name == "test_site_labeled.dxf"

    # T05: Check unique deterministic numbering
    valid_ids = [p.parcel_id for p in parcels if p.status == "VALID"]
    assert valid_ids == ["P001", "P002"]

    # T06: Check CSV export
    assert csv_file.exists()
    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 3
        assert reader[0]["parcel_id"] == "P001"
        assert float(reader[0]["area_m2"]) == 10000.0
        assert reader[2]["geometry_status"] == "OPEN"
