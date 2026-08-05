"""结果摘要与面板区 (Result Zone Widget with KPI Hero Bar, Table, 2D Canvas & HTML Console Logs)."""
from pathlib import Path
from typing import Dict, Any, List, Optional
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem, QTabWidget, QWidget
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QColor

from planning_toolbox.gui.widgets.canvas_widget import CADPreviewCanvas

class ResultZoneWidget(QFrame):
    """
    结果区：展示运行状态胶囊、英雄数值摘要条、结果表格、嵌入式 2D CAD 预览画布、中文警告提示框、输出文件列表及彩色 HTML 控制台日志。
    """

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

        # 4. 中文警告提示框 (如孔洞/NESTED_RING)
        self.lbl_warning_banner = QLabel("")
        self.lbl_warning_banner.setStyleSheet(
            "background-color: #451a03; color: #fbbf24; border: 1px solid #d97706; "
            "border-radius: 6px; padding: 6px 10px; font-weight: 700;"
        )
        self.lbl_warning_banner.setWordWrap(True)
        self.lbl_warning_banner.hide()
        layout.addWidget(self.lbl_warning_banner)

        # 5. 子选项卡: 表格视图 / 2D 画布预览 / 控制台日志
        self.result_tabs = QTabWidget()

        # Tab 1: 表格视图
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["地块 ID / 统计项", "面积 / 状态", "主要指标 / 规则要求", "详情 / 错误提示"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_tabs.addTab(self.table, "📋 表格清单视图")

        # Tab 2: 2D CAD 画布预览
        self.canvas = CADPreviewCanvas()
        self.result_tabs.addTab(self.canvas, "🎨 2D CAD 矢量预览")

        # Tab 3: 控制台与安全日志
        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("LogTextEdit")
        self.log_edit.setReadOnly(True)
        self.result_tabs.addTab(self.log_edit, "💻 运行与日志记录")

        layout.addWidget(self.result_tabs, stretch=6)

        # 6. 底部：输出文件列表与快捷按钮
        file_bar = QHBoxLayout()
        file_bar.addWidget(QLabel("生成文件列表:"))

        self.btn_open_folder = QPushButton("📁 打开输出文件夹")
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        self.btn_open_file = QPushButton("📄 打开选中文件")
        self.btn_open_file.clicked.connect(self._open_selected_file)

        file_bar.addStretch()
        file_bar.addWidget(self.btn_open_folder)
        file_bar.addWidget(self.btn_open_file)
        layout.addLayout(file_bar)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(65)
        self.file_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.file_list)

        self.last_output_dir = None
        self.last_dxf_path = None

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
        return card

    def start_task(self, task_name: str, dxf_path: Optional[str] = None):
        """记录任务开始状态并重置 UI。"""
        self.last_dxf_path = dxf_path
        self.lbl_status_badge.setText("正在计算中...")
        self.lbl_status_badge.setObjectName("BadgeWarning")
        self.lbl_status_badge.setStyle(self.lbl_status_badge.style())

        self.progress_bar.setValue(10)
        self.lbl_warning_banner.hide()
        self.table.setRowCount(0)
        self.file_list.clear()
        
        self.kpi_parcels.val_label.setText("-")
        self.kpi_area.val_label.setText("-")
        self.kpi_far.val_label.setText("-")
        self.kpi_setback.val_label.setText("-")

        self.append_log(f"<span style='color:#60a5fa;'><b>=== 任务启动: {task_name} ===</b></span>")

        # 若提供了 DXF 路径，更新 2D 画布
        if dxf_path and Path(dxf_path).exists():
            self.canvas.load_dxf_preview(dxf_path)

    def update_progress(self, val: int, msg: str):
        """更新进度条与控制台日志。"""
        self.progress_bar.setValue(val)
        self.append_log(f"<span style='color:#94a3b8;'>[{val}%] {msg}</span>")

    def show_result(self, res: Dict[str, Any]):
        """根据任务返回的摘要字典，填充结果表格、KPI 卡片与文件列表。"""
        self.progress_bar.setValue(100)
        self.lbl_status_badge.setText("✓ 成功完成")
        self.lbl_status_badge.setObjectName("BadgeSuccess")
        self.lbl_status_badge.setStyle(self.lbl_status_badge.style())

        task_type = res.get("task_type")

        # 填充文件列表
        out_files = res.get("output_files", [])
        for label, fpath in out_files:
            item = QListWidgetItem(f"{label}: {fpath}")
            item.setData(Qt.UserRole, fpath)
            self.file_list.addItem(item)
            if not self.last_output_dir:
                self.last_output_dir = str(Path(fpath).parent)

        if task_type == "parcel":
            self._display_parcel_result(res)
        elif task_type == "indicator":
            self._display_indicator_result(res)
        elif task_type == "validate":
            self._display_validate_result(res)
        elif task_type in ("gis_export", "gis_import"):
            self._display_gis_result(res)

        self.append_log("<span style='color:#34d399;'><b>=== 任务成功完成 ===</b></span>")

    def show_error(self, title: str, message: str):
        """任务失败处理。"""
        self.progress_bar.setValue(0)
        self.lbl_status_badge.setText("✗ 任务中断/失败")
        self.lbl_status_badge.setObjectName("BadgeError")
        self.lbl_status_badge.setStyle(self.lbl_status_badge.style())

        self.lbl_warning_banner.setText(f"🛑 {title}:\n{message}")
        self.lbl_warning_banner.show()
        self.append_log(f"<span style='color:#f87171;'><b>[ERROR] {title}: {message}</b></span>")

    def append_log(self, html_text: str):
        self.log_edit.append(html_text)
        self.log_edit.moveCursor(self.log_edit.textCursor().End)

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
                item_status.setForeground(QColor("#34d399"))
            elif st == "VIOLATION":
                item_status.setForeground(QColor("#f87171"))
            elif st == "NO_BUILDING":
                item_status.setForeground(QColor("#fbbf24"))

            self.table.setItem(row, 0, QTableWidgetItem(pid))
            self.table.setItem(row, 1, item_status)
            self.table.setItem(row, 2, QTableWidgetItem(metrics))
            self.table.setItem(row, 3, QTableWidgetItem(err))

    def _display_gis_result(self, res: Dict[str, Any]):
        task_type = res.get("task_type")
        self.table.setRowCount(1)

        if task_type == "gis_export":
            self.kpi_parcels.val_label.setText(f"{res['parcels_count']} 个")
            self.table.setItem(0, 0, QTableWidgetItem("GeoJSON 导出"))
            self.table.setItem(0, 1, QTableWidgetItem(f"包含地块数: {res['parcels_count']}"))
            self.table.setItem(0, 2, QTableWidgetItem("格式: RFC 7946 Standard"))
            self.table.setItem(0, 3, QTableWidgetItem(res.get("crs_warning", "")))
        else:
            self.kpi_parcels.val_label.setText(f"{res['imported_polygons']} 个")
            self.table.setItem(0, 0, QTableWidgetItem("GeoJSON 导入 CAD"))
            self.table.setItem(0, 1, QTableWidgetItem(f"已导入多边形: {res['imported_polygons']}"))
            self.table.setItem(0, 2, QTableWidgetItem(f"跳过不支持类型: {res['skipped_unsupported']}"))
            self.table.setItem(0, 3, QTableWidgetItem("已成功生成 LWPOLYLINE 图层"))

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
