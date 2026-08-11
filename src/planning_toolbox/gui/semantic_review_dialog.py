"""Visual, non-destructive review of image-derived CAD semantic candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QItemSelectionModel, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from planning_toolbox.gui.widgets.native_canvas_widget import NativeCADPreviewCanvas
from planning_toolbox.project.semantic_scene import (
    apply_semantic_candidate_reviews,
    load_semantic_scene_for_dxf,
)


_ROLE_LABELS = {
    "building": "建筑",
    "parcel": "地块",
    "green": "绿化",
    "road": "道路",
    "water": "水体",
    "parking": "停车",
}
_STATUS_LABELS = {
    "pending": "待确认",
    "accepted": "已接受",
    "rejected": "已拒绝（保留为参考）",
}
_STATUS_COLORS = {
    "pending": ("#F4E9D3", "#8B6B3F"),
    "accepted": ("#E3EEE8", "#557665"),
    "rejected": ("#F4DDDA", "#9B5C57"),
}


class SemanticCandidateReviewDialog(QDialog):
    """Review candidates while keeping the source image and DXF immutable."""

    def __init__(self, dxf_path: Path | str, parent=None):
        super().__init__(parent)
        self.dxf_path = Path(dxf_path).resolve()
        scene = load_semantic_scene_for_dxf(self.dxf_path)
        if scene is None:
            raise FileNotFoundError("当前 DXF 没有可复核的语义候选清单。")
        self._scene_sha256 = str(scene["file_sha256"])
        self._candidates = [
            dict(item)
            for item in scene.get("object_registry", [])
            if str(item.get("review_status", "pending")) != "layer_confirmed"
        ]
        self._by_id = {
            str(item["id"]): item for item in self._candidates
        }
        self._history: list[dict[str, str]] = []
        self._marker_items: list[Any] = []
        self.review_result: dict[str, Any] | None = None

        self.setWindowTitle("图转 CAD 候选复核")
        self.resize(1120, 720)
        self.setMinimumSize(900, 600)
        self._init_ui()
        self._populate_table()
        self.preview.load_dxf_preview(self.dxf_path)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("逐项确认图转 CAD 候选")
        title.setObjectName("ZoneTitle")
        layout.addWidget(title)

        intro = QLabel(
            "左侧选择候选，右侧会定位其在 CAD 中的位置。接受后可继续按对象用途建模；"
            "拒绝后只降级为锁定参考底图，不会从 DXF 删除。取消窗口不会保存任何决定。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        splitter = QSplitter(Qt.Horizontal)
        table_panel = QWidget()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["编号", "类型", "CAD 图层", "图元", "可信度", "复核状态"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._highlight_selected)
        table_layout.addWidget(self.table, stretch=1)

        selection_row = QHBoxLayout()
        select_all = QPushButton("全选")
        select_all.clicked.connect(self.table.selectAll)
        pending_only = QPushButton("只选待确认")
        pending_only.clicked.connect(self._select_pending)
        selection_row.addWidget(select_all)
        selection_row.addWidget(pending_only)
        selection_row.addStretch()
        table_layout.addLayout(selection_row)

        decision_row = QHBoxLayout()
        accept_button = QPushButton("✓ 接受所选")
        accept_button.setObjectName("PrimaryButton")
        accept_button.clicked.connect(lambda: self._set_selected_status("accepted"))
        reject_button = QPushButton("✕ 拒绝所选")
        reject_button.clicked.connect(lambda: self._set_selected_status("rejected"))
        reset_button = QPushButton("恢复待确认")
        reset_button.clicked.connect(lambda: self._set_selected_status("pending"))
        self.undo_button = QPushButton("↶ 撤销上一步")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self._undo)
        decision_row.addWidget(accept_button)
        decision_row.addWidget(reject_button)
        decision_row.addWidget(reset_button)
        decision_row.addWidget(self.undo_button)
        table_layout.addLayout(decision_row)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        table_layout.addWidget(self.summary_label)

        self.preview = NativeCADPreviewCanvas()
        self.preview.preview_loaded.connect(self._highlight_selected)
        splitter.addWidget(table_panel)
        splitter.addWidget(self.preview)
        splitter.setSizes([560, 560])
        layout.addWidget(splitter, stretch=1)

        note = QLabel(
            "提示：这里确认的是“机器候选是否可作为该类对象继续使用”，不是规范审批。"
            "边界、比例、高度、道路组织和最终表达仍须人工检查。"
        )
        note.setWordWrap(True)
        note.setObjectName("MutedHint")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存复核结果")
        buttons.button(QDialogButtonBox.Cancel).setText("取消（不保存）")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            values = (
                f"C{row + 1:03d}",
                _ROLE_LABELS.get(str(candidate.get("role")), "其他"),
                str(candidate.get("source_layer", "0")),
                str(candidate.get("source_type", "")),
                f"{float(candidate.get('confidence', 0.0)):.2f}",
                _STATUS_LABELS.get(
                    str(candidate.get("review_status", "pending")), "待确认"
                ),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, str(candidate["id"]))
                self.table.setItem(row, column, item)
            self._refresh_status_cell(row)
        self._refresh_summary()
        if self._candidates:
            self.table.selectRow(0)

    def _selected_rows(self) -> list[int]:
        return sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()}
        )

    def _selected_candidates(self) -> list[dict[str, Any]]:
        return [self._candidates[row] for row in self._selected_rows()]

    def _select_pending(self) -> None:
        self.table.clearSelection()
        selection_model = self.table.selectionModel()
        for row, candidate in enumerate(self._candidates):
            if str(candidate.get("review_status", "pending")) == "pending":
                selection_model.select(
                    self.table.model().index(row, 0),
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )

    def _set_selected_status(self, status: str) -> None:
        selected = self._selected_candidates()
        if not selected:
            QMessageBox.information(self, "请先选择", "请先在候选表中选择一项或多项。")
            return
        previous = {
            str(item["id"]): str(item.get("review_status", "pending"))
            for item in selected
            if str(item.get("review_status", "pending")) != status
        }
        if not previous:
            return
        self._history.append(previous)
        self._history = self._history[-30:]
        for item in selected:
            item["review_status"] = status
        for row in self._selected_rows():
            self._refresh_status_cell(row)
        self.undo_button.setEnabled(True)
        self._refresh_summary()

    def _undo(self) -> None:
        if not self._history:
            return
        previous = self._history.pop()
        for object_id, status in previous.items():
            self._by_id[object_id]["review_status"] = status
        for row in range(self.table.rowCount()):
            self._refresh_status_cell(row)
        self.undo_button.setEnabled(bool(self._history))
        self._refresh_summary()

    def _refresh_status_cell(self, row: int) -> None:
        candidate = self._candidates[row]
        status = str(candidate.get("review_status", "pending"))
        item = self.table.item(row, 5)
        item.setText(_STATUS_LABELS.get(status, "待确认"))
        background, foreground = _STATUS_COLORS.get(status, _STATUS_COLORS["pending"])
        item.setBackground(QBrush(QColor(background)))
        item.setForeground(QBrush(QColor(foreground)))

    def _refresh_summary(self) -> None:
        counts = {status: 0 for status in _STATUS_LABELS}
        for item in self._candidates:
            status = str(item.get("review_status", "pending"))
            if status in counts:
                counts[status] += 1
        self.summary_label.setText(
            f"共 {len(self._candidates)} 个候选：已接受 {counts['accepted']}，"
            f"已拒绝 {counts['rejected']}，待确认 {counts['pending']}。"
        )

    def _clear_markers(self) -> None:
        for item in self._marker_items:
            try:
                self.preview.scene.removeItem(item)
            except RuntimeError:
                pass
        self._marker_items.clear()

    def _highlight_selected(self) -> None:
        self._clear_markers()
        rows = self._selected_rows()
        if not rows:
            return
        row = rows[0]
        candidate = self._candidates[row]
        bounds = candidate.get("bounds", [])
        if not isinstance(bounds, list) or len(bounds) != 4:
            return
        min_x, min_y, max_x, max_y = (float(value) for value in bounds)
        width = max(max_x - min_x, 0.5)
        height = max(max_y - min_y, 0.5)
        rect = QRectF(min_x, -max_y, width, height)
        pen = QPen(QColor("#C45F55"), 3.0)
        pen.setCosmetic(True)
        marker = self.preview.scene.addRect(
            rect, pen, QBrush(QColor(196, 95, 85, 34))
        )
        marker.setZValue(1000)
        label = self.preview.scene.addSimpleText(f"C{row + 1:03d}")
        label.setBrush(QBrush(QColor("#9B403A")))
        label.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        label.setPos(rect.left(), rect.top() - label.boundingRect().height())
        label.setZValue(1001)
        self._marker_items.extend((marker, label))
        margin = max(width, height, 2.0) * 1.4
        focus = rect.adjusted(-margin, -margin, margin, margin)
        self.preview.view.fitInView(focus, Qt.KeepAspectRatio)

    def _save(self) -> None:
        decisions = {
            str(item["id"]): str(item.get("review_status", "pending"))
            for item in self._candidates
        }
        try:
            self.review_result = apply_semantic_candidate_reviews(
                self.dxf_path,
                decisions,
                expected_scene_sha256=self._scene_sha256,
            )
        except Exception as exc:
            QMessageBox.warning(self, "候选复核未保存", str(exc))
            return
        self.accept()

    def done(self, result: int) -> None:
        self.preview.cancel_preview(wait=True)
        super().done(result)


__all__ = ["SemanticCandidateReviewDialog"]
