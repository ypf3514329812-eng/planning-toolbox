"""In-app editor for exact-pixel semantic guide images.

The original planning image is displayed only as a visual reference.  Painting
always happens on a separate white RGB image which is saved as a new PNG; this
keeps the source image immutable and makes the saved file directly usable by
the semantic-guide CAD converter.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from planning_toolbox.cad.planning.semantic_palette import SEMANTIC_GUIDE_PALETTE
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


GUIDE_LABELS = {
    "AI_ROAD": "道路",
    "AI_BUILDING": "建筑",
    "AI_GREEN": "绿地 / 树木",
    "AI_WATER": "水体",
    "AI_PARKING": "停车",
    "ERASER": "擦除为留白",
}


class SemanticGuideCanvas(QGraphicsView):
    """A compact pixel-preserving brush canvas over an immutable reference."""

    guide_changed = Signal()

    def __init__(
        self,
        source_path: Path | str,
        guide_path: Path | str | None = None,
        parent: QWidget | None = None,
        review_overlay_path: Path | str | None = None,
    ):
        super().__init__(parent)
        self.source_path = Path(source_path).resolve()
        self.source_sha256 = sha256_file(self.source_path)
        self._source_image = QImage(str(self.source_path)).convertToFormat(QImage.Format_RGB32)
        if self._source_image.isNull():
            raise ValueError("无法读取原始底图，请选择 PNG、JPG 或 BMP 图片。")

        self._guide_image = self._load_guide(guide_path)
        # Keep only compact paint operations instead of copying a full raster
        # for every undo step.  This is important for large plan sheets.
        self._base_guide_image = self._guide_image.copy()
        self._history: list[list[tuple[str, int, tuple[int, int], tuple[int, int]]]] = []
        self._redo_history: list[list[tuple[str, int, tuple[int, int], tuple[int, int]]]] = []
        self._pending_brush_stroke: list[tuple[str, int, tuple[int, int], tuple[int, int]]] = []
        self._path_points: list[tuple[int, int]] = []
        self._path_segments: list[tuple[str, int, tuple[int, int], tuple[int, int]]] = []
        self._draw_mode = "brush"
        self._brush_key = "AI_ROAD"
        self._brush_size = 18
        self._last_point: QPoint | None = None
        self._drawing = False
        self._zoom_steps = 0

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._source_item = QGraphicsPixmapItem(QPixmap.fromImage(self._source_image))
        self._guide_item = QGraphicsPixmapItem(QPixmap.fromImage(self._guide_image))
        self._guide_item.setOpacity(0.56)
        self._scene.addItem(self._source_item)
        self._scene.addItem(self._guide_item)
        if review_overlay_path:
            overlay_path = Path(review_overlay_path).resolve()
            review_image = QImage(str(overlay_path)).convertToFormat(QImage.Format_RGB32)
            if review_image.isNull():
                raise ValueError("无法读取道路复核叠加图，请重新运行图片转 CAD。")
            if review_image.size() != self._source_image.size():
                raise ValueError(
                    "道路复核叠加图必须与原图像素尺寸完全一致；"
                    f"原图为 {self._source_image.width()}×{self._source_image.height()}，"
                    f"叠加图为 {review_image.width()}×{review_image.height()}。"
                )
            self._review_overlay_item = QGraphicsPixmapItem(QPixmap.fromImage(review_image))
            self._review_overlay_item.setOpacity(0.48)
            self._scene.addItem(self._review_overlay_item)
        else:
            self._review_overlay_item = None
        self._scene.setSceneRect(
            QRectF(0, 0, self._source_image.width(), self._source_image.height())
        )

        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QColor("#F3F0E8"))
        self.setFrameShape(QGraphicsView.NoFrame)

    def _load_guide(self, guide_path: Path | str | None) -> QImage:
        if guide_path:
            candidate = Path(guide_path).resolve()
            image = QImage(str(candidate)).convertToFormat(QImage.Format_RGB32)
            if image.isNull():
                raise ValueError("无法读取现有语义引导图，请选择有效的图片文件。")
            if image.size() != self._source_image.size():
                raise ValueError(
                    "现有语义引导图必须与原图像素尺寸完全一致；"
                    f"原图为 {self._source_image.width()}×{self._source_image.height()}，"
                    f"引导图为 {image.width()}×{image.height()}。"
                )
            return image
        image = QImage(self._source_image.size(), QImage.Format_RGB32)
        image.fill(Qt.white)
        return image

    @property
    def guide_size(self):
        return self._guide_image.size()

    def set_brush(self, key: str) -> None:
        if key not in {*SEMANTIC_GUIDE_PALETTE, "ERASER"}:
            raise ValueError(f"不支持的语义画笔：{key}")
        self._brush_key = key

    def set_brush_size(self, value: int) -> None:
        self._brush_size = max(1, min(int(value), 500))

    def set_draw_mode(self, mode: str) -> None:
        if mode not in {"brush", "road_path"}:
            raise ValueError(f"不支持的绘制模式：{mode}")
        if mode != "road_path":
            self.finish_path()
        self._draw_mode = mode

    @property
    def draw_mode(self) -> str:
        return self._draw_mode

    @property
    def brush_key(self) -> str:
        return self._brush_key

    @property
    def path_point_count(self) -> int:
        return len(self._path_points)

    @property
    def history_depth(self) -> int:
        return len(self._history)

    def reset_to_blank(self) -> None:
        self.cancel_path()
        self._guide_image.fill(Qt.white)
        self._base_guide_image = self._guide_image.copy()
        self._history.clear()
        self._redo_history.clear()
        self._refresh_guide_item()
        self.guide_changed.emit()

    def apply_stroke(self, start: QPoint, end: QPoint | None = None) -> None:
        """Paint a single editable stroke in source-image pixel coordinates."""
        operation = self._operation_tuple(start, end or start)
        self._paint_operation(operation)
        self._history.append([operation])
        self._redo_history.clear()
        self._refresh_guide_item()
        self.guide_changed.emit()

    def _operation_tuple(
        self, start: QPoint, end: QPoint
    ) -> tuple[str, int, tuple[int, int], tuple[int, int]]:
        return (
            self._brush_key,
            self._brush_size,
            (start.x(), start.y()),
            (end.x(), end.y()),
        )

    def _paint_operation(
        self, operation: tuple[str, int, tuple[int, int], tuple[int, int]]
    ) -> None:
        key, size, start, end = operation
        finish = end or start
        painter = QPainter(self._guide_image)
        painter.setRenderHint(QPainter.Antialiasing, False)
        color = (
            QColor(*SEMANTIC_GUIDE_PALETTE[key])
            if key != "ERASER"
            else QColor(Qt.white)
        )
        pen = QPen(color, size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(QPoint(*start), QPoint(*end))
        painter.end()

    def _rebuild_from_history(self) -> None:
        self._guide_image = self._base_guide_image.copy()
        for group in self._history:
            for operation in group:
                self._paint_operation(operation)
        self._refresh_guide_item()
        self.guide_changed.emit()

    def undo(self) -> bool:
        self.cancel_path()
        if not self._history:
            return False
        self._redo_history.append(self._history.pop())
        self._rebuild_from_history()
        return True

    def redo(self) -> bool:
        self.cancel_path()
        if not self._redo_history:
            return False
        self._history.append(self._redo_history.pop())
        self._rebuild_from_history()
        return True

    def finish_path(self) -> bool:
        if not self._path_segments:
            self._path_points.clear()
            return False
        self._history.append(list(self._path_segments))
        self._redo_history.clear()
        self._path_segments.clear()
        self._path_points.clear()
        self.guide_changed.emit()
        return True

    def cancel_path(self) -> None:
        if not self._path_segments and not self._path_points:
            return
        self._path_segments.clear()
        self._path_points.clear()
        self._rebuild_from_history()

    def add_path_point(self, point: QPoint) -> None:
        current = (point.x(), point.y())
        if self._path_points and current == self._path_points[-1]:
            return
        if self._path_points:
            operation = (
                "AI_ROAD",
                self._brush_size,
                self._path_points[-1],
                current,
            )
            self._paint_operation(operation)
            self._path_segments.append(operation)
            self._refresh_guide_item()
            self.guide_changed.emit()
        self._path_points.append(current)

    def _add_path_point(self, point: QPoint) -> None:
        self.add_path_point(point)

    def save_png(self, destination: Path | str) -> Path:
        target = Path(destination).resolve()
        if target == self.source_path:
            raise ValueError("不能覆盖原始底图；请保存为新的语义引导 PNG。")
        if target.suffix.lower() != ".png":
            target = target.with_suffix(".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not self._guide_image.save(str(target), "PNG"):
            raise ValueError("语义引导图保存失败，请确认输出文件夹可写。")
        reopened = QImage(str(target))
        if reopened.isNull() or reopened.size() != self._source_image.size():
            raise ValueError("保存后的语义引导图尺寸异常，已阻止继续使用。")
        assert_file_unchanged(self.source_path, self.source_sha256)
        return target

    def fit_to_source(self) -> None:
        rect = self.sceneRect()
        if rect.isValid() and not rect.isEmpty():
            margin_x = max(rect.width() * 0.03, 1.0)
            margin_y = max(rect.height() * 0.03, 1.0)
            self.fitInView(
                rect.adjusted(-margin_x, -margin_y, margin_x, margin_y),
                Qt.KeepAspectRatio,
            )
            self._zoom_steps = 0

    def _refresh_guide_item(self) -> None:
        self._guide_item.setPixmap(QPixmap.fromImage(self._guide_image))

    def _image_point(self, viewport_point: QPointF) -> QPoint | None:
        point = self.mapToScene(viewport_point.toPoint())
        if not self.sceneRect().contains(point):
            return None
        return QPoint(
            max(0, min(self._source_image.width() - 1, round(point.x()))),
            max(0, min(self._source_image.height() - 1, round(point.y()))),
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            point = self._image_point(event.position())
            if point is not None:
                if self._draw_mode == "road_path":
                    self._add_path_point(point)
                    event.accept()
                    return
                self._pending_brush_stroke = []
                self._drawing = True
                self._last_point = point
                operation = self._operation_tuple(point, point)
                self._paint_operation(operation)
                self._pending_brush_stroke.append(operation)
                self._refresh_guide_item()
                self.guide_changed.emit()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawing and event.buttons() & Qt.LeftButton:
            point = self._image_point(event.position())
            if point is not None and self._last_point is not None:
                operation = self._operation_tuple(self._last_point, point)
                self._paint_operation(operation)
                self._pending_brush_stroke.append(operation)
                self._refresh_guide_item()
                self.guide_changed.emit()
                self._last_point = point
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drawing:
            self._drawing = False
            self._last_point = None
            if self._pending_brush_stroke:
                self._history.append(list(self._pending_brush_stroke))
                self._redo_history.clear()
            self._pending_brush_stroke = []
            event.accept()
            return
        super().mouseReleaseEvent(event)

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

    def mouseDoubleClickEvent(self, event):
        if self._draw_mode == "road_path":
            self.finish_path()
        else:
            self.fit_to_source()
        event.accept()


class SemanticGuideEditorDialog(QDialog):
    """Beginner-facing dialog for painting a valid semantic guide locally."""

    guide_saved = Signal(str)

    def __init__(
        self,
        source_path: Path | str,
        guide_path: Path | str | None = None,
        parent: QWidget | None = None,
        review_overlay_path: Path | str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("语义引导图编辑器（原图只读）")
        self.setMinimumSize(860, 620)
        self.resize(1120, 760)
        self.source_path = Path(source_path).resolve()
        self.saved_path = ""
        self.canvas = SemanticGuideCanvas(
            self.source_path,
            guide_path,
            self,
            review_overlay_path=review_overlay_path,
        )
        self._brush_buttons: dict[str, QPushButton] = {}
        self._mode_buttons: dict[str, QPushButton] = {}
        self._build_ui()
        self.canvas.fit_to_source()
        self._select_brush("AI_ROAD")
        self._select_mode("brush")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        notice = QLabel(
            "原图只作为对齐参考，不会被修改。左键涂画；滚轮缩放；中键拖动；双击复位。"
            "橙色/红色道路线只用于复核提示，不会保存进语义引导图；"
            "保存后得到与原图完全同像素尺寸的 PNG，可直接用于“原图 + 彩色语义引导图”。"
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color:#536F83; font-size:12px; padding:4px;")
        layout.addWidget(notice)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("画笔类别:"))
        for key in ("AI_ROAD", "AI_BUILDING", "AI_GREEN", "AI_WATER", "AI_PARKING", "ERASER"):
            button = QPushButton(GUIDE_LABELS[key])
            button.setCheckable(True)
            if key != "ERASER":
                color = QColor(*SEMANTIC_GUIDE_PALETTE[key])
                button.setStyleSheet(
                    f"QPushButton {{ background:{color.name()}; color:#24323B; padding:5px 9px; }}"
                    "QPushButton:checked { border:2px solid #405E78; font-weight:700; }"
                )
            else:
                button.setStyleSheet(
                    "QPushButton { background:#FFFFFF; padding:5px 9px; }"
                    "QPushButton:checked { border:2px solid #405E78; font-weight:700; }"
                )
            button.clicked.connect(lambda checked=False, value=key: self._select_brush(value))
            self._brush_buttons[key] = button
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        mode_toolbar = QHBoxLayout()
        mode_toolbar.addWidget(QLabel("绘制方式:"))
        for mode, label in (("brush", "自由画笔"), ("road_path", "道路路径")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(
                "按点点击道路边界或中心辅助线，双击或点击完成路径；路径会以道路颜色绘制。"
                if mode == "road_path"
                else "按住鼠标左键自由补画语义区域。"
            )
            button.clicked.connect(lambda checked=False, value=mode: self._select_mode(value))
            self._mode_buttons[mode] = button
            mode_toolbar.addWidget(button)
        self.finish_path_button = QPushButton("完成路径")
        self.finish_path_button.setEnabled(False)
        self.finish_path_button.clicked.connect(self._finish_path)
        mode_toolbar.addWidget(self.finish_path_button)
        cancel_path_button = QPushButton("取消路径")
        cancel_path_button.clicked.connect(self._cancel_path)
        mode_toolbar.addWidget(cancel_path_button)
        undo = QPushButton("撤销")
        undo.setToolTip("撤销最近一次画笔或道路路径操作。")
        undo.clicked.connect(self._undo)
        mode_toolbar.addWidget(undo)
        redo = QPushButton("重做")
        redo.setToolTip("恢复刚刚撤销的操作。")
        redo.clicked.connect(self._redo)
        mode_toolbar.addWidget(redo)
        mode_toolbar.addWidget(QLabel("画笔大小:"))
        self.brush_size = QSpinBox()
        self.brush_size.setRange(1, 500)
        self.brush_size.setValue(18)
        self.brush_size.setSuffix(" px")
        self.brush_size.valueChanged.connect(self.canvas.set_brush_size)
        mode_toolbar.addWidget(self.brush_size)
        reset = QPushButton("清空语义图")
        reset.clicked.connect(self._confirm_reset)
        mode_toolbar.addWidget(reset)
        fit = QPushButton("适应窗口")
        fit.clicked.connect(self.canvas.fit_to_source)
        mode_toolbar.addWidget(fit)
        mode_toolbar.addStretch()
        layout.addLayout(mode_toolbar)
        layout.addWidget(self.canvas, stretch=1)

        footer = QHBoxLayout()
        self.status = QLabel(
            f"底图尺寸：{self.canvas.guide_size.width()} × {self.canvas.guide_size.height()} px"
        )
        self.status.setStyleSheet("color:#74766F; font-size:11px;")
        footer.addWidget(self.status)
        footer.addStretch()
        save = QPushButton("保存引导图并使用")
        save.setObjectName("SaveSemanticGuideButton")
        save.clicked.connect(self._choose_and_save)
        footer.addWidget(save)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        layout.addLayout(footer)

    def _select_brush(self, key: str) -> None:
        self.canvas.set_brush(key)
        for candidate, button in self._brush_buttons.items():
            button.setChecked(candidate == key)
        self.status.setText(
            f"当前画笔：{GUIDE_LABELS[key]}；底图尺寸："
            f"{self.canvas.guide_size.width()} × {self.canvas.guide_size.height()} px"
        )

    def _select_mode(self, mode: str) -> None:
        if mode == "road_path":
            self.canvas.set_brush("AI_ROAD")
            for candidate, button in self._brush_buttons.items():
                button.setChecked(candidate == "AI_ROAD")
        self.canvas.set_draw_mode(mode)
        for candidate, button in self._mode_buttons.items():
            button.setChecked(candidate == mode)
        self.finish_path_button.setEnabled(mode == "road_path")
        self._update_status()

    def _update_status(self) -> None:
        mode_label = "道路路径" if self.canvas.draw_mode == "road_path" else "自由画笔"
        path_label = (
            f"；当前路径 {self.canvas.path_point_count} 个点"
            if self.canvas.draw_mode == "road_path"
            else ""
        )
        self.status.setText(
            f"绘制方式：{mode_label}；画笔：{GUIDE_LABELS[self.canvas.brush_key]}；"
            f"底图尺寸：{self.canvas.guide_size.width()} × "
            f"{self.canvas.guide_size.height()} px{path_label}"
        )

    def _finish_path(self) -> None:
        if self.canvas.finish_path():
            self._update_status()

    def _cancel_path(self) -> None:
        self.canvas.cancel_path()
        self._update_status()

    def _undo(self) -> None:
        self.canvas.undo()
        self._update_status()

    def _redo(self) -> None:
        self.canvas.redo()
        self._update_status()

    def _confirm_reset(self) -> None:
        choice = QMessageBox.question(
            self,
            "清空语义引导图",
            "这会清空当前编辑画布中的颜色标记，但不会修改原图或已保存文件。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice == QMessageBox.Yes:
            self.canvas.reset_to_blank()

    def save_to(self, destination: Path | str) -> str:
        saved = self.canvas.save_png(destination)
        self.saved_path = str(saved)
        self.guide_saved.emit(self.saved_path)
        return self.saved_path

    def _choose_and_save(self) -> None:
        default = self.source_path.with_name(f"{self.source_path.stem}_semantic_guide_manual.png")
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "保存语义引导图（PNG）",
            str(default),
            "PNG 图片 (*.png)",
        )
        if not selected:
            return
        try:
            self.save_to(selected)
        except Exception as exc:
            QMessageBox.warning(self, "无法保存语义引导图", str(exc))
            return
        QMessageBox.information(
            self,
            "语义引导图已保存",
            "已保存同像素尺寸 PNG，并已自动填入“语义引导图”输入框。"
            "现在可直接运行图片转 CAD。",
        )
        self.accept()
