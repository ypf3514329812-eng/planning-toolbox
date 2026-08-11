"""Lightweight state model for the beginner full-chain coursework workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple


WORKFLOW_VERSION = 2
MAX_LINEAGE_RECORDS = 50


@dataclass(frozen=True)
class WorkflowStage:
    """One user-visible stage in the GIS-CAD-SketchUp coursework chain."""

    key: str
    title: str
    summary: str
    checklist: Tuple[str, ...]
    task_index: int | None = None
    optional: bool = False


WORKFLOW_STAGES: Tuple[WorkflowStage, ...] = (
    WorkflowStage(
        "setup",
        "建立作业项目",
        "统一项目名称、CAD 单位、坐标系和 SketchUp 本地原点。",
        (
            "填写容易辨认的项目名称和作业类型",
            "确认 CAD 单位；规划总平面通常使用米",
            "涉及 GIS 或 SketchUp 时确认投影坐标和近原点",
        ),
    ),
    WorkflowStage(
        "source",
        "导入资料",
        "选择现有 DXF，或从 AI 参考图、GIS 数据生成新的 DXF。",
        (
            "DXF：直接选择原始图纸",
            "AI 参考图：使用清晰黑白俯视图并明确场地宽度",
            "GIS：先确认坐标系，再转换为新的 DXF",
            "图片转换后确认向导显示“语义接力已连接”",
        ),
    ),
    WorkflowStage(
        "inspection",
        "无损运行前检查",
        "后台读取图层、拓扑和单位；此步骤不会修改原始图纸。",
        (
            "确认文件可以正常读取",
            "确认 $INSUNITS 不是未知值",
            "查看地块、建筑、绿地等主要图层数量",
        ),
    ),
    WorkflowStage(
        "standardize",
        "图层标准化",
        "把混乱图层整理为可配置的课程作业或中国制图参考结构。",
        (
            "选择是否使用中国课程制图参考模板",
            "预览映射结果，不覆盖原始 DXF",
            "复核建筑、道路、绿地和文字是否归类正确",
        ),
        task_index=6,
        optional=True,
    ),
    WorkflowStage(
        "quality",
        "图纸检查与安全修复",
        "检查重复线、微小断线、自交和异常比例，并输出新的修复副本。",
        (
            "先查看问题数量和位置",
            "优先使用“尽量减少人工”安全修复配置",
            "对比修复前后结果，再决定是否用于后续步骤",
            "采用修复副本后确认语义交接仍随工作图存在",
        ),
        task_index=7,
    ),
    WorkflowStage(
        "analysis",
        "规划分析与方案判断",
        "按作业需要计算面积、指标、退线，或生成概念方案。",
        (
            "明确楼层数、退线距离等作业参数",
            "不要把示例参数当作当地法定标准",
            "检查表格、图形预览和警告信息",
        ),
        task_index=1,
    ),
    WorkflowStage(
        "gis",
        "GIS 数据交换",
        "与 ArcGIS Pro 或通用 GIS 文件交换地块和规划对象。",
        (
            "确认项目使用投影坐标而不是经纬度直接量算",
            "选择 GeoPackage、GeoJSON 或 Shapefile",
            "导出后在 ArcGIS Pro 中检查位置和属性字段",
        ),
        task_index=3,
        optional=True,
    ),
    WorkflowStage(
        "sketchup",
        "SketchUp 模型交接",
        "生成轻量交接文件，按稳定对象编号在 SketchUp 中自动建模。",
        (
            "确认建筑图层、层数、层高和模型精细度",
            "投影坐标项目必须启用近原点",
            "图片来源图纸先确认语义接力已连接",
            "导入后检查 PT_* 标签、屋顶和重点建筑",
        ),
        task_index=9,
        optional=True,
    ),
    WorkflowStage(
        "export",
        "整理并导出成果",
        "导出 Excel、PDF、PNG，并把当前结果整理为可检查的作业包。",
        (
            "先检查当前结果和预览图",
            "导出 Excel、PDF 与 PNG 汇报材料",
            "生成作业包 ZIP，并在提交前人工复核",
        ),
    ),
)


SOURCE_KINDS = (
    ("dxf", "现有 DXF / DWG 图纸"),
    ("image", "AI 生成或扫描的参考图"),
    ("gis", "ArcGIS / GIS 矢量数据"),
)

TASK_STAGE_MAP = {
    "dwg_convert": "source",
    "image_to_dxf": "source",
    "gis_import": "gis",
    "gis_export": "gis",
    "layer_standardize": "standardize",
    "quality_check": "quality",
    "parcel": "analysis",
    "indicator": "analysis",
    "validate": "analysis",
    "concept_plan": "analysis",
    "sketchup_export": "sketchup",
}

AUTO_CONTINUATION_TASKS = {"dwg_convert", "image_to_dxf", "gis_import"}
REVIEW_CONTINUATION_TASKS = {"layer_standardize", "quality_check", "concept_plan"}


def _ordered_valid(values: Iterable[Any]) -> list[str]:
    requested = {str(value) for value in values}
    return [stage.key for stage in WORKFLOW_STAGES if stage.key in requested]


def default_workflow_state() -> Dict[str, Any]:
    """Return a compact, JSON-friendly workflow state."""
    return {
        "version": WORKFLOW_VERSION,
        "current_step": WORKFLOW_STAGES[0].key,
        "source_kind": "dxf",
        "completed_steps": [],
        "skipped_steps": [],
        "working_dxf": "",
        "dxf_lineage": [],
    }


def _normalize_lineage(value: Any) -> list[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    records: list[Dict[str, str]] = []
    for item in value[-MAX_LINEAGE_RECORDS:]:
        if not isinstance(item, Mapping):
            continue
        output_path = str(item.get("output_path", "")).strip()
        if not output_path:
            continue
        records.append(
            {
                "task_type": str(item.get("task_type", "")).strip(),
                "stage": str(item.get("stage", "")).strip(),
                "source_path": str(item.get("source_path", "")).strip(),
                "output_path": output_path,
                "mode": (
                    "automatic"
                    if str(item.get("mode", "")).strip() == "automatic"
                    else "confirmed"
                ),
            }
        )
    return records


def normalize_workflow_state(value: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Migrate and sanitize workflow state saved by current or older builds."""
    state = default_workflow_state()
    if not isinstance(value, Mapping):
        return state
    valid_keys = {stage.key for stage in WORKFLOW_STAGES}
    source_kinds = {key for key, _label in SOURCE_KINDS}
    current = str(value.get("current_step", state["current_step"]))
    source = str(value.get("source_kind", state["source_kind"]))
    completed = _ordered_valid(value.get("completed_steps", []))
    skipped = _ordered_valid(value.get("skipped_steps", []))
    optional = {stage.key for stage in WORKFLOW_STAGES if stage.optional}
    state.update(
        current_step=current if current in valid_keys else WORKFLOW_STAGES[0].key,
        source_kind=source if source in source_kinds else "dxf",
        completed_steps=completed,
        skipped_steps=[key for key in skipped if key in optional and key not in completed],
        working_dxf=str(value.get("working_dxf", "")).strip(),
        dxf_lineage=_normalize_lineage(value.get("dxf_lineage", [])),
    )
    return state


