import csv
import time
from pathlib import Path
import pytest
import ezdxf
from planning_toolbox.core.geometry.parser import parse_parcel_geometry, get_interior_label_point
from planning_toolbox.cad.parcels.calculator import process_parcels
from planning_toolbox.config import load_config
from tests.fixtures.gold_standards import (
    GS_001_SQUARE, GS_002_RECTANGLE, GS_003_SETBACK,
)


# ===== T01–T04: Core Geometry Validation =====

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


# ===== Gold Standard Fixtures =====

def test_gs_003_setback():
    """GS-003: 5m Setback region inside 100x100 square gives 8,100 m²."""
    status, poly, err = parse_parcel_geometry(GS_003_SETBACK.vertices, is_closed=True)
    assert status == "VALID"
    assert pytest.approx(poly.area, rel=1e-5) == GS_003_SETBACK.expected_area_m2


# ===== Geometry Edge Cases =====

def test_fewer_than_3_vertices():
    """Polyline with fewer than 3 vertices must be rejected."""
    status, poly, err = parse_parcel_geometry([(0, 0), (100, 0)], is_closed=True)
    assert status == "INVALID_GEOMETRY"
    assert poly is None
    assert "fewer than 3" in err.lower()


def test_zero_area_polygon():
    """Degenerate polygon with zero area (collinear points) must be rejected."""
    status, poly, err = parse_parcel_geometry([(0, 0), (100, 0), (200, 0)], is_closed=True)
    assert status in ("ZERO_AREA", "INVALID_GEOMETRY")
    assert poly is None


def test_l_shaped_polygon_interior_point():
    """Interior label point for an L-shaped polygon must lie within the polygon."""
    # L-shape: a polygon where centroid might fall outside
    l_shape = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
    status, poly, err = parse_parcel_geometry(l_shape, is_closed=True)
    assert status == "VALID"
    pt = get_interior_label_point(poly)
    from shapely.geometry import Point
    assert poly.contains(Point(pt[0], pt[1]))


# ===== Config Loader Tests =====

def test_config_loader_default():
    """Config loader should find and load default.yaml successfully."""
    cfg = load_config()
    assert "parcel" in cfg
    assert "output" in cfg
    assert "input_layers" in cfg["parcel"]


def test_config_loader_custom_path(tmp_path):
    """Config loader should load from a custom path."""
    custom_cfg_file = tmp_path / "custom.yaml"
    custom_cfg_file.write_text("parcel:\n  id_prefix: X\n", encoding="utf-8")
    cfg = load_config(custom_cfg_file)
    assert cfg["parcel"]["id_prefix"] == "X"


def test_config_loader_missing_file():
    """Config loader must raise FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


# ===== End-to-End DXF Processing (T05, T06, T07) =====

def _create_test_dxf(path, unit_code=6, include_open=True):
    """Helper: create a test DXF file with parcels."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = unit_code
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    # Valid square 100x100 (top)
    p1 = msp.add_lwpolyline([(0, 100), (100, 100), (100, 0), (0, 0)], dxfattribs={"layer": "PARCEL"})
    p1.close(True)

    # Valid rectangle 200x50 (right)
    p2 = msp.add_lwpolyline([(150, 50), (350, 50), (350, 0), (150, 0)], dxfattribs={"layer": "PARCEL"})
    p2.close(True)

    if include_open:
        # Open polyline (error)
        p3 = msp.add_lwpolyline([(0, -50), (50, -50), (50, -100)], dxfattribs={"layer": "PARCEL"})
        p3.close(False)

    doc.saveas(path)
    return doc


def test_end_to_end_dxf_processing(tmp_path):
    """
    Tests T05, T06, T07 end-to-end using a temporary DXF file:
    - Unique deterministic parcel numbering (T05)
    - Correct CSV export (T06)
    - Labeled DXF export without touching original DXF file (T07)
    """
    original_dxf = tmp_path / "test_site.dxf"
    _create_test_dxf(original_dxf)

    import hashlib
    sha256_before = hashlib.sha256(original_dxf.read_bytes()).hexdigest()
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

    # T07: Check original DXF was NOT modified (SHA-256 hash & mtime/size check)
    sha256_after = hashlib.sha256(original_dxf.read_bytes()).hexdigest()
    orig_stat_after = original_dxf.stat()
    assert sha256_before == sha256_after, f"SHA-256 hash mismatch! Original file modified: {sha256_before} vs {sha256_after}"
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
        assert pytest.approx(float(reader[0]["area_m2"]), abs=0.1) == 10000.0
        assert reader[2]["geometry_status"] == "OPEN"

    # Check report file exists
    assert report_file.exists()
    report_content = report_file.read_text(encoding="utf-8")
    assert "Valid closed parcels: 2" in report_content
    assert "Open polylines: 1" in report_content


