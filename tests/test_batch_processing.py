"""Acceptance tests for folder-based DXF batch analysis."""

from pathlib import Path
import shutil

import ezdxf
import pytest

from planning_toolbox.batch.analyzer import analyze_dxf_batch


def _prepare_input_folder(tmp_path: Path, include_unknown_unit: bool = False) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    sample = Path("sample_data/sample_parcels.dxf")
    shutil.copy2(sample, input_dir / "01_valid.dxf")
    if include_unknown_unit:
        unknown = input_dir / "02_unknown_unit.dxf"
        shutil.copy2(sample, unknown)
        doc = ezdxf.readfile(unknown)
        doc.header["$INSUNITS"] = 0
        doc.saveas(unknown)
    else:
        shutil.copy2(sample, input_dir / "02_valid.dxf")
    return input_dir


def test_batch_parcel_processes_all_files_and_writes_summary(tmp_path):
    input_dir = _prepare_input_folder(tmp_path)
    result = analyze_dxf_batch(input_dir, tmp_path / "output", task_type="parcel")

    assert result["processed_count"] == 2
    assert result["success_count"] == 2
    assert result["failed_count"] == 0
    assert Path(result["summary_file"]).exists()
    assert (tmp_path / "output" / "01_valid" / "01_valid_report.txt").exists()


def test_batch_indicator_requires_floors_and_isolates_bad_file(tmp_path):
    input_dir = _prepare_input_folder(tmp_path, include_unknown_unit=True)

    with pytest.raises(ValueError, match="楼层倍数"):
        analyze_dxf_batch(input_dir, tmp_path / "blocked", task_type="indicator")

    result = analyze_dxf_batch(
        input_dir,
        tmp_path / "output",
        task_type="indicator",
        floors=6,
    )
    assert result["processed_count"] == 2
    assert result["success_count"] == 1
    assert result["failed_count"] == 1
    failed = [item for item in result["items"] if item["status"] == "FAILED"]
    assert failed and failed[0]["message"]
