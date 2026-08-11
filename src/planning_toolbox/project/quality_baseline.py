"""Write conservative, source-bound quality baselines for the main workflow.

The reports in this module deliberately describe *evidence and review gates*,
not survey accuracy or design quality.  They make repeated Image -> CAD ->
SketchUp runs comparable without making unsupported precision claims.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from planning_toolbox.utils.file_integrity import sha256_file


QUALITY_BASELINE_FORMAT = "planning-toolbox-quality-baseline"
QUALITY_BASELINE_SCHEMA_VERSION = 1


def quality_baseline_path_for_artifact(path: Path | str) -> Path:
    """Return the sidecar path for a generated DXF or SketchUp handoff."""
    artifact = Path(path).resolve()
    return artifact.with_name(f"{artifact.stem}_quality_baseline.json")


def _gate(
    key: str,
    status: str,
    label: str,
    evidence: Mapping[str, Any],
    recommendation: str = "",
) -> dict[str, Any]:
    if status not in {"pass", "review", "blocked"}:
        raise ValueError(f"Unsupported quality-gate status: {status}")
    return {
        "key": key,
        "status": status,
        "label": label,
        "evidence": dict(evidence),
        "recommendation": recommendation,
    }


def _summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = sum(1 for item in gates if item["status"] == "blocked")
    review = sum(1 for item in gates if item["status"] == "review")
    passed = sum(1 for item in gates if item["status"] == "pass")
    return {
        "status": (
            "blocked"
            if blocked
            else "review_required"
            if review
            else "concept_ready"
        ),
        "passed_count": passed,
        "review_count": review,
        "blocked_count": blocked,
        "gate_count": len(gates),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _write(payload: dict[str, Any], output_path: Path | str) -> dict[str, Any]:
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = dict(payload["summary"])
    return {
        "path": str(destination),
        "sha256": sha256_file(destination),
        **summary,
    }


def write_image_to_cad_quality_baseline(
    result: Mapping[str, Any],
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a review-first quality baseline for an Image -> CAD run."""
    source = Path(str(result["source_file"])).resolve()
    dxf = Path(str(result["dxf_file"])).resolve()
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else quality_baseline_path_for_artifact(dxf)
    )
    expected_source_hash = str(result.get("source_sha256", "")).lower()
    source_exists = source.is_file()
    dxf_exists = dxf.is_file()
    actual_source_hash = sha256_file(source) if source_exists else ""
    actual_dxf_hash = sha256_file(dxf) if dxf_exists else ""
    reference_width_m = result.get("reference_width_m")
    explicit_scale = isinstance(reference_width_m, (int, float)) and reference_width_m > 0
    gates: list[dict[str, Any]] = [
        _gate(
            "explicit_scale",
            "pass" if explicit_scale else "blocked",
            "明确图像尺度",
            {"reference_width_m": reference_width_m},
            "请填写底图实际宽度（米）；系统不会猜测比例。",
        ),
        _gate(
            "source_integrity",
            "pass" if source_exists and actual_source_hash == expected_source_hash else "blocked",
            "原始图片只读校验",
            {
                "source_file": str(source),
                "expected_sha256": expected_source_hash,
                "actual_sha256": actual_source_hash,
            },
            "原图已变化或不可读取，请重新执行转换以保持链路可追溯。",
        ),
        _gate(
            "dxf_output",
            "pass" if dxf_exists else "blocked",
            "DXF 输出可读取",
            {"dxf_file": str(dxf), "dxf_sha256": actual_dxf_hash},
            "未生成有效 DXF，请查看转换报告后重试。",
        ),
    ]

    scene_path_text = str(result.get("semantic_scene_file", "")).strip()
    scene_path = Path(scene_path_text).resolve() if scene_path_text else None
    scene = _read_json(scene_path) if scene_path and scene_path.is_file() else None
    scene_source = dict((scene or {}).get("source", {}))
    scene_bound = bool(
        scene
        and scene_source.get("dxf_sha256") == actual_dxf_hash
        and scene_source.get("source_image_sha256") == expected_source_hash
    )
    gates.append(
        _gate(
            "semantic_traceability",
            "pass" if scene_bound else "review",
            "语义场景与源文件对应",
            {
                "semantic_scene_file": str(scene_path or ""),
                "semantic_scene_sha256": str(result.get("semantic_scene_sha256", "")),
                "semantic_object_count": int(
                    dict(result.get("semantic_scene_summary", {})).get(
                        "semantic_object_count", 0
                    )
                ),
                "source_bound": scene_bound,
            },
            "请重新生成语义场景文件，再交给 CAD/SU 后续任务。",
        )
    )

    mode = str(result.get("conversion_mode", "color_regions"))
    if mode == "black_white_linework":
        road_candidates = int(result.get("road_centerline_candidate_count", 0))
        review_required = int(result.get("road_centerline_review_required_count", 0))
        road_status = "pass" if road_candidates and review_required == 0 else "review"
        gates.append(
            _gate(
                "road_centerline_quality",
                road_status,
                "道路中心线与连通性",
                {
                    "candidate_count": road_candidates,
                    "review_required_count": review_required,
                    "network_components_after": int(
                        result.get("road_centerline_network_component_count_after", 0)
                    ),
                    "junction_snap_count": int(
                        result.get("road_centerline_junction_snap_count", 0)
                    ),
                    "alignment_quality": dict(result.get("alignment_quality", {})).get(
                        "road", {}
                    ),
                },
                "在道路中心线复核图中检查断线、岔口和道路宽度后再用于建模。",
            )
        )
    else:
        road = dict(result.get("semantic_road_detection", {}))
        road_status = str(road.get("status", "no_road_region"))
        gates.append(
            _gate(
                "road_region_quality",
                "pass" if road_status == "single_network" else "review",
                "道路面连通性",
                {
                    "status": road_status,
                    "network_component_count": int(road.get("network_component_count", 0)),
                    "nearby_gap_suggestion_count": int(
                        road.get("nearby_gap_suggestion_count", 0)
                    ),
                    "region_count_after_gap_heal": int(
                        road.get("region_count_after_gap_heal", 0)
                    ),
                },
                "请查看矢量预览；相邻道路未连通时应在 CAD 中人工修正。",
            )
        )

    review_count = int(
        dict(result.get("semantic_scene_summary", {})).get("review_required_count", 0)
    )
    gates.append(
        _gate(
            "manual_geometry_review",
            "review",
            "人工几何复核",
            {
                "conversion_mode": mode,
                "semantic_candidate_review_count": review_count,
                "source_image_size_px": list(result.get("image_size", [])),
                "processed_size_px": list(result.get("processed_size", [])),
            },
            "这是概念性矢量化。请叠加原图检查建筑、道路、绿地和比例后再量算或出图。",
        )
    )

    summary = _summary(gates)
    payload = {
        "format": QUALITY_BASELINE_FORMAT,
        "schema_version": QUALITY_BASELINE_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "Planning Toolbox",
        "workflow": "image_to_cad",
        "scope": "concept_vectorization_review",
        "not_a_claim": "This report is not a survey, approval, or design-quality certificate.",
        "inputs": {
            "conversion_mode": mode,
            "source_file": str(source),
            "source_sha256": expected_source_hash,
            "reference_width_m": reference_width_m,
            "pixel_size_m": result.get("pixel_size_m"),
        },
        "outputs": {
            "dxf_file": str(dxf),
            "dxf_sha256": actual_dxf_hash,
            "semantic_scene_file": str(scene_path or ""),
        },
        "gates": gates,
        "summary": summary,
    }
    return _write(payload, destination)


