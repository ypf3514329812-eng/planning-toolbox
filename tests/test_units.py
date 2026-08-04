import pytest
import ezdxf
from planning_toolbox.core.units.unit_manager import resolve_unit, UnitError, get_area_scale_to_m2
from planning_toolbox.cad.io.dxf_reader import read_dxf_parcels
from planning_toolbox.cad.parcels.calculator import process_parcels

def test_t08_unknown_unit_handling():
    """T08: Unknown or unspecified unit must be rejected when strict_check is enabled or fallback is missing."""
    # 0 = Unspecified
    with pytest.raises(UnitError) as exc_info:
        resolve_unit(doc_unit_code=0, fallback_unit=None, strict_check=False)
    assert "Unspecified" in str(exc_info.value)

    with pytest.raises(UnitError):
        resolve_unit(doc_unit_code=0, fallback_unit="m", strict_check=True)

    # Unit 6 = Meters
    unit_name = resolve_unit(doc_unit_code=6, fallback_unit="m", strict_check=True)
    assert unit_name == "Meters"
    assert get_area_scale_to_m2(unit_name) == 1.0

    # Unit 4 = Millimeters -> area scale 1e-6
    mm_unit = resolve_unit(doc_unit_code=4, fallback_unit=None)
    assert mm_unit == "Millimeters"
    assert pytest.approx(get_area_scale_to_m2(mm_unit)) == 0.000001


def test_unit_001_dxf_reader_unspecified_unit_failsafe(tmp_path):
    """UNIT-001: read_dxf_parcels API must fail-safe (raise UnitError) when INSUNITS=0 and no fallback given."""
    dxf_file = tmp_path / "unspecified.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.saveas(dxf_file)

    with pytest.raises(UnitError):
        read_dxf_parcels(dxf_file, target_layers=["PARCEL"])


def test_unit_002_dxf_reader_explicit_fallback(tmp_path):
    """UNIT-002: read_dxf_parcels with INSUNITS=0 works when user explicitly specifies fallback and strict_check=False."""
    dxf_file = tmp_path / "unspecified.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.saveas(dxf_file)

    doc_read, entities, unit_name, scale = read_dxf_parcels(
        dxf_file, target_layers=["PARCEL"], fallback_unit="m", strict_unit_check=False
    )
    assert unit_name == "m"
    assert scale == 1.0


def test_unit_003_dxf_reader_known_unit(tmp_path):
    """UNIT-003: read_dxf_parcels with INSUNITS=6 (Meters) processes normally without fallback."""
    dxf_file = tmp_path / "meters.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.saveas(dxf_file)

    doc_read, entities, unit_name, scale = read_dxf_parcels(dxf_file, target_layers=["PARCEL"])
    assert unit_name == "Meters"
    assert scale == 1.0


def test_unit_004_process_parcels_empty_config_failsafe(tmp_path):
    """UNIT-004: process_parcels with empty config on INSUNITS=0 DXF must raise UnitError (BLOCKED)."""
    dxf_file = tmp_path / "unspecified.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.saveas(dxf_file)

    with pytest.raises(UnitError):
        process_parcels(dxf_file, config={}, output_dir=tmp_path / "out")


def test_unit_005_no_silent_meter_assumption():
    """UNIT-005: Confirm resolve_unit strictly refuses doc_unit_code=0 when fallback_unit=None."""
    with pytest.raises(UnitError) as exc:
        resolve_unit(doc_unit_code=0, fallback_unit=None, strict_check=True)
    assert "Unspecified" in str(exc.value)
