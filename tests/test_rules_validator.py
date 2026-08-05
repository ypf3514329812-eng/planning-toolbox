import pytest
import ezdxf
from shapely.geometry import Polygon
from planning_toolbox.validators.topology import validate_polyline_topology
from planning_toolbox.validators.setback import check_building_setback

def test_topology_validation_valid_and_invalid():
    """Test topology validator on valid, open, and invalid polyline entities."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Valid closed square
    p1 = msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], dxfattribs={"layer": "PARCEL"})
    p1.close(True)
    res1 = validate_polyline_topology(p1, 0)
    assert res1.status == "VALID"
    assert res1.is_simple is True

    # Open polyline
    p2 = msp.add_lwpolyline([(0, 0), (100, 0), (100, 100)], dxfattribs={"layer": "PARCEL"})
    p2.close(False)
    res2 = validate_polyline_topology(p2, 1)
    assert res2.status == "OPEN"

    # Self-intersecting figure-8 polyline
    p3 = msp.add_lwpolyline([(0, 0), (100, 100), (100, 0), (0, 100)], dxfattribs={"layer": "PARCEL"})
    p3.close(True)
    res3 = validate_polyline_topology(p3, 2)
    assert res3.status == "INVALID_GEOMETRY"


def test_setback_check_compliant():
    """Test building footprint placed 10m inside parcel satisfies 5m setback requirement."""
    parcel_poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)]) # 100x100
    building_poly = Polygon([(10, 10), (50, 10), (50, 50), (10, 50)]) # 10m from all edges

    res = check_building_setback(
        parcel_polygon=parcel_poly,
        building_polygons=[building_poly],
        required_setback_m=5.0,
        parcel_id="P001"
    )

    assert res.status == "COMPLIANT"
    assert res.building_inside_setback is True
    assert res.violations_count == 0
    assert res.min_distance_m == 10.0


def test_setback_check_violation():
    """Test building footprint placed 2m from boundary violates 5m setback requirement."""
    parcel_poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    building_poly = Polygon([(2, 2), (50, 2), (50, 50), (2, 50)]) # 2m from left/bottom edges

    res = check_building_setback(
        parcel_polygon=parcel_poly,
        building_polygons=[building_poly],
        required_setback_m=5.0,
        parcel_id="P001"
    )

    assert res.status == "VIOLATION"
    assert res.building_inside_setback is False
    assert res.violations_count == 1
    assert res.min_distance_m == 2.0
