"""Tests for the lightweight GIS-CAD-SketchUp coursework workflow guide."""

from planning_toolbox.gui.workflow import (
    apply_verified_context,
    continuation_dxf_candidate,
    default_workflow_state,
    mark_stage_complete,
    normalize_workflow_state,
    progress_percent,
    record_working_dxf,
    set_stage_skipped,
)


def test_workflow_state_advances_from_verified_evidence():
    state = apply_verified_context(
        default_workflow_state(),
        {
            "project_configured": True,
            "source_ready": True,
            "inspection_ready": True,
        },
    )

    assert state["completed_steps"] == ["setup", "source", "inspection"]
    assert state["current_step"] == "standardize"
    assert progress_percent(state) == 33

    state = mark_stage_complete(state, "standardize")
    assert state["current_step"] == "quality"


def test_workflow_only_allows_optional_stages_to_be_skipped():
    state = set_stage_skipped(default_workflow_state(), "quality", True)
    assert state["skipped_steps"] == []

    state = set_stage_skipped(state, "gis", True)
    assert state["skipped_steps"] == ["gis"]

    restored = set_stage_skipped(state, "gis", False)
    assert restored["skipped_steps"] == []


def test_workflow_state_sanitizes_unknown_saved_values():
    state = normalize_workflow_state(
        {
            "current_step": "unknown",
            "source_kind": "camera",
            "completed_steps": ["setup", "bad", "quality"],
            "skipped_steps": ["quality", "gis", "bad"],
        }
    )

    assert state["current_step"] == "setup"
    assert state["source_kind"] == "dxf"
    assert state["completed_steps"] == ["setup", "quality"]
    assert state["skipped_steps"] == ["gis"]


def test_continuation_candidate_uses_task_specific_editable_dxf():
    quality = {
        "task_type": "quality_check",
        "repair": {"output_file": "C:/work/site_repaired.dxf"},
        "output_files": [
            ("质量报告", "C:/work/report.txt"),
            ("安全修复 DXF", "C:/work/other.dxf"),
        ],
    }
    assert continuation_dxf_candidate(quality).endswith("site_repaired.dxf")
    assert continuation_dxf_candidate(
        {
            "task_type": "layer_standardize",
            "output_files": [("标准化 DXF", "C:/work/site_standardized.dxf")],
        }
    ).endswith("site_standardized.dxf")
    assert continuation_dxf_candidate(
        {"task_type": "indicator", "output_files": [("结果", "C:/work/marked.dxf")]}
    ) == ""


def test_working_dxf_lineage_is_bounded_deduplicated_and_migrates_v1():
    state = record_working_dxf(
        {"version": 1, "completed_steps": ["setup"]},
        source_path="C:/work/source.dxf",
        output_path="C:/work/repaired.dxf",
        task_type="quality_check",
        automatic=False,
    )
    state = record_working_dxf(
        state,
        source_path="C:/work/source.dxf",
        output_path="C:/work/repaired.dxf",
        task_type="quality_check",
        automatic=False,
    )

    assert state["version"] == 2
    assert state["working_dxf"].endswith("repaired.dxf")
    assert len(state["dxf_lineage"]) == 1
    assert state["dxf_lineage"][0]["mode"] == "confirmed"
    assert state["dxf_lineage"][0]["stage"] == "quality"

