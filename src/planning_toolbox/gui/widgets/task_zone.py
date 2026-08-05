"""任务选择与参数配置区 (Task Zone Widget)."""
from typing import Dict, Any
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QWidget,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton, QFileDialog
)
from PySide6.QtCore import Signal, Qt

class TaskZoneWidget(QFrame):
    """
    任务区：提供 4 大规划分析任务页签及其参数配置表单，包含核心“运行分析”按钮。
    """
    run_task_signal = Signal(str, dict)    # (task_type, params_dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoneFrame")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        title = QLabel("规划分析任务与参数 (Analysis Tasks & Settings)")
        title.setObjectName("ZoneTitle")
        layout.addWidget(title)

        # QTabWidget 4 大任务页签
        self.tabs = QTabWidget()

        self._setup_parcel_tab()
        self._setup_indicator_tab()
        self._setup_validate_tab()
        self._setup_gis_tab()

        layout.addWidget(self.tabs)

        # 底部大运行按钮
        self.btn_run = QPushButton("🚀 运行所选分析任务 (Run Analysis)")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.clicked.connect(self._on_run_clicked)
        layout.addWidget(self.btn_run)

    # ─── 1. 地块面积与编号 Tab ───
    def _setup_parcel_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.parcel_layer_input = QLineEdit("PARCEL")
        form.addRow("目标地块图层名称:", self.parcel_layer_input)

        info = QLabel("💡 功能说明: 自动识别目标图层闭合多边形、去重嵌套环、按确定性规则排序编号并输出标注 DXF、CSV 统计表与 GeoJSON。")
        info.setStyleSheet("color: #9999a6; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)

        self.tabs.addTab(tab, "1. 地块面积与编号")

    # ─── 2. 规划指标计算 Tab ───
    def _setup_indicator_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.spin_floors = QSpinBox()
        self.spin_floors.setRange(1, 200)
        self.spin_floors.setValue(6)
        form.addRow("建筑楼层倍数 (必填):", self.spin_floors)

        self.ind_b_layer = QLineEdit("BUILDING")
        form.addRow("建筑轮廓图层:", self.ind_b_layer)

        self.ind_g_layer = QLineEdit("GREEN")
        form.addRow("绿地范围图层:", self.ind_g_layer)

        notice = QLabel("⚠️ 注意: 楼层数会用于估算总建筑面积。不同建筑楼层不一致时，请谨慎使用。程序将自动执行空间求交并去重重叠轮廓。")
        notice.setStyleSheet("color: #ffcc66; font-size: 12px;")
        notice.setWordWrap(True)
        form.addRow(notice)

        self.tabs.addTab(tab, "2. 规划指标计算")

    # ─── 3. 拓扑与退线检查 Tab ───
    def _setup_validate_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.spin_setback = QDoubleSpinBox()
        self.spin_setback.setRange(0.1, 100.0)
        self.spin_setback.setValue(5.0)
        self.spin_setback.setSuffix(" 米 (m)")
        form.addRow("建筑退线要求距离:", self.spin_setback)

        self.val_p_layer = QLineEdit("PARCEL")
        form.addRow("地块图层名称:", self.val_p_layer)

        self.val_b_layer = QLineEdit("BUILDING")
        form.addRow("建筑图层名称:", self.val_b_layer)

        self.combo_fallback = QComboBox()
        self.combo_fallback.addItems(["严格检查 (严格阻断未知单位)", "m (米)", "cm (厘米)", "mm (毫米)", "ft (英尺)"])
        form.addRow("单位回退策略:", self.combo_fallback)

        info = QLabel("💡 说明: 校验多段线自交、未闭合拓扑，并按实际地块归属校验建筑基底是否越过用地红线退线边界。")
        info.setStyleSheet("color: #9999a6; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)

        self.tabs.addTab(tab, "3. 拓扑与建筑退线检查")

    # ─── 4. GIS 导出/导入 Tab ───
    def _setup_gis_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.gis_mode_combo = QComboBox()
        self.gis_mode_combo.addItems(["CAD DXF 导出至 GeoJSON (GIS Export)", "GeoJSON 导入至 CAD DXF (GIS Import)"])
        self.gis_mode_combo.currentIndexChanged.connect(self._on_gis_mode_changed)
        form.addRow("GIS 操作模式:", self.gis_mode_combo)

        # 导入专用行
        self.geojson_file_input = QLineEdit()
        self.geojson_file_input.setPlaceholderText("请选择要导入的 GeoJSON 文件...")
        self.btn_browse_geojson = QPushButton("选择 GeoJSON...")
        self.btn_browse_geojson.clicked.connect(self._browse_geojson)
        
        geojson_box = QHBoxLayout()
        geojson_box.addWidget(self.geojson_file_input)
        geojson_box.addWidget(self.btn_browse_geojson)
        
        self.lbl_geojson = QLabel("GeoJSON 文件:")
        form.addRow(self.lbl_geojson, geojson_box)

        self.combo_gis_unit = QComboBox()
        self.combo_gis_unit.addItems(["m (米)", "cm (厘米)", "mm (毫米)", "ft (英尺)", "in (英寸)"])
        self.lbl_gis_unit = QLabel("DXF 写入单位:")
        form.addRow(self.lbl_gis_unit, self.combo_gis_unit)

        # 警告提示
        self.gis_notice = QLabel(
            "⚠️ CRS 提示: 当前未进行 CRS 坐标转换。请不要把本地 CAD 坐标直接当作真实经纬度使用。"
        )
        self.gis_notice.setStyleSheet("color: #ffcc66; font-size: 12px;")
        self.gis_notice.setWordWrap(True)
        form.addRow(self.gis_notice)

        self._on_gis_mode_changed(0)  # 默认导出模式
        self.tabs.addTab(tab, "4. GIS 导出与导入")

    def _on_gis_mode_changed(self, index: int):
        is_import = (index == 1)
        self.lbl_geojson.setVisible(is_import)
        self.geojson_file_input.setVisible(is_import)
        self.btn_browse_geojson.setVisible(is_import)
        self.lbl_gis_unit.setVisible(is_import)
        self.combo_gis_unit.setVisible(is_import)

        if is_import:
            self.gis_notice.setText(
                "🛑 CRS 安全阻断提示: 若 GeoJSON 声明为 WGS84 经纬度坐标，系统将拒绝直接导入。\n"
                "请先在 QGIS 或 ArcGIS 中转换为适合测距和面积计算的平面坐标系 (如 CGCS2000 高斯投影)。"
            )
        else:
            self.gis_notice.setText(
                "⚠️ CRS 提示: 当前未进行 CRS 坐标转换。请不要把本地 CAD 坐标直接当作真实经纬度使用。"
            )

    def _browse_geojson(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择矢量 GeoJSON 文件", "", "GeoJSON 矢量文件 (*.geojson *.json)"
        )
        if file_path:
            self.geojson_file_input.setText(file_path)

    def _on_run_clicked(self):
        idx = self.tabs.currentIndex()
        if idx == 0:
            task_type = "parcel"
            params = {"target_layer": self.parcel_layer_input.text().strip()}
        elif idx == 1:
            task_type = "indicator"
            params = {
                "floors": self.spin_floors.value(),
                "building_layer": self.ind_b_layer.text().strip(),
                "green_layer": self.ind_g_layer.text().strip()
            }
        elif idx == 2:
            task_type = "validate"
            fallback_map = {0: None, 1: "m", 2: "cm", 3: "mm", 4: "ft"}
            params = {
                "setback_m": self.spin_setback.value(),
                "parcel_layer": self.val_p_layer.text().strip(),
                "building_layer": self.val_b_layer.text().strip(),
                "fallback_unit": fallback_map.get(self.combo_fallback.currentIndex())
            }
        elif idx == 3:
            gis_mode = self.gis_mode_combo.currentIndex()
            if gis_mode == 0:
                task_type = "gis_export"
                params = {}
            else:
                task_type = "gis_import"
                unit_map = {0: "m", 1: "cm", 2: "mm", 3: "ft", 4: "in"}
                params = {
                    "geojson_path": self.geojson_file_input.text().strip(),
                    "unit": unit_map.get(self.combo_gis_unit.currentIndex(), "m")
                }
        else:
            return

        self.run_task_signal.emit(task_type, params)

    def set_running_state(self, running: bool):
        """控制运行按钮的状态，防止多重并发点击。"""
        self.btn_run.setEnabled(not running)
        if running:
            self.btn_run.setText("⏳ 任务正在后台计算中...")
        else:
            self.btn_run.setText("🚀 运行所选分析任务 (Run Analysis)")
