"""Render multiple saved project DXF results as a color-coded overlay."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import ezdxf
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Polygon as MplPolygon
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.ops import unary_union

from planning_toolbox.core.geometry.parser import points_from_dxf_polyline
from planning_toolbox.gui.project_file import load_project


OVERLAY_COLORS = ["#5E7FA3", "#B87670", "#6F927B", "#B08B50", "#806B9B", "#4F9A9A"]


def project_dxf_path(project_path: Path | str) -> Path | None:
    """Find the most useful DXF output recorded in a .ptx project."""
    state = load_project(project_path)
    result = state.get("last_result") or {}
    candidates: List[Path] = []
    for item in result.get("output_files", []):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        path = Path(str(item[1]))
        if path.suffix.lower() == ".dxf" and path.exists():
            candidates.append(path)
    source = Path(str(state.get("dxf_path", result.get("source_file", ""))))
    if source.exists() and source.suffix.lower() == ".dxf":
        candidates.append(source)
    return candidates[0].resolve() if candidates else None


def read_project_overlay(project_path: Path | str) -> Dict[str, Any]:
    path = project_dxf_path(project_path)
    if path is None:
        raise FileNotFoundError(f"项目没有可用的 DXF 结果：{Path(project_path).name}")
    doc = ezdxf.readfile(path)
    geometries = []
    for entity in doc.modelspace():
        if entity.dxftype() not in {"LWPOLYLINE", "POLYLINE"}:
            continue
        points, is_closed, _ = points_from_dxf_polyline(entity)
        if len(points) < 2:
            continue
        geometries.append({
            "points": points,
            "closed": is_closed,
            "layer": str(getattr(entity.dxf, "layer", "0")),
        })
    return {
        "project_path": str(Path(project_path).resolve()),
        "project_name": Path(project_path).stem,
        "dxf_path": str(path),
        "geometries": geometries,
    }


def _polygon_style(layer: str, color: str) -> Tuple[float, float]:
    upper = layer.upper()
    if "BUILDING" in upper or "PARKING" in upper:
        return 0.28, 1.5
    if "GREEN" in upper:
        return 0.18, 1.2
    if "ROAD" in upper or "SETBACK" in upper:
        return 0.10, 1.2
    return 0.06, 1.8


def _closed_shape(record: Dict[str, Any]):
    """Build a tolerant union used only for visual difference highlighting."""
    shapes = []
    for geometry in record["geometries"]:
        if not geometry["closed"]:
            continue
        try:
            shape = ShapelyPolygon(geometry["points"])
            if not shape.is_valid:
                shape = shape.buffer(0)
            if not shape.is_empty and shape.area > 0:
                shapes.append(shape)
        except Exception:
            continue
    return unary_union(shapes) if shapes else None


def _polygon_parts(geometry):
    if geometry is None or geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [part for part in geometry.geoms if part.geom_type == "Polygon"]
    return []


def render_project_overlays(
    figure: Figure,
    project_paths: Iterable[Path | str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Render each project in a distinct color; overlaps blend visually."""
    records: List[Dict[str, Any]] = []
    errors: List[str] = []
    for project_path in project_paths:
        try:
            records.append(read_project_overlay(project_path))
        except Exception as exc:
            errors.append(f"{Path(project_path).name}: {exc}")

    figure.clear()
    ax = figure.add_subplot(111)
    ax.set_facecolor("#F3F0E8")
    ax.set_title("多方案 CAD 图形叠加（颜色区分方案，重叠处混色，斜线标出差异）", color="#566D8E", fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.25, color="#9AAFC4")
    ax.tick_params(colors="#74766F", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#D0CBC0")

    legend_handles = []
    project_shapes = [_closed_shape(record) for record in records]
    for index, record in enumerate(records):
        color = OVERLAY_COLORS[index % len(OVERLAY_COLORS)]
        for geometry in record["geometries"]:
            points = geometry["points"]
            layer = geometry["layer"]
            if geometry["closed"]:
                alpha, linewidth = _polygon_style(layer, color)
                ax.add_patch(
                    MplPolygon(
                        points,
                        closed=True,
                        facecolor=color,
                        edgecolor=color,
                        alpha=alpha,
                        linewidth=linewidth,
                    )
                )
            else:
                xs, ys = zip(*points)
                ax.plot(xs, ys, color=color, alpha=0.72, linewidth=1.1, linestyle="--")
        legend_handles.append(
            Patch(facecolor=color, edgecolor=color, alpha=0.45, label=f"{record['project_name']} ({len(record['geometries'])} 个轮廓)")
        )

    # Base fills show overlap naturally; a hatched outline makes the actual
    # scheme-only difference easier for beginners to identify.
    difference_handle_added = False
    for index, shape in enumerate(project_shapes):
        if shape is None:
            continue
        others = [other for other_index, other in enumerate(project_shapes) if other_index != index and other is not None]
        unique = shape.difference(unary_union(others)) if others else shape
        records[index]["unique_area"] = float(unique.area) if not unique.is_empty else 0.0
        color = OVERLAY_COLORS[index % len(OVERLAY_COLORS)]
        for part in _polygon_parts(unique):
            ax.add_patch(
                MplPolygon(
                    list(part.exterior.coords),
                    closed=True,
                    facecolor="none",
                    edgecolor=color,
                    hatch="///",
                    linewidth=1.8,
                    linestyle="-.",
                )
            )
        if not difference_handle_added and not unique.is_empty and unique.area > 0:
            legend_handles.append(
                Patch(
                    facecolor="none",
                    edgecolor="#8C645E",
                    hatch="///",
                    label="斜线：方案独有差异区域",
                )
            )
            difference_handle_added = True

    if records:
        ax.autoscale_view()
        ax.set_aspect("equal", adjustable="datalim")
        ax.legend(handles=legend_handles, loc="upper right", facecolor="#FBFAF6", edgecolor="#D8D3C8", fontsize=8)
    else:
        ax.text(0.5, 0.5, "请选择包含可用 DXF 结果的项目", color="#74766F", ha="center", va="center", transform=ax.transAxes)
    figure.tight_layout()
    return records, errors


def export_overlay_png(output_dir: Path | str, figure: Figure) -> Path:
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"方案叠加_{timestamp}.png"
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor=figure.get_facecolor())
    return path