def continuation_dxf_candidate(result: Mapping[str, Any] | None) -> str:
    """Return the task's intended editable DXF continuation, if it has one."""
    if not isinstance(result, Mapping):
        return ""
    task_type = str(result.get("task_type", "")).strip()
    if task_type not in AUTO_CONTINUATION_TASKS | REVIEW_CONTINUATION_TASKS:
        return ""
    if task_type == "dwg_convert":
        converted = str(result.get("converted_dxf", "")).strip()
        if converted:
            return converted
    if task_type == "quality_check":
        repair = result.get("repair", {})
        if isinstance(repair, Mapping):
            repaired = str(repair.get("output_file", "")).strip()
            if repaired:
                return repaired
    output_files = result.get("output_files", [])
    if isinstance(output_files, Iterable) and not isinstance(
        output_files, (str, bytes, Mapping)
    ):
        for item in output_files:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            path = str(item[1]).strip()
            if path.lower().endswith(".dxf"):
                return path
    return ""


def record_working_dxf(
    value: Mapping[str, Any] | None,
    *,
    source_path: str,
    output_path: str,
    task_type: str,
    automatic: bool,
) -> Dict[str, Any]:
    """Record one lightweight, bounded DXF handoff without copying geometry."""
    state = normalize_workflow_state(value)
    source = str(source_path).strip()
    output = str(output_path).strip()
    if not output:
        return state
    state["working_dxf"] = output
    if source.casefold() == output.casefold():
        return state
    record = {
        "task_type": str(task_type).strip(),
        "stage": TASK_STAGE_MAP.get(str(task_type).strip(), ""),
        "source_path": source,
        "output_path": output,
        "mode": "automatic" if automatic else "confirmed",
    }
    existing = [
        item
        for item in state["dxf_lineage"]
        if not (
            item.get("task_type") == record["task_type"]
            and item.get("output_path", "").casefold() == output.casefold()
        )
    ]
    existing.append(record)
    state["dxf_lineage"] = existing[-MAX_LINEAGE_RECORDS:]
    return state