def test_multi_parcel_deterministic_numbering(tmp_path):
    """T05 extended: Verify that parcels are numbered top-to-bottom, left-to-right."""
    dxf_path = tmp_path / "multi.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    # Add parcels in reverse spatial order (bottom-right first, top-left last)
    # Parcel at bottom-right
    p1 = msp.add_lwpolyline([(100, 0), (200, 0), (200, -100), (100, -100)], dxfattribs={"layer": "PARCEL"})
    p1.close(True)
    # Parcel at bottom-left
    p2 = msp.add_lwpolyline([(0, 0), (50, 0), (50, -50), (0, -50)], dxfattribs={"layer": "PARCEL"})
    p2.close(True)
    # Parcel at top-left
    p3 = msp.add_lwpolyline([(0, 200), (80, 200), (80, 150), (0, 150)], dxfattribs={"layer": "PARCEL"})
    p3.close(True)

    doc.saveas(dxf_path)

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

    parcels, *_ = process_parcels(dxf_path, config, tmp_path / "out")
    valid = [p for p in parcels if p.status == "VALID"]

    # Top-left parcel (highest y) should be P001
    assert valid[0].parcel_id == "P001"
    assert pytest.approx(valid[0].geometry.bounds[3], abs=1) == 200  # maxy ≈ 200

    # Bottom parcels should be P002 (left) and P003 (right) by minx
    assert valid[1].parcel_id == "P002"
    assert valid[2].parcel_id == "P003"


def test_dxf_writer_isolation(tmp_path):
    """DXF annotation writer must not corrupt the document's existing entities."""
    dxf_path = tmp_path / "writer_test.dxf"
    _create_test_dxf(dxf_path, include_open=False)

    config = {
        "parcel": {
            "input_layers": ["PARCEL"],
            "fallback_unit": "m",
            "strict_unit_check": False,
            "id_prefix": "T",
            "id_digits": 2,
            "annotation": {"layer_name": "TEST_LABEL", "text_height": 3.0, "show_ha": True, "show_m2": True}
        },
        "output": {"dir": str(tmp_path / "out")}
    }

    parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, config, tmp_path / "out")

    # Verify the labeled DXF can be opened and has MTEXT entities on the label layer
    labeled_doc = ezdxf.readfile(labeled_dxf)
    label_entities = [e for e in labeled_doc.modelspace() if e.dxf.layer == "TEST_LABEL"]
    assert len(label_entities) == 2  # Two valid parcels should have labels

    # Verify that the original PARCEL layer polylines still exist
    parcel_entities = [e for e in labeled_doc.modelspace() if e.dxf.layer == "PARCEL"]
    assert len(parcel_entities) == 2  # Two original polylines preserved


# ===== RING-001 to RING-005: Nested Ring / Hole Detection Tests =====

def test_ring_001_nested_ring_prevents_false_sum(tmp_path):
    """RING-001: 100x100 outer ring containing 20x20 inner ring must NOT sum to 10,400 m². Inner ring is flagged."""
    dxf_path = tmp_path / "nested.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    # Outer 100x100 (10,000 m²)
    p_outer = msp.add_lwpolyline([(0, 100), (100, 100), (100, 0), (0, 0)], dxfattribs={"layer": "PARCEL"})
    p_outer.close(True)

    # Inner 20x20 (400 m²) inside outer
    p_inner = msp.add_lwpolyline([(40, 60), (60, 60), (60, 40), (40, 40)], dxfattribs={"layer": "PARCEL"})
    p_inner.close(True)

    doc.saveas(dxf_path)

    config = {
        "parcel": {
            "input_layers": ["PARCEL"],
            "fallback_unit": "m",
            "strict_unit_check": False,
            "id_prefix": "P",
            "id_digits": 3
        },
        "output": {"dir": str(tmp_path / "out")}
    }

    parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, config, tmp_path / "out")

    valid_parcels = [p for p in parcels if p.status == "VALID"]
    nested_parcels = [p for p in parcels if p.status == "NESTED_RING_DETECTED"]

    # Verify only 1 valid parcel (the outer 10,000 m² square)
    assert len(valid_parcels) == 1
    assert valid_parcels[0].area_m2 == 10000.0

    # Verify inner parcel is flagged as NESTED_RING_DETECTED
    assert len(nested_parcels) == 1
    assert "Nested ring detected" in nested_parcels[0].error_message

    # Total valid sum must be exactly 10,000 m², NOT 10,400 m²
    total_valid_m2 = sum(p.area_m2 for p in valid_parcels)
    assert total_valid_m2 == 10000.0


def test_ring_002_disjoint_parcels_remain_valid(tmp_path):
    """RING-002: Two disjoint separate parcels remain valid independent parcels."""
    dxf_path = tmp_path / "disjoint.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    # Parcel 1: 100x100 at (0, 0)
    p1 = msp.add_lwpolyline([(0, 100), (100, 100), (100, 0), (0, 0)], dxfattribs={"layer": "PARCEL"})
    p1.close(True)

    # Parcel 2: 50x50 at (200, 0)
    p2 = msp.add_lwpolyline([(200, 50), (250, 50), (250, 0), (200, 0)], dxfattribs={"layer": "PARCEL"})
    p2.close(True)

    doc.saveas(dxf_path)

    config = {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}}
    parcels, *_ = process_parcels(dxf_path, config, tmp_path / "out")

    valid_parcels = [p for p in parcels if p.status == "VALID"]
    assert len(valid_parcels) == 2


