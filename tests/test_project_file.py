"""Tests for save/load of local coursework project files."""

import json

import pytest

from planning_toolbox.gui.project_file import load_project, save_project
from planning_toolbox.project.chain_manifest import CRSDefinition, new_chain_manifest


def test_project_file_round_trip_preserves_workspace_and_result(tmp_path):
    project_path = tmp_path / "studio_work.ptx"
    state = {
        "dxf_path": "C:/study/site.dxf",
        "output_dir": "C:/study/output",
        "task": {"current_tab_index": 5, "concept_floors": 6},
        "last_task_name": "参数化概念方案草图生成",
        "last_result": {
            "task_type": "concept_plan",
            "output_files": [["概念方案 DXF", "C:/study/output/plan.dxf"]],
        },
        "workflow": {
            "version": 1,
            "current_step": "analysis",
            "source_kind": "dxf",
            "completed_steps": ["setup", "source", "inspection", "quality"],
            "skipped_steps": ["standardize"],
            "working_dxf": "C:/study/output/plan.dxf",
            "dxf_lineage": [
                {
                    "task_type": "concept_plan",
                    "stage": "analysis",
                    "source_path": "C:/study/site.dxf",
                    "output_path": "C:/study/output/plan.dxf",
                    "mode": "confirmed",
                }
            ],
        },
    }

    saved = save_project(project_path, state)
    loaded = load_project(saved)

    assert saved.suffix == ".ptx"
    assert loaded["dxf_path"] == state["dxf_path"]
    assert loaded["task"]["concept_floors"] == 6
    assert loaded["last_result"]["task_type"] == "concept_plan"
    assert loaded["workflow"]["current_step"] == "analysis"
    assert loaded["workflow"]["dxf_lineage"][0]["output_path"].endswith("plan.dxf")
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    assert payload["format"] == "planning-toolbox-project"
    assert payload["version"] == 2
    assert payload["chain_manifest"]["schema_version"] == 1


def test_project_file_preserves_chain_identity_and_coordinate_contract(tmp_path):
    project_path = tmp_path / "chain.ptx"
    manifest = new_chain_manifest("GIS-CAD-SU 课程作业", "urban_design").with_updates(
        crs=CRSDefinition(code=4547, name="CGCS2000 投影坐标", kind="projected").to_dict(),
        cad_unit="m",
    )

    save_project(project_path, {"dxf_path": "site.dxf", "chain_manifest": manifest.to_dict()})
    loaded = load_project(project_path)

    assert loaded["chain_manifest"]["project_id"] == manifest.project_id
    assert loaded["chain_manifest"]["crs"]["code"] == 4547


def test_version_one_project_is_migrated_with_stable_identity(tmp_path):
    project_path = tmp_path / "legacy_coursework.ptx"
    project_path.write_text(
        json.dumps(
            {
                "format": "planning-toolbox-project",
                "version": 1,
                "saved_at": "2026-01-01T12:00:00",
                "state": {"dxf_path": "legacy.dxf", "task": {}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first = load_project(project_path)
    second = load_project(project_path)

    assert first["dxf_path"] == "legacy.dxf"
    assert first["chain_manifest"]["name"] == "legacy_coursework"
    assert first["chain_manifest"]["project_id"] == second["chain_manifest"]["project_id"]


def test_project_file_rejects_unknown_format(tmp_path):
    project_path = tmp_path / "wrong.ptx"
    project_path.write_text('{"format":"other"}', encoding="utf-8")

    with pytest.raises(ValueError, match="不是 Planning Toolbox 项目文件"):
        load_project(project_path)