def write_cad_to_sketchup_quality_baseline(
    result: Mapping[str, Any],
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a review-first quality baseline for a CAD -> SketchUp handoff."""
    source = Path(str(result["source_file"])).resolve()
    handoff = Path(str(result["handoff_file"])).resolve()
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else quality_baseline_path_for_artifact(handoff)
    )
    expected_source_hash = str(result.get("source_sha256", "")).lower()
    source_exists = source.is_file()
    handoff_exists = handoff.is_file()
    actual_source_hash = sha256_file(source) if source_exists else ""
    actual_handoff_hash = sha256_file(handoff) if handoff_exists else ""
    handoff_payload = _read_json(handoff) if handoff_exists else None
    handoff_source = dict((handoff_payload or {}).get("source", {}))
    handoff_bound = bool(
        handoff_payload and str(handoff_source.get("sha256", "")).lower() == expected_source_hash
    )
    readiness = dict(result.get("course_model_readiness", {}))
    gates: list[dict[str, Any]] = [
        _gate(
            "source_integrity",
            "pass" if source_exists and actual_source_hash == expected_source_hash else "blocked",
            "源 DXF 只读校验",
            {
                "source_file": str(source),
                "expected_sha256": expected_source_hash,
                "actual_sha256": actual_source_hash,
            },
            "源 DXF 已变化或不可读取，请重新导出交接文件。",
        ),
        _gate(
            "handoff_traceability",
            "pass" if handoff_bound else "blocked",
            "SketchUp 交接文件对应源 DXF",
            {
                "handoff_file": str(handoff),
                "handoff_sha256": actual_handoff_hash,
                "source_bound": handoff_bound,
            },
            "交接 JSON 不完整或不对应当前 DXF，请重新导出。",
        ),
        _gate(
            "building_coverage",
            "pass" if int(result.get("extruded_building_count", 0)) > 0 else "review",
            "建筑三维覆盖",
            {
                "building_footprint_count": int(result.get("building_footprint_count", 0)),
                "extruded_building_count": int(result.get("extruded_building_count", 0)),
                "building_mode": str(result.get("building_mode", "")),
            },
            "请确认每个需要体量化的建筑轮廓都有楼层或高度参数。",
        ),
        _gate(
            "road_coverage",
            "pass" if int(result.get("road_design_surface_count", 0)) > 0 else "review",
            "道路建模覆盖",
            {
                "road_surface_count": int(result.get("road_design_surface_count", 0)),
                "centerline_corridor_count": int(
                    result.get("road_centerline_corridor_hint_count", 0)
                ),
                "roundabout_hint_count": int(result.get("road_roundabout_hint_count", 0)),
            },
            "请确认道路面或中心线已归入 ROAD 图层，并在 SketchUp 中核对宽度和转角。",
        ),
    ]

    crossing_review = sum(
        int(result.get(key, 0))
        for key in (
            "road_crossing_manual_count",
            "road_crossing_fallback_count",
            "road_crossing_ambiguous_count",
            "road_crossing_unmatched_count",
        )
    )
    gates.append(
        _gate(
            "crosswalk_alignment",
            "review" if crossing_review else "pass",
            "斑马线与道路方向",
            {
                "total_count": int(result.get("road_crossing_total_count", 0)),
                "auto_aligned_count": int(result.get("road_crossing_auto_aligned_count", 0)),
                "review_signal_count": crossing_review,
            },
            "存在手动、回退、歧义或未匹配斑马线时，请在 SU 中核对其与道路中心线的垂直关系。",
        )
    )
    gates.append(
        _gate(
            "course_model_readiness",
            "pass" if readiness.get("status") == "refinement_ready" else "review",
            "课程模型完善度",
            {
                "status": readiness.get("status", "unavailable"),
                "passed_count": int(readiness.get("passed_count", 0)),
                "review_count": int(readiness.get("review_count", 0)),
                "review_labels": list(readiness.get("review_labels", [])),
            },
            "该检查仅提示需补足的建筑、道路、绿化或候选对象，不代表课程评分或规范审查。",
        )
    )
    gates.append(
        _gate(
            "manual_model_review",
            "review",
            "人工建模复核",
            {
                "semantic_scene_validated": bool(result.get("semantic_scene_validated")),
                "semantic_review_required_count": int(
                    result.get("semantic_review_required_count", 0)
                ),
                "skipped_count": int(result.get("skipped_count", 0)),
            },
            "请在 SketchUp 中叠加原 CAD，检查道路、建筑高度、构件方向和材质表达后再提交。",
        )
    )

    summary = _summary(gates)
    payload = {
        "format": QUALITY_BASELINE_FORMAT,
        "schema_version": QUALITY_BASELINE_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "Planning Toolbox",
        "workflow": "cad_to_sketchup",
        "scope": "editable_concept_model_review",
        "not_a_claim": "This report is not a rendering-quality, approval, or course-grade certificate.",
        "inputs": {
            "source_file": str(source),
            "source_sha256": expected_source_hash,
            "floors": result.get("floors"),
            "floor_height_m": result.get("floor_height_m"),
            "model_detail_level": result.get("model_detail_level"),
            "road_design_preset": result.get("road_design_preset"),
        },
        "outputs": {
            "handoff_file": str(handoff),
            "handoff_sha256": actual_handoff_hash,
            "semantic_scene_file": str(result.get("semantic_scene_file", "")),
        },
        "gates": gates,
        "summary": summary,
    }
    return _write(payload, destination)


__all__ = [
    "QUALITY_BASELINE_FORMAT",
    "QUALITY_BASELINE_SCHEMA_VERSION",
    "quality_baseline_path_for_artifact",
    "write_image_to_cad_quality_baseline",
    "write_cad_to_sketchup_quality_baseline",
]