def _next_unfinished(state: Mapping[str, Any], after_key: str) -> str:
    completed = set(state.get("completed_steps", []))
    skipped = set(state.get("skipped_steps", []))
    keys = [stage.key for stage in WORKFLOW_STAGES]
    start = keys.index(after_key) + 1 if after_key in keys else 0
    for key in keys[start:] + keys[:start]:
        if key not in completed and key not in skipped:
            return key
    return keys[-1]


def mark_stage_complete(value: Mapping[str, Any] | None, stage_key: str) -> Dict[str, Any]:
    """Mark one verified stage complete and advance to the next unfinished stage."""
    state = normalize_workflow_state(value)
    valid_keys = {stage.key for stage in WORKFLOW_STAGES}
    if stage_key not in valid_keys:
        return state
    completed = set(state["completed_steps"])
    completed.add(stage_key)
    state["completed_steps"] = _ordered_valid(completed)
    state["skipped_steps"] = [key for key in state["skipped_steps"] if key != stage_key]
    if state["current_step"] == stage_key:
        state["current_step"] = _next_unfinished(state, stage_key)
    return state


def set_stage_skipped(
    value: Mapping[str, Any] | None, stage_key: str, skipped: bool = True
) -> Dict[str, Any]:
    """Skip only explicitly optional stages; required safety stages cannot be skipped."""
    state = normalize_workflow_state(value)
    optional = {stage.key for stage in WORKFLOW_STAGES if stage.optional}
    if stage_key not in optional or stage_key in state["completed_steps"]:
        return state
    values = set(state["skipped_steps"])
    if skipped:
        values.add(stage_key)
    else:
        values.discard(stage_key)
    state["skipped_steps"] = _ordered_valid(values)
    if skipped and state["current_step"] == stage_key:
        state["current_step"] = _next_unfinished(state, stage_key)
    return state


def apply_verified_context(
    value: Mapping[str, Any] | None, context: Mapping[str, Any]
) -> Dict[str, Any]:
    """Advance only stages whose evidence is already available in the workbench."""
    state = normalize_workflow_state(value)
    if bool(context.get("project_configured")):
        state = mark_stage_complete(state, "setup")
    if bool(context.get("source_ready")):
        state = mark_stage_complete(state, "source")
    if bool(context.get("inspection_ready")):
        state = mark_stage_complete(state, "inspection")
    return state


def progress_percent(value: Mapping[str, Any] | None) -> int:
    """Return whole-workflow progress, treating explicitly skipped optional stages as resolved."""
    state = normalize_workflow_state(value)
    resolved = set(state["completed_steps"]) | set(state["skipped_steps"])
    return round(100 * len(resolved) / len(WORKFLOW_STAGES))
