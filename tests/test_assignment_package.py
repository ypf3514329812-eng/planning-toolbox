"""Tests for the local coursework package exporter."""

from pathlib import Path

from planning_toolbox.gui.assignment_package import build_assignment_package


def test_build_assignment_package_categorizes_outputs_and_writes_notes(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    dxf = output_dir / "concept_plan.dxf"
    csv = output_dir / "concept_schedule.csv"
    report = output_dir / "concept_report.txt"
    dxf.write_text("DXF placeholder", encoding="utf-8")
    csv.write_text("id,area\nP001,100", encoding="utf-8")
    report.write_text("report", encoding="utf-8")

    package_dir, archive_path = build_assignment_package(
        output_dir,
        "参数化概念方案草图生成",
        {
            "task_type": "concept_plan",
            "source_file": "sample.dxf",
            "source_sha256": "abc123",
            "standards_profile_name": "居住区国家标准框架",
            "standards_references": ("GB 50180-2018",),
            "output_files": [
                ("概念方案 DXF", str(dxf)),
                ("明细表", str(csv)),
                ("文字报告", str(report)),
            ],
        },
    )

    assert package_dir.is_dir()
    assert archive_path.is_file()
    assert (package_dir / "01_CAD" / dxf.name).is_file()
    assert (package_dir / "02_数据表" / csv.name).is_file()
    assert (package_dir / "03_报告" / report.name).is_file()
    manifest = (package_dir / "00_作业包说明.txt").read_text(encoding="utf-8")
    assert "参数化概念方案草图生成" in manifest
    assert "GB 50180-2018" in manifest
    assert "输入文件 SHA-256：abc123" in manifest


def test_assignment_package_uses_unique_timestamped_directory(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    source = output_dir / "result.csv"
    source.write_text("ok", encoding="utf-8")
    result = {"output_files": [("结果", str(source))]}

    first_dir, first_zip = build_assignment_package(output_dir, "任务", result)
    second_dir, second_zip = build_assignment_package(output_dir, "任务", result)

    assert first_dir != second_dir
    assert first_zip != second_zip
    assert Path(first_zip).is_file()
    assert Path(second_zip).is_file()
