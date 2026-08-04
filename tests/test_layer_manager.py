import pytest
from pathlib import Path
import ezdxf
from planning_toolbox.cad.layers.template import create_planning_template
from planning_toolbox.cad.layers.manager import load_layer_config, standardize_dxf_layers, build_alias_map

def test_template_generation(tmp_path):
    """Test generating a blank CAD template containing all standard planning layers."""
    cfg = load_layer_config()
    template_path = tmp_path / "planning_template.dxf"
    out = create_planning_template(template_path, cfg)

    assert out.exists()
    doc = ezdxf.readfile(out)
    layer_names = [l.dxf.name for l in doc.layers]

    # Verify standard layers exist
    assert "PARCEL" in layer_names
    assert "ROAD_CENTER" in layer_names
    assert "ROAD_REDLINE" in layer_names
    assert "BUILDING" in layer_names
    assert "GREEN" in layer_names

    # Verify layer properties
    parcel_layer = doc.layers.get("PARCEL")
    assert parcel_layer.dxf.color == 2  # Yellow
    assert parcel_layer.dxf.lineweight == 30

    road_center = doc.layers.get("ROAD_CENTER")
    assert road_center.dxf.color == 1  # Red
    assert road_center.dxf.linetype == "CENTER"

def test_layer_alias_mapping():
    """Test layer alias map building."""
    cfg = load_layer_config()
    alias_map = build_alias_map(cfg["layers"])

    assert alias_map["PARCEL"] == "PARCEL"
    assert alias_map["地块"] == "PARCEL"
    assert alias_map["地块红线"] == "PARCEL"
    assert alias_map["中心线"] == "ROAD_CENTER"
    assert alias_map["BUILDING_FOOTPRINT"] == "BUILDING"

def test_standardize_dxf_layers(tmp_path):
    """Test layer standardization and entity remapping on a DXF file."""
    raw_dxf = tmp_path / "messy.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="地块红线", color=1)
    doc.layers.add(name="ROAD_CL", color=2)
    doc.layers.add(name="UNKNOWN_CUSTOM_LAYER", color=5)
    msp = doc.modelspace()

    # Add entities on non-standard layers
    p1 = msp.add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], dxfattribs={"layer": "地块红线"})
    p1.close(True)

    r1 = msp.add_lwpolyline([(0, 200), (500, 200)], dxfattribs={"layer": "ROAD_CL"})

    u1 = msp.add_line((0, 0), (10, 10), dxfattribs={"layer": "UNKNOWN_CUSTOM_LAYER"})

    doc.saveas(raw_dxf)
    orig_stat_before = raw_dxf.stat()

    cfg = load_layer_config()
    std_dxf, report_file, remapped_counts, unmapped = standardize_dxf_layers(raw_dxf, cfg, tmp_path / "out")

    # Original file unmodified
    orig_stat_after = raw_dxf.stat()
    assert orig_stat_before.st_mtime == orig_stat_after.st_mtime
    assert std_dxf.exists()

    # Verify remapping in standardized DXF
    std_doc = ezdxf.readfile(std_dxf)
    std_msp = std_doc.modelspace()

    parcel_entities = [e for e in std_msp if e.dxf.layer == "PARCEL"]
    assert len(parcel_entities) == 1

    road_center_entities = [e for e in std_msp if e.dxf.layer == "ROAD_CENTER"]
    assert len(road_center_entities) == 1

    # Check report contents
    assert report_file.exists()
    report_text = report_file.read_text(encoding="utf-8")
    assert "PARCEL" in report_text
    assert "UNKNOWN_CUSTOM_LAYER" in report_text
