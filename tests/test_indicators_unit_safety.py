"""Tests for indicators engine unit fail-safe policy enforcement (P0-2 fix verification)."""
import pytest
import ezdxf
from pathlib import Path
from planning_toolbox.indicators.calculator import process_dxf_indicators
from planning_toolbox.core.units.unit_manager import UnitError

def test_indicators_unspecified_unit_raises_unit_error(tmp_path):
    """Test that process_dxf_indicators raises UnitError when DXF unit is $INSUNITS=0 and strict_unit_check=True."""
    dxf_file = tmp_path / "unspecified_unit.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0  # Unspecified
    doc.layers.add(name="PARCEL", color=2)
    p = doc.modelspace().add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], dxfattribs={"layer": "PARCEL"})
    p.close(True)
    doc.saveas(dxf_file)

    config = {"strict_unit_check": True, "fallback_unit": None}
    with pytest.raises(UnitError) as exc_info:
        process_dxf_indicators(dxf_file, config=config, output_dir=tmp_path / "out")

    assert "CAD document unit ($INSUNITS) is Unspecified" in str(exc_info.value)
