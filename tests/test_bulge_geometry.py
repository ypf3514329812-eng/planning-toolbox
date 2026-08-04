import math
import pytest
import ezdxf
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry

# Standard math constants for arc segment calculations
# 90-degree arc bulge = tan(pi/8) = sqrt(2) - 1 ≈ 0.41421356237309515
BULGE_90_DEG = math.tan(math.pi / 8.0)

# Segment area formula for 90-degree arc on side L=100: R = 100/sqrt(2) = 50*sqrt(2)
# Segment area = 0.5 * R^2 * (pi/2 - 1) = 2500 * (pi/2 - 1) ≈ 1426.9908169872415 m²
SEGMENT_AREA_90_L100 = 2500.0 * (math.pi / 2.0 - 1.0)


def create_lwpolyline_doc(points, bulge_dict=None, is_closed=True):
    """Helper to create a DXF document with a single LWPOLYLINE containing specified bulges."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    msp = doc.modelspace()
    poly = msp.add_lwpolyline(points, dxfattribs={"layer": "PARCEL"})
    if bulge_dict:
        for idx, b in bulge_dict.items():
            poly[idx] = (points[idx][0], points[idx][1], 0, 0, b)
    poly.close(is_closed)
    return poly


def test_bulge_001_positive_90_deg_arc():
    """
    BULGE-001: Counter-clockwise polyline top edge with positive 90-degree bulge.
    For segment (100,100) -> (0,100) (Westward):
    Positive bulge curves outward (North, y>100), increasing area.
    Expected theoretical area = 10,000 + 1,426.99 = 11,426.99 m².
    """
    pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    poly_ent = create_lwpolyline_doc(pts, bulge_dict={2: BULGE_90_DEG})

    vertices, is_closed, _has_approx = points_from_dxf_polyline(poly_ent)
    status, poly, err = parse_parcel_geometry(vertices, is_closed)

    assert status == "VALID"
    expected_area = 10000.0 + SEGMENT_AREA_90_L100  # 11,426.9908 m²
    actual_area = poly.area
    abs_err = abs(actual_area - expected_area)
    rel_err = abs_err / expected_area

    # Discretization via ezdxf.path flattening(distance=0.01) achieves 0.70 m² error (< 0.007% relative error)
    assert abs_err < 1.0, f"Expected {expected_area:.2f}, got {actual_area:.2f}, error={abs_err:.4f}"
    assert rel_err < 1e-3


def test_bulge_002_negative_90_deg_arc():
    """
    BULGE-002: Counter-clockwise polyline top edge with negative 90-degree bulge.
    For segment (100,100) -> (0,100) (Westward):
    Negative bulge curves inward (South, y<100), decreasing area.
    Expected theoretical area = 10,000 - 1,426.99 = 8,573.01 m².
    """
    pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    poly_ent = create_lwpolyline_doc(pts, bulge_dict={2: -BULGE_90_DEG})

    vertices, is_closed, _has_approx = points_from_dxf_polyline(poly_ent)
    status, poly, err = parse_parcel_geometry(vertices, is_closed)

    assert status == "VALID"
    expected_area = 10000.0 - SEGMENT_AREA_90_L100  # 8,573.0092 m²
    actual_area = poly.area
    abs_err = abs(actual_area - expected_area)

    assert abs_err < 1.0, f"Expected {expected_area:.2f}, got {actual_area:.2f}, error={abs_err:.4f}"


def test_bulge_003_multiple_bulge_segments():
    """BULGE-003: Polyline with multiple bulge segments (two outward 90° arcs). Expected area = 10,000 + 2*1,426.99 = 12,853.98 m²."""
    pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    # Segment 0: (0,0)->(100,0) (Eastward, positive bulge = outward South)
    # Segment 2: (100,100)->(0,100) (Westward, positive bulge = outward North)
    poly_ent = create_lwpolyline_doc(pts, bulge_dict={0: BULGE_90_DEG, 2: BULGE_90_DEG})

    vertices, is_closed, _has_approx = points_from_dxf_polyline(poly_ent)
    status, poly, err = parse_parcel_geometry(vertices, is_closed)

    assert status == "VALID"
    expected_area = 10000.0 + 2 * SEGMENT_AREA_90_L100  # 12,853.98 m²
    actual_area = poly.area
    assert abs(actual_area - expected_area) < 2.0


def test_bulge_004_arc_greater_than_180_deg():
    """BULGE-004: Arc greater than 180 degrees (large bulge b = tan(3*pi/8) ≈ 2.41421356). Expected area > 11,426 m²."""
    b_large = math.tan(3 * math.pi / 8.0)
    pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    poly_ent = create_lwpolyline_doc(pts, bulge_dict={2: b_large})

    vertices, is_closed, _has_approx = points_from_dxf_polyline(poly_ent)
    status, poly, err = parse_parcel_geometry(vertices, is_closed)

    assert status == "VALID"
    assert poly.area > 11426.0


def test_bulge_005_mixed_straight_and_curved_boundary():
    """BULGE-005: Mixed straight lines and curved arc boundaries."""
    pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    poly_ent = create_lwpolyline_doc(pts, bulge_dict={2: BULGE_90_DEG})

    vertices, is_closed, _has_approx = points_from_dxf_polyline(poly_ent)
    status, poly, err = parse_parcel_geometry(vertices, is_closed)

    assert status == "VALID"
    assert poly.area > 10000.0


def test_bulge_006_clockwise_vs_counter_clockwise_equivalence():
    """BULGE-006: Clockwise and counter-clockwise vertex orders with equivalent arc orientation produce identical area."""
    # CCW polygon with top edge outward bulge (Segment 2: (100,100)->(0,100), bulge = +b)
    pts_ccw = [(0, 0), (100, 0), (100, 100), (0, 100)]
    poly_ccw = create_lwpolyline_doc(pts_ccw, bulge_dict={2: BULGE_90_DEG})

    v_ccw, c_ccw, _ = points_from_dxf_polyline(poly_ccw)
    s_ccw, p_ccw, _ = parse_parcel_geometry(v_ccw, c_ccw)

    # CW polygon with top edge outward bulge (Segment 0: (0,100)->(100,100), bulge = -b)
    pts_cw = [(0, 100), (100, 100), (100, 0), (0, 0)]
    poly_cw = create_lwpolyline_doc(pts_cw, bulge_dict={0: -BULGE_90_DEG})

    v_cw, c_cw, _ = points_from_dxf_polyline(poly_cw)
    s_cw, p_cw, _ = parse_parcel_geometry(v_cw, c_cw)

    assert s_ccw == "VALID" and s_cw == "VALID"
    assert pytest.approx(p_ccw.area, rel=1e-3) == p_cw.area


def test_bulge_007_closed_curved_capsule_parcel():
    """BULGE-007: Closed capsule polygon with two 180-degree semi-circle ends (bulge = +1.0 on Segment 1 and Segment 3). Expected area = 10,000 + 2500*pi ≈ 17,853.98 m²."""
    pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    # Segment 1: (100,0)->(100,100) (Northward, positive bulge = outward East)
    # Segment 3: (0,100)->(0,0) (Southward, positive bulge = outward West)
    poly_ent = create_lwpolyline_doc(pts, bulge_dict={1: 1.0, 3: 1.0})

    vertices, is_closed, _has_approx = points_from_dxf_polyline(poly_ent)
    status, poly, err = parse_parcel_geometry(vertices, is_closed)

    assert status == "VALID"
    expected_area = 10000.0 + 2 * (0.5 * math.pi * 50.0**2)  # 17,853.98 m²
    actual_area = poly.area
    assert abs(actual_area - expected_area) < 2.0
