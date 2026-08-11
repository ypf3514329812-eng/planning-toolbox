"""Low-memory Qt-native 2D CAD preview canvas."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from planning_toolbox.gui.widgets.preview_parser import DxfPreviewWorker


BACKGROUND = QColor("#F3F0E8")


def _pen(color: str, width: float = 1.0, style=Qt.SolidLine) -> QPen:
    pen = QPen(QColor(color), width, style)
    pen.setCosmetic(True)
    return pen


class ZoomableCADView(QGraphicsView):
    """CAD-like wheel zoom and hand-drag navigation."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom_steps = 0
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(BACKGROUND))
        self.setFrameShape(QGraphicsView.NoFrame)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            return super().wheelEvent(event)
        direction = 1 if delta > 0 else -1
        next_steps = self._zoom_steps + direction
        if -12 <= next_steps <= 24:
            factor = 1.18 if direction > 0 else 1 / 1.18
            self.scale(factor, factor)
            self._zoom_steps = next_steps
        event.accept()

    def fit_scene(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isValid() and not rect.isEmpty():
            margin_x = max(rect.width() * 0.05, 1.0)
            margin_y = max(rect.height() * 0.05, 1.0)
            self.fitInView(rect.adjusted(-margin_x, -margin_y, margin_x, margin_y), Qt.KeepAspectRatio)
            self._zoom_steps = 0

    def mouseDoubleClickEvent(self, event):
        """Fit the full drawing when the user double-clicks the canvas itself."""
        self.fit_scene()
        event.accept()


class NativeCADPreviewCanvas(QWidget):
    """Render planning linework with QGraphicsScene instead of Matplotlib."""

    preview_loaded = Signal()
    inspection_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview_worker: Optional[DxfPreviewWorker] = None
        self._preview_workers = set()
        self._preview_request_id = 0
        self._geometry_item_count = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        toolbar = QHBoxLayout()
        self.info_label = QLabel("滚轮缩放 · 按住左键拖动画布 · 双击或点击按钮复位")
        self.info_label.setStyleSheet("color:#74766F; font-size:11px; padding:2px 6px;")
        reset_button = QPushButton("适应窗口")
        reset_button.setToolTip("显示全部 CAD 图元")
        reset_button.clicked.connect(self.fit_to_view)
        toolbar.addWidget(self.info_label)
        toolbar.addStretch()
        toolbar.addWidget(reset_button)
        layout.addLayout(toolbar)

        self.scene = QGraphicsScene(self)
        self.view = ZoomableCADView(self.scene, self)
        layout.addWidget(self.view, stretch=1)
        self.clear_canvas()

    @property
    def geometry_item_count(self) -> int:
        return self._geometry_item_count

    def clear_canvas(self, message: str = "等待加载 CAD DXF 图纸..."):
        self._preview_request_id += 1
        self.cancel_preview(wait=False)
        self.scene.clear()
        self._geometry_item_count = 0
        item = self.scene.addSimpleText(message)
        item.setBrush(QBrush(QColor("#74766F")))
        item.setFont(QFont("Microsoft YaHei", 11))
        rect = item.boundingRect()
        item.setPos(-rect.width() / 2, -rect.height() / 2)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-30, -20, 30, 20))
        self.view.resetTransform()

    def load_dxf_preview(self, dxf_path: Path | str, layer_config_path: Optional[Path | str] = None):
        path = Path(dxf_path)
        if not path.exists():
            self.clear_canvas("文件不存在")
            return
        self._preview_request_id += 1
        request_id = self._preview_request_id
        self.cancel_preview(wait=False)
        self.info_label.setText(f"正在后台读取：{path.name}")
        worker = DxfPreviewWorker(path, layer_config_path, self)
        self._preview_worker = worker
        self._preview_workers.add(worker)
        worker.result_ready.connect(
            lambda info, geometry, worker=worker, request_id=request_id:
                self._on_preview_result(request_id, worker, info, geometry)
        )
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda worker=worker: self._on_worker_finished(worker))
        worker.start()

    def _on_preview_result(self, request_id, worker, info, geometry):
        if request_id != self._preview_request_id or worker is not self._preview_worker:
            return
        self.inspection_ready.emit(info)
        self._render_geometry(geometry)
        self.preview_loaded.emit()

    def _on_worker_finished(self, worker):
        self._preview_workers.discard(worker)
        if worker is self._preview_worker:
            self._preview_worker = None

    def cancel_preview(self, wait: bool = True) -> bool:
        workers = [worker for worker in self._preview_workers if worker.isRunning()]
        for worker in workers:
            worker.requestInterruption()
        if not wait:
            return True
        return all(worker.wait(2000) for worker in workers)

    @staticmethod
    def _polygon(points):
        return QPolygonF([QPointF(float(x), -float(y)) for x, y in points])

    def _add_semantic_polygon(self, points, fill: str, edge: str, alpha: int, width: float):
        brush_color = QColor(fill)
        brush_color.setAlpha(alpha)
        item = self.scene.addPolygon(self._polygon(points), _pen(edge, width), QBrush(brush_color))
        item.setToolTip("规划语义闭合多段线")
        self._geometry_item_count += 1
        return item

    def _render_geometry(self, geometry):
        self.scene.clear()
        self._geometry_item_count = 0
        for index, points in enumerate(geometry.get("parcel", []), start=1):
            item = self._add_semantic_polygon(points, "#8197B5", "#7189AA", 65, 2.0)
            center = item.boundingRect().center()
            label = self.scene.addSimpleText(f"P{index:03d}")
            label.setBrush(QBrush(QColor("#566D8E")))
            label.setFont(QFont("Microsoft YaHei", 8, QFont.Bold))
            label_rect = label.boundingRect()
            label.setPos(center.x() - label_rect.width() / 2, center.y() - label_rect.height() / 2)
        for points in geometry.get("road", []):
            self._add_semantic_polygon(points, "#979791", "#737774", 72, 1.6)
        for points in geometry.get("water", []):
            self._add_semantic_polygon(points, "#769DB8", "#567D99", 86, 1.4)
        for points in geometry.get("parking", []):
            self._add_semantic_polygon(points, "#CCA971", "#9C7A45", 82, 1.3)
        for points in geometry.get("building", []):
            self._add_semantic_polygon(points, "#D7A39E", "#A96761", 105, 1.5)
        for points in geometry.get("green", []):
            self._add_semantic_polygon(points, "#829A8B", "#607A6A", 85, 1.2)

        for record in geometry.get("linework", []):
            points = record.get("points", [])
            if len(points) < 2:
                continue
            path = QPainterPath(QPointF(float(points[0][0]), -float(points[0][1])))
            for x, y in points[1:]:
                path.lineTo(float(x), -float(y))
            if record.get("closed"):
                path.closeSubpath()
            role = record.get("role", "")
            if role == "road_centerline":
                pen = _pen("#4F6B8E", 1.25, Qt.DashLine)
            elif role == "green":
                pen = _pen("#607A6A", 1.1)
            elif role == "parking":
                pen = _pen("#9C7A45", 1.1)
            else:
                pen = _pen("#74766F", 0.9)
            item = self.scene.addPath(path, pen)
            item.setToolTip(f"图层：{record.get('layer', '0')}")
            self._geometry_item_count += 1

        for record in geometry.get("curves", []):
            x, y = record["center"]
            radius = float(record["radius"])
            rect = QRectF(x - radius, -y - radius, radius * 2, radius * 2)
            curve_pen = (
                _pen("#607A6A", 1.1)
                if record.get("role") == "green"
                else _pen("#74766F", 0.9)
            )
            if record["type"] == "CIRCLE":
                self.scene.addEllipse(rect, curve_pen)
            else:
                start = float(record["start_angle"])
                end = float(record["end_angle"])
                sweep = (end - start) % 360.0
                path = QPainterPath()
                path.arcMoveTo(rect, start)
                path.arcTo(rect, start, sweep)
                self.scene.addPath(path, curve_pen)
            self._geometry_item_count += 1

        for record in geometry.get("inserts", []):
            x, y = record["point"]
            path = QPainterPath(QPointF(x - 1.5, -y))
            path.lineTo(x + 1.5, -y)
            path.moveTo(x, -y - 1.5)
            path.lineTo(x, -y + 1.5)
            item = self.scene.addPath(path, _pen("#B08B50", 1.1))
            item.setToolTip(f"块参照：{record['name']}")
            self._geometry_item_count += 1

        for record in geometry.get("texts", []):
            x, y = record["point"]
            text_item = self.scene.addSimpleText(record["text"])
            text_item.setBrush(QBrush(QColor("#74766F")))
            text_item.setFont(QFont("Microsoft YaHei", 6))
            text_item.setPos(x, -y)
            self._geometry_item_count += 1

        rect = self.scene.itemsBoundingRect()
        if rect.isValid() and not rect.isEmpty():
            margin_x = max(rect.width() * 0.05, 1.0)
            margin_y = max(rect.height() * 0.05, 1.0)
            self.scene.setSceneRect(rect.adjusted(-margin_x, -margin_y, margin_x, margin_y))
        self.info_label.setText(
            f"已显示 {self._geometry_item_count} 个 CAD 图元 · 滚轮缩放 · 按住左键拖动"
        )
        self.fit_to_view()

    def fit_to_view(self):
        self.view.fit_scene()

    def save_png(self, path: Path | str, max_dimension: int = 2400) -> Path:
        """Export the full vector scene, independent of the visible viewport."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        source_rect = self.scene.itemsBoundingRect()
        if source_rect.isEmpty():
            source_rect = QRectF(0, 0, 16, 9)
        margin_x = max(source_rect.width() * 0.04, 1.0)
        margin_y = max(source_rect.height() * 0.04, 1.0)
        source_rect = source_rect.adjusted(-margin_x, -margin_y, margin_x, margin_y)
        longest = max(source_rect.width(), source_rect.height(), 1.0)
        scale = max_dimension / longest
        width = max(320, int(source_rect.width() * scale))
        height = max(240, int(source_rect.height() * scale))
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(BACKGROUND)
        painter = QPainter(image)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.scene.render(painter, QRectF(0, 0, width, height), source_rect, Qt.KeepAspectRatio)
        painter.end()
        if not image.save(str(output), "PNG"):
            raise OSError(f"无法保存 CAD 预览图：{output}")
        return output
