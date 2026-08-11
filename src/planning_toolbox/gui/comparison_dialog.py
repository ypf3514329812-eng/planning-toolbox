"""Beginner-friendly multi-scenario comparison dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from planning_toolbox.gui.comparison import (
    COMPARISON_COLUMNS,
    build_comparison_rows,
    export_comparison_csv,
    export_comparison_excel,
)
from planning_toolbox.gui.overlay import export_overlay_png, render_project_overlays


class ComparisonDialog(QDialog):
    """Compare saved .ptx project results side by side."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HelpDialog")
        self.setWindowTitle("Planning Toolbox 多方案结果对比")
        self.setMinimumSize(1120, 650)
        self.resize(1280, 760)
        self.setModal(False)
        self.project_paths: List[Path] = []
        self.rows: List[Dict[str, Any]] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("多方案结果对比")
        title.setObjectName("HelpTitle")
        layout.addWidget(title)
        intro = QLabel(
            "先分别保存两个或多个 .ptx 作业项目，再在这里选择它们。系统会从最近一次结果记录中提取指标，"
            "帮助你比较不同参数下的方案表现；不会重新计算，也不会修改原始 DXF。"
        )
        intro.setObjectName("HelpIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        file_bar = QHBoxLayout()
        self.btn_add = QPushButton("📂 添加项目")
        self.btn_add.clicked.connect(self._add_projects)
        self.btn_remove = QPushButton("移除选中")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.clicked.connect(self._clear_projects)
        file_bar.addWidget(self.btn_add)
        file_bar.addWidget(self.btn_remove)
        file_bar.addWidget(self.btn_clear)
        file_bar.addStretch()
        self.btn_compare = QPushButton("📊 开始对比")
        self.btn_compare.setObjectName("PrimaryButton")
        self.btn_compare.clicked.connect(self._compare)
        file_bar.addWidget(self.btn_compare)
        self.btn_update_overlay = QPushButton("🎨 更新叠加图")
        self.btn_update_overlay.clicked.connect(self._render_overlay)
        file_bar.addWidget(self.btn_update_overlay)
        layout.addLayout(file_bar)

        self.project_list = QListWidget()
        self.project_list.setMaximumHeight(95)
        self.project_list.setToolTip("至少选择两个已保存的 .ptx 项目")
        layout.addWidget(self.project_list)

        self.status_label = QLabel("请添加至少两个 .ptx 项目文件。")
        self.status_label.setObjectName("BadgeInfo")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, len(COMPARISON_COLUMNS))
        self.table.setHorizontalHeaderLabels(COMPARISON_COLUMNS)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.views = QTabWidget()
        self.views.addTab(self.table, "📋 指标对比")

        self.overlay_figure = Figure(figsize=(8, 5), dpi=100)
        self.overlay_canvas = FigureCanvasQTAgg(self.overlay_figure)
        self.overlay_canvas.setMinimumHeight(360)
        self.overlay_records = []
        self.overlay_errors = []
        render_project_overlays(self.overlay_figure, [])
        self.overlay_canvas.draw_idle()
        self.views.addTab(self.overlay_canvas, "🎨 图形叠加")
        layout.addWidget(self.views, stretch=1)

        export_bar = QHBoxLayout()
        export_bar.addStretch()
        self.btn_export_csv = QPushButton("导出对比 CSV")
        self.btn_export_csv.setEnabled(False)
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_excel = QPushButton("导出对比 Excel")
        self.btn_export_excel.setEnabled(False)
        self.btn_export_excel.clicked.connect(self._export_excel)
        self.btn_export_overlay = QPushButton("导出叠加 PNG")
        self.btn_export_overlay.setEnabled(False)
        self.btn_export_overlay.clicked.connect(self._export_overlay)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.close)
        export_bar.addWidget(self.btn_export_csv)
        export_bar.addWidget(self.btn_export_excel)
        export_bar.addWidget(self.btn_export_overlay)
        export_bar.addWidget(close_button)
        layout.addLayout(export_bar)

    def _add_projects(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择 Planning Toolbox 作业项目",
            "",
            "Planning Toolbox 项目 (*.ptx)",
        )
        for raw_path in paths:
            path = Path(raw_path).resolve()
            if path not in self.project_paths:
                self.project_paths.append(path)
                self.project_list.addItem(str(path))
        self.status_label.setText(f"已添加 {len(self.project_paths)} 个项目；建议至少选择两个后开始对比。")

    def _remove_selected(self):
        row = self.project_list.currentRow()
        if row < 0:
            return
        self.project_list.takeItem(row)
        self.project_paths.pop(row)
        self.status_label.setText(f"已添加 {len(self.project_paths)} 个项目。")

    def _clear_projects(self):
        self.project_paths.clear()
        self.project_list.clear()
        self.rows = []
        self.table.setRowCount(0)
        self.overlay_records = []
        self.overlay_errors = []
        render_project_overlays(self.overlay_figure, [])
        self.overlay_canvas.draw_idle()
        self.btn_export_csv.setEnabled(False)
        self.btn_export_excel.setEnabled(False)
        self.btn_export_overlay.setEnabled(False)
        self.status_label.setText("请添加至少两个 .ptx 项目文件。")

    @staticmethod
    def _display_value(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:,.2f}"
        return str(value)

    def _compare(self):
        if len(self.project_paths) < 2:
            QMessageBox.information(self, "项目数量不足", "请至少添加两个 .ptx 项目，再开始对比。")
            return
        rows, errors = build_comparison_rows(self.project_paths)
        self.rows = rows
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, column in enumerate(COMPARISON_COLUMNS):
                self.table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(self._display_value(row.get(column))),
                )
        self.btn_export_csv.setEnabled(bool(rows))
        self.btn_export_excel.setEnabled(bool(rows))
        self._render_overlay()
        if errors:
            self.status_label.setText("部分项目无法读取：" + "；".join(errors))
            self.status_label.setObjectName("BadgeWarning")
        else:
            self.status_label.setText(f"已完成 {len(rows)} 个方案的对比。数值仅比较已保存的最近一次结果。")
            self.status_label.setObjectName("BadgeSuccess")
        self.status_label.setStyle(self.status_label.style())

    def _render_overlay(self):
        self.overlay_records, self.overlay_errors = render_project_overlays(
            self.overlay_figure,
            self.project_paths,
        )
        self.overlay_canvas.draw_idle()
        self.btn_export_overlay.setEnabled(bool(self.overlay_records))
        if self.overlay_errors:
            self.status_label.setText(
                self.status_label.text()
                + " 图形叠加部分项目无法读取："
                + "；".join(self.overlay_errors)
            )

    def _export_overlay(self):
        if not self.overlay_records:
            return
        directory = self._choose_export_dir()
        if not directory:
            return
        path = export_overlay_png(directory, self.overlay_figure)
        self.status_label.setText(f"✅ 方案叠加 PNG 已生成：{path}")
        self.status_label.setObjectName("BadgeSuccess")
        self.status_label.setStyle(self.status_label.style())

    def _choose_export_dir(self) -> Path | None:
        directory = QFileDialog.getExistingDirectory(self, "选择对比结果保存目录")
        return Path(directory) if directory else None

    def _export_csv(self):
        directory = self._choose_export_dir()
        if not directory:
            return
        path = export_comparison_csv(directory, self.rows)
        self.status_label.setText(f"✅ 对比 CSV 已生成：{path}")
        self.status_label.setObjectName("BadgeSuccess")
        self.status_label.setStyle(self.status_label.style())

    def _export_excel(self):
        directory = self._choose_export_dir()
        if not directory:
            return
        path = export_comparison_excel(directory, self.rows)
        self.status_label.setText(f"✅ 对比 Excel 已生成：{path}")
        self.status_label.setObjectName("BadgeSuccess")
        self.status_label.setStyle(self.status_label.style())
