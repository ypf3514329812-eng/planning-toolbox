"""2D CAD 图元矢量预览画布组件 (Embedded Matplotlib Canvas for PySide6)."""
from pathlib import Path
from typing import Optional
import matplotlib
matplotlib.use("QtAgg")
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Arc as MplArc
from matplotlib.patches import Circle as MplCircle
from matplotlib.patches import Polygon as MplPolygon
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout

from planning_toolbox.gui.widgets.preview_parser import DxfPreviewWorker

class CADPreviewCanvas(QWidget):
    """
    可嵌入 PySide6 UI 的 2D 矢量 CAD 预览画布。
    自动绘制 PARCEL(蓝色), BUILDING(青色), GREEN(绿色) 的空间轮廓与标注编号。
    """

    preview_loaded = Signal()
    inspection_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview_worker: Optional[DxfPreviewWorker] = None
        self._preview_workers = set()
        self._preview_request_id = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建暗色调 Matplotlib 控件
        self.figure = Figure(figsize=(6, 4), facecolor="#F3F0E8")
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self._setup_ax_style()

        layout.addWidget(self.canvas)

    def _setup_ax_style(self):
        self.ax.set_facecolor("#F3F0E8")
        self.ax.tick_params(colors="#74766F", labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color("#D0CBC0")
        self.ax.set_title("CAD 2D 矢量图元实时预览", color="#566D8E", fontsize=11, fontweight="bold", pad=8)
        self.ax.title.set_color("#566D8E")
        self.ax.grid(True, linestyle="--", alpha=0.28, color="#9AAFC4")

    def clear_canvas(self, message: str = "等待加载 CAD DXF 图纸..."):
        self._preview_request_id += 1
        self.cancel_preview(wait=False)
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._setup_ax_style()
        self.ax.text(
            0.5, 0.5, message, color="#74766F", fontsize=12,
            ha="center", va="center", transform=self.ax.transAxes
        )
        self.canvas.draw()

    def load_dxf_preview(self, dxf_path: Path | str, layer_config_path: Optional[Path | str] = None):
        """Asynchronously parse a DXF and render its geometry on the GUI thread."""
        path = Path(dxf_path)
        if not path.exists():
            self.clear_canvas("文件不存在")
            return

        self._preview_request_id += 1
        request_id = self._preview_request_id
        self.cancel_preview(wait=False)
        worker = DxfPreviewWorker(path, layer_config_path, self)
        self._preview_worker = worker
        self._preview_workers.add(worker)
        worker.result_ready.connect(
            lambda info, geometry, worker=worker, request_id=request_id:
                self._on_preview_result(request_id, worker, info, geometry)
        )
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(
            lambda worker=worker: self._on_preview_worker_finished(worker)
        )
        worker.start()

    def _on_preview_result(self, request_id, worker, info, geometry):
        if request_id != self._preview_request_id or worker is not self._preview_worker:
            return
        self.inspection_ready.emit(info)
        self._render_geometry(geometry)
        self.preview_loaded.emit()

    def _on_preview_worker_finished(self, worker):
        self._preview_workers.discard(worker)
        if worker is self._preview_worker:
            self._preview_worker = None

    def cancel_preview(self, wait: bool = True) -> bool:
        """Request preview cancellation; optionally wait for safe shutdown."""
        workers = [worker for worker in self._preview_workers if worker.isRunning()]
        for worker in workers:
            worker.requestInterruption()
        if not wait:
            return True
        wait_results = [worker.wait(2000) for worker in workers]
        return all(wait_results)

    def _render_geometry(self, geometry):
        """Render already-parsed geometry; this method only touches Qt widgets."""
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._setup_ax_style()

        # 绘制 PARCEL (蓝色地块)
        for idx, pts in enumerate(geometry.get("parcel", []), start=1):
            patch = MplPolygon(pts, closed=True, facecolor="#8197B5", alpha=0.24, edgecolor="#7189AA", linewidth=2.0)
            self.ax.add_patch(patch)
            # 计算质心并绘制编号
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)
            self.ax.text(cx, cy, f"P{idx:03d}", color="#566D8E", fontsize=10, fontweight="bold", ha="center", va="center")

        # 绘制 BUILDING (青色建筑)
        for pts in geometry.get("building", []):
            patch = MplPolygon(pts, closed=True, facecolor="#D7A39E", alpha=0.45, edgecolor="#A96761", linewidth=1.5)
            self.ax.add_patch(patch)

        # 绘制 GREEN (绿地)
        for pts in geometry.get("green", []):
            patch = MplPolygon(pts, closed=True, facecolor="#829A8B", alpha=0.35, edgecolor="#607A6A", linewidth=1.2)
            self.ax.add_patch(patch)

        # Other common CAD entities are shown as neutral reference linework.
        # They remain excluded from area/FAR calculations unless explicitly
        # converted to validated semantic polygons.
        for item in geometry.get("linework", []):
            points = item.get("points", [])
            if len(points) < 2:
                continue
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            if item.get("closed"):
                xs.append(points[0][0])
                ys.append(points[0][1])
            self.ax.plot(xs, ys, color="#74766F", alpha=0.78, linewidth=0.9)

        for item in geometry.get("curves", []):
            center = item["center"]
            radius = item["radius"]
            if item["type"] == "CIRCLE":
                patch = MplCircle(center, radius, fill=False, edgecolor="#74766F", linewidth=0.9)
            else:
                patch = MplArc(
                    center,
                    radius * 2,
                    radius * 2,
                    theta1=item["start_angle"],
                    theta2=item["end_angle"],
                    edgecolor="#74766F",
                    linewidth=0.9,
                )
            self.ax.add_patch(patch)

        for item in geometry.get("inserts", []):
            x, y = item["point"]
            self.ax.plot([x], [y], marker="+", color="#B08B50", markersize=7)
            self.ax.text(x, y, item["name"], color="#8B6B3F", fontsize=6, ha="left", va="bottom")

        for item in geometry.get("texts", []):
            x, y = item["point"]
            self.ax.text(x, y, item["text"], color="#74766F", fontsize=6, alpha=0.8)

        self.ax.autoscale_view()
        self.ax.set_aspect("equal", adjustable="datalim")

        # 图例
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='#8197B5', edgecolor='#7189AA', alpha=0.35, label='地块 (PARCEL)'),
            Patch(facecolor='#D7A39E', edgecolor='#A96761', alpha=0.5, label='建筑 (BUILDING)'),
            Patch(facecolor='#829A8B', edgecolor='#607A6A', alpha=0.4, label='绿地 (GREEN)')
        ]
        self.ax.legend(handles=legend_elements, loc='upper right', facecolor='#FBFAF6', edgecolor='#D8D3C8', labelcolor='#3C3D39', fontsize=8)

        self.canvas.draw()
