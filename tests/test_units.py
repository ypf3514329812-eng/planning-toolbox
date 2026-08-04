import pytest
from planning_toolbox.core.units.unit_manager import resolve_unit, UnitError, get_area_scale_to_m2

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

def test_unspecified_dxf_unit_failsafe_blocked():
    """Fail-Safe Test: Unspecified DXF unit ($INSUNITS=0) without fallback MUST raise UnitError (BLOCKED)."""
    with pytest.raises(UnitError) as exc:
        resolve_unit(doc_unit_code=0, fallback_unit=None, strict_check=True)
    assert "Unspecified" in str(exc.value)
