"""Planning Toolbox 规划分析工作台 — 主窗口 (PySide6 MainWindow)."""
from pathlib import Path
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

from planning_toolbox import __version__
from planning_toolbox.gui.widgets.file_zone import FileZoneWidget
from planning_toolbox.gui.widgets.inspection_zone import InspectionZoneWidget
from planning_toolbox.gui.widgets.task_zone import TaskZoneWidget
from planning_toolbox.gui.widgets.result_zone import ResultZoneWidget
from planning_toolbox.gui.workers.task_worker import TaskWorker
from planning_toolbox.gui.utils.dxf_inspector import inspect_dxf_file
from planning_toolbox.gui.styles.qss_theme import APP_QSS_THEME

class PlanningToolboxMainWindow(QMainWindow):
    """
    Planning Toolbox 桌面 GUI 主窗口。
    组装 4 大区域：文件区、数据检查区、任务配置区、结果与日志区。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Planning Toolbox 规划分析工作台 v{__version__}")
        self.resize(1180, 820)
        self.setMinimumSize(960, 680)
        
        # 应用 QSS 皮肤样式表
        self.setStyleSheet(APP_QSS_THEME)

        self.current_worker: Optional[TaskWorker] = None
        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. 顶部：文件与输出位置选择区 (File Zone)
        self.file_zone = FileZoneWidget()
        self.file_zone.file_changed.connect(self._on_dxf_file_changed)
        main_layout.addWidget(self.file_zone)

        # 2. 中部分隔面板：左侧数据检查区，右侧任务配置区
        middle_splitter = QSplitter(Qt.Horizontal)

        self.inspection_zone = InspectionZoneWidget()
        self.task_zone = TaskZoneWidget()
        self.task_zone.run_task_signal.connect(self._start_analysis_task)

        middle_splitter.addWidget(self.inspection_zone)
        middle_splitter.addWidget(self.task_zone)
        middle_splitter.setStretchFactor(0, 4)
        middle_splitter.setStretchFactor(1, 6)

        main_layout.addWidget(middle_splitter, stretch=4)

        # 3. 底部：结果与日志区 (Result Zone)
        self.result_zone = ResultZoneWidget()
        main_layout.addWidget(self.result_zone, stretch=6)

    def _on_dxf_file_changed(self, file_path: str):
        """当 DXF 文件切换时，执行无损前置扫描并更新数据检查区。"""
        if not file_path or not Path(file_path).exists():
            self.inspection_zone.clear_inspection()
            return

        # 快速扫描
        info = inspect_dxf_file(file_path)
        self.inspection_zone.update_inspection(info)

    def _start_analysis_task(self, task_type: str, params: Dict[str, Any]):
        """启动后台计算任务。"""
        dxf_path = self.file_zone.get_dxf_path()
        out_dir = self.file_zone.get_output_dir()

        if task_type != "gis_import" and (not dxf_path or not Path(dxf_path).exists()):
            QMessageBox.warning(self, "未选择文件", "请先选择合法的 CAD DXF 图纸文件！")
            return

        params["dxf_path"] = dxf_path
        params["output_dir"] = out_dir

        # 数据检查区未确认单位时的阻断拦截
        if task_type in ("parcel", "indicator", "validate"):
            info = inspect_dxf_file(dxf_path)
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
        task_names = {
            "parcel": "地块面积计算与编号",
            "indicator": "规划指标自动核算",
            "validate": "拓扑与建筑退线检查",
            "gis_export": "CAD 导出至 GeoJSON",
            "gis_import": "GeoJSON 导入至 CAD DXF"
        }
        self.result_zone.start_task(task_names.get(task_type, task_type))

        # 启动 QThread Worker
        self.current_worker = TaskWorker(task_type, params, self)
        self.current_worker.progress_signal.connect(self.result_zone.update_progress)
        self.current_worker.finished_signal.connect(self._on_task_finished)
        self.current_worker.error_signal.connect(self._on_task_error)
        self.current_worker.start()

    def _on_task_finished(self, res: Dict[str, Any]):
        """任务成功完成回调。"""
        self.result_zone.show_result(res)
        self.task_zone.set_running_state(False)
        self.current_worker = None

        # 如果生成了新文件，自动触发一次数据检查刷新
        dxf_path = self.file_zone.get_dxf_path()
        if dxf_path and Path(dxf_path).exists():
            self._on_dxf_file_changed(dxf_path)

    def _on_task_error(self, title: str, message: str):
        """任务失败回调。"""
        self.result_zone.show_error(title, message)
        self.task_zone.set_running_state(False)
        self.current_worker = None

    def closeEvent(self, event):
        """主窗口关闭事件：确保后台线程安全退出，防止内存泄漏。"""
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.cancel()
            self.current_worker.wait(2000)
        event.accept()
