"""Planning Toolbox 规划分析工作台 — 主窗口 (PySide6 MainWindow)."""
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Any, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QMessageBox,
    QLabel, QPushButton, QScrollArea, QFrame, QFileDialog, QDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from planning_toolbox import __version__
from planning_toolbox.gui.widgets.file_zone import FileZoneWidget
from planning_toolbox.gui.widgets.inspection_zone import InspectionZoneWidget
from planning_toolbox.gui.widgets.task_zone import TaskZoneWidget
from planning_toolbox.gui.widgets.result_zone import ResultZoneWidget
from planning_toolbox.gui.styles.qss_theme import APP_QSS_THEME
from planning_toolbox.gui.help_dialog import HelpDialog
from planning_toolbox.gui.assignment_guide import AssignmentGuideDialog
from planning_toolbox.gui.project_file import save_project, load_project
from planning_toolbox.gui.project_settings_dialog import ProjectSettingsDialog
from planning_toolbox.gui.resources import gui_asset_path
from planning_toolbox.gui.workflow import (
    AUTO_CONTINUATION_TASKS,
    TASK_STAGE_MAP,
    apply_verified_context,
    continuation_dxf_candidate,
    default_workflow_state,
    mark_stage_complete,
    normalize_workflow_state,
    record_working_dxf,
)
from planning_toolbox.project.chain_manifest import ChainManifest, new_chain_manifest

if TYPE_CHECKING:
    from planning_toolbox.gui.comparison_dialog import ComparisonDialog
    from planning_toolbox.gui.workers.task_worker import TaskWorker

