"""2D CAD 图元矢量预览画布组件 (Embedded Matplotlib Canvas for PySide6)."""
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import ezdxf
import matplotlib
matplotlib.use("QtAgg")
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Polygon as MplPolygon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry
from planning_toolbox.cad.layers.manager import load_layer_config, build_alias_map

class CADPreviewCanvas(QWidget):
    """
    可嵌入 PySide6 UI 的 2D 矢量 CAD 预览画布。
    自动绘制 PARCEL(蓝色), BUILDING(青色), GREEN(绿色) 的空间轮廓与标注编号。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建暗色调 Matplotlib 控件
        self.figure = Figure(figsize=(6, 4), facecolor="#12141c")
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self._setup_ax_style()

        layout.addWidget(self.canvas)

    def _setup_ax_style(self):
        self.ax.set_facecolor("#12141c")
        self.ax.tick_params(colors="#64748b", labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color("#282b3a")
        self.ax.set_title("CAD 2D 矢量图元实时预览", color="#94a3b8", fontsize=11, fontweight="bold", pad=8)
        self.ax.grid(True, linestyle="--", alpha=0.15, color="#38bdf8")

    def clear_canvas(self, message: str = "等待加载 CAD DXF 图纸..."):
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._setup_ax_style()
        self.ax.text(
            0.5, 0.5, message, color="#64748b", fontsize=12,
            ha="center", va="center", transform=self.ax.transAxes
        )
        self.canvas.draw()

    def load_dxf_preview(self, dxf_path: Path | str, layer_config_path: Optional[Path | str] = None):
        """解析 DXF 图纸并在画布上高质感绘制多边形轮廓。"""
        path = Path(dxf_path)
        if not path.exists():
            self.clear_canvas("文件不存在")
            return

        try:
            doc = ezdxf.readfile(path)
        except Exception:
            self.clear_canvas("DXF 解析失败")
            return

        try:
            layer_cfg = load_layer_config(layer_config_path)
            alias_map = build_alias_map(layer_cfg.get("layers", {}))
        except Exception:
            alias_map = {"PARCEL": "PARCEL", "BUILDING": "BUILDING", "GREEN": "GREEN"}

        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._setup_ax_style()

        msp = doc.modelspace()
        parcels_pts = []
        buildings_pts = []
        greens_pts = []

        for entity in msp:
            if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
                layer_orig = str(entity.dxf.layer).upper()
                std_layer = alias_map.get(layer_orig, layer_orig)

                pts, is_closed, _ = points_from_dxf_polyline(entity)
                status, poly, _ = parse_parcel_geometry(pts, is_closed)

                if poly and len(pts) >= 3:
                    if std_layer == "PARCEL":
                        parcels_pts.append(pts)
                    elif std_layer == "BUILDING":
                        buildings_pts.append(pts)
                    elif std_layer == "GREEN":
                        greens_pts.append(pts)

        # 绘制 PARCEL (蓝色地块)
        for idx, pts in enumerate(parcels_pts, start=1):
            patch = MplPolygon(pts, closed=True, facecolor="#3b82f6", alpha=0.15, edgecolor="#3b82f6", linewidth=2.0)
            self.ax.add_patch(patch)
            # 计算质心并绘制编号
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)
            self.ax.text(cx, cy, f"P{idx:03d}", color="#60a5fa", fontsize=10, fontweight="bold", ha="center", va="center")

        # 绘制 BUILDING (青色建筑)
        for pts in buildings_pts:
            patch = MplPolygon(pts, closed=True, facecolor="#06b6d4", alpha=0.45, edgecolor="#0891b2", linewidth=1.5)
            self.ax.add_patch(patch)

        # 绘制 GREEN (绿地)
        for pts in greens_pts:
            patch = MplPolygon(pts, closed=True, facecolor="#10b981", alpha=0.35, edgecolor="#059669", linewidth=1.2)
            self.ax.add_patch(patch)

        self.ax.autoscale_view()
        self.ax.set_aspect("equal", adjustable="datalim")

        # 图例
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#3b82f6', edgecolor='#3b82f6', alpha=0.3, label='地块 (PARCEL)'),
            Patch(facecolor='#06b6d4', edgecolor='#0891b2', alpha=0.5, label='建筑 (BUILDING)'),
            Patch(facecolor='#10b981', edgecolor='#059669', alpha=0.4, label='绿地 (GREEN)')
        ]
        self.ax.legend(handles=legend_elements, loc='upper right', facecolor='#1e2230', edgecolor='#333a4e', labelcolor='#e2e8f0', fontsize=8)

        self.canvas.draw()
