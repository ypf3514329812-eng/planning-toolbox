"""Tests for the unified planning-toolbox CLI subcommands."""
import pytest
from pathlib import Path
from planning_toolbox.cli import main
import sys

def test_cli_version_and_help(capsys, monkeypatch):
    """Test CLI --version and basic help flag."""
    monkeypatch.setattr(sys, "argv", ["planning-toolbox", "--version"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "Planning Toolbox v" in captured.out or "Planning Toolbox v" in captured.err

def test_cli_parcel_command(tmp_path, capsys, monkeypatch):
    """Test 'planning-toolbox parcel' subcommand on sample DXF."""
    import ezdxf
    dxf_file = tmp_path / "test_parcel.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=2)
    lw = doc.modelspace().add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], dxfattribs={"layer": "PARCEL"})
    lw.close(True)
    doc.saveas(dxf_file)

    out_dir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["planning-toolbox", "parcel", "--dxf", str(dxf_file), "--output", str(out_dir)])
    main()

    captured = capsys.readouterr()
    assert "地块面积计算与编号工具" in captured.out
    assert "有效闭合地块:         1" in captured.out
    assert (out_dir / "test_parcel_labeled.dxf").exists()
    assert (out_dir / "test_parcel.csv").exists()

def test_cli_indicator_manual_command(capsys, monkeypatch):
    """Test 'planning-toolbox indicator' with manual area values."""
    monkeypatch.setattr(sys, "argv", [
        "planning-toolbox", "indicator",
        "--site-area", "10000",
        "--building-footprint", "2500",
        "--total-building", "20000",
        "--green-area", "3500"
    ])
    main()

    captured = capsys.readouterr()
    assert "容积率 (FAR):         2.00" in captured.out
    assert "建筑密度:             25.00%" in captured.out
    assert "绿地率:               35.00%" in captured.out

def test_cli_validate_blocks_unknown_dxf_units(tmp_path, monkeypatch):
    """A meter-based setback check must not run on an unspecified-unit DXF."""
    import ezdxf
    dxf_file = tmp_path / "unknown_unit.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.layers.add(name="PARCEL", color=2)
    p = doc.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        dxfattribs={"layer": "PARCEL"},
    )
    p.close(True)
    doc.saveas(dxf_file)

    monkeypatch.setattr(sys, "argv", ["planning-toolbox", "validate", "--dxf", str(dxf_file)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_cli_validate_associates_buildings_with_parcels(tmp_path, capsys, monkeypatch):
    """Buildings from another parcel must not create false setback violations."""
    import ezdxf
    dxf_file = tmp_path / "multi_parcel_val.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=2)
    doc.layers.add(name="BUILDING", color=4)
    msp = doc.modelspace()

    for points in (
        [(0, 0), (100, 0), (100, 100), (0, 100)],
        [(200, 0), (300, 0), (300, 100), (200, 100)],
    ):
        parcel = msp.add_lwpolyline(points, dxfattribs={"layer": "PARCEL"})
        parcel.close(True)
    building = msp.add_lwpolyline(
        [(10, 10), (40, 10), (40, 40), (10, 40)],
        dxfattribs={"layer": "BUILDING"},
    )
    building.close(True)
    doc.saveas(dxf_file)

    monkeypatch.setattr(sys, "argv", ["planning-toolbox", "validate", "--dxf", str(dxf_file)])
    main()

    captured = capsys.readouterr()
    assert captured.out.count("[合规]") == 1
    assert captured.out.count("[无建筑]") == 1


def test_cli_validate_command(tmp_path, capsys, monkeypatch):
    """Test 'planning-toolbox validate' subcommand."""
    import ezdxf
    dxf_file = tmp_path / "test_val.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=2)
    doc.layers.add(name="BUILDING", color=4)
    p = doc.modelspace().add_lwpolyline([(0, 0), (100, 0), (100, 100), (0, 100)], dxfattribs={"layer": "PARCEL"})
    p.close(True)
    b = doc.modelspace().add_lwpolyline([(10, 10), (40, 10), (40, 40), (10, 40)], dxfattribs={"layer": "BUILDING"})
    b.close(True)
    doc.saveas(dxf_file)

    monkeypatch.setattr(sys, "argv", ["planning-toolbox", "validate", "--dxf", str(dxf_file), "--setback", "5.0"])
    main()

    captured = capsys.readouterr()
    assert "拓扑与退线规则检查" in captured.out
    assert "合规" in captured.out


def test_cli_china_drafting_template_and_standardize(tmp_path, capsys, monkeypatch):
    import ezdxf

    template = tmp_path / "china_coursework_template.dxf"
    monkeypatch.setattr(sys, "argv", [
        "planning-toolbox",
        "layer",
        "template",
        "--drafting-profile",
        "china_coursework_general",
        "--output",
        str(template),
    ])
    main()
    assert template.is_file()
    template_doc = ezdxf.readfile(template)
    assert "PT_NORTH_ARROW" in {block.name for block in template_doc.blocks}
    assert "DIMENSION" in {layer.dxf.name for layer in template_doc.layers}

    source = tmp_path / "raw_coursework.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("地块红线")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 80), (0, 80)],
        close=True,
        dxfattribs={"layer": "地块红线"},
    )
    doc.saveas(source)
    output_dir = tmp_path / "standardized"
    monkeypatch.setattr(sys, "argv", [
        "planning-toolbox",
        "layer",
        "standardize",
        "--dxf",
        str(source),
        "--drafting-profile",
        "china_coursework_general",
        "--output",
        str(output_dir),
    ])
    main()

    captured = capsys.readouterr()
    assert "中国制图辅助检查" in captured.out
    assert (output_dir / "raw_coursework_standardized.dxf").is_file()
    assert (output_dir / "raw_coursework_standardized_china_drafting_check.txt").is_file()
    assert (output_dir / "raw_coursework_standardized_china_drafting_check.json").is_file()
