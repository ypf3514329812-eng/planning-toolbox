"""结果摘要与面板区 (Result Zone Widget with KPI Hero Bar, Table, 2D Canvas & HTML Console Logs)."""
from pathlib import Path
from typing import Dict, Any, List, Optional
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem, QTabWidget, QWidget,
    QFileDialog, QMessageBox, QDialog,
)
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QColor, QTextCursor

from planning_toolbox.gui.widgets.lazy_canvas_widget import LazyCADPreviewCanvas
from planning_toolbox.gui.workflow import (
    REVIEW_CONTINUATION_TASKS,
    continuation_dxf_candidate,
)

class ResultZoneWidget(QFrame):
    """
    结果区：展示运行状态胶囊、英雄数值摘要条、结果表格、嵌入式 2D CAD 预览画布、中文警告提示框、输出文件列表及彩色 HTML 控制台日志。
    """

    artifacts_exported = Signal(str)
    working_dxf_requested = Signal(str, str)
    road_repair_requested = Signal(str, str, str)
    sketchup_handoff_requested = Signal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoneFrame")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        # 1. 标题与状态胶囊
        top_bar = QHBoxLayout()
        title = QLabel("分析结果与可视化 (Results & Visual Dashboard)")
        title.setObjectName("ZoneTitle")
        top_bar.addWidget(title)

        top_bar.addStretch()
        self.lbl_status_badge = QLabel("等待运行")
        self.lbl_status_badge.setObjectName("BadgeWarning")
        top_bar.addWidget(self.lbl_status_badge)

        layout.addLayout(top_bar)

        # 2. 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        layout.addWidget(self.progress_bar)

        # 3. KPI 结果摘要栏 (有效地块, 总面积, 容积率范围, 退线合规率)
        self.kpi_bar = QHBoxLayout()
        self.kpi_bar.setSpacing(10)

        self.kpi_parcels = self._create_kpi_mini_card("有效地块", "-", "📍")
        self.kpi_area = self._create_kpi_mini_card("有效总面积", "-", "📐")
        self.kpi_far = self._create_kpi_mini_card("容积率 (FAR)", "-", "🏢")
        self.kpi_setback = self._create_kpi_mini_card("退线合规率", "-", "🛡️")

        self.kpi_bar.addWidget(self.kpi_parcels)
        self.kpi_bar.addWidget(self.kpi_area)
        self.kpi_bar.addWidget(self.kpi_far)
        self.kpi_bar.addWidget(self.kpi_setback)
        layout.addLayout(self.kpi_bar)

        # 4. 全链路质量关卡：区分“程序完成”和“成果可继续/需复核/被阻断”
        self.lbl_quality_review = QLabel("")
        self.lbl_quality_review.setWordWrap(True)
        self.lbl_quality_review.hide()
        layout.addWidget(self.lbl_quality_review)

        # 5. 中文警告提示框 (如孔洞/NESTED_RING)
        self.lbl_warning_banner = QLabel("")
        self.lbl_warning_banner.setStyleSheet(
            "background-color: #F4E9D3; color: #8B6B3F; border: 1px solid #D8B781; "
            "border-radius: 6px; padding: 6px 10px; font-weight: 700;"
        )
        self.lbl_warning_banner.setWordWrap(True)
        self.lbl_warning_banner.hide()
        layout.addWidget(self.lbl_warning_banner)

        # 6. 子选项卡: 表格视图 / 2D 画布预览 / 控制台日志
        self.result_tabs = QTabWidget()
        self.result_tabs.setMinimumHeight(220)

        # Tab 1: 表格视图
        self.table = QTableWidget()
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["地块 ID / 统计项", "面积 / 状态", "主要指标 / 规则要求", "详情 / 错误提示"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_tabs.addTab(self.table, "📋 表格清单视图")

        # Tab 2: 2D CAD 画布预览
        self.canvas = LazyCADPreviewCanvas()
        self.result_tabs.addTab(self.canvas, "🎨 2D CAD 矢量预览")

        # Tab 3: 控制台与安全日志
        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("LogTextEdit")
        self.log_edit.setReadOnly(True)
        self.result_tabs.addTab(self.log_edit, "💻 运行与日志记录")

        layout.addWidget(self.result_tabs, stretch=6)

        # 7. 底部：输出文件列表与快捷按钮
        file_bar = QHBoxLayout()
        file_bar.setSpacing(6)
        file_bar.addWidget(QLabel("生成文件:"))

        self.btn_open_folder = QPushButton("📁 输出文件夹")
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        self.btn_open_file = QPushButton("📄 打开文件")
        self.btn_open_file.clicked.connect(self._open_selected_file)
        self.btn_assignment_package = QPushButton("🧰 作业包")
        self.btn_assignment_package.setToolTip("把本次生成的 CAD、数据表和报告整理到新文件夹，并生成 ZIP")
        self.btn_assignment_package.setEnabled(False)
        self.btn_assignment_package.clicked.connect(self._export_assignment_package)
        self.btn_result_export = QPushButton("📤 导出成果")
        self.btn_result_export.setToolTip("把当前结果导出为 Excel、PDF 报告和 PNG 预览图")
        self.btn_result_export.setEnabled(False)
        self.btn_result_export.clicked.connect(self._export_result_artifacts)
        self.btn_repair_compare = QPushButton("🔎 修复对比")
        self.btn_repair_compare.setToolTip("叠加显示修复前后线条，红色表示删除/替换，绿色表示新增/替换")
        self.btn_repair_compare.setEnabled(False)
        self.btn_repair_compare.clicked.connect(self._open_repair_comparison)
        self.btn_edit_road_guide = QPushButton("🖍️ 修正道路")
        self.btn_edit_road_guide.setToolTip(
            "打开同像素语义引导图编辑器，用道路路径补画漏检路段；原图和原始 DXF 保持只读"
        )
        self.btn_edit_road_guide.setEnabled(False)
        self.btn_edit_road_guide.clicked.connect(self._request_road_repair)
        self.btn_curate_cad = QPushButton("⭐ 收藏精修 CAD")
        self.btn_curate_cad.setToolTip(
            "选择你已经人工精修并核对过的 DXF，把它作为少量精选参考样本附加到本次知识卡"
        )
        self.btn_curate_cad.setEnabled(False)
        self.btn_curate_cad.clicked.connect(self._curate_refined_cad)

        file_bar.addStretch()
        file_bar.addWidget(self.btn_curate_cad)
        file_bar.addWidget(self.btn_repair_compare)
        file_bar.addWidget(self.btn_result_export)
        file_bar.addWidget(self.btn_assignment_package)
        file_bar.addWidget(self.btn_open_folder)
        file_bar.addWidget(self.btn_open_file)
        layout.addLayout(file_bar)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(65)
        self.file_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.file_list)

        road_repair_bar = QHBoxLayout()
        self.lbl_road_repair_hint = QLabel(
            "道路漏检时，可沿叠加图进入道路路径修正：原图和原始 DXF 不会被覆盖。"
        )
        self.lbl_road_repair_hint.setWordWrap(True)
        self.lbl_road_repair_hint.setObjectName("MutedHint")
        road_repair_bar.addWidget(self.lbl_road_repair_hint, stretch=1)
        road_repair_bar.addWidget(self.btn_edit_road_guide)
        self.road_repair_bar = QWidget()
        self.road_repair_bar.setLayout(road_repair_bar)
        self.road_repair_bar.hide()
        layout.addWidget(self.road_repair_bar)

        semantic_review_bar = QHBoxLayout()
        self.lbl_semantic_review_hint = QLabel(
            "在系统内逐项接受或拒绝机器候选；拒绝项只降级为参考底图，不会删除 DXF 图元。"
        )
        self.lbl_semantic_review_hint.setWordWrap(True)
        self.lbl_semantic_review_hint.setObjectName("MutedHint")
        semantic_review_bar.addWidget(self.lbl_semantic_review_hint, stretch=1)
        self.btn_review_semantic_candidates = QPushButton("✅ 复核候选对象")
        self.btn_review_semantic_candidates.setToolTip(
            "打开带 CAD 定位框的候选清单，可批量接受、拒绝、恢复待确认和撤销"
        )
        self.btn_review_semantic_candidates.setEnabled(False)
        self.btn_review_semantic_candidates.clicked.connect(
            self._review_semantic_candidates
        )
        semantic_review_bar.addWidget(self.btn_review_semantic_candidates)
        self.semantic_review_bar = QWidget()
        self.semantic_review_bar.setLayout(semantic_review_bar)
        self.semantic_review_bar.hide()
        layout.addWidget(self.semantic_review_bar)

        sketchup_bar = QHBoxLayout()
        self.lbl_sketchup_handoff_hint = QLabel(
            "图转 CAD 已完成；可以直接进入 SketchUp 交接，自动复用同目录的语义底图和结果。"
        )
        self.lbl_sketchup_handoff_hint.setWordWrap(True)
        self.lbl_sketchup_handoff_hint.setObjectName("MutedHint")
        sketchup_bar.addWidget(self.lbl_sketchup_handoff_hint, stretch=1)
        self.btn_continue_sketchup = QPushButton("🏙️ 继续生成 SketchUp")
        self.btn_continue_sketchup.setToolTip(
            "把本次图转 CAD 生成的 DXF 直接带入 SketchUp 交接页；不会覆盖原图或原始 DXF。"
        )
        self.btn_continue_sketchup.setEnabled(False)
        self.btn_continue_sketchup.clicked.connect(self._request_sketchup_handoff)
        sketchup_bar.addWidget(self.btn_continue_sketchup)
        self.sketchup_handoff_bar = QWidget()
        self.sketchup_handoff_bar.setLayout(sketchup_bar)
        self.sketchup_handoff_bar.hide()
        layout.addWidget(self.sketchup_handoff_bar)

        self.continuation_bar = QFrame()
        self.continuation_bar.setObjectName("ContinuationBar")
        continuation_layout = QHBoxLayout(self.continuation_bar)
        continuation_layout.setContentsMargins(10, 6, 8, 6)
        continuation_layout.setSpacing(8)
        self.continuation_label = QLabel()
        self.continuation_label.setObjectName("ContinuationLabel")
        self.continuation_label.setWordWrap(True)
        continuation_layout.addWidget(self.continuation_label, stretch=1)
        self.btn_use_working_dxf = QPushButton("➡️ 用作下一步工作图")
        self.btn_use_working_dxf.setToolTip(
            "确认后把这个新 DXF 载入顶部输入框并重新执行无损预检查；不会删除或覆盖原图"
        )
        self.btn_use_working_dxf.clicked.connect(self._request_working_dxf)
        continuation_layout.addWidget(self.btn_use_working_dxf)
        self.continuation_bar.hide()
        layout.addWidget(self.continuation_bar)

        self.last_output_dir = None
        self.last_dxf_path = None
        self.last_result: Optional[Dict[str, Any]] = None
        self.last_task_name = ""
        self._repair_comparison_dialog = None
        self._continuation_path = ""
        self._continuation_task_type = ""

    def _create_kpi_mini_card(self, label: str, val: str, icon: str) -> QFrame:
        card = QFrame()
        card.setObjectName("KpiCard")
        l = QVBoxLayout(card)
        l.setContentsMargins(6, 4, 6, 4)
        l.setSpacing(1)

        lbl_t = QLabel(f"{icon} {label}")
        lbl_t.setObjectName("KpiLabel")
        lbl_v = QLabel(val)
        lbl_v.setObjectName("KpiValue")

        l.addWidget(lbl_t)
        l.addWidget(lbl_v)
        card.val_label = lbl_v
        card.title_label = lbl_t
        return card

    def start_task(self, task_name: str, dxf_path: Optional[str] = None):
        """记录任务开始状态并重置 UI。"""
        self.last_dxf_path = dxf_path
        self.lbl_status_badge.setText("正在计算中...")
        self.lbl_status_badge.setObjectName("BadgeWarning")
        self.lbl_status_badge.setStyle(self.lbl_status_badge.style())

        self.progress_bar.setValue(10)
        self.lbl_quality_review.hide()
        self.lbl_warning_banner.hide()
        self.table.setRowCount(0)
        self.file_list.clear()
        self.last_output_dir = None
        self.last_result = None
        self.last_task_name = task_name
        self.btn_assignment_package.setEnabled(False)
        self.btn_result_export.setEnabled(False)
        self.btn_repair_compare.setEnabled(False)
        self.btn_edit_road_guide.setEnabled(False)
        self.road_repair_bar.hide()
        self.btn_review_semantic_candidates.setEnabled(False)
        self.semantic_review_bar.hide()
        self.btn_continue_sketchup.setEnabled(False)
        self.sketchup_handoff_bar.hide()
        self.btn_curate_cad.setEnabled(False)
        self.btn_use_working_dxf.setText("➡️ 用作下一步工作图")
        self.continuation_bar.hide()
        self._continuation_path = ""
        self._continuation_task_type = ""
        
        self.kpi_parcels.val_label.setText("-")
        self.kpi_area.val_label.setText("-")
        self.kpi_far.val_label.setText("-")
        self.kpi_setback.val_label.setText("-")

        self.kpi_parcels.title_label.setText("📍 有效地块")
        self.kpi_area.title_label.setText("📐 有效总面积")
        self.kpi_far.title_label.setText("🏢 容积率 (FAR)")
        self.kpi_setback.title_label.setText("🛡️ 退线合规率")

        self.append_log(f"<span style='color:#7189AA;'><b>=== 任务启动: {task_name} ===</b></span>")

        # 若提供了 DXF 路径，更新 2D 画布
        if dxf_path and Path(dxf_path).exists():
            self.canvas.load_dxf_preview(dxf_path)

    def update_progress(self, val: int, msg: str):
        """更新进度条与控制台日志。"""
        self.progress_bar.setValue(val)
        self.append_log(f"<span style='color:#74766F;'>[{val}%] {msg}</span>")

    def show_result(self, res: Dict[str, Any]):
        """根据任务返回的摘要字典，填充结果表格、KPI 卡片与文件列表。"""
        self.progress_bar.setValue(100)
        self.lbl_status_badge.setText("✓ 成功完成")
        self.lbl_status_badge.setObjectName("BadgeSuccess")
        self.lbl_status_badge.setStyle(self.lbl_status_badge.style())

        task_type = res.get("task_type")
        source_sha256 = res.get("source_sha256")
        if source_sha256:
            self.append_log(
                f"<span style='color:#74766F;'>输入文件 SHA-256：{source_sha256}</span>"
            )

        # 填充文件列表
        out_files = res.get("output_files", [])
        for label, fpath in out_files:
            item = QListWidgetItem(f"{label}: {fpath}")
            item.setData(Qt.UserRole, fpath)
            self.file_list.addItem(item)
            if not self.last_output_dir:
                self.last_output_dir = str(Path(fpath).parent)
        self.last_result = dict(res)
        candidate = continuation_dxf_candidate(res)
        if task_type in REVIEW_CONTINUATION_TASKS and candidate:
            candidate_path = Path(candidate)
            self._continuation_path = str(candidate_path)
            self._continuation_task_type = str(task_type)
            candidate_ready = candidate_path.is_file() and candidate_path.suffix.lower() == ".dxf"
            self.continuation_label.setText(
                f"✅ 已生成可继续处理的新 DXF：{candidate_path.name}。"
                "请先查看结果；确认后可一键接入下一步骤。"
            )
            self.btn_use_working_dxf.setEnabled(candidate_ready)
            self.continuation_bar.show()
        card_path = res.get("knowledge_card", {}).get("card_path", "")
        self.btn_curate_cad.setEnabled(bool(card_path) and Path(card_path).is_file())
        self.btn_assignment_package.setEnabled(bool(out_files))
        self.btn_result_export.setEnabled(bool(out_files))
        road_repair_available = (
            task_type == "image_to_dxf"
            and bool(res.get("semantic_guide_template_file"))
            and bool(res.get("source_file"))
            and Path(str(res.get("semantic_guide_template_file"))).is_file()
            and Path(str(res.get("source_file"))).is_file()
        )
        self.btn_edit_road_guide.setEnabled(road_repair_available)
        self.road_repair_bar.setVisible(road_repair_available)
        semantic_scene_path = str(res.get("semantic_scene_file", "") or "").strip()
        semantic_review_available = (
            task_type == "image_to_dxf"
            and bool(semantic_scene_path)
            and Path(semantic_scene_path).is_file()
            and bool(str(res.get("dxf_file", "") or "").strip())
            and Path(str(res.get("dxf_file", ""))).is_file()
        )
        semantic_summary = res.get("semantic_scene_summary", {})
        if not isinstance(semantic_summary, dict):
            semantic_summary = {}
        self.lbl_semantic_review_hint.setText(
            "候选复核："
            f"已接受 {int(semantic_summary.get('accepted_count', 0) or 0)}，"
            f"已拒绝 {int(semantic_summary.get('rejected_count', 0) or 0)}，"
            f"待确认 {int(semantic_summary.get('review_required_count', 0) or 0)}。"
            "拒绝项不会从 DXF 删除。"
        )
        self.btn_review_semantic_candidates.setEnabled(semantic_review_available)
        self.semantic_review_bar.setVisible(semantic_review_available)

        sketchup_dxf = str(res.get("dxf_file", "") or "").strip()
        if not sketchup_dxf:
            for _label, candidate in out_files:
                if str(candidate).lower().endswith(".dxf"):
                    sketchup_dxf = str(candidate)
                    break
        sketchup_available = (
            task_type == "image_to_dxf"
            and bool(sketchup_dxf)
            and Path(sketchup_dxf).is_file()
        )
        centerline_count = int(res.get("road_centerline_candidate_count", 0) or 0)
        centerline_review_count = int(
            res.get("road_centerline_review_required_count", 0) or 0
        )
        if sketchup_available:
            self.lbl_sketchup_handoff_hint.setText(
                "图转 CAD 已完成；可直接进入 SketchUp 交接。"
                + (
                    f" 已发现 {centerline_count} 条道路中心线候选，其中 {centerline_review_count} 条需复核；进入后会按可信度安全生成道路带。"
                    if centerline_count
                    else " 生成的语义底图和原图会继续绑定。"
                )
            )
        self.btn_continue_sketchup.setEnabled(sketchup_available)
        self.sketchup_handoff_bar.setVisible(sketchup_available)

        if task_type == "parcel":
            self._display_parcel_result(res)
        elif task_type == "indicator":
            self._display_indicator_result(res)
        elif task_type == "validate":
            self._display_validate_result(res)
        elif task_type in ("gis_export", "gis_import"):
            self._display_gis_result(res)
        elif task_type == "batch":
            self._display_batch_result(res)
        elif task_type == "concept_plan":
            self._display_concept_result(res)
        elif task_type == "layer_standardize":
            self._display_layer_result(res)
        elif task_type == "quality_check":
            self._display_quality_result(res)
        elif task_type == "image_to_dxf":
            self._display_image_to_dxf_result(res)
        elif task_type == "dwg_convert":
            self._display_dwg_result(res)
        elif task_type == "sketchup_export":
            self._display_sketchup_result(res)

        self._display_quality_baseline(res)

        self.append_log("<span style='color:#607A6A;'><b>=== 任务成功完成 ===</b></span>")

    def _display_quality_baseline(self, res: Dict[str, Any]):
        baseline = res.get("quality_baseline", {})
        if not isinstance(baseline, dict) or not baseline.get("status"):
            self.lbl_quality_review.hide()
            return

        status = str(baseline.get("status"))
        passed = int(baseline.get("passed_count", 0) or 0)
        review = int(baseline.get("review_count", 0) or 0)
        blocked = int(baseline.get("blocked_count", 0) or 0)
        gate_count = int(baseline.get("gate_count", 0) or 0)
        review_items = [
            item
            for item in baseline.get("review_items", [])
            if isinstance(item, dict)
        ]
        priority_labels = [
            str(item.get("label", "")).strip()
            for item in review_items
            if str(item.get("label", "")).strip()
        ]
        priority_text = "、".join(priority_labels[:3])
        if len(priority_labels) > 3:
            priority_text += f"等 {len(priority_labels)} 项"

        palette = {
            "blocked": ("🛑 质量关卡已阻断", "#F4DDDA", "#9B5C57", "#D6A19A"),
            "review_required": ("⚠️ 质量关卡需人工复核", "#F4E9D3", "#8B6B3F", "#D8B781"),
            "concept_ready": ("✅ 质量关卡通过，可继续概念流程", "#E3EEE8", "#557665", "#AAC6B5"),
        }
        headline, background, foreground, border = palette.get(
            status, palette["review_required"]
        )
        next_step = {
            "blocked": "请先修复阻断项，再进入下一步骤。",
            "review_required": "可以继续概念流程，但提交或量算前必须人工复核。",
            "concept_ready": "仍请在提交前抽查原图、比例和主要对象。",
        }.get(status, "请完成人工复核。")
        detail = f"通过 {passed}/{gate_count}，需复核 {review}，阻断 {blocked}。"
        if priority_text:
            detail += f" 优先检查：{priority_text}。"
        if baseline.get("review_path"):
            detail += " 双击下方“中文质量复核清单”可查看逐项操作。"
        self.lbl_quality_review.setText(f"{headline}｜{detail}{next_step}")
        self.lbl_quality_review.setStyleSheet(
            f"background-color: {background}; color: {foreground}; "
            f"border: 1px solid {border}; border-radius: 7px; "
            "padding: 7px 10px; font-weight: 700;"
        )
        self.lbl_quality_review.show()

        badge_text, badge_style = {
            "blocked": ("完成 · 结果已阻断", "BadgeError"),
            "review_required": ("完成 · 需人工复核", "BadgeWarning"),
            "concept_ready": ("完成 · 概念流程可继续", "BadgeSuccess"),
        }.get(status, ("完成 · 需人工复核", "BadgeWarning"))
        self.lbl_status_badge.setText(badge_text)
        self.lbl_status_badge.setObjectName(badge_style)
        self.lbl_status_badge.setStyle(self.lbl_status_badge.style())

        row = 0
        self.table.insertRow(row)
        values = (
            "全链路质量关卡",
            headline.replace("🛑 ", "").replace("⚠️ ", "").replace("✅ ", ""),
            f"通过 {passed} / 复核 {review} / 阻断 {blocked}",
            f"{priority_text or '无专项问题'}；{next_step}",
        )
        background_color = QColor(background)
        foreground_color = QColor(foreground)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setBackground(background_color)
            item.setForeground(foreground_color)
            self.table.setItem(row, column, item)

    def _request_working_dxf(self):
        if self._continuation_path:
            self.working_dxf_requested.emit(
                self._continuation_path, self._continuation_task_type
            )

    def _request_road_repair(self):
        if not self.last_result:
            return
        source = str(self.last_result.get("source_file", ""))
        guide = str(self.last_result.get("semantic_guide_template_file", ""))
        review_overlay = str(self.last_result.get("road_review_overlay_file", ""))
        if source and guide:
            self.road_repair_requested.emit(source, guide, review_overlay)

    def _review_semantic_candidates(self):
        if not self.last_result:
            return
        dxf_path = str(self.last_result.get("dxf_file", "") or "").strip()
        if not dxf_path or not Path(dxf_path).is_file():
            self.lbl_warning_banner.setText("🛑 找不到本次图转 CAD 的 DXF，无法打开候选复核。")
            self.lbl_warning_banner.show()
            return
        try:
            from planning_toolbox.gui.semantic_review_dialog import (
                SemanticCandidateReviewDialog,
            )

            dialog = SemanticCandidateReviewDialog(dxf_path, self)
        except Exception as exc:
            self.lbl_warning_banner.setText(f"🛑 无法打开候选复核：{exc}")
            self.lbl_warning_banner.show()
            return
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.review_result:
            return

        updated = dict(self.last_result)
        review_result = dict(dialog.review_result)
        updated["semantic_scene_file"] = review_result["path"]
        updated["semantic_scene_sha256"] = review_result["sha256"]
        updated["semantic_scene_summary"] = dict(review_result["summary"])
        try:
            from planning_toolbox.project.quality_baseline import (
                write_image_to_cad_quality_baseline,
            )

            quality_baseline = write_image_to_cad_quality_baseline(updated)
            updated["quality_baseline_file"] = quality_baseline["path"]
            updated["quality_baseline"] = quality_baseline
        except Exception as exc:
            self.lbl_warning_banner.setText(
                f"⚠️ 候选决定已保存，但质量复核清单更新失败：{exc}"
            )
            self.lbl_warning_banner.show()
            return

        self.table.setRowCount(0)
        self.file_list.clear()
        self.lbl_quality_review.hide()
        self.lbl_warning_banner.hide()
        self.show_result(updated)
        changed = int(review_result.get("changed_count", 0) or 0)
        self.append_log(
            f"<span style='color:#607A6A;'><b>候选复核已保存：</b>本次更新 {changed} 个对象；原 DXF 未修改。</span>"
        )

    def _request_sketchup_handoff(self):
        if not self.last_result or self.last_result.get("task_type") != "image_to_dxf":
            return
        dxf_path = str(self.last_result.get("dxf_file", "") or "").strip()
        if not dxf_path:
            for _label, candidate in self.last_result.get("output_files", []):
                if str(candidate).lower().endswith(".dxf"):
                    dxf_path = str(candidate)
                    break
        if dxf_path and Path(dxf_path).is_file():
            self.sketchup_handoff_requested.emit(
                dxf_path,
                int(self.last_result.get("road_centerline_candidate_count", 0) or 0),
                int(
                    self.last_result.get(
                        "road_centerline_review_required_count", 0
                    )
                    or 0
                ),
            )

    def mark_working_dxf_adopted(self, path: str):
        """Show an explicit confirmation after the main workbench adopts a DXF."""
        adopted = Path(path)
        if self._continuation_path and adopted == Path(self._continuation_path):
            self.continuation_label.setText(
                f"✅ 当前工作图已切换为：{adopted.name}。系统正在重新执行无损预检查。"
            )
            self.btn_use_working_dxf.setText("已采用")
            self.btn_use_working_dxf.setEnabled(False)

    def restore_project_result(self, task_name: str, result: Dict[str, Any]):
        """Restore a saved result record without rerunning the analysis."""
        source_file = result.get("source_file")
        self.start_task(task_name, source_file if source_file and Path(source_file).exists() else None)
        self.show_result(result)
        self.append_log("<span style='color:#7189AA;'><b>已从作业项目恢复最近一次结果记录，未重新计算。</b></span>")

    def show_error(self, title: str, message: str):
        """任务失败处理。"""
        self.progress_bar.setValue(0)
        self.lbl_status_badge.setText("✗ 任务中断/失败")
        self.lbl_status_badge.setObjectName("BadgeError")
        self.lbl_status_badge.setStyle(self.lbl_status_badge.style())

        self.lbl_warning_banner.setText(f"🛑 {title}:\n{message}")
        self.lbl_warning_banner.show()
        self.append_log(f"<span style='color:#A96761;'><b>[ERROR] {title}: {message}</b></span>")

    def append_log(self, html_text: str):
        self.log_edit.append(html_text)
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)

    # ─── 格式化表格渲染与 KPI 更新 ───

    def _display_parcel_result(self, res: Dict[str, Any]):
        self.kpi_parcels.val_label.setText(f"{res['valid_count']} 个")
        self.kpi_area.val_label.setText(f"{res['total_ha']:.4f} ha")
        self.kpi_far.val_label.setText("-")
        self.kpi_setback.val_label.setText("-")

        self.table.setRowCount(4)
        items = [
            ("有效地块数量", f"{res['valid_count']} 个", f"总面积: {res['total_ha']:.4f} ha ({res['total_m2']:,.2f} m²)", "通过闭合几何校验"),
            ("未闭合多段线", f"{res['open_count']} 个", "-", "已排除计算" if res['open_count'] > 0 else "无"),
            ("无效/自交几何", f"{res['invalid_count']} 个", "-", "已排除计算" if res['invalid_count'] > 0 else "无"),
            ("嵌套环/孔洞歧义", f"{res['nested_count']} 组", "-", "已暂停计入总面积，待人工确认")
        ]

        for row, (c0, c1, c2, c3) in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(c0))
            self.table.setItem(row, 1, QTableWidgetItem(c1))
            self.table.setItem(row, 2, QTableWidgetItem(c2))
            self.table.setItem(row, 3, QTableWidgetItem(c3))

        if res['nested_count'] > 0:
            self.lbl_warning_banner.setText(
                "⚠️ 发现可能的孔洞或嵌套地块。系统已自动暂停计入该部分面积，请人工确认。"
            )
            self.lbl_warning_banner.show()

    def _display_indicator_result(self, res: Dict[str, Any]):
        indicators = res.get("indicators", [])
        self.kpi_parcels.val_label.setText(f"{len(indicators)} 个")
        
        total_site = sum(i.get("site_area_ha", 0) for i in indicators)
        self.kpi_area.val_label.setText(f"{total_site:.4f} ha")

        fars = [i.get("far", 0) for i in indicators if i.get("far") is not None]
        if fars:
            min_f, max_f = min(fars), max(fars)
            self.kpi_far.val_label.setText(f"{min_f:.2f} ~ {max_f:.2f}" if min_f != max_f else f"{min_f:.2f}")
        else:
            self.kpi_far.val_label.setText("-")

        self.kpi_setback.val_label.setText("-")

        self.table.setRowCount(len(indicators))
        for row, ind in enumerate(indicators):
            pid = ind.get("parcel_id", f"P{row+1:03d}")
            site_area = f"{ind.get('site_area_m2', 0):,.2f} m² ({ind.get('site_area_ha', 0):.4f} ha)"
            metrics = f"FAR: {ind.get('far', 0):.2f} | 密度: {ind.get('building_density_pct', 0):.2f}% | 绿地率: {ind.get('green_ratio_pct', 0):.2f}%"
            detail = f"基底: {ind.get('building_footprint_m2', 0):,.1f}m² | 绿地: {ind.get('green_area_m2', 0):,.1f}m² | 楼层: {res.get('floors')}层"

            self.table.setItem(row, 0, QTableWidgetItem(pid))
            self.table.setItem(row, 1, QTableWidgetItem(site_area))
            self.table.setItem(row, 2, QTableWidgetItem(metrics))
            self.table.setItem(row, 3, QTableWidgetItem(detail))

    def _display_validate_result(self, res: Dict[str, Any]):
        setback_res = res.get("setback_results", [])
        compliant_n = sum(1 for s in setback_res if s.get("status") == "COMPLIANT")
        total_s = len(setback_res)

        self.kpi_parcels.val_label.setText(f"{res['valid_count']} 个")
        self.kpi_area.val_label.setText("-")
        self.kpi_far.val_label.setText("-")
        
        if total_s > 0:
            rate = (compliant_n / total_s) * 100
            self.kpi_setback.val_label.setText(f"{rate:.0f}% ({compliant_n}/{total_s})")
        else:
            self.kpi_setback.val_label.setText("-")

        self.table.setRowCount(len(setback_res) + 1)
        self.table.setItem(0, 0, QTableWidgetItem("拓扑总览"))
        self.table.setItem(0, 1, QTableWidgetItem(f"有效闭合: {res['valid_count']}"))
        self.table.setItem(0, 2, QTableWidgetItem(f"未闭合: {res['open_count']} | 自交: {res['invalid_count']}"))
        self.table.setItem(0, 3, QTableWidgetItem(f"扫描多段线总数: {res['scanned_polylines']}"))

        for row, s in enumerate(setback_res, start=1):
            pid = s.get("parcel_id")
            st = s.get("status")
            status_cn = {"COMPLIANT": "[合规]", "VIOLATION": "[违规]", "NO_BUILDING": "[无建筑]"}.get(st, st)
            metrics = f"要求: ≥{res['setback_m']}m | 最近: {s.get('min_distance_m', 0):.2f}m"
            err = s.get("error_message", "")

            item_status = QTableWidgetItem(status_cn)
            if st == "COMPLIANT":
                item_status.setForeground(QColor("#607A6A"))
            elif st == "VIOLATION":
                item_status.setForeground(QColor("#A96761"))
            elif st == "NO_BUILDING":
                item_status.setForeground(QColor("#A6814D"))

            self.table.setItem(row, 0, QTableWidgetItem(pid))
            self.table.setItem(row, 1, item_status)
            self.table.setItem(row, 2, QTableWidgetItem(metrics))
            self.table.setItem(row, 3, QTableWidgetItem(err))

    def _display_gis_result(self, res: Dict[str, Any]):
        task_type = res.get("task_type")
        self.table.setRowCount(1)

        if task_type == "gis_export":
            self.kpi_parcels.val_label.setText(f"{res['parcels_count']} 个")
            is_gpkg = res.get("output_format") == "gpkg"
            self.table.setItem(0, 0, QTableWidgetItem("GeoPackage 导出" if is_gpkg else "GeoJSON 导出"))
            self.table.setItem(0, 1, QTableWidgetItem(f"包含地块数: {res['parcels_count']}"))
            self.table.setItem(
                0,
                2,
                QTableWidgetItem(
                    f"格式: {'GeoPackage + 空间索引' if is_gpkg else 'GeoJSON'} | "
                    f"适配器: {res.get('conversion_adapter', '内置')} | 坐标: {res.get('project_crs', '未设置')}"
                ),
            )
            self.table.setItem(0, 3, QTableWidgetItem(res.get("crs_warning", "")))
        else:
            self.kpi_parcels.val_label.setText(f"{res['imported_polygons']} 个")
            source_format = str(res.get("source_format", "geojson")).upper()
            transformation = str(res.get("geographic_transformation", "")).strip()
            transformation_note = f" | 地理转换: {transformation}" if transformation else ""
            self.table.setItem(0, 0, QTableWidgetItem(f"{source_format} 导入 CAD"))
            self.table.setItem(0, 1, QTableWidgetItem(f"已导入多边形: {res['imported_polygons']}"))
            self.table.setItem(0, 2, QTableWidgetItem(f"跳过不支持类型: {res['skipped_unsupported']}"))
            self.table.setItem(
                0,
                3,
                QTableWidgetItem(
                    f"已生成 LWPOLYLINE | 适配器: {res.get('conversion_adapter', '内置')} | "
                    f"坐标: {res.get('project_crs', '未设置')}{transformation_note}"
                )
            )

    def _display_batch_result(self, res: Dict[str, Any]):
        items = res.get("items", [])
        self.kpi_parcels.val_label.setText(
            f"{res.get('success_count', 0)}/{res.get('processed_count', 0)}"
        )
        self.kpi_area.val_label.setText(
            f"{sum(item.get('total_ha', 0.0) for item in items if item.get('status') == 'SUCCESS'):.4f} ha"
        )
        self.kpi_far.val_label.setText("批量")
        self.kpi_setback.val_label.setText(
            f"失败 {res.get('failed_count', 0)}"
        )

        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            source_name = Path(item.get("source_file", "")).name
            status = "成功" if item.get("status") == "SUCCESS" else "失败"
            detail = item.get("message", "") or item.get("report_file", "")
            self.table.setItem(row, 0, QTableWidgetItem(source_name))
            self.table.setItem(row, 1, QTableWidgetItem(status))
            self.table.setItem(
                row, 2, QTableWidgetItem(f"有效地块: {item.get('valid_count', 0)}")
            )
            self.table.setItem(row, 3, QTableWidgetItem(detail))

    def _display_concept_result(self, res: Dict[str, Any]):
        parcels = res.get("parcels_count", 0)
        footprint_m2 = res.get("building_footprint_m2", 0.0)
        gfa_m2 = res.get("estimated_gfa_m2")
        parcel_area_m2 = res.get("parcel_area_m2", 0.0)
        parking_required = res.get("parking_required", 0)
        parking_generated = res.get("parking_generated", 0)
        parking_unplaced = res.get("parking_unplaced", 0)

        self.kpi_parcels.title_label.setText("📍 概念地块")
        self.kpi_area.title_label.setText("📐 概念总建面" if gfa_m2 is not None else "📐 建筑基底")
        self.kpi_far.title_label.setText("🏢 估算 FAR")
        self.kpi_setback.title_label.setText("🅿️ 概念车位")
        self.kpi_parcels.val_label.setText(f"{parcels} 个")
        self.kpi_area.val_label.setText(
            f"{gfa_m2:,.0f} m²" if gfa_m2 is not None else f"{footprint_m2:,.0f} m²"
        )
        if gfa_m2 is not None and parcel_area_m2 > 0:
            self.kpi_far.val_label.setText(f"{gfa_m2 / parcel_area_m2:.2f}")
        else:
            self.kpi_far.val_label.setText("未估算")
        if res.get("parking_ratio") is not None:
            self.kpi_setback.val_label.setText(f"{parking_generated}/{parking_required}")
        else:
            self.kpi_setback.val_label.setText("未估算")

        rows = [
            ("有效地块", f"{parcels} 个", "已读取有效闭合 PARCEL", ""),
            ("建筑轮廓", f"{res.get('building_footprints', 0)} 栋", "已写入 CONCEPT_BUILDING 图层", f"基底面积约 {footprint_m2:,.2f} m²"),
            ("概念总建筑面积", f"{gfa_m2:,.2f} m²" if gfa_m2 is not None else "未估算", "需要明确填写楼层数", "仅为方案研究估算"),
            ("概念停车位", f"{parking_generated}/{parking_required} 个", "已写入 CONCEPT_PARKING 图层" if parking_required else "未填写停车配比", f"未放置 {parking_unplaced} 个" if parking_unplaced else "全部尝试放置"),
            ("绿地轮廓", f"{res.get('green_polygons', 0)} 块", "已写入 CONCEPT_GREEN 图层", f"面积约 {res.get('green_area_m2', 0.0):,.2f} m²"),
            ("实际建筑覆盖率", f"{res.get('actual_coverage_ratio', 0.0) * 100:.2f}%", "由生成建筑基底面积反算", "可能低于目标值，表示可用空间不足或受间距约束"),
            ("最小生成退线", f"{res.get('minimum_setback_m', 0.0):.2f} m" if res.get('minimum_setback_m') is not None else "无建筑", "建筑到地块边界的最小距离", "用于结果核对"),
            ("最小生成建筑间距", f"{res.get('minimum_building_gap_m', 0.0):.2f} m" if res.get('minimum_building_gap_m') is not None else "单栋或未生成", "建筑之间的最小边界距离", "用于结果核对"),
            ("概念道路/消防通道", f"{res.get('access_width_m', 0.0):.2f} m", "已写入 CONCEPT_ROAD 图层" if res.get('access_width_m', 0.0) > 0 else "未生成", f"面积约 {res.get('access_corridor_m2', 0.0):,.2f} m²"),
            ("布局风格", "自然曲线" if res.get("layout_style", "organic") == "organic" else "简洁矩形", "圆角建筑与弧形通行引导" if res.get("layout_style", "organic") == "organic" else "规整矩形示意", "可在任务参数中切换"),
            ("规范依据框架", res.get('standards_profile_name', '自定义/地方条件'), "已写入概念方案报告", "不是自动合规结论，请核对最新版地方要求"),
            ("参考标准", "；".join(res.get('standards_references', ())), "仅作学习和核对索引", "不替代正式标准文本"),
            ("单位", str(res.get('unit_name', '')), "生成过程使用的 CAD 单位", ""),
            ("用途边界", "概念草图", "请在 CAD 中人工调整，不作为审批成果", ""),
        ]
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.lbl_warning_banner.setText(
            "🧩 已生成参数化概念方案草图。道路/消防通道、停车位、总建面和 FAR 都是输入参数下的学习估算；请继续核对道路连通性、消防、日照、规范条件和实际设计意图。"
        )
        if parking_unplaced > 0:
            self.lbl_warning_banner.setText(
                f"⚠️ 概念停车位有 {parking_unplaced} 个未能放入可用范围。请在 CAD 中重新组织道路、停车和建筑布局；结果不代表停车配建合规。"
            )
        self.lbl_warning_banner.show()

    def _display_layer_result(self, res: Dict[str, Any]):
        remapped_counts = res.get("remapped_counts", {})
        unmapped_layers = res.get("unmapped_layers", [])
        compliance = res.get("drafting_compliance", {})
        compliance_warnings = compliance.get("warnings", [])
        compliance_blockers = compliance.get("blockers", [])
        self.kpi_parcels.title_label.setText("🧹 已映射图元")
        self.kpi_parcels.val_label.setText(str(res.get("remapped_total", 0)))
        self.kpi_area.title_label.setText("📚 标准图层")
        self.kpi_area.val_label.setText(str(len(remapped_counts)))
        self.kpi_far.title_label.setText("⚠️ 待确认项")
        self.kpi_far.val_label.setText(
            str(len(unmapped_layers) + len(compliance_warnings) + len(compliance_blockers))
        )
        self.kpi_setback.title_label.setText("🛡️ 原图保护")
        self.kpi_setback.val_label.setText("通过")

        profile_name = res.get("drafting_profile_name", "基础图层配置")
        reference_codes = "；".join(
            str(item.get("code", "")) for item in res.get("drafting_references", [])
        )
        status_labels = {
            "pass": "辅助检查通过",
            "review_required": "需要人工确认",
            "blocked": "存在阻断项",
        }
        compliance_status = compliance.get("status", "未启用")
        rows = [
            ("标准化图元总数", str(res.get("remapped_total", 0)), "已映射到标准图层", "输出为新 DXF，不覆盖原始文件"),
            ("标准图层映射", "；".join(f"{key}: {value}" for key, value in remapped_counts.items()), "各标准图层的映射数量", "可在图层检查报告中复核"),
            ("未识别图层", str(len(unmapped_layers)), "；".join(unmapped_layers) or "无", "自定义图层会保留，不会被删除"),
            ("中国制图模板", profile_name, reference_codes or "未启用", "只作学习辅助，不等于法定审查"),
            (
                "辅助检查结论",
                status_labels.get(compliance_status, compliance_status),
                f"阻断 {len(compliance_blockers)} 项；待确认 {len(compliance_warnings)} 项",
                "请打开中国制图辅助检查报告逐项查看",
            ),
            ("安全校验", "原始 DXF SHA-256 已复核", "只读保护", str(res.get("source_sha256", ""))),
        ]
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        if compliance_blockers:
            self.lbl_warning_banner.setText(
                f"🛑 中国制图辅助检查发现 {len(compliance_blockers)} 个阻断项。"
                "标准化副本已经生成，但不要用于尺寸或面积判断，请先打开检查报告处理单位等问题。"
            )
        elif compliance_warnings or unmapped_layers:
            self.lbl_warning_banner.setText(
                "⚠️ 标准化完成，但仍有需要人工确认的空图层、自定义图层、坐标或地方要求。"
                "这表示图纸更整齐，不表示已经通过国标或审批审查。"
            )
        else:
            self.lbl_warning_banner.setText(
                "✅ 所选中国制图辅助模板的机器可检查项已经通过。仍请核对最新版标准文本、课程任务书和地方规划条件。"
            )
        self.lbl_warning_banner.show()

    def _display_quality_result(self, res: Dict[str, Any]):
        repair = res.get("repair", {})
        self.btn_repair_compare.setEnabled(
            bool(res.get("source_file")) and bool(repair.get("output_file"))
        )
        complex_counts = res.get("complex_entity_counts", {})
        empty_layers = res.get("empty_layers", [])
        scale_warnings = res.get("scale_warnings", [])
        block_refs = res.get("block_reference_counts", {})
        unresolved_blocks = res.get("unresolved_block_references", [])
        external_refs = res.get("external_reference_names", [])
        self.kpi_parcels.title_label.setText("🧩 合并碎线组")
        self.kpi_parcels.val_label.setText(str(repair.get("merged_fragment_groups", 0)))
        self.kpi_area.title_label.setText("📉 减少图元")
        entity_reduction = max(
            0,
            int(repair.get("source_entity_count", 0))
            - int(repair.get("output_entity_count", 0)),
        )
        self.kpi_area.val_label.setText(str(entity_reduction))
        self.kpi_far.title_label.setText("✂️ 清理顶点")
        vertex_reduction = (
            int(repair.get("removed_collinear_vertices", 0))
            + int(repair.get("removed_short_vertices", 0))
        )
        self.kpi_far.val_label.setText(str(vertex_reduction))
        self.kpi_setback.title_label.setText("🧾 修改记录")
        self.kpi_setback.val_label.setText(str(repair.get("change_count", 0)))

        rows = [
            ("精确重复图元", str(int(res.get("duplicate_count", 0)) + int(res.get("duplicate_line_count", 0))), "多段线与 LINE 候选", f"输出已删除 {int(repair.get('removed_duplicates', 0)) + int(repair.get('removed_duplicate_lines', 0))} 条"),
            ("未闭合多段线", str(res.get("open_count", 0)), f"其中近闭合 {res.get('near_closed_count', 0)} 条", f"输出已闭合 {repair.get('closed_polylines', 0)} 条"),
            ("散线与开放轮廓", str(res.get("straight_fragment_count", 0)), "只合并同图层、同线型、无分叉链", f"{repair.get('merged_source_entities', 0)} 个碎片合并为 {repair.get('merged_fragment_groups', 0)} 条"),
            ("共线/极短冗余点", str(vertex_reduction), f"共线 {repair.get('removed_collinear_vertices', 0)}；极短 {repair.get('removed_short_vertices', 0)}", f"简化 {repair.get('simplified_polylines', 0)} 条多段线"),
            ("语义图层整理", str(repair.get("standardized_layer_count", 0)), "按内置中英文别名映射", "无法识别的自定义图层保持原样"),
            ("分叉碎线组", str(repair.get("branching_components_skipped", 0)), "为避免改变道路/管线连接关系，系统主动跳过", "请在 CAD 中人工判断"),
            ("自交候选", str(res.get("self_intersection_count", 0)), "可能影响面积和拓扑计算", "请在 CAD 中定位并人工确认"),
            ("空图层", str(len(empty_layers)), "；".join(empty_layers) or "无", "空图层不会自动删除"),
            ("复杂 CAD 图元", str(complex_counts) if complex_counts else "无", "已统计 LINE/ARC/CIRCLE/ELLIPSE/SPLINE/INSERT 等", "复杂图元暂不参与地块面积计算"),
            ("块参照与外部参照", str(sum(block_refs.values())), f"块：{block_refs or '无'}；XREF：{external_refs or '无'}", f"无法解析块：{unresolved_blocks or '无'}；保留原样并提示人工复核"),
            ("布局空间图元", str(res.get("paper_space_entity_count", 0)), "已纳入兼容性清点，但面积分析仅使用模型空间", "避免把图框、标题栏误计入规划指标"),
            ("异常比例/坐标", str(len(scale_warnings)), "；".join(scale_warnings) or "未发现明显异常", "请结合项目坐标系人工复核"),
        ]
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))

        warning_count = (
            int(res.get("duplicate_count", 0))
            + int(res.get("duplicate_line_count", 0))
            + int(res.get("open_count", 0))
            + int(res.get("self_intersection_count", 0))
            + int(repair.get("branching_components_skipped", 0))
            + len(empty_layers)
            + len(scale_warnings)
        )
        if warning_count:
            self.lbl_warning_banner.setText(
                f"⚠️ 质量检查仍有 {warning_count} 项需要关注。系统已生成修复副本和逐项修改 CSV；"
                "建议先查看分叉、自交与复杂图元，再继续 CAD 编辑。"
            )
        else:
            self.lbl_warning_banner.setText(
                "✅ 未发现明显重复线、断线、自交或范围异常；仍建议在 CAD 中抽查修复副本。"
            )
        self.lbl_warning_banner.show()

    def _open_repair_comparison(self):
        """Open the heavyweight visual comparison only when requested."""
        if not self.last_result or self.last_result.get("task_type") != "quality_check":
            return
        repair = self.last_result.get("repair", {})
        source_path = self.last_result.get("source_file")
        repaired_path = repair.get("output_file")
        if not source_path or not repaired_path:
            return
        from planning_toolbox.gui.repair_comparison import RepairComparisonDialog

        self._repair_comparison_dialog = RepairComparisonDialog(
            source_path,
            repaired_path,
            self.last_output_dir or Path(repaired_path).parent,
            self,
        )
        self._repair_comparison_dialog.show()
        self._repair_comparison_dialog.raise_()

    def _display_image_to_dxf_result(self, res: Dict[str, Any]):
        if res.get("conversion_mode") == "black_white_linework":
            line_count = int(res.get("line_count", 0))
            raw_line_count = int(res.get("raw_line_count", line_count))
            building_candidates = int(res.get("building_candidate_count", 0))
            tree_candidates = int(res.get("tree_candidate_count", 0))
            parking_candidates = int(res.get("parking_candidate_count", 0))
            landscape_candidates = int(res.get("landscape_candidate_count", 0))
            vertex_reduction = int(res.get("vertex_reduction", 0))
            layer_counts = res.get("line_layer_counts", {})
            reduction = max(0, raw_line_count - line_count)
            semantic_summary = res.get("semantic_scene_summary", {})
            trace_label = (
                "中心线精修"
                if res.get("trace_method") == "centerline"
                else "轮廓描边"
            )
            self.kpi_parcels.title_label.setText("CAD 对象")
            self.kpi_parcels.val_label.setText(str(line_count))
            self.kpi_area.title_label.setText("输出图层")
            self.kpi_area.val_label.setText(
                str(max(1, sum(1 for value in layer_counts.values() if int(value) > 0)))
            )
            self.kpi_far.title_label.setText("图片比例")
            self.kpi_far.val_label.setText(f"{res.get('reference_width_m', 0):g} m")
            self.kpi_setback.title_label.setText("原图保护")
            self.kpi_setback.val_label.setText("通过")

            rows = [
                (
                    "黑白线稿",
                    f"{line_count} 条 CAD 线",
                    f"阈值 {res.get('line_threshold', 0)}",
                    f"{trace_label} · 自动整理{'开启' if res.get('optimization_enabled') else '关闭'}",
                ),
                (
                    "自动整理",
                    f"原始 {raw_line_count} 条",
                    f"减少 {reduction} 条",
                    f"建筑候选 {building_candidates} 个",
                ),
                (
                    "重复图元",
                    f"树木块 {tree_candidates} 个",
                    f"停车位块 {parking_candidates} 个",
                    f"减少多段线顶点 {vertex_reduction} 个",
                ),
                (
                    "底色与曲线",
                    "黑底白线" if res.get("line_polarity_detected") == "light_on_dark" else "白底黑线",
                    f"景观椭圆 {landscape_candidates} 个",
                    "底色自动判断" if res.get("line_polarity_requested") == "auto" else "底色手动指定",
                ),
                (
                    "识别参数",
                    f"宽度 {res.get('reference_width_m', 0):g} m",
                    f"最小区域 {res.get('min_component_pixels', 0)} 像素",
                    "请在 CAD 中检查断线和噪点",
                ),
                (
                    "知识库辅助",
                    (
                        f"匹配 {res.get('knowledge_assist', {}).get('curated_cad_count', 0)} 份精修 CAD"
                        if res.get("knowledge_assist", {}).get("profile_found")
                        else (
                            "请先选择图纸类型"
                            if res.get("knowledge_assist", {}).get("disabled_reason") == "project_type_required"
                            else "暂无可用精修样本"
                        )
                    ),
                    f"校正 {res.get('knowledge_assist', {}).get('adjustment_count', 0)} 个规则图元",
                    "只使用 user_curated 样本；大差异对象保持原样",
                ),
            ]
            if res.get("semantic_scene_file"):
                rows.append(
                    (
                        "全链路语义交接",
                        f"候选对象 {semantic_summary.get('semantic_object_count', 0)} 个",
                        f"接受 {semantic_summary.get('accepted_count', 0)} / 拒绝 {semantic_summary.get('rejected_count', 0)} / 待复核 {semantic_summary.get('review_required_count', 0)}",
                        f"参考底图 {semantic_summary.get('underlay_entity_count', 0)} 条；会随修复和标准化继续传递",
                    )
                )
            if res.get("semantic_guide_template_file"):
                prefill = res.get("semantic_guide_template_prefill_counts", {})
                rows.append(
                    (
                        "可编辑语义引导草稿",
                        "与原图像素尺寸完全相同",
                        (
                            f"预填建筑 {prefill.get('AI_BUILDING', 0)}、"
                            f"道路 {prefill.get('AI_ROAD', 0)}、"
                            f"绿化 {prefill.get('AI_GREEN', 0)}"
                        ),
                        "补涂遗漏道路后，用“原图 + 彩色语义引导图”重新运行",
                    )
                )
            alignment_quality = res.get("alignment_quality", {})
            if alignment_quality:
                building_quality = alignment_quality.get("building", {})
                road_quality = alignment_quality.get("road", {})
                quality_status = (
                    "建筑/道路候选均贴合原图边界"
                    if building_quality.get("status") == "aligned"
                    and road_quality.get("status") in {"aligned", "no_candidates"}
                    else "道路或建筑候选存在边界偏差，建议先看叠加图"
                )
                rows.append(
                    (
                        "原图边界对齐",
                        f"建筑均值 {building_quality.get('mean_boundary_distance_px', 0):g} px",
                        f"道路均值 {road_quality.get('mean_boundary_distance_px', 0):g} px；"
                        f"P90 {road_quality.get('p90_boundary_distance_px', 0):g} px",
                        quality_status,
                    )
                )
            road_centerline_count = int(res.get("road_centerline_candidate_count", 0) or 0)
            if road_centerline_count:
                suggested_width = res.get("road_centerline_width_m")
                width_profile = res.get("road_detection", {}).get(
                    "centerline_width_profile"
                )
                review_count = int(
                    res.get("road_centerline_review_required_count", 0) or 0
                )
                joined_fragment_count = int(
                    res.get("road_centerline_joined_fragment_count", 0) or 0
                )
                ready_count = max(0, road_centerline_count - review_count)
                suggested_width_text = (
                    f"建议总宽 {float(suggested_width):g} m"
                    if suggested_width not in (None, "", 0, 0.0)
                    else (
                        "各中心线保留独立宽度"
                        if width_profile == "mixed_widths"
                        else "暂无可靠宽度"
                    )
                )
                rows.append(
                    (
                        "道路中心线候选",
                        f"{road_centerline_count} 条",
                        "可接力 SketchUp 道路带",
                        f"高可信 {ready_count} 条，需复核 {review_count} 条；"
                        f"安全拼接碎段 {joined_fragment_count} 个；"
                        f"{suggested_width_text}；先看叠加图",
                    )
                )
                junction_snap_count = int(
                    res.get("road_centerline_junction_snap_count", 0) or 0
                )
                components_before = int(
                    res.get(
                        "road_centerline_network_component_count_before", 0
                    )
                    or 0
                )
                components_after = int(
                    res.get(
                        "road_centerline_network_component_count_after", 0
                    )
                    or 0
                )
                rows.append(
                    (
                        "可信道路网络连续性",
                        f"安全吸附路口 {junction_snap_count} 处",
                        f"网络块 {components_before} → {components_after}",
                        f"最大端点移动 {float(res.get('road_centerline_maximum_junction_snap_distance_m', 0) or 0):g} m；歧义路口保持原样",
                    )
                )
            rows.append(
                (
                    "CAD 视觉分层",
                    f"浅色语义填充 {int(res.get('semantic_presentation_fill_count', 0) or 0)} 个",
                    "建筑暖红、道路灰、绿化绿、停车米黄",
                    "原始参考线保留为灰色细线；颜色、填充和候选边界均可按图层单独关闭",
                )
            )
            self.table.setRowCount(len(rows))
            for row, values in enumerate(rows):
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(str(value)))

            self.lbl_warning_banner.setText(
                "已生成并整理黑白线稿 CAD。BW_BUILDING_CANDIDATE 只是建筑候选，"
                "BW_TREE_CANDIDATE 与 BW_LANDSCAPE_CANDIDATE 也是几何候选；"
                "BW_PARKING_CANDIDATE 是重复窄矩形候选；"
                "BW_CLOSED、BW_DETAIL 和 BW_LINEWORK 不代表审批语义；"
                "已识别建筑和道路带有可关闭的低饱和浅填充，原始参考线仍以灰色细线保留；"
                "知识库只对接近精修样本的尺寸做保守校正；语义候选已写入轻量交接文件，"
                "但测量和进入 SketchUp 前仍需人工复核。"
            )
            if res.get("semantic_guide_template_file"):
                self.lbl_warning_banner.setText(
                    self.lbl_warning_banner.text()
                    + " 已生成同像素尺寸的可编辑语义引导草稿；道路不完整时只需补涂灰色范围，不必重画整张图。"
                )
            self.lbl_warning_banner.show()
            return

        counts = res.get("region_counts", {})
        areas = res.get("region_areas_m2", {})
        total_regions = sum(int(value) for value in counts.values())
        total_area = sum(float(value) for value in areas.values())

        self.kpi_parcels.title_label.setText("🧩 识别区域")
        self.kpi_parcels.val_label.setText(str(total_regions))
        self.kpi_area.title_label.setText("📐 识别面积")
        self.kpi_area.val_label.setText(f"{total_area:,.1f} m²")
        self.kpi_far.title_label.setText("🗺️ 图片比例")
        self.kpi_far.val_label.setText(f"{res.get('reference_width_m', 0):g} m")
        self.kpi_setback.title_label.setText("🔒 原图保护")
        self.kpi_setback.val_label.setText("通过")
        centerline_width = res.get("centerline_corridor_width_m")
        centerline_width_text = (
            f"{float(centerline_width):g} m"
            if centerline_width not in (None, "", 0, 0.0)
            else "知识库默认 6 m"
        )
        layer_names = {
            "AI_BUILDING": "建筑",
            "AI_ROAD": "道路",
            "AI_GREEN": "绿地",
            "AI_WATER": "水体",
            "AI_PARKING": "停车",
        }
        rows = [
            (
                layer_names.get(layer, layer),
                f"{int(counts.get(layer, 0))} 个区域",
                f"{float(areas.get(layer, 0.0)):,.1f} m²",
                "已写入同名 AI CAD 图层",
            )
            for layer in layer_names
        ]
        rows.append(
            (
                "识别参数",
                f"宽度 {res.get('reference_width_m', 0):g} m",
                f"颜色容差 {res.get('color_tolerance', 0)}",
                "像素区域已转为闭合多段线",
            )
        )
        if res.get("conversion_mode") == "semantic_guide":
            rows.append(
                (
                    "语义引导图",
                    "原图与引导图均为只读",
                    "像素尺寸已严格对齐",
                    "请先打开叠加检查 PNG，再进入 CAD / SketchUp",
                )
            )
        road_detection = res.get("semantic_road_detection", {})
        if road_detection:
            network_count = int(road_detection.get("network_component_count", 0))
            road_status = road_detection.get("status", "no_road_region")
            status_text = {
                "single_network": "已连成一个道路网络",
                "nearby_gaps_review": "发现近距离断口，建议在编辑器中补连",
                "multiple_networks_review": "存在多个网络块，请检查道路是否断开",
                "no_road_region": "未识别到道路区域",
            }.get(road_status, "请人工复核")
            rows.append(
                (
                    "道路网络检查",
                    f"道路面 {int(road_detection.get('region_count_after_gap_heal', 0))} 个",
                    f"网络块 {network_count} 个；小断口修复 {int(road_detection.get('healed_region_count', 0))} 个；近距离断口建议 {int(road_detection.get('nearby_gap_suggestion_count', 0))} 个",
                    status_text,
                )
            )
        alignment_quality = res.get("alignment_quality", {})
        if alignment_quality:
            building_quality = alignment_quality.get("building", {})
            road_quality = alignment_quality.get("road", {})
            quality_status = (
                "建筑/道路候选均贴合原图边界"
                if building_quality.get("status") == "aligned"
                and road_quality.get("status") in {"aligned", "no_candidates"}
                else "道路或建筑候选存在边界偏差，建议先看叠加图"
            )
            rows.append(
                (
                    "原图边界对齐",
                    f"建筑均值 {building_quality.get('mean_boundary_distance_px', 0):g} px",
                    f"道路均值 {road_quality.get('mean_boundary_distance_px', 0):g} px；"
                    f"P90 {road_quality.get('p90_boundary_distance_px', 0):g} px",
                    quality_status,
                )
            )
        semantic_summary = res.get("semantic_scene_summary", {})
        if res.get("semantic_scene_file"):
            rows.append(
                (
                    "全链路语义交接",
                    f"候选对象 {semantic_summary.get('semantic_object_count', 0)} 个",
                    f"接受 {semantic_summary.get('accepted_count', 0)} / 拒绝 {semantic_summary.get('rejected_count', 0)} / 待复核 {semantic_summary.get('review_required_count', 0)}",
                    f"参考底图 {semantic_summary.get('underlay_entity_count', 0)} 条；下游不再重复猜图层用途",
                )
            )
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))

        if res.get("conversion_mode") == "semantic_guide":
            self.lbl_warning_banner.setText(
                "已保留原图作为全链路底图，并用语义引导图生成 AI_* 闭合范围。"
                "请先查看原图与引导叠加检查图；颜色偏移或漏涂会原样进入 CAD。"
                "该结果仍是课程辅助，不能替代测绘、规范审查或最终设计。"
            )
        else:
            self.lbl_warning_banner.setText(
                "⚠️ 已生成分层 CAD 概念草图。该结果依赖图片颜色和比例，不能替代真实测绘、规范审查或最终设计；"
                "请在 CAD 中打开 AI_* 图层，逐项检查建筑轮廓、道路宽度、文字和比例。"
            )
        self.lbl_warning_banner.show()

    def _display_dwg_result(self, res: Dict[str, Any]):
        self.kpi_parcels.title_label.setText("📐 模型空间图元")
        self.kpi_parcels.val_label.setText(str(res.get("entity_count", 0)))
        self.kpi_area.title_label.setText("🧾 DXF 版本")
        self.kpi_area.val_label.setText(str(res.get("dxf_version", "—")))
        self.kpi_far.title_label.setText("💻 转换方式")
        self.kpi_far.val_label.setText("本机")
        self.kpi_setback.title_label.setText("🛡️ 原图保护")
        self.kpi_setback.val_label.setText("通过")
        rows = [
            ("原始 DWG", Path(str(res.get("source_file", ""))).name, "SHA-256 已复核", "未上传、未覆盖"),
            ("转换 DXF", Path(str(res.get("converted_dxf", ""))).name, str(res.get("dxf_version", "")), f"模型空间 {res.get('entity_count', 0)} 个图元"),
            ("转换组件", str(res.get("converter", "")), "仅在当前电脑本地运行", "转换后仍需检查字体、代理对象、外部参照和布局"),
        ]
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.lbl_warning_banner.setText(
            "✅ DWG 已转换为新的 DXF 并自动载入。建议先运行“图纸质量增强检查”，"
            "再核对字体、块参照、外部参照和布局空间；原始 DWG 保持不变。"
        )
        self.lbl_warning_banner.show()

    def _display_sketchup_result(self, res: Dict[str, Any]):
        """Explain the two-file SketchUp handoff in beginner-friendly terms."""
        floors = int(res.get("floors", 0))
        floor_height = float(res.get("floor_height_m", 0.0))
        source_object_count = int(res.get("object_count", 0))
        top_level_object_count = int(
            res.get("top_level_object_count", source_object_count)
        )
        centerline_width = res.get("centerline_corridor_width_m")
        centerline_width_text = (
            f"{float(centerline_width):g} m"
            if centerline_width not in (None, "", 0, 0.0)
            else "知识库默认 6 m"
        )
        centerline_policy = str(
            res.get("centerline_confidence_policy", "all") or "all"
        )
        centerline_policy_text = (
            "仅高可信生成实体"
            if centerline_policy == "trusted_only"
            else "全部候选生成实体"
        )
        self.kpi_parcels.title_label.setText("🧩 SU 顶层对象")
        self.kpi_parcels.val_label.setText(str(top_level_object_count))
        self.kpi_area.title_label.setText("🏢 建筑对象")
        self.kpi_area.val_label.setText(str(res.get("building_count", 0)))
        self.kpi_far.title_label.setText("📦 三维体量")
        override_count = int(res.get("building_override_count", 0))
        matched_override_count = int(res.get("matched_building_override_count", 0))
        unmatched_override_count = int(res.get("unmatched_building_override_count", 0))
        layer_semantics_count = int(res.get("building_layer_semantics_count", 0))
        readiness = res.get("course_model_readiness", {})
        if not isinstance(readiness, dict):
            readiness = {}
        readiness_labels = [str(value) for value in readiness.get("review_labels", [])]
        readiness_review_text = "、".join(readiness_labels) or "基础资料项均已提供"
        if override_count:
            mass_label = f"逐栋 {matched_override_count} 栋"
        elif layer_semantics_count:
            mass_label = f"图层参数 {layer_semantics_count} 栋"
        else:
            mass_label = f"{floors} 层 × {floor_height:g} m" if floors > 0 else "二维线面"
        self.kpi_far.val_label.setText(mass_label)
        self.kpi_setback.title_label.setText("🔒 原图保护")
        self.kpi_setback.val_label.setText("通过")

        rows = [
            (
                "模型交接文件",
                Path(str(res.get("handoff_file", ""))).name,
                f"{top_level_object_count} 个顶层对象",
                "在 SketchUp 插件中选择此文件",
            ),
            (
                "全链路语义",
                "已校验" if res.get("semantic_scene_validated") else "普通 CAD（无图片语义）",
                f"{res.get('underlay_source_entity_count', 0)} 条参考线 → {res.get('underlay_bundle_count', 0)} 个锁定底图组",
                f"接受 {res.get('semantic_accepted_count', 0)} / 拒绝 {res.get('semantic_rejected_count', 0)} / 待复核 {res.get('semantic_review_required_count', 0)}；源几何 {source_object_count} 个",
            ),
            (
                "导入插件",
                Path(str(res.get("plugin_file", ""))).name,
                f"{int(res.get('plugin_size_bytes', 0)) / 1024:.1f} KB",
                "只需在 SketchUp 扩展程序管理器安装一次",
            ),
            (
                "坐标交接",
                str(res.get("project_crs", "未设置")),
                "近原点" if res.get("local_origin_enabled") else "CAD 本地坐标",
                "坐标以米存储，可按项目设置反算",
            ),
            (
                "复杂图元",
                f"块分组 {res.get('block_count', 0)} 个",
                f"三维面 {res.get('surface_face_count', 0)} 个",
                f"文字标签 {res.get('text_count', 0)} 个",
            ),
            (
                "自动建模细节",
                f"程序化建筑 {res.get('procedural_building_count', 0)} 个",
                f"预计窗组件 {res.get('estimated_facade_module_count', 0)} 个",
                f"楼层辅助线 {res.get('floor_guide_segment_count', 0)} 条",
            ),
            (
                "建筑精细构件",
                f"入口/雨棚 {res.get('building_entrance_count', 0)} 组",
                f"预计阳台 {res.get('estimated_balcony_count', 0)} 个",
                f"屋顶设备 {res.get('rooftop_equipment_count', 0)} 个",
            ),
            (
                "场地与绿化",
                f"共享树木 {res.get('procedural_tree_count', 0)} 个",
                f"分层场地面 {res.get('styled_site_surface_count', 0)} 个",
                f"显式花池/遮阳 {res.get('explicit_library_symbol_count', 0)} 个",
            ),
            (
                "道路自动建模",
                f"可细化道路 {res.get('road_design_surface_count', 0)} 条",
                f"人行道 {res.get('estimated_road_sidewalk_band_count', 0)} 条 / 箭头 {res.get('estimated_road_direction_arrow_count', 0)} 个",
                f"预设 {res.get('road_design_preset', 'auto')}；弯道 {res.get('road_curved_hint_count', 0)} 条；环岛 {res.get('road_roundabout_hint_count', 0)} 条；中心线道路带 {res.get('road_centerline_corridor_hint_count', 0)} 条",
            ),
            (
                "斑马线方向校正",
                f"自动校正 {res.get('road_crossing_auto_aligned_count', 0)} 个",
                f"手动固定 {res.get('road_crossing_manual_count', 0)} 个",
                f"局部切线 {res.get('road_crossing_local_tangent_count', 0)} 个；待复核 {res.get('road_crossing_fallback_count', 0)} 个",
            ),
            (
                "道路几何可信度",
                f"中心线辅助 {res.get('road_centerline_hint_count', 0)} 条；道路带 {res.get('road_centerline_corridor_hint_count', 0)} 条",
                f"低可信保留线索 {res.get('road_centerline_corridor_suppressed_count', 0)} 条；重复道路面转复核轮廓 {res.get('road_surface_generation_suppressed_count', 0)} 个",
                f"{centerline_policy_text}；阈值 {float(res.get('centerline_confidence_threshold', 0.65)):.2f}；道路带宽度：{centerline_width_text}",
            ),
            (
                "道路全长覆盖",
                f"完整取样 {res.get('road_centerline_full_path_resampled_count', 0)} 条",
                "沿道路起点至终点均匀取样",
                "每条最多 64 个断面；长折线不截尾，控制模型体量",
            ),
            (
                "逐栋建筑参数",
                f"已保存 {override_count} 条",
                f"成功匹配 {matched_override_count} 栋",
                f"未匹配 {unmatched_override_count} 条",
            ),
            (
                "建筑图层参数接力",
                f"明确参数 {layer_semantics_count} 栋",
                f"楼层 {res.get('building_layer_floor_semantics_count', 0)} / 总高 {res.get('building_layer_total_height_semantics_count', 0)}",
                "支持如 住宅_6F_层高3.0_平屋顶；逐栋设置优先",
            ),
            (
                "课程基础模型检查",
                f"通过 {readiness.get('passed_count', 0)}/{readiness.get('item_count', 0)} 项",
                f"待完善：{readiness_review_text}",
                "只检查资料完整度，不代表课程评分或规范符合",
            ),
            (
                "轻量建模知识库",
                str(res.get("modeling_knowledge_version", "未记录")),
                f"参考来源 {res.get('modeling_knowledge_source_count', 0)} 项",
                "规则已参与建筑、场地和植被生成；不含图片、SKP 或模型权重",
            ),
            (
                "可复用组件库",
                str(res.get("component_library_version", "未记录")),
                f"精选组件 {res.get('bundled_component_count', 0)} 个 / {int(res.get('bundled_component_total_bytes', 0)) / 1024:.0f} KB",
                "CC0、离线按需加载；入口/树木/街灯自动使用，道路设施可用 PT_* 块显式放置",
            ),
            (
                "减少返工",
                "增量更新" if res.get("incremental_update") else "每次新建",
                str(res.get("building_type", "generic")),
                "在 SketchUp 中锁定已手工调整对象，可防止再次导入覆盖",
            ),
            (
                "未自动交接",
                f"{res.get('skipped_count', 0)} 个",
                "复杂/不支持图元",
                "填充、外部参照、材质和复杂网格请在 SketchUp/CAD 中复核",
            ),
        ]
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        unmatched_notice = (
            f"注意：有 {unmatched_override_count} 条逐栋设置没有匹配当前图纸，"
            "请重新打开逐栋参数表核对。"
            if unmatched_override_count
            else "逐栋参数已按稳定建筑编号匹配。"
        )
        self.lbl_warning_banner.setText(
            "下一步：① 打开 SketchUp 的扩展程序管理器；② 安装输出目录中的 RBZ；"
            "③ 打开“扩展程序 → 导入 Planning Toolbox 模型交接”；④ 选择 .ptsu.json。"
            "如提示插件可更新，请安装本次新生成的 RBZ。调整重点建筑前先在扩展程序菜单中锁定对象；"
            "以后重复导入只更新变化部分。"
            f"{unmatched_notice}课程模型待完善：{readiness_review_text}。"
            "生成后仍请核对建筑高度、PT_* 标签、复杂曲线和场地原点。"
        )
        self.lbl_warning_banner.show()

    def _export_assignment_package(self):
        """整理当前结果，方便学生检查、保存和提交作业。"""
        if not self.last_result or not self.last_output_dir:
            return
        try:
            from planning_toolbox.gui.assignment_package import build_assignment_package

            package_dir, archive_path = build_assignment_package(
                self.last_output_dir,
                self.last_task_name or "规划分析任务",
                self.last_result,
            )
        except Exception as exc:
            self.lbl_warning_banner.setText(f"🛑 作业包整理失败：{exc}")
            self.lbl_warning_banner.show()
            self.append_log(f"<span style='color:#A96761;'><b>[ERROR] 作业包整理失败：{exc}</b></span>")
            return

        for label, path in (("作业包文件夹", package_dir), ("作业包 ZIP", archive_path)):
            item = QListWidgetItem(f"{label}: {path}")
            item.setData(Qt.UserRole, str(path))
            self.file_list.addItem(item)
        self.lbl_warning_banner.setText(
            f"✅ 作业包已整理完成：{package_dir.name}。已同时生成 ZIP，可打开检查后保存或提交。"
        )
        self.lbl_warning_banner.show()
        self.append_log(
            f"<span style='color:#607A6A;'><b>作业包已生成：</b>{package_dir}；ZIP：{archive_path}</span>"
        )
        self.artifacts_exported.emit("assignment_package")

    def _export_result_artifacts(self):
        """导出适合 Excel、打印和汇报使用的结果文件。"""
        if not self.last_result or not self.last_output_dir:
            return
        try:
            from planning_toolbox.gui.result_export import export_result_artifacts

            exported = export_result_artifacts(
                self.last_output_dir,
                self.last_task_name or "规划分析任务",
                self.last_result,
                self.canvas,
            )
        except Exception as exc:
            self.lbl_warning_banner.setText(f"🛑 结果导出失败：{exc}")
            self.lbl_warning_banner.show()
            self.append_log(f"<span style='color:#A96761;'><b>[ERROR] 结果导出失败：{exc}</b></span>")
            return

        for label, path in exported:
            item = QListWidgetItem(f"{label}: {path}")
            item.setData(Qt.UserRole, str(path))
            self.file_list.addItem(item)
        self.lbl_warning_banner.setText(
            "✅ 已导出 Excel 结果表、PDF 结果报告和 PNG 预览图；如需整理提交材料，请继续点击“整理为作业包”。"
        )
        self.lbl_warning_banner.show()
        self.append_log(
            "<span style='color:#607A6A;'><b>汇报材料已导出：</b>Excel / PDF / PNG</span>"
        )
        self.artifacts_exported.emit("result_artifacts")

    def _curate_refined_cad(self):
        """Attach one user-confirmed refined DXF to the lightweight card."""
        if not self.last_result:
            return
        card_path = self.last_result.get("knowledge_card", {}).get("card_path", "")
        if not card_path or not Path(card_path).is_file():
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择已经人工精修并核对过的 CAD",
            self.last_output_dir or "",
            "DXF 图纸 (*.dxf)",
        )
        if not selected:
            return
        decision = QMessageBox.question(
            self,
            "确认收藏精修 CAD",
            "请确认这份 DXF 已经由你人工检查过比例、单位、图层和主要轮廓。\n\n"
            "收藏后只作为个人学习参考，不会被当作审批或规范标准。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if decision != QMessageBox.Yes:
            return
        try:
            from planning_toolbox.knowledge.image_cards import (
                attach_cad_reference_to_card,
            )

            reference = attach_cad_reference_to_card(
                card_path,
                selected,
                title=f"{Path(selected).stem} · 人工精修参考",
                review_status="user_curated",
            )
        except Exception as exc:
            QMessageBox.warning(self, "收藏失败", str(exc))
            return
        item = QListWidgetItem(f"精选 CAD 参考样本: {reference['path']}")
        item.setData(Qt.UserRole, reference["path"])
        self.file_list.addItem(item)
        self.lbl_warning_banner.setText(
            "✅ 精修 CAD 已复制到本地知识库，并记录单位、图层、图元数量和 SHA-256。"
        )
        self.lbl_warning_banner.show()
        self.append_log(
            "<span style='color:#607A6A;'><b>已收藏人工精修 CAD 参考样本。</b></span>"
        )

    # ─── 打开文件与目录 ───

    def _open_output_folder(self):
        if self.last_output_dir and Path(self.last_output_dir).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_output_dir))
        else:
            out_dir = Path("output").resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    def _open_selected_file(self):
        item = self.file_list.currentItem()
        if item:
            fpath = item.data(Qt.UserRole)
            if fpath and Path(fpath).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(fpath).resolve())))

    def _on_item_double_clicked(self, item: QListWidgetItem):
        fpath = item.data(Qt.UserRole)
        if fpath and Path(fpath).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(fpath).resolve())))
