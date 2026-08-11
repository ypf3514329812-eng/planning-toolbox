"""Non-blocking beginner dialog for navigating the existing full-chain tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from planning_toolbox.gui.workflow import (
    SOURCE_KINDS,
    WORKFLOW_STAGES,
    normalize_workflow_state,
    progress_percent,
    set_stage_skipped,
)


class FullChainWorkflowDialog(QDialog):
    """Guide users through the existing tools without loading any heavy engine."""

    state_changed = Signal(dict)
    navigate_requested = Signal(str, str)
    save_requested = Signal()

    def __init__(self, state: Mapping[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkflowDialog")
        self.setWindowTitle("GIS–CAD–SketchUp 全链路作业向导")
        self.setMinimumSize(760, 560)
        self.resize(860, 620)
        self._state = normalize_workflow_state(state)
        self._context: Dict[str, Any] = {}
        self._building_ui = True
        self._init_ui()
        self._building_ui = False
        self.set_state(self._state)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(11)

        title = QLabel("全链路作业向导")
        title.setObjectName("WorkflowTitle")
        layout.addWidget(title)

        intro = QLabel(
            "按顺序完成资料导入、无损检查、CAD 整理、规划分析、GIS/SU 交接和成果导出。"
            "向导只负责导航和保存进度，原有计算仍在后台运行，不会复制或修改原始图纸。"
        )
        intro.setObjectName("WorkflowIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("我的资料来源："))
        self.source_combo = QComboBox()
        for key, label in SOURCE_KINDS:
            self.source_combo.addItem(label, key)
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        source_row.addWidget(self.source_combo, stretch=1)
        layout.addLayout(source_row)

        self.working_file_label = QLabel("当前工作图：尚未选择 DXF")
        self.working_file_label.setObjectName("WorkflowWorkingFile")
        self.working_file_label.setWordWrap(True)
        layout.addWidget(self.working_file_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFormat("全链路进度 %p%")
        layout.addWidget(self.progress)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.stage_list = QListWidget()
        self.stage_list.setObjectName("WorkflowStageList")
        self.stage_list.setMinimumWidth(245)
        self.stage_list.setMaximumWidth(290)
        self.stage_list.setWordWrap(True)
        self.stage_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stage_list.currentRowChanged.connect(self._stage_selected)
        body.addWidget(self.stage_list)

        detail = QFrame()
        detail.setObjectName("WorkflowDetail")
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(10)
        self.stage_title = QLabel()
        self.stage_title.setObjectName("WorkflowStageTitle")
        self.stage_title.setWordWrap(True)
        detail_layout.addWidget(self.stage_title)
        self.stage_summary = QLabel()
        self.stage_summary.setWordWrap(True)
        detail_layout.addWidget(self.stage_summary)
        checklist_title = QLabel("这一阶段需要确认：")
        checklist_title.setStyleSheet("font-weight: 700; color: #566D8E;")
        detail_layout.addWidget(checklist_title)
        self.stage_checklist = QLabel()
        self.stage_checklist.setWordWrap(True)
        self.stage_checklist.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail_layout.addWidget(self.stage_checklist)
        self.stage_status = QLabel()
        self.stage_status.setWordWrap(True)
        detail_layout.addWidget(self.stage_status)
        detail_layout.addStretch()

        action_row = QHBoxLayout()
        self.skip_button = QPushButton("跳过可选步骤")
        self.skip_button.clicked.connect(self._toggle_skip)
        action_row.addWidget(self.skip_button)
        action_row.addStretch()
        self.navigate_button = QPushButton("进入此步骤")
        self.navigate_button.setObjectName("PrimaryButton")
        self.navigate_button.clicked.connect(self._navigate)
        action_row.addWidget(self.navigate_button)
        detail_layout.addLayout(action_row)
        body.addWidget(detail, stretch=1)
        layout.addLayout(body, stretch=1)

        footer = QHBoxLayout()
        self.previous_button = QPushButton("← 上一步")
        self.previous_button.clicked.connect(lambda: self._move_selection(-1))
        footer.addWidget(self.previous_button)
        self.next_button = QPushButton("下一步 →")
        self.next_button.clicked.connect(lambda: self._move_selection(1))
        footer.addWidget(self.next_button)
        footer.addStretch()
        self.save_button = QPushButton("💾 保存项目进度")
        self.save_button.clicked.connect(self.save_requested.emit)
        footer.addWidget(self.save_button)
        close_button = QPushButton("关闭向导")
        close_button.clicked.connect(self.close)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def state(self) -> Dict[str, Any]:
        return normalize_workflow_state(self._state)

    def set_state(self, value: Mapping[str, Any] | None) -> None:
        self._state = normalize_workflow_state(value)
        source_index = self.source_combo.findData(self._state["source_kind"])
        self.source_combo.blockSignals(True)
        self.source_combo.setCurrentIndex(max(0, source_index))
        self.source_combo.blockSignals(False)
        keys = [stage.key for stage in WORKFLOW_STAGES]
        row = keys.index(self._state["current_step"])
        self.stage_list.blockSignals(True)
        self._rebuild_stage_list()
        self.stage_list.setCurrentRow(row)
        self.stage_list.blockSignals(False)
        self._refresh_detail()
        self.progress.setValue(progress_percent(self._state))

    def refresh_context(self, context: Mapping[str, Any]) -> None:
        self._context = dict(context)
        working_dxf = str(self._context.get("working_dxf", "")).strip()
        lineage_count = int(self._context.get("lineage_count", 0) or 0)
        if working_dxf:
            working_path = Path(working_dxf)
            suffix = f" · 已接力 {lineage_count} 次" if lineage_count else " · 原始工作图"
            semantic_suffix = (
                " · 语义接力已连接"
                if self._context.get("semantic_scene_ready")
                else ""
            )
            self.working_file_label.setText(
                f"当前工作图：{working_path.name}{suffix}{semantic_suffix}"
            )
            semantic_path = str(self._context.get("semantic_scene_path", "")).strip()
            tooltip = str(working_path)
            if semantic_path:
                tooltip += f"\n语义交接：{semantic_path}"
            self.working_file_label.setToolTip(tooltip)
        else:
            self.working_file_label.setText("当前工作图：尚未选择 DXF")
            self.working_file_label.setToolTip("")
        self._refresh_detail()

    def _rebuild_stage_list(self) -> None:
        self.stage_list.clear()
        completed = set(self._state["completed_steps"])
        skipped = set(self._state["skipped_steps"])
        for number, stage in enumerate(WORKFLOW_STAGES, start=1):
            if stage.key in completed:
                prefix = "✓"
            elif stage.key in skipped:
                prefix = "—"
            elif stage.key == self._state["current_step"]:
                prefix = "▶"
            else:
                prefix = "○"
            suffix = "（可选）" if stage.optional else ""
            item = QListWidgetItem(f"{prefix} {number}. {stage.title}{suffix}")
            item.setData(Qt.UserRole, stage.key)
            self.stage_list.addItem(item)

    def _stage_selected(self, row: int) -> None:
        if row < 0 or row >= len(WORKFLOW_STAGES):
            return
        self._state["current_step"] = WORKFLOW_STAGES[row].key
        self._refresh_detail()
        if not self._building_ui:
            self.state_changed.emit(self.state())

    def _refresh_detail(self) -> None:
        row = self.stage_list.currentRow()
        if row < 0 or row >= len(WORKFLOW_STAGES):
            return
        stage = WORKFLOW_STAGES[row]
        optional = " · 可按作业需要跳过" if stage.optional else ""
        self.stage_title.setText(f"{row + 1}. {stage.title}{optional}")
        self.stage_summary.setText(stage.summary)
        self.stage_checklist.setText("\n".join(f"• {line}" for line in stage.checklist))
        completed = stage.key in self._state["completed_steps"]
        skipped = stage.key in self._state["skipped_steps"]
        if completed:
            status_text, object_name = "✅ 已获得本步骤的完成证据，可以继续。", "BadgeSuccess"
        elif skipped:
            status_text, object_name = "— 已明确跳过这个可选步骤，随时可以恢复。", "BadgeInfo"
        else:
            status_text, object_name = self._pending_status(stage.key), "BadgeWarning"
        self.stage_status.setText(status_text)
        self.stage_status.setObjectName(object_name)
        self.stage_status.setStyle(self.stage_status.style())
        self.skip_button.setVisible(stage.optional)
        self.skip_button.setText("恢复此步骤" if skipped else "跳过可选步骤")
        self.navigate_button.setText(self._navigate_label(stage.key))
        self.previous_button.setEnabled(row > 0)
        self.next_button.setEnabled(row < len(WORKFLOW_STAGES) - 1)
        self.progress.setValue(progress_percent(self._state))

    def _pending_status(self, stage_key: str) -> str:
        if stage_key == "setup":
            return "⚠️ 尚未确认项目名称、单位和坐标信息。"
        if stage_key == "source":
            return "⚠️ 尚未选择一个可以继续处理的 DXF 工作文件。"
        if stage_key == "inspection":
            if self._context.get("inspection_blocked"):
                return "🛑 预检查发现单位未知或文件无法读取，请先解决阻断项。"
            return "⚠️ 正在等待 DXF 无损预检查完成。"
        if stage_key == "export" and not self._context.get("result_available"):
            return "⚠️ 当前还没有可导出的任务结果，请先完成至少一项分析。"
        return "⚠️ 进入对应功能并成功运行后，本步骤会自动标记完成。"

    def _navigate_label(self, stage_key: str) -> str:
        labels = {
            "setup": "打开项目设置",
            "source": "选择或转换资料",
            "inspection": "查看检查结果",
            "export": "前往成果导出",
        }
        return labels.get(stage_key, "进入此步骤")

    def _source_changed(self, _index: int) -> None:
        self._state["source_kind"] = str(self.source_combo.currentData())
        self.state_changed.emit(self.state())
        self._refresh_detail()

    def _navigate(self) -> None:
        row = self.stage_list.currentRow()
        if row < 0:
            return
        stage = WORKFLOW_STAGES[row]
        self.navigate_requested.emit(stage.key, self._state["source_kind"])

    def _toggle_skip(self) -> None:
        row = self.stage_list.currentRow()
        if row < 0:
            return
        stage = WORKFLOW_STAGES[row]
        skipped = stage.key not in self._state["skipped_steps"]
        self._state = set_stage_skipped(self._state, stage.key, skipped)
        self.set_state(self._state)
        self.state_changed.emit(self.state())

    def _move_selection(self, delta: int) -> None:
        row = self.stage_list.currentRow()
        self.stage_list.setCurrentRow(max(0, min(len(WORKFLOW_STAGES) - 1, row + delta)))