class PlanningToolboxMainWindow(QMainWindow):
    """
    Planning Toolbox 桌面 GUI 主窗口。
    组装 4 大区域：文件区、数据检查区、任务配置区、结果与日志区。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        icon_path = gui_asset_path("planning_toolbox.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowTitle(f"Planning Toolbox 规划分析工作台 v{__version__}")
        self.resize(1180, 820)
        self.setMinimumSize(960, 680)
        
        # 应用 QSS 皮肤样式表
        self.setStyleSheet(APP_QSS_THEME)

        self.current_worker: Optional["TaskWorker"] = None
        self._closing = False
        self._inspection_cache_key = None
        self._inspection_cache = None
        self.help_dialog: Optional[HelpDialog] = None
        self.assignment_guide: Optional[AssignmentGuideDialog] = None
        self.comparison_dialog: Optional["ComparisonDialog"] = None
        self.workflow_dialog = None
        self.current_project_path: Optional[Path] = None
        self.chain_manifest = new_chain_manifest()
        self.workflow_state = default_workflow_state()
        self._init_ui()

    def _init_ui(self):
        # Keep the workbench usable on short laptop screens: the whole page
        # can scroll instead of compressing labels and tables into clipped rows.
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("MainScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        central_widget = QWidget()
        central_widget.setObjectName("MainContent")
        self.scroll_area.setWidget(central_widget)
        self.setCentralWidget(self.scroll_area)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Compact header: keep primary actions visible without forcing the
        # whole page wider than a common laptop screen.
        header_frame = QFrame()
        header_frame.setObjectName("AppHeader")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(14, 8, 10, 8)
        header.setSpacing(8)

        brand_box = QVBoxLayout()
        brand_box.setContentsMargins(0, 0, 0, 0)
        brand_box.setSpacing(0)
        brand = QLabel("Planning Toolbox 规划分析工作台")
        brand.setObjectName("AppBrand")
        brand_box.addWidget(brand)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("AppSubtitle")
        self.subtitle.setToolTip("显示当前全链路项目名称、坐标系和 CAD 单位")
        brand_box.addWidget(self.subtitle)
        header.addLayout(brand_box, stretch=1)
        header.addStretch()
        self.project_setup_button = QPushButton("🧭")
        self.project_setup_button.setObjectName("CompactHeaderButton")
        self.project_setup_button.setAccessibleName("全链路项目设置")
        self.project_setup_button.setToolTip("设置 GIS–CAD–SU 共用的项目名称、坐标和本地建模原点")
        self.project_setup_button.clicked.connect(self._open_project_settings)
        header.addWidget(self.project_setup_button)
        self.workflow_button = QPushButton("🧩 流程")
        self.workflow_button.setObjectName("HeaderActionButton")
        self.workflow_button.setToolTip("按步骤完成 GIS–CAD–SketchUp 全链路作业并保存进度")
        self.workflow_button.clicked.connect(self._open_workflow)
        header.addWidget(self.workflow_button)
        self.open_project_button = QPushButton("📂 打开")
        self.open_project_button.setObjectName("HeaderActionButton")
        self.open_project_button.setToolTip("打开之前保存的 DXF、参数和结果记录")
        self.open_project_button.clicked.connect(self._open_project)
        header.addWidget(self.open_project_button)
        self.save_project_button = QPushButton("💾 保存")
        self.save_project_button.setObjectName("HeaderActionButton")
        self.save_project_button.setToolTip("保存当前图纸、任务参数和最近一次结果记录")
        self.save_project_button.clicked.connect(self._save_project)
        header.addWidget(self.save_project_button)
        self.comparison_button = QPushButton("📊 对比")
        self.comparison_button.setObjectName("HeaderActionButton")
        self.comparison_button.setToolTip("选择多个已保存项目，对比关键规划指标")
        self.comparison_button.clicked.connect(self._open_comparison)
        header.addWidget(self.comparison_button)
        self.assignment_button = QPushButton("📝 作业")
        self.assignment_button.setObjectName("HeaderActionButton")
        self.assignment_button.setToolTip("按作业类型查看步骤、输出文件和常见问题")
        self.assignment_button.clicked.connect(self._open_assignment_guide)
        header.addWidget(self.assignment_button)
        self.help_button = QPushButton("📖 帮助")
        self.help_button.setObjectName("HelpButton")
        self.help_button.setToolTip("查看从选择图纸到生成结果的完整中文教程")
        self.help_button.clicked.connect(self._open_help)
        header.addWidget(self.help_button)
        main_layout.addWidget(header_frame)
        self._refresh_project_context()

        # 1. 顶部：文件与输出位置选择区 (File Zone)
        self.file_zone = FileZoneWidget()
        self.file_zone.file_changed.connect(self._on_dxf_file_changed)
        self.file_zone.dwg_conversion_requested.connect(self._start_dwg_conversion)
        main_layout.addWidget(self.file_zone)

        # 2. 中部分隔面板：左侧数据检查区，右侧任务配置区
        self.middle_splitter = QSplitter(Qt.Horizontal)

        self.inspection_zone = InspectionZoneWidget()
        self.task_zone = TaskZoneWidget()
        self.task_zone.run_task_signal.connect(self._start_analysis_task)
        self.task_zone.configure_sketchup_buildings_signal.connect(
            self._open_sketchup_building_schedule
        )

        self.middle_splitter.addWidget(self.inspection_zone)
        self.middle_splitter.addWidget(self.task_zone)
        self.middle_splitter.setStretchFactor(0, 4)
        self.middle_splitter.setStretchFactor(1, 6)
        self.middle_splitter.setMinimumHeight(330)
        self.inspection_zone.setMinimumHeight(300)
        self.task_zone.setMinimumHeight(300)

        main_layout.addWidget(self.middle_splitter, stretch=4)

        # 3. 底部：结果与日志区 (Result Zone)
        self.result_zone = ResultZoneWidget()
        self.result_zone.setMinimumHeight(390)
        self.result_zone.canvas.inspection_ready.connect(self._on_inspection_ready)
        self.result_zone.artifacts_exported.connect(self._on_workflow_exported)
        self.result_zone.working_dxf_requested.connect(self._on_working_dxf_requested)
        self.result_zone.road_repair_requested.connect(self._open_road_repair_editor)
        self.result_zone.sketchup_handoff_requested.connect(
            self._open_sketchup_handoff
        )
        main_layout.addWidget(self.result_zone, stretch=6)
        self._update_responsive_layout(self.width())

    def resizeEvent(self, event):
        """Stack the work panels on narrow screens instead of clipping them."""
        super().resizeEvent(event)
        self._update_responsive_layout(event.size().width())

    def _update_responsive_layout(self, window_width: int):
        self._update_header_actions(window_width)
        if not hasattr(self, "middle_splitter"):
            return
        orientation = Qt.Vertical if window_width < 1180 else Qt.Horizontal
        if self.middle_splitter.orientation() == orientation:
            return
        self.middle_splitter.setOrientation(orientation)
        if orientation == Qt.Vertical:
            self.middle_splitter.setMinimumHeight(650)
            self.inspection_zone.setMinimumHeight(280)
            self.task_zone.setMinimumHeight(340)
            self.middle_splitter.setSizes([290, 360])
        else:
            self.middle_splitter.setMinimumHeight(330)
            self.inspection_zone.setMinimumHeight(300)
            self.task_zone.setMinimumHeight(300)
            self.middle_splitter.setSizes([420, 630])

    def _update_header_actions(self, window_width: int):
        """Collapse header labels on narrow screens to prevent horizontal clipping."""
        if not hasattr(self, "workflow_button"):
            return
        actions = (
            (self.workflow_button, "🧩", "🧩 流程", "GIS–CAD–SketchUp 全链路作业向导"),
            (self.open_project_button, "📂", "📂 打开", "打开已保存的作业项目"),
            (self.save_project_button, "💾", "💾 保存", "保存当前作业项目和流程进度"),
            (self.comparison_button, "📊", "📊 对比", "比较多个已保存方案"),
            (self.assignment_button, "📝", "📝 作业", "查看按作业类型整理的操作教程"),
            (self.help_button, "📖", "📖 帮助", "打开完整中文帮助"),
        )
        compact = window_width < 1050
        for button, icon_text, full_text, accessible_name in actions:
            button.setText(icon_text if compact else full_text)
            button.setAccessibleName(accessible_name)
            button.setObjectName("CompactHeaderButton" if compact else (
                "HelpButton" if button is self.help_button else "HeaderActionButton"
            ))
            if compact:
                button.setMinimumWidth(34)
                button.setMaximumWidth(34)
            else:
                button.setMinimumWidth(0)
                button.setMaximumWidth(16_777_215)
            style = button.style()
            style.unpolish(button)
            style.polish(button)

    def _open_help(self):
        """Show the reusable help window without blocking the workbench."""
        if self.help_dialog is None:
            self.help_dialog = HelpDialog(self)
        self.help_dialog.show()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()

    def _open_assignment_guide(self):
        """Show the coursework-oriented guide without blocking the workbench."""
        if self.assignment_guide is None:
            self.assignment_guide = AssignmentGuideDialog(self)
        self.assignment_guide.show()
        self.assignment_guide.raise_()
        self.assignment_guide.activateWindow()

    def _open_workflow(self):
        """Open the non-blocking full-chain guide and reuse the existing tools."""
        if self.workflow_dialog is None:
            from planning_toolbox.gui.workflow_dialog import FullChainWorkflowDialog

            self.workflow_dialog = FullChainWorkflowDialog(self.workflow_state, self)
            self.workflow_dialog.state_changed.connect(self._set_workflow_state)
            self.workflow_dialog.navigate_requested.connect(self._navigate_workflow_stage)
            self.workflow_dialog.save_requested.connect(self._save_workflow_progress)
        self._sync_workflow_context()
        self.workflow_dialog.show()
        self.workflow_dialog.raise_()
        self.workflow_dialog.activateWindow()

    def _set_workflow_state(self, state: Dict[str, Any]):
        self.workflow_state = normalize_workflow_state(state)

    def _save_workflow_progress(self):
        """Save progress to the current project, or ask for a project file once."""
        if self.current_project_path:
            self._save_project_to_path(self.current_project_path)
        else:
            self._save_project()

    def _workflow_context(self) -> Dict[str, Any]:
        dxf_path = self.file_zone.get_dxf_path() if hasattr(self, "file_zone") else ""
        source = Path(dxf_path) if dxf_path else None
        semantic_scene = source.with_suffix(".ptscene.json") if source else None
        source_ready = bool(
            source and source.is_file() and source.suffix.lower() == ".dxf"
        )
        inspection_ready = bool(
            self._inspection_cache
            and self._inspection_cache.get("valid_dxf")
            and self._inspection_cache.get("unit_known")
        )
        inspection_blocked = bool(
            self._inspection_cache
            and (
                not self._inspection_cache.get("valid_dxf")
                or not self._inspection_cache.get("unit_known")
            )
        )
        return {
            "project_configured": self.chain_manifest.configured,
            "source_ready": source_ready,
            "inspection_ready": inspection_ready,
            "inspection_blocked": inspection_blocked,
            "result_available": bool(
                hasattr(self, "result_zone")
                and self.result_zone.last_result
                and self.result_zone.last_result.get("output_files")
            ),
            "working_dxf": dxf_path,
            "lineage_count": len(self.workflow_state.get("dxf_lineage", [])),
            "semantic_scene_ready": bool(
                semantic_scene and semantic_scene.is_file()
            ),
            "semantic_scene_path": str(semantic_scene) if semantic_scene else "",
        }

    def _sync_workflow_context(self):
        """Use verified workbench evidence to advance safety stages automatically."""
        context = self._workflow_context()
        self.workflow_state = apply_verified_context(self.workflow_state, context)
        if self.workflow_dialog is not None:
            self.workflow_dialog.set_state(self.workflow_state)
            self.workflow_dialog.refresh_context(context)

    def _navigate_workflow_stage(self, stage_key: str, source_kind: str):
        """Route a guide stage to the matching existing workbench control."""
        if stage_key == "setup":
            self._open_project_settings()
            return
        if stage_key == "source":
            if source_kind == "image":
                self.task_zone.task_selector.setCurrentIndex(8)
                self.scroll_area.ensureWidgetVisible(self.task_zone)
            elif source_kind == "gis":
                self.task_zone.task_selector.setCurrentIndex(3)
                self.scroll_area.ensureWidgetVisible(self.task_zone)
            else:
                self.file_zone._browse_dxf()
            return
        if stage_key == "inspection":
            if not self.file_zone.get_dxf_path():
                QMessageBox.information(self, "先选择图纸", "请先在“导入资料”步骤选择一份 DXF 图纸。")
            self.scroll_area.ensureWidgetVisible(self.inspection_zone)
            return
        if stage_key == "export":
            if not self.result_zone.last_result:
                QMessageBox.information(
                    self,
                    "还没有可导出结果",
                    "请先完成一项规划分析，再使用下方“导出成果”或“作业包”。",
                )
            self.scroll_area.ensureWidgetVisible(self.result_zone)
            return
        stage_to_index = {
            "standardize": 6,
            "quality": 7,
            "analysis": 1,
            "gis": 3,
            "sketchup": 9,
        }
        index = stage_to_index.get(stage_key)
        if index is not None:
            self.task_zone.task_selector.setCurrentIndex(index)
            self.scroll_area.ensureWidgetVisible(self.task_zone)

    def _open_project_settings(self):
        """Edit the lightweight coordinate contract shared by GIS, CAD and SU."""
        dialog = ProjectSettingsDialog(self.chain_manifest, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.chain_manifest = dialog.result_manifest()
        self._refresh_project_context()
        if self.chain_manifest.crs.metric_ready:
            message = "全链路项目设置已更新；坐标类型适合面积、距离和三维对齐。"
            status = "success"
        else:
            message = "项目设置已保存；坐标尚未满足量算要求，请在 GIS 步骤补充投影坐标。"
            status = "warning"
        self.task_zone.set_preflight_status(message, status)
        self._sync_workflow_context()

    def _open_sketchup_building_schedule(self):
        """Open the read-only DXF catalog used for per-building modeling settings."""
        dxf_path = self.file_zone.get_dxf_path()
        if not dxf_path or not Path(dxf_path).is_file():
            QMessageBox.warning(
                self, "未选择 DXF", "请先在顶部选择一份有效的 DXF 图纸。"
            )
            return
        try:
            from planning_toolbox.gui.building_schedule_dialog import (
                BuildingScheduleDialog,
            )

            dialog = BuildingScheduleDialog(
                dxf_path=dxf_path,
                chain_manifest=self.chain_manifest,
                building_layers=self.task_zone.sketchup_building_layers.text(),
                existing_overrides=self.task_zone.get_sketchup_building_overrides(),
                global_defaults={
                    "floors": self.task_zone.sketchup_floors.value(),
                    "floor_height_m": self.task_zone.sketchup_floor_height.value(),
                    "model_detail_level": self.task_zone.sketchup_model_detail.currentData(),
                    "building_type": self.task_zone.sketchup_building_type.currentData(),
                    "roof_type": self.task_zone.sketchup_roof_type.currentData(),
                },
                parent=self,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "无法读取建筑列表",
                f"系统没有修改原图，但无法从当前建筑图层读取闭合轮廓：\n{exc}",
            )
            return
        if dialog.building_count() == 0:
            QMessageBox.information(
                self,
                "没有识别到建筑",
                "当前建筑图层中没有可用的顶层闭合轮廓。请先检查建筑图层名称和轮廓闭合情况。",
            )
        if dialog.exec() == QDialog.Accepted:
            self.task_zone.set_sketchup_building_overrides(
                dialog.building_overrides()
            )
            self.task_zone.set_preflight_status(
                "逐栋建筑参数已保存；运行 SketchUp 交接时会自动应用。",
                "success",
            )

    def _refresh_project_context(self):
        """Show project metadata without adding another permanent panel."""
        manifest = self.chain_manifest
        if not manifest.configured:
            self.subtitle.setText("未配置全链路项目 · CAD–GIS–SU 本地处理")
            return
        origin_text = "近原点已启用" if manifest.local_origin.enabled else "未设置近原点"
        self.subtitle.setText(
            f"{manifest.name} · {manifest.crs.identifier} · CAD {manifest.cad_unit} · {origin_text}"
        )

    def _project_state(self) -> Dict[str, Any]:
        return {
            "dxf_path": self.file_zone.get_dxf_path(),
            "output_dir": self.file_zone.get_output_dir(),
            "task": self.task_zone.get_project_state(),
            "last_task_name": self.result_zone.last_task_name,
            "last_result": self.result_zone.last_result,
            "chain_manifest": self.chain_manifest.to_dict(),
            "workflow": normalize_workflow_state(self.workflow_state),
        }

    def _save_project_to_path(self, project_path: Path):
        try:
            saved_path = save_project(project_path, self._project_state())
        except Exception as exc:
            QMessageBox.critical(self, "项目保存失败", f"无法保存项目文件：\n{exc}")
            return False
        self.current_project_path = saved_path
        self.task_zone.set_preflight_status(
            f"项目已保存：{saved_path.name}。下次可以点击“打开项目”继续。", "success"
        )
        return True

    def _save_project(self):
        default_path = str(self.current_project_path) if self.current_project_path else "planning_project.ptx"
        project_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 Planning Toolbox 作业项目",
            default_path,
            "Planning Toolbox 项目 (*.ptx)",
        )
        if not project_path:
            return
        path = Path(project_path)
        if path.suffix.lower() != ".ptx":
            path = path.with_suffix(".ptx")
        self._save_project_to_path(path)

    def _load_project_from_path(self, project_path: Path):
        try:
            state = load_project(project_path)
            manifest_data = state.get("chain_manifest", {})
            self.chain_manifest = ChainManifest.from_dict(manifest_data)
            self.workflow_state = normalize_workflow_state(state.get("workflow"))
            self._refresh_project_context()
            self.file_zone.set_output_dir(str(state.get("output_dir", "output")))
            self.task_zone.apply_project_state(state.get("task", {}))
            self.current_project_path = project_path.resolve()
            dxf_path = str(state.get("dxf_path", ""))
            if dxf_path:
                self.file_zone.set_dxf_path(dxf_path)
            last_result = state.get("last_result")
            last_task_name = str(state.get("last_task_name", ""))
            if isinstance(last_result, dict) and last_result.get("output_files"):
                self.result_zone.restore_project_result(last_task_name or "已保存任务", last_result)
            else:
                self.result_zone.lbl_warning_banner.setText(
                    "📂 项目已打开。参数已恢复，如需得到最新结果请重新运行任务。"
                )
                self.result_zone.lbl_warning_banner.show()
            self.task_zone.set_preflight_status(
                f"项目已打开：{project_path.name}。请确认图纸路径和参数后继续。", "success"
            )
            self._sync_workflow_context()
            return True
        except Exception as exc:
            QMessageBox.critical(self, "项目打开失败", f"无法打开项目文件：\n{exc}")
            return False

    def _open_project(self):
        project_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开 Planning Toolbox 作业项目",
            "",
            "Planning Toolbox 项目 (*.ptx)",
        )
        if project_path:
            self._load_project_from_path(Path(project_path))

    def _open_comparison(self):
        """Show the non-blocking multi-project comparison window."""
        if self.comparison_dialog is None:
            from planning_toolbox.gui.comparison_dialog import ComparisonDialog

            self.comparison_dialog = ComparisonDialog(self)
        self.comparison_dialog.show()
        self.comparison_dialog.raise_()
        self.comparison_dialog.activateWindow()

    def _on_dxf_file_changed(self, file_path: str):
        """当 DXF 文件切换时，执行无损前置扫描并更新数据检查区与 2D 画布。"""
        if not file_path or not Path(file_path).exists():
            self._inspection_cache_key = None
            self._inspection_cache = None
            self.inspection_zone.clear_inspection()
            self.task_zone.set_preflight_status(
                "请先选择一个存在的 DXF 文件。", "warning"
            )
            self.result_zone.canvas.clear_canvas("等待选择 DXF 文件...")
            self._sync_workflow_context()
            return

        # 预检查和预览都在后台执行；结果通过 inspection_ready 回到主线程。
        self._inspection_cache_key = None
        self._inspection_cache = None
        self.inspection_zone.clear_inspection()
        self.task_zone.set_preflight_status(
            "正在读取 DXF 并进行运行前检查，请稍候...", "info"
        )
        self.result_zone.canvas.load_dxf_preview(file_path)
        self._sync_workflow_context()

    def _on_inspection_ready(self, info: Dict[str, Any]):
        """Receive the asynchronous DXF inspection result from the preview worker."""
        file_path = self.file_zone.get_dxf_path()
        if not file_path or not Path(file_path).exists():
            return
        try:
            stat = Path(file_path).stat()
            self._inspection_cache_key = (str(Path(file_path).resolve()), stat.st_mtime_ns, stat.st_size)
            self._inspection_cache = info
        except OSError:
            self._inspection_cache_key = None
            self._inspection_cache = None
        self.inspection_zone.update_inspection(info)
        if info.get("valid_dxf") and info.get("unit_known"):
            self.task_zone.set_preflight_status(
                "运行前检查完成：文件、图层和单位可识别，可以开始分析。", "success"
            )
        elif info.get("valid_dxf"):
            self.task_zone.set_preflight_status(
                "运行前检查发现 DXF 单位未知；面积和退线任务会被阻断，请先指定回退单位。",
                "error",
            )
        else:
            self.task_zone.set_preflight_status(
                "DXF 文件无法读取，请更换文件后再试。", "error"
            )
        self._sync_workflow_context()

    def _start_analysis_task(self, task_type: str, params: Dict[str, Any]):
        """启动后台计算任务。"""
        if self.current_worker and self.current_worker.isRunning():
            return

        params = dict(params)
        dxf_path = self.file_zone.get_dxf_path()
        out_dir = self.file_zone.get_output_dir()

        if task_type == "batch":
            batch_dir = Path(params.get("input_dir", ""))
            if not batch_dir.exists() or not batch_dir.is_dir():
                QMessageBox.warning(
                    self,
                    "批量文件夹无效",
                    "请选择一个包含 DXF 图纸的文件夹。",
                )
                return
        elif task_type == "image_to_dxf":
            image_path = Path(params.get("image_path", ""))
            if not image_path.exists() or not image_path.is_file():
                QMessageBox.warning(
                    self,
                    "未选择效果图",
                    "请先选择一张 PNG、JPG 或 JPEG 俯视平面效果图。",
                )
                return
            if params.get("conversion_mode") == "semantic_guide":
                guide_path = Path(params.get("semantic_guide_path", ""))
                if not guide_path.exists() or not guide_path.is_file():
                    QMessageBox.warning(
                        self,
                        "未选择语义引导图",
                        "该模式需要选择一张与原图像素尺寸完全一致的标准颜色引导图。",
                    )
                    return
            if float(params.get("reference_width_m", 0.0)) <= 0:
                QMessageBox.warning(
                    self,
                    "未填写场地比例",
                    "请填写图片中整个场地的实际宽度，系统不会自动猜测 CAD 比例。",
                )
                return
        elif task_type == "gis_import":
            gis_path = Path(params.get("geojson_path", ""))
            if not gis_path.is_file():
                QMessageBox.warning(
                    self,
                    "未选择 GIS 文件",
                    "请先选择有效的 GeoJSON、GeoPackage 或 Shapefile 文件。",
                )
                return
        elif task_type != "gis_import" and (not dxf_path or not Path(dxf_path).exists()):
            QMessageBox.warning(self, "未选择文件", "请先选择合法的 CAD DXF 图纸文件！")
            return

        if not out_dir:
            QMessageBox.warning(
                self,
                "未设置输出目录",
                "请先选择用于保存结果文件的输出目录。",
            )
            return
        output_path = Path(out_dir)
        if output_path.exists() and not output_path.is_dir():
            QMessageBox.warning(
                self,
                "输出目录无效",
                "当前输出路径不是文件夹，请重新选择输出目录。",
            )
            return

        requires_floors = task_type == "indicator" or (
            task_type == "batch" and params.get("batch_task") == "indicator"
        )
        if requires_floors and not params.get("floors"):
            QMessageBox.warning(
                self,
                "楼层倍数未填写",
                "请先明确填写建筑楼层倍数，系统不会自动假设楼层数。",
            )
            return

        if (
            task_type == "sketchup_export"
            and int(params.get("floors", 0)) > 0
            and float(params.get("floor_height_m", 0.0)) <= 0
        ):
            QMessageBox.warning(
                self,
                "标准层高未填写",
                "你选择了生成三维建筑，请明确填写大于 0 的标准层高。\n"
                "如果只需要二维线面，请把建筑楼层数设为 0。",
            )
            return

        if dxf_path:
            params["dxf_path"] = dxf_path
        params["output_dir"] = out_dir
        if task_type in {"gis_export", "gis_import", "sketchup_export"}:
            params["chain_manifest"] = self.chain_manifest.to_dict()
        if params.get("requires_project_crs"):
            try:
                from planning_toolbox.gis.crs import require_projected_metric_crs

                require_projected_metric_crs(self.chain_manifest)
            except ValueError as exc:
                QMessageBox.warning(self, "请先确认项目坐标", str(exc))
                return

        # 数据检查区未确认单位时的阻断拦截
        if task_type in (
            "parcel",
            "indicator",
            "validate",
            "concept_plan",
            "sketchup_export",
        ):
            try:
                stat = Path(dxf_path).stat()
                cache_key = (str(Path(dxf_path).resolve()), stat.st_mtime_ns, stat.st_size)
            except OSError:
                cache_key = None
            if cache_key and cache_key == self._inspection_cache_key and self._inspection_cache is not None:
                info = self._inspection_cache
            else:
                QMessageBox.information(
                    self,
                    "图纸仍在预检查",
                    "图纸正在后台读取和预览，请稍候再运行分析任务。",
                )
                return
            if not info.get("unit_known") and not params.get("fallback_unit"):
                QMessageBox.critical(
                    self, "未知 DXF 单位拦截",
                    "无法确认 DXF 单位 ($INSUNITS=0)，系统已阻止面积和距离计算！\n\n"
                    "解决办法:\n"
                    "1. 请在 AutoCAD 中使用 UNITS 命令将图纸单位设置为【米】(Meters)。\n"
                    "2. 或在任务参数中显式选择单位回退值 (Fallback Unit)。"
                )
                return

        # 锁定 UI 运行状态，防止重复并发点击
        self.task_zone.set_running_state(True)
        self.task_zone.set_preflight_status(
            "任务已启动，正在后台计算；界面仍可响应。", "info"
        )
        task_names = {
            "parcel": "地块面积计算与编号",
            "indicator": "规划指标自动核算",
            "validate": "拓扑与建筑退线检查",
            "gis_export": (
                "CAD 导出至 GeoPackage"
                if params.get("output_format") == "gpkg"
                else "CAD 导出至 GeoJSON"
            ),
            "gis_import": (
                "GeoPackage / Shapefile 导入至 CAD DXF"
                if params.get("use_vector_bridge")
                else "GeoJSON 导入至 CAD DXF"
            ),
            "batch": "批量 DXF 分析",
            "concept_plan": "参数化概念方案草图生成",
            "layer_standardize": "CAD 图层标准化",
            "quality_check": "图纸质量增强检查与安全修复",
            "image_to_dxf": "AI 效果图转 CAD 概念草图",
            "sketchup_export": "CAD → SketchUp 模型交接",
        }
        # 文件切换时已经完成一次预览；这里不重复在主线程解析大型 DXF。
        self.result_zone.start_task(task_names.get(task_type, task_type), dxf_path=None)

        # 启动 QThread Worker
        from planning_toolbox.gui.workers.task_worker import TaskWorker

        self.current_worker = TaskWorker(task_type, params, self)
        self.current_worker.progress_signal.connect(self.result_zone.update_progress)
        self.current_worker.finished_signal.connect(self._on_task_finished)
        self.current_worker.error_signal.connect(self._on_task_error)
        self.current_worker.finished.connect(
            lambda worker=self.current_worker: self._on_worker_thread_finished(worker)
        )
        self.current_worker.finished.connect(self.current_worker.deleteLater)
        self.current_worker.start()

    def _on_task_finished(self, res: Dict[str, Any]):
        """任务成功完成回调。"""
        if self._closing:
            return
        self.result_zone.show_result(res)
        task_type = str(res.get("task_type", ""))
        stage_key = TASK_STAGE_MAP.get(task_type)
        if stage_key:
            self.workflow_state = mark_stage_complete(self.workflow_state, stage_key)
        candidate = continuation_dxf_candidate(res)
        if task_type in AUTO_CONTINUATION_TASKS and candidate:
            self._adopt_working_dxf(
                candidate,
                task_type,
                automatic=True,
                source_path=str(res.get("source_file", "")),
            )
        self._sync_workflow_context()

    def _on_working_dxf_requested(self, path: str, task_type: str):
        self._adopt_working_dxf(path, task_type, automatic=False)

    def _adopt_working_dxf(
        self,
        path: str,
        task_type: str,
        *,
        automatic: bool,
        source_path: str = "",
    ) -> bool:
        """Adopt a generated DXF as the next read-only input and record its lineage."""
        candidate = Path(path)
        if not candidate.is_file() or candidate.suffix.lower() != ".dxf":
            QMessageBox.warning(
                self,
                "无法接入工作图",
                "生成的 DXF 已被移动、删除或格式不正确，请在结果区重新检查文件。",
            )
            return False
        candidate = candidate.resolve()
        source_text = source_path or self.file_zone.get_dxf_path()
        source = Path(source_text).resolve() if source_text else None
        if source == candidate:
            self.task_zone.set_preflight_status(
                f"当前已经使用 {candidate.name}，无需重复切换。", "info"
            )
            return True
        self.workflow_state = record_working_dxf(
            self.workflow_state,
            source_path=str(source) if source else "",
            output_path=str(candidate),
            task_type=task_type,
            automatic=automatic,
        )
        self.file_zone.set_dxf_path(str(candidate))
        self.workflow_state = mark_stage_complete(self.workflow_state, "source")
        self.result_zone.mark_working_dxf_adopted(str(candidate))
        action = "已自动接入" if automatic else "已采用"
        self.task_zone.set_preflight_status(
            f"{action}新的工作图 {candidate.name}；原图仍保留，系统正在重新进行无损预检查。",
            "success",
        )
        self._sync_workflow_context()
        return True

    def _on_workflow_exported(self, _export_kind: str):
        self.workflow_state = mark_stage_complete(self.workflow_state, "export")
        self._sync_workflow_context()

    def _open_road_repair_editor(
        self,
        source_path: str,
        guide_path: str,
        review_overlay_path: str = "",
    ):
        """Jump from image-to-CAD results directly into safe road-path correction."""
        source = Path(source_path).resolve()
        guide = Path(guide_path).resolve()
        if not source.is_file() or not guide.is_file():
            QMessageBox.warning(
                self,
                "道路修正文件不可用",
                "原图或语义引导草稿已被移动，请重新运行图片转 CAD。",
            )
            return
        self.task_zone.task_selector.setCurrentIndex(8)
        self.task_zone.image_file_input.setText(str(source))
        self.task_zone.image_conversion_mode.setCurrentIndex(2)
        self.task_zone.image_semantic_guide_input.setText(str(guide))
        self.scroll_area.ensureWidgetVisible(self.task_zone)
        review_overlay = Path(review_overlay_path).resolve() if review_overlay_path else None
        self.task_zone._edit_semantic_guide(
            review_overlay_path=str(review_overlay)
            if review_overlay and review_overlay.is_file()
            else None
        )

    def _open_sketchup_handoff(
        self,
        dxf_path: str,
        centerline_count: int = 0,
        centerline_review_count: int = 0,
    ):
        """Carry an image-to-CAD result directly into the SketchUp page.

        Image conversion already writes the semantic sidecar beside the DXF.
        This route only changes the active input and task page; it never runs
        the export silently, so floors, road detail and other user choices
        remain visible and reviewable before the handoff.
        """
        dxf = Path(dxf_path).resolve()
        if not dxf.is_file() or dxf.suffix.lower() != ".dxf":
            QMessageBox.warning(
                self,
                "SketchUp 交接文件不可用",
                "图转 CAD 的 DXF 已被移动或删除，请重新运行图转 CAD。",
            )
            return
        self.file_zone.set_dxf_path(str(dxf))
        self.task_zone.task_selector.setCurrentIndex(9)
        if int(centerline_count or 0) > 0:
            self.task_zone.sketchup_centerline_corridor.setChecked(True)
            policy_index = (
                self.task_zone.sketchup_centerline_confidence_policy.findData(
                    "trusted_only"
                )
            )
            if policy_index >= 0:
                self.task_zone.sketchup_centerline_confidence_policy.setCurrentIndex(
                    policy_index
                )
            ready_count = max(
                0,
                int(centerline_count or 0) - int(centerline_review_count or 0),
            )
            self.task_zone.set_preflight_status(
                f"已带入图转 CAD 结果；道路中心线候选 {int(centerline_count)} 条，"
                f"其中高可信 {ready_count} 条、待复核 {int(centerline_review_count or 0)} 条。"
                "已启用推荐策略：仅高可信候选生成道路实体。请确认道路宽度后再运行。",
                "info",
            )
        else:
            self.task_zone.set_preflight_status(
                "已带入图转 CAD 结果；请确认楼层、层高和道路建模选项后再运行 SketchUp 交接。",
                "info",
            )
        self.scroll_area.ensureWidgetVisible(self.task_zone)

    def _start_dwg_conversion(self, dwg_path: str):
        """Run the optional local DWG bridge without blocking the interface."""
        if self.current_worker and self.current_worker.isRunning():
            QMessageBox.information(self, "已有任务运行", "请等待当前任务完成后再导入 DWG。")
            return
        output_dir = self.file_zone.get_output_dir()
        if not output_dir:
            QMessageBox.warning(self, "请选择输出目录", "DWG 会转换为新的 DXF，请先选择保存目录。")
            return
        from planning_toolbox.gui.workers.task_worker import TaskWorker

        self.task_zone.set_running_state(True)
        self.task_zone.set_preflight_status("正在本机转换 DWG，界面仍可响应。", "info")
        self.result_zone.start_task("DWG 本机转换为 DXF", dxf_path=None)
        self.current_worker = TaskWorker(
            "dwg_convert",
            {"dwg_path": dwg_path, "output_dir": output_dir},
            self,
        )
        self.current_worker.progress_signal.connect(self.result_zone.update_progress)
        self.current_worker.finished_signal.connect(self._on_task_finished)
        self.current_worker.error_signal.connect(self._on_task_error)
        self.current_worker.finished.connect(
            lambda worker=self.current_worker: self._on_worker_thread_finished(worker)
        )
        self.current_worker.finished.connect(self.current_worker.deleteLater)
        self.current_worker.start()

    def _on_task_error(self, title: str, message: str):
        """任务失败回调。"""
        if self._closing:
            return
        self.result_zone.show_error(title, message)

    def _on_worker_thread_finished(self, worker: "TaskWorker"):
        """Release the worker only after the OS thread has actually stopped."""
        if self.current_worker is worker:
            self.current_worker = None
            if not self._closing:
                self.task_zone.set_running_state(False)
                self.task_zone.set_preflight_status(
                    "任务已结束，请查看下方结果或错误提示。", "info"
                )

    def closeEvent(self, event):
        """主窗口关闭事件：确保后台线程安全退出，防止内存泄漏。"""
        if not self.result_zone.canvas.cancel_preview(wait=True):
            QMessageBox.warning(
                self,
                "预览任务仍在运行",
                "CAD 预览尚未安全结束，窗口暂不能关闭。",
            )
            event.ignore()
            return
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.cancel()
            if not self.current_worker.wait(2000):
                QMessageBox.warning(
                    self,
                    "后台任务仍在运行",
                    "后台计算尚未安全结束，窗口暂不能关闭。\n"
                    "请等待任务结束后再关闭程序。",
                )
                event.ignore()
                return
        self._closing = True
        event.accept()
