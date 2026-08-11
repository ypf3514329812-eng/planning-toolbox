import pytest
from pathlib import Path
import ezdxf
from planning_toolbox.cad.layers.compliance import audit_dxf_drafting_compliance
from planning_toolbox.cad.layers.template import create_planning_template
from planning_toolbox.cad.layers.manager import (
    build_alias_map,
    load_drafting_layer_config,
    load_layer_config,
    standardize_dxf_layers,
)

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

    # A small editable vector library is embedded as block definitions only.
    block_names = {block.name for block in doc.blocks}
    assert {
        "PT_NORTH_ARROW",
        "PT_SCALE_BAR_100M",
        "PT_ENTRANCE",
        "PT_TREE",
        "PT_PARKING_STALL",
    } <= block_names

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
    import hashlib
    sha256_before = hashlib.sha256(raw_dxf.read_bytes()).hexdigest()
    orig_stat_before = raw_dxf.stat()

    cfg = load_layer_config()
    std_dxf, report_file, remapped_counts, unmapped = standardize_dxf_layers(raw_dxf, cfg, tmp_path / "out")

    # Original file unmodified (SHA-256 & mtime check)
    sha256_after = hashlib.sha256(raw_dxf.read_bytes()).hexdigest()
    orig_stat_after = raw_dxf.stat()
    assert sha256_before == sha256_after
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


def test_china_drafting_profile_filters_layers_and_keeps_traceable_sources():
    cfg = load_drafting_layer_config("china_residential_site")

    assert cfg["profile"]["profile_id"] == "china_residential_site"
    assert cfg["style_authority"] == "assistive_defaults_not_statutory_values"
    assert "FIRE_ACCESS" in cfg["layers"]
    assert "PARKING" in cfg["layers"]
    assert "ECO_REDLINE" not in cfg["layers"]
    codes = {item["code"] for item in cfg["profile"]["references"]}
    assert "GB/T 50001-2017" in codes
    assert "GB 50180-2018" in codes


def test_china_drafting_standardization_aligns_styles_and_reports_review_items(tmp_path):
    source = tmp_path / "coursework.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("地块红线", color=1, lineweight=9)
    doc.layers.add("BUILDING", color=1, lineweight=9)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (80, 0), (80, 60), (0, 60)],
        close=True,
        dxfattribs={"layer": "地块红线"},
    )
    msp.add_lwpolyline(
        [(10, 10), (30, 10), (30, 20), (10, 20)],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    doc.saveas(source)

    cfg = load_drafting_layer_config("china_coursework_general")
    output, _, _, unmapped = standardize_dxf_layers(source, cfg, tmp_path / "out")
    result = audit_dxf_drafting_compliance(
        output,
        cfg,
        output_dir=tmp_path / "out",
        unmapped_layers=unmapped,
    )

    output_doc = ezdxf.readfile(output)
    assert output_doc.layers.get("PARCEL").dxf.color == cfg["layers"]["PARCEL"]["color"]
    assert output_doc.layers.get("BUILDING").dxf.lineweight == 30
    assert result["status"] == "review_required"
    assert result["blockers"] == []
    assert result["style_mismatches"] == []
    assert "GREEN" in result["empty_required_layers"]
    assert Path(result["report_path"]).is_file()
    assert Path(result["json_path"]).is_file()


def test_china_drafting_check_blocks_unknown_units_without_editing_source(tmp_path):
    source = tmp_path / "unknown_units.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.saveas(source)
    before = source.read_bytes()
    cfg = load_drafting_layer_config("china_coursework_general")

    result = audit_dxf_drafting_compliance(source, cfg, output_dir=tmp_path)

    assert result["status"] == "blocked"
    assert result["unit_code"] == 0
    assert result["blockers"]
    assert source.read_bytes() == before
