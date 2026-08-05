"""Test validator setback end-to-end integration (P0-1 fix verification)."""
import pytest
import ezdxf
from pathlib import Path
from planning_toolbox.validators.setback import check_building_setback
from shapely.geometry import Polygon

def test_setback_compliant_building():
    """100x100m parcel with 20x30m building offset by 10m from all edges (satisfies 5.0m setback)."""
    parcel = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    building = Polygon([(10, 10), (40, 10), (40, 40), (10, 40)])

    result = check_building_setback(parcel, [building], required_setback_m=5.0, parcel_id="P001")
    assert result.status == "COMPLIANT"
    assert result.building_inside_setback is True
    assert result.violations_count == 0
    assert result.min_distance_m == 10.0

def test_setback_violating_building():
    """100x100m parcel with building offset by only 2.0m from edge (violates 5.0m setback requirement)."""
    parcel = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    building_violating = Polygon([(2, 10), (30, 10), (30, 40), (2, 40)])

    result = check_building_setback(parcel, [building_violating], required_setback_m=5.0, parcel_id="P002")
    assert result.status == "VIOLATION"
    assert result.building_inside_setback is False
    assert result.violations_count == 1
    assert result.min_distance_m == 2.0


def test_setback_converts_non_meter_geometry_units():
    parcel = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    building = Polygon([(16, 20), (30, 20), (30, 40), (16, 40)])

    result = check_building_setback(
        parcel,
        [building],
        required_setback_m=5.0,
        geometry_unit_to_m=0.3048,
    )

    assert result.status == "VIOLATION"
    assert result.min_distance_m == pytest.approx(4.8768, abs=0.01)


def test_setback_rejects_negative_requirement():
    parcel = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    with pytest.raises(ValueError, match="non-negative"):
        check_building_setback(parcel, [], required_setback_m=-1.0)


def test_setback_uses_hole_boundary_as_parcel_boundary():
    parcel = Polygon(
        shell=[(0, 0), (100, 0), (100, 100), (0, 100)],
        holes=[[(40, 40), (60, 40), (60, 60), (40, 60)]],
    )
    building_in_hole = Polygon([(45, 45), (50, 45), (50, 50), (45, 50)])

    result = check_building_setback(parcel, [building_in_hole], required_setback_m=5.0)

    assert result.status == "VIOLATION"
    assert result.min_distance_m == 5.0
