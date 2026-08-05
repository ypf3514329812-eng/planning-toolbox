import pytest
import ezdxf
from planning_toolbox.indicators.models import PlanningParcelIndicators
from planning_toolbox.indicators.calculator import calculate_parcel_indicators, process_dxf_indicators

def test_indicators_manual_calculation():
    """Test manual calculation of FAR, Building Density %, and Green Ratio %."""
    ind = calculate_parcel_indicators(
        parcel_id="P001",
        site_area_m2=10000.0,
        building_footprint_m2=2500.0,
        total_building_m2=20000.0,
        green_area_m2=3500.0
    )

    assert ind.far == 2.0
    assert ind.building_density_pct == 25.0
    assert ind.green_ratio_pct == 35.0
    assert ind.status == "VALID"


def test_indicators_zero_site_area_safety():
    """Test safety handling when site area is zero."""
    ind = calculate_parcel_indicators(
        parcel_id="P_ERR",
        site_area_m2=0.0,
        building_footprint_m2=500.0
    )

    assert ind.far == 0.0
    assert ind.building_density_pct == 0.0
    assert ind.green_ratio_pct == 0.0
    assert ind.status == "ZERO_SITE_AREA"


def test_indicators_dxf_extraction(tmp_path):
    """Test DXF layer intersection for PARCEL, BUILDING, GREEN layers."""
    dxf_path = tmp_path / "planning_site.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    doc.layers.add(name="BUILDING", color=2)
    doc.layers.add(name="GREEN", color=3)
    msp = doc.modelspace()

    # 100x100 Site Parcel (10,000 m²)
    p = msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], dxfattribs={"layer": "PARCEL"})
    p.close(True)

    # 50x50 Building Footprint (2,500 m²) inside site
    b = msp.add_lwpolyline([(10, 10), (60, 10), (60, 60), (10, 60)], dxfattribs={"layer": "BUILDING"})
    b.close(True)

    # 30x30 Green Area (900 m²) inside site
    g = msp.add_lwpolyline([(65, 65), (95, 65), (95, 95), (65, 95)], dxfattribs={"layer": "GREEN"})
    g.close(True)

    doc.saveas(dxf_path)

    config = {"default_floors": 4}
    results, csv_file, report_file = process_dxf_indicators(dxf_path, config=config, output_dir=tmp_path / "out")

    assert len(results) == 1
    ind = results[0]
    assert ind.site_area_m2 == 10000.0
    assert ind.building_footprint_m2 == 2500.0
    assert ind.green_area_m2 == 900.0
    assert ind.total_building_m2 == 10000.0  # 2,500 * 4 floors
    assert ind.far == 1.0
    assert ind.building_density_pct == 25.0
    assert ind.green_ratio_pct == 9.0