def test_ring_003_polygon_contains_polygon_triggers_nested(tmp_path):
    """RING-003: Polygon A contains Polygon B -> triggers NESTED_RING_DETECTED on B."""
    dxf_path = tmp_path / "contains.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    # Outer 200x200
    p_a = msp.add_lwpolyline([(0, 200), (200, 200), (200, 0), (0, 0)], dxfattribs={"layer": "PARCEL"})
    p_a.close(True)

    # Inner 50x50
    p_b = msp.add_lwpolyline([(50, 100), (100, 100), (100, 50), (50, 50)], dxfattribs={"layer": "PARCEL"})
    p_b.close(True)

    doc.saveas(dxf_path)

    config = {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}}
    parcels, *_ = process_parcels(dxf_path, config, tmp_path / "out")

    nested = [p for p in parcels if p.status == "NESTED_RING_DETECTED"]
    assert len(nested) == 1


def test_ring_004_touching_boundaries_not_hole(tmp_path):
    """RING-004: Two parcels sharing a boundary wall are NOT flagged as nested holes."""
    dxf_path = tmp_path / "touching.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    # Parcel 1: 100x100 from (0,0) to (100,100)
    p1 = msp.add_lwpolyline([(0, 100), (100, 100), (100, 0), (0, 0)], dxfattribs={"layer": "PARCEL"})
    p1.close(True)

    # Parcel 2: 100x100 touching Parcel 1 at x=100 line
    p2 = msp.add_lwpolyline([(100, 100), (200, 100), (200, 0), (100, 0)], dxfattribs={"layer": "PARCEL"})
    p2.close(True)

    doc.saveas(dxf_path)

    config = {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}}
    parcels, *_ = process_parcels(dxf_path, config, tmp_path / "out")

    valid_parcels = [p for p in parcels if p.status == "VALID"]
    nested_parcels = [p for p in parcels if p.status == "NESTED_RING_DETECTED"]

    # Both parcels should remain VALID
    assert len(valid_parcels) == 2
    assert len(nested_parcels) == 0


def test_ring_005_three_adjacent_parcels(tmp_path):
    """RING-005: Three adjacent parcels sharing boundaries remain valid separate parcels."""
    dxf_path = tmp_path / "three_adj.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()

    p1 = msp.add_lwpolyline([(0, 50), (50, 50), (50, 0), (0, 0)], dxfattribs={"layer": "PARCEL"})
    p1.close(True)

    p2 = msp.add_lwpolyline([(50, 50), (100, 50), (100, 0), (50, 0)], dxfattribs={"layer": "PARCEL"})
    p2.close(True)

    p3 = msp.add_lwpolyline([(100, 50), (150, 50), (150, 0), (100, 0)], dxfattribs={"layer": "PARCEL"})
    p3.close(True)

    doc.saveas(dxf_path)

    config = {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}}
    parcels, *_ = process_parcels(dxf_path, config, tmp_path / "out")

    valid_parcels = [p for p in parcels if p.status == "VALID"]
    assert len(valid_parcels) == 3


# ===== SAFE-001 to SAFE-003: Source File Protection & Path Collision Tests =====

def test_safe_001_path_collision_forbidden(tmp_path):
    """SAFE-001: export_labeled_dxf must raise ValueError if output_path == source_path."""
    dxf_path = tmp_path / "same_path.dxf"
    _create_test_dxf(dxf_path, include_open=False)

    doc = ezdxf.readfile(dxf_path)
    parcels, *_ = process_parcels(dxf_path, {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}}, tmp_path / "out")

    from planning_toolbox.cad.annotation.dxf_writer import export_labeled_dxf
    with pytest.raises(ValueError) as exc:
        export_labeled_dxf(doc, parcels, dxf_path, {})
    assert "Direct overwrite is forbidden" in str(exc.value)


def test_safe_002_normal_different_output_path(tmp_path):
    """SAFE-002: export_labeled_dxf succeeds when output_path is different from source_path."""
    src_path = tmp_path / "source.dxf"
    out_path = tmp_path / "different_labeled.dxf"
    _create_test_dxf(src_path, include_open=False)

    doc = ezdxf.readfile(src_path)
    parcels, *_ = process_parcels(src_path, {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}}, tmp_path / "out")

    from planning_toolbox.cad.annotation.dxf_writer import export_labeled_dxf
    result_path = export_labeled_dxf(doc, parcels, out_path, {})
    assert result_path.exists()
    assert result_path.resolve() != src_path.resolve()


def test_safe_003_sha256_hash_match_before_after(tmp_path):
    """SAFE-003: Source file SHA-256 hash before processing must match after processing 100%."""
    import hashlib
    src_path = tmp_path / "sha_check.dxf"
    _create_test_dxf(src_path, include_open=True)

    hash_before = hashlib.sha256(src_path.read_bytes()).hexdigest()
    parcels, labeled_dxf, csv_file, report_file = process_parcels(
        src_path,
        {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}},
        tmp_path / "out"
    )
    hash_after = hashlib.sha256(src_path.read_bytes()).hexdigest()

    assert hash_before == hash_after


