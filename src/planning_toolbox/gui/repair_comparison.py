"""Visual before/after confirmation for traceable CAD repair copies."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import ezdxf
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from planning_toolbox.core.geometry.parser import points_from_dxf_polyline

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "DejaVu Sans",
    "sans-serif",
]
matplotlib.rcParams["axes.unicode_minus"] = False


Point2D = Tuple[float, float]


def _normalise(points: Iterable[Point2D], closed: bool):
    values = tuple((round(float(x), 6), round(float(y), 6)) for x, y in points)
    if not values:
        return values
    if closed:
        rotations = [values[index:] + values[:index] for index in range(len(values))]
        reversed_values = tuple(reversed(values))
        rotations.extend(
            reversed_values[index:] + reversed_values[:index]
            for index in range(len(reversed_values))
        )
        return min(rotations)
    return min(values, tuple(reversed(values)))


def read_repair_linework(path: Path | str) -> List[Dict[str, Any]]:
    """Read only the linework types that the safe repair engine may change."""
    doc = ezdxf.readfile(Path(path).resolve())
    records: List[Dict[str, Any]] = []
    for entity in doc.modelspace():
        entity_type = entity.dxftype()
        if entity_type in {"LWPOLYLINE", "POLYLINE"}:
            points, closed, _ = points_from_dxf_polyline(entity)
        elif entity_type == "LINE":
            points = [
                (float(entity.dxf.start.x), float(entity.dxf.start.y)),
                (float(entity.dxf.end.x), float(entity.dxf.end.y)),
            ]
            closed = False
        else:
            continue
        if len(points) < 2:
            continue
        signature = (
            str(getattr(entity.dxf, "layer", "0")).upper(),
            bool(closed),
            _normalise(points, bool(closed)),
        )
        records.append({
            "points": points,
            "closed": bool(closed),
            "layer": signature[0],
            "signature": signature,
        })
    return records


def _draw_record(ax, record: Dict[str, Any], color: str, linewidth: float, linestyle: str, alpha: float):
    points = list(record["points"])
    if record["closed"]:
        points.append(points[0])
    xs, ys = zip(*points)
    ax.plot(xs, ys, color=color, linewidth=linewidth, linestyle=linestyle, alpha=alpha)


def render_repair_difference(
    figure: Figure,
    source_path: Path | str,
    repaired_path: Path | str,
) -> Dict[str, int]:
    """Overlay unchanged, removed and added linework with explicit colors."""
    before = read_repair_linework(source_path)
    after = read_repair_linework(repaired_path)
    before_map = {record["signature"]: record for record in before}
    after_map = {record["signature"]: record for record in after}
    common = before_map.keys() & after_map.keys()
    removed = before_map.keys() - after_map.keys()
    added = after_map.keys() - before_map.keys()

    figure.clear()
    ax = figure.add_subplot(111)
    ax.set_facecolor("#F7F5EF")
    ax.set_title("CAD 修复前后差异确认", color="#566D8E", fontsize=11, fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.2, color="#9AAFC4")
    for spine in ax.spines.values():
        spine.set_color("#D0CBC0")

    for signature in common:
        _draw_record(ax, after_map[signature], "#A8A59D", 0.8, "-", 0.5)
    for signature in removed:
        _draw_record(ax, before_map[signature], "#B45E59", 2.0, "--", 0.95)
    for signature in added:
        _draw_record(ax, after_map[signature], "#4F8064", 2.0, "-", 0.95)

    handles = [
        Line2D([0], [0], color="#A8A59D", linewidth=1.0, label="未变化"),
        Line2D([0], [0], color="#B45E59", linewidth=2.0, linestyle="--", label="修复前已删除/替换"),
        Line2D([0], [0], color="#4F8064", linewidth=2.0, label="修复后新增/替换"),
    ]
    ax.legend(handles=handles, loc="upper right", facecolor="#FBFAF6", edgecolor="#D8D3C8", fontsize=8)
    if before or after:
        ax.autoscale_view()
        ax.set_aspect("equal", adjustable="datalim")
    else:
        ax.text(0.5, 0.5, "没有可对比的直线或多段线", ha="center", va="center", transform=ax.transAxes)
    figure.tight_layout()
    return {
        "unchanged": len(common),
        "removed_or_replaced": len(removed),
        "added_or_replaced": len(added),
    }


class RepairComparisonDialog(QDialog):
    """Non-blocking visual confirmation window for a quality-repair result."""

    def __init__(self, source_path: Path | str, repaired_path: Path | str, output_dir: Path | str, parent=None):
        super().__init__(parent)
        self.source_path = Path(source_path).resolve()
        self.repaired_path = Path(repaired_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.setWindowTitle("Planning Toolbox 修复前后对比")
        self.setMinimumSize(960, 620)
        self.setModal(False)

        layout = QVBoxLayout(self)
        title = QLabel("修复前后差异确认")
        title.setObjectName("HelpTitle")
        layout.addWidget(title)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.figure = Figure(figsize=(9, 5), dpi=100, facecolor="#F7F5EF")
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(self.canvas, stretch=1)
        summary = render_repair_difference(self.figure, self.source_path, self.repaired_path)
        self.canvas.draw_idle()
        self.summary_label.setText(
            f"灰色未变化 {summary['unchanged']} 条；红色删除/替换 {summary['removed_or_replaced']} 条；"
            f"绿色新增/替换 {summary['added_or_replaced']} 条。请重点检查红色与绿色位置。"
        )

        bar = QHBoxLayout()
        bar.addStretch()
        export_button = QPushButton("导出差异 PNG")
        export_button.clicked.connect(self._export_png)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        bar.addWidget(export_button)
        bar.addWidget(close_button)
        layout.addLayout(bar)

    def _export_png(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.output_dir / f"CAD修复差异_{stamp}.png"
        self.figure.savefig(path, dpi=180, bbox_inches="tight", facecolor=self.figure.get_facecolor())
        self.summary_label.setText(f"✅ 差异图已导出：{path}")
