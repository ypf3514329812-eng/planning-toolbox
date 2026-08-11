"""任务选择与参数配置区 (Task Zone Widget)."""
from pathlib import Path
from typing import Dict, Any
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QWidget,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton,
    QFileDialog, QScrollArea, QCheckBox
)
from PySide6.QtCore import Signal, Qt
from planning_toolbox.rules.presets import get_rule_preset, list_rule_presets
from planning_toolbox.rules.standards import get_standards_profile, list_standards_profiles
from planning_toolbox.rules.drafting import get_drafting_profile, list_drafting_profiles

class TaskZoneWidget(QFrame):
    """
    任务区：提供 4 大规划分析任务页签及其参数配置表单，包含核心“运行分析”按钮。
    """
    run_task_signal = Signal(str, dict)    # (task_type, params_dict)
    configure_sketchup_buildings_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoneFrame")
        self._sketchup_building_overrides: Dict[str, Dict[str, Any]] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        title = QLabel("规划分析任务与参数 (Analysis Tasks & Settings)")
        title.setObjectName("ZoneTitle")
        layout.addWidget(title)

        # Beginner-friendly examples; these are not legal planning standards.
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("快速填充示例:"))
        self.preset_combo = QComboBox()
        for preset in list_rule_presets():
            self.preset_combo.addItem(preset.name, preset.preset_id)
        self.preset_combo.setToolTip(
            "示例只用于学习和演示；正式项目请按当地规划条件自行填写。"
        )
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        preset_row.addWidget(self.preset_combo, stretch=1)
        layout.addLayout(preset_row)

        # Keep QTabWidget as the page container, but use a single clear
        # selector instead of nine horizontally crowded tabs.
        self.tabs = QTabWidget()

        self._setup_parcel_tab()
        self._setup_indicator_tab()
        self._setup_validate_tab()
        self._setup_gis_tab()
        self._setup_batch_tab()
        self._setup_concept_tab()
        self._setup_layer_tab()
        self._setup_quality_tab()
        self._setup_image_to_cad_tab()
        self._setup_sketchup_tab()

        self.tabs.tabBar().hide()
        task_nav = QHBoxLayout()
        task_nav.setSpacing(8)
        nav_label = QLabel("选择功能:")
        nav_label.setObjectName("NavLabel")
        task_nav.addWidget(nav_label)
        self.task_selector = QComboBox()
        self.task_selector.setObjectName("TaskSelector")
        for index in range(self.tabs.count()):
            self.task_selector.addItem(self.tabs.tabText(index), index)
        self.task_selector.setToolTip("选择需要执行的规划分析或 CAD 辅助功能")
        self.task_selector.currentIndexChanged.connect(self._select_task_page)
        self.tabs.currentChanged.connect(self._sync_task_selector)
        task_nav.addWidget(self.task_selector, stretch=1)
        layout.addLayout(task_nav)

        layout.addWidget(self.tabs)

        self.lbl_preflight = QLabel("请先选择 DXF 文件，系统会自动进行运行前检查。")
        self.lbl_preflight.setObjectName("BadgeInfo")
        self.lbl_preflight.setWordWrap(True)
        layout.addWidget(self.lbl_preflight)

        # 底部大运行按钮
        self.btn_run = QPushButton()
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.clicked.connect(self._on_run_clicked)
        layout.addWidget(self.btn_run)
        self._update_run_button_label()

    def _select_task_page(self, index: int):
        """Switch task pages from the compact beginner-friendly selector."""
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)
        self._update_run_button_label()

    def _sync_task_selector(self, index: int):
        """Keep saved projects and programmatic tab changes in sync."""
        if self.task_selector.currentIndex() != index:
            self.task_selector.blockSignals(True)
            self.task_selector.setCurrentIndex(index)
            self.task_selector.blockSignals(False)
        self._update_run_button_label()

    def _update_run_button_label(self):
        if not hasattr(self, "btn_run") or not hasattr(self, "task_selector"):
            return
        task_name = self.task_selector.currentText().strip()
        self.btn_run.setText(f"🚀 运行：{task_name}")

    # ─── 1. 地块面积与编号 Tab ───
    def _setup_parcel_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.parcel_layer_input = QLineEdit("PARCEL")
        form.addRow("目标地块图层名称:", self.parcel_layer_input)

        info = QLabel("💡 功能说明: 自动识别目标图层闭合多边形、去重嵌套环、按确定性规则排序编号并输出标注 DXF、CSV 统计表与 GeoJSON。")
        info.setStyleSheet("color: #74766F; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)

        self._add_scrollable_tab(tab, "1. 地块面积与编号")

    # ─── 2. 规划指标计算 Tab ───
    def _setup_indicator_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.spin_floors = QSpinBox()
        self.spin_floors.setRange(0, 200)
        self.spin_floors.setValue(0)
        self.spin_floors.setSpecialValueText("未指定（必须填写）")
        self.spin_floors.setToolTip("请根据规划条件明确填写楼层倍数；系统不会自动假设楼层数")
        form.addRow("建筑楼层倍数 (必填):", self.spin_floors)

        self.ind_b_layer = QLineEdit("BUILDING")
        form.addRow("建筑轮廓图层:", self.ind_b_layer)

        self.ind_g_layer = QLineEdit("GREEN")
        form.addRow("绿地范围图层:", self.ind_g_layer)

        notice = QLabel("⚠️ 注意: 楼层数会用于估算总建筑面积。不同建筑楼层不一致时，请谨慎使用。程序将自动执行空间求交并去重重叠轮廓。")
        notice.setStyleSheet("color: #A6814D; font-size: 12px;")
        notice.setWordWrap(True)
        form.addRow(notice)

        self._add_scrollable_tab(tab, "2. 规划指标计算")

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
        info.setStyleSheet("color: #74766F; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)

        self._add_scrollable_tab(tab, "3. 拓扑与建筑退线检查")

    # ─── 4. GIS 导出/导入 Tab ───
    def _setup_gis_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.gis_mode_combo = QComboBox()
        self.gis_mode_combo.addItem("CAD DXF 导出至 GeoJSON（轻量兼容）", "dxf_to_geojson")
        self.gis_mode_combo.addItem("GeoJSON 导入至 CAD DXF（轻量兼容）", "geojson_to_dxf")
        self.gis_mode_combo.addItem("GeoPackage / Shapefile 导入至 CAD DXF", "vector_to_dxf")
        self.gis_mode_combo.addItem("CAD DXF 导出至 GeoPackage", "dxf_to_gpkg")
        self.gis_mode_combo.currentIndexChanged.connect(self._on_gis_mode_changed)
        form.addRow("GIS 操作模式:", self.gis_mode_combo)

        # 导入专用行
        self.geojson_file_input = QLineEdit()
        self.geojson_file_input.setPlaceholderText("请选择要导入的 GIS 矢量文件...")
        self.btn_browse_geojson = QPushButton("选择 GIS 文件...")
        self.btn_browse_geojson.clicked.connect(self._browse_geojson)
        
        geojson_box = QHBoxLayout()
        geojson_box.addWidget(self.geojson_file_input)
        geojson_box.addWidget(self.btn_browse_geojson)
        
        self.lbl_geojson = QLabel("GIS 矢量文件:")
        form.addRow(self.lbl_geojson, geojson_box)

        self.combo_gis_unit = QComboBox()
        self.combo_gis_unit.addItems(["m (米)", "cm (厘米)", "mm (毫米)", "ft (英尺)", "in (英寸)"])
        self.lbl_gis_unit = QLabel("DXF 写入单位:")
        form.addRow(self.lbl_gis_unit, self.combo_gis_unit)

        # 警告提示
        self.gis_notice = QLabel(
            "⚠️ CRS 提示: 当前未进行 CRS 坐标转换。请不要把本地 CAD 坐标直接当作真实经纬度使用。"
        )
        self.gis_notice.setStyleSheet("color: #A6814D; font-size: 12px;")
        self.gis_notice.setWordWrap(True)
        form.addRow(self.gis_notice)

        self._on_gis_mode_changed(0)  # 默认导出模式
        self._add_scrollable_tab(tab, "4. GIS 导出与导入")

    def _setup_batch_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.batch_folder_input = QLineEdit()
        self.batch_folder_input.setPlaceholderText("请选择包含多张 DXF 图纸的文件夹...")
        self.btn_browse_batch_folder = QPushButton("选择文件夹...")
        self.btn_browse_batch_folder.clicked.connect(self._browse_batch_folder)
        folder_box = QHBoxLayout()
        folder_box.addWidget(self.batch_folder_input)
        folder_box.addWidget(self.btn_browse_batch_folder)
        form.addRow("DXF 文件夹:", folder_box)

        self.batch_task_combo = QComboBox()
        self.batch_task_combo.addItems(["地块面积与编号", "规划指标计算"])
        form.addRow("批量任务:", self.batch_task_combo)

        self.batch_floors = QSpinBox()
        self.batch_floors.setRange(0, 200)
        self.batch_floors.setValue(0)
        self.batch_floors.setSpecialValueText("未指定（指标任务必须填写）")
        form.addRow("指标楼层倍数:", self.batch_floors)

        info = QLabel(
            "批量任务会为每张 DXF 建立独立结果文件夹，并生成 batch_summary.csv。"
            "单张图纸失败时会记录原因，不影响其他图纸继续处理。"
        )
        info.setStyleSheet("color: #74766F; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)
        self._add_scrollable_tab(tab, "5. 批量分析")

    def _setup_concept_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.concept_standard_profile = QComboBox()
        for profile in list_standards_profiles():
            self.concept_standard_profile.addItem(profile.name, profile.profile_id)
        self.concept_standard_profile.currentIndexChanged.connect(self._on_standard_profile_changed)
        form.addRow("规范依据框架:", self.concept_standard_profile)

        self.lbl_concept_standard = QLabel()
        self.lbl_concept_standard.setWordWrap(True)
        self.lbl_concept_standard.setStyleSheet("color: #74766F; font-size: 12px;")
        form.addRow(self.lbl_concept_standard)

        self.concept_layout_style = QComboBox()
        self.concept_layout_style.addItem("自然曲线（推荐）", "organic")
        self.concept_layout_style.addItem("简洁矩形", "rectilinear")
        self.concept_layout_style.setToolTip(
            "自然曲线会生成圆角建筑、弧形通道和更接近人工方案草图的空间轮廓"
        )
        form.addRow("概念方案布局风格:", self.concept_layout_style)

        self.concept_building_count = QSpinBox()
        self.concept_building_count.setRange(1, 20)
        self.concept_building_count.setValue(1)
        self.concept_building_count.setToolTip("每个有效地块生成的概念建筑数量，不代表最终建筑单体数量")
        form.addRow("每个地块建筑数量:", self.concept_building_count)

        self.concept_coverage = QDoubleSpinBox()
        self.concept_coverage.setRange(1.0, 80.0)
        self.concept_coverage.setDecimals(1)
        self.concept_coverage.setValue(25.0)
        self.concept_coverage.setSuffix(" %")
        form.addRow("概念建筑覆盖率:", self.concept_coverage)

        self.concept_setback = QDoubleSpinBox()
        self.concept_setback.setRange(0.0, 100.0)
        self.concept_setback.setDecimals(1)
        self.concept_setback.setValue(5.0)
        self.concept_setback.setSuffix(" m")
        form.addRow("建筑退线距离:", self.concept_setback)

        self.concept_building_gap = QDoubleSpinBox()
        self.concept_building_gap.setRange(0.0, 100.0)
        self.concept_building_gap.setDecimals(1)
        self.concept_building_gap.setValue(0.0)
        self.concept_building_gap.setSpecialValueText("未指定（只避免建筑重叠）")
        self.concept_building_gap.setSuffix(" m")
        self.concept_building_gap.setToolTip("可选的概念建筑间距约束；正式项目请按当地规范填写")
        form.addRow("概念建筑间距（选填）:", self.concept_building_gap)

        self.concept_access_width = QDoubleSpinBox()
        self.concept_access_width.setRange(0.0, 100.0)
        self.concept_access_width.setDecimals(1)
        self.concept_access_width.setValue(0.0)
        self.concept_access_width.setSpecialValueText("未指定（不生成通道）")
        self.concept_access_width.setSuffix(" m")
        self.concept_access_width.setToolTip("可选的概念道路/消防通道宽度；正式项目请按当地规范和道路条件复核")
        form.addRow("概念道路/消防通道宽度（选填）:", self.concept_access_width)

        self.concept_floors = QSpinBox()
        self.concept_floors.setRange(0, 200)
        self.concept_floors.setValue(0)
        self.concept_floors.setSpecialValueText("未指定（不估算总建筑面积）")
        self.concept_floors.setToolTip("填写后可估算概念总建筑面积；程序不会替你猜楼层数")
        form.addRow("概念建筑层数（选填）:", self.concept_floors)

        self.concept_parking_ratio = QDoubleSpinBox()
        self.concept_parking_ratio.setRange(0.0, 100.0)
        self.concept_parking_ratio.setDecimals(1)
        self.concept_parking_ratio.setValue(0.0)
        self.concept_parking_ratio.setSpecialValueText("未指定（不估算停车位）")
        self.concept_parking_ratio.setSuffix(" 个/1000m²")
        self.concept_parking_ratio.setToolTip("选填的学习估算参数；填写停车配比后必须同时填写楼层数")
        form.addRow("概念停车配比（选填）:", self.concept_parking_ratio)

        self.concept_parcel_layer = QLineEdit("PARCEL")
        form.addRow("地块图层名称:", self.concept_parcel_layer)

        self.concept_fallback = QComboBox()
        self.concept_fallback.addItems(["严格检查（单位未知时阻断）", "m (米)", "cm (厘米)", "mm (毫米)", "ft (英尺)"])
        form.addRow("单位回退策略:", self.concept_fallback)

        info = QLabel(
            "🧩 说明：系统会在每个有效地块内生成简单的矩形建筑轮廓、退线边界和剩余绿地轮廓，输出独立 DXF。"
            "填写楼层和停车配比后，还会估算总建筑面积并生成概念停车位。"
            "填写建筑间距后，会尽量按地块主方向布置并保持该间距。"
            "填写道路/消防通道宽度后，建筑和停车位会避开概念通道。"
            "这是概念草图，不是法定规划方案、施工图或审批成果，请在 CAD 中继续调整和复核。"
        )
        info.setStyleSheet("color: #A6814D; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)
        self._add_scrollable_tab(tab, "6. 方案草图生成")
        self._on_standard_profile_changed(0)

    def _setup_layer_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.layer_use_china_standard = QCheckBox("使用中国标准制图辅助（推荐）")
        self.layer_use_china_standard.setChecked(True)
        self.layer_use_china_standard.setToolTip(
            "启用后按所选课程/规划图件模板建立图层、统一样式并生成辅助检查报告；不等于法定审查通过"
        )
        form.addRow("制图辅助:", self.layer_use_china_standard)

        self.layer_drafting_profile = QComboBox()
        for profile in list_drafting_profiles():
            self.layer_drafting_profile.addItem(profile.name, profile.profile_id)
        form.addRow("中国制图模板:", self.layer_drafting_profile)

        self.lbl_layer_drafting_profile = QLabel()
        self.lbl_layer_drafting_profile.setWordWrap(True)
        self.lbl_layer_drafting_profile.setStyleSheet("color: #74766F; font-size: 12px;")
        form.addRow(self.lbl_layer_drafting_profile)

        self.layer_drafting_profile.currentIndexChanged.connect(
            self._on_drafting_profile_changed
        )
        self.layer_use_china_standard.toggled.connect(
            self._update_layer_drafting_controls
        )

        info = QLabel(
            "🧹 功能说明：识别常见中文/英文图层别名，生成新的标准化 DXF、图层报告和"
            "中国制图辅助检查。原始图纸不会被覆盖。"
        )
        info.setStyleSheet("color: #74766F; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)

        notice = QLabel(
            "系统只检查单位、图层和辅助样式；地方退线、停车配比、消防、审批要求仍须人工核对。"
            "无法识别的自定义图层会保留并写入报告。"
        )
        notice.setStyleSheet("color: #A6814D; font-size: 12px;")
        notice.setWordWrap(True)
        form.addRow(notice)
        self._add_scrollable_tab(tab, "7. CAD 图层标准化")
        self._on_drafting_profile_changed(0)
        self._update_layer_drafting_controls(True)

    def _setup_quality_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.quality_repair_profile = QComboBox()
        self.quality_repair_profile.addItem("最低人工修改（推荐）", "minimize_manual")
        self.quality_repair_profile.addItem("安全修复（仅明确问题）", "safe")
        self.quality_repair_profile.addItem("只检查，不修改", "inspect")
        self.quality_repair_profile.setToolTip(
            "推荐模式会合并无分叉碎线并清理冗余顶点；遇到路口、曲线和块参照会停止并要求人工复核"
        )
        form.addRow("自动整理模式:", self.quality_repair_profile)

        self.quality_remove_duplicates = QComboBox()
        self.quality_remove_duplicates.addItems(["修复精确重复多段线", "只检查，不删除重复线"])
        form.addRow("重复线处理:", self.quality_remove_duplicates)

        self.quality_close_near = QComboBox()
        self.quality_close_near.addItems(["修复近闭合断线", "只检查，不自动闭合"])
        form.addRow("近闭合断线处理:", self.quality_close_near)

        self.quality_tolerance = QDoubleSpinBox()
        self.quality_tolerance.setRange(0.0, 100.0)
        self.quality_tolerance.setDecimals(4)
        self.quality_tolerance.setValue(0.01)
        self.quality_tolerance.setSuffix(" 图纸单位")
        self.quality_tolerance.setToolTip("仅当断线首尾距离不超过该容差时才会自动闭合；不确定时请保持只检查。")
        form.addRow("近闭合判断容差:", self.quality_tolerance)

        self.quality_remove_duplicate_lines = QCheckBox("删除同图层的精确重复 LINE")
        self.quality_remove_duplicate_lines.setChecked(True)
        form.addRow("散线去重:", self.quality_remove_duplicate_lines)

        self.quality_merge_fragments = QCheckBox("连接同图层、同线型、无分叉的碎线链")
        self.quality_merge_fragments.setChecked(True)
        form.addRow("碎线合并:", self.quality_merge_fragments)

        self.quality_join_tolerance = QDoubleSpinBox()
        self.quality_join_tolerance.setRange(0.0, 100.0)
        self.quality_join_tolerance.setDecimals(4)
        self.quality_join_tolerance.setValue(0.05)
        self.quality_join_tolerance.setSuffix(" 图纸单位")
        self.quality_join_tolerance.setToolTip(
            "两个端点距离不超过该值时才会吸附连接；分叉节点始终跳过"
        )
        form.addRow("碎线连接容差:", self.quality_join_tolerance)

        self.quality_simplify_collinear = QCheckBox("删除直线多段线中的共线冗余顶点")
        self.quality_simplify_collinear.setChecked(True)
        form.addRow("共线点清理:", self.quality_simplify_collinear)

        self.quality_collinear_tolerance = QDoubleSpinBox()
        self.quality_collinear_tolerance.setRange(0.0, 100.0)
        self.quality_collinear_tolerance.setDecimals(4)
        self.quality_collinear_tolerance.setValue(0.01)
        self.quality_collinear_tolerance.setSuffix(" 图纸单位")
        form.addRow("共线判断容差:", self.quality_collinear_tolerance)

        self.quality_remove_short_vertices = QCheckBox("清理多段线中的重复点和极短段")
        self.quality_remove_short_vertices.setChecked(True)
        form.addRow("极短段清理:", self.quality_remove_short_vertices)

        self.quality_min_segment_length = QDoubleSpinBox()
        self.quality_min_segment_length.setRange(0.0, 100.0)
        self.quality_min_segment_length.setDecimals(4)
        self.quality_min_segment_length.setValue(0.01)
        self.quality_min_segment_length.setSuffix(" 图纸单位")
        form.addRow("最短保留线段:", self.quality_min_segment_length)

        self.quality_standardize_layers = QCheckBox("同时按内置别名整理规划图层")
        self.quality_standardize_layers.setChecked(True)
        form.addRow("语义图层整理:", self.quality_standardize_layers)

        info = QLabel(
            "🧪 说明：推荐模式会把同图层、同线型且无分叉的 LINE/开放多段线连接成可编辑多段线，"
            "并清理共线冗余点、极短段和常见图层别名。所有修改另存为新 DXF 和逐项 CSV，原图不变。"
        )
        info.setStyleSheet("color: #74766F; font-size: 12px;")
        info.setWordWrap(True)
        form.addRow(info)

        warning = QLabel(
            "⚠️ 深度整理要求 DXF 已设置明确单位。分叉路口、圆弧/SPLINE、自交、块参照和无法识别图层"
            "不会被强行处理，仍会保留给你复核。"
        )
        warning.setStyleSheet("color: #A6814D; font-size: 12px;")
        warning.setWordWrap(True)
        form.addRow(warning)
        self.quality_repair_profile.currentIndexChanged.connect(
            self._on_quality_profile_changed
        )
        for checkbox in (
            self.quality_merge_fragments,
            self.quality_simplify_collinear,
            self.quality_remove_short_vertices,
        ):
            checkbox.toggled.connect(self._update_quality_controls)
        self._on_quality_profile_changed(0)
        self._add_scrollable_tab(tab, "8. 图纸质量增强检查")

    def _on_quality_profile_changed(self, _index: int):
        """Apply beginner-friendly repair presets; users may still fine-tune."""
        profile = self.quality_repair_profile.currentData()
        if profile == "minimize_manual":
            self.quality_remove_duplicates.setCurrentIndex(0)
            self.quality_close_near.setCurrentIndex(0)
            self.quality_remove_duplicate_lines.setChecked(True)
            self.quality_merge_fragments.setChecked(True)
            self.quality_simplify_collinear.setChecked(True)
            self.quality_remove_short_vertices.setChecked(True)
            self.quality_standardize_layers.setChecked(True)
        elif profile == "safe":
            self.quality_remove_duplicates.setCurrentIndex(0)
            self.quality_close_near.setCurrentIndex(0)
            self.quality_remove_duplicate_lines.setChecked(False)
            self.quality_merge_fragments.setChecked(False)
            self.quality_simplify_collinear.setChecked(False)
            self.quality_remove_short_vertices.setChecked(False)
            self.quality_standardize_layers.setChecked(False)
        else:
            self.quality_remove_duplicates.setCurrentIndex(1)
            self.quality_close_near.setCurrentIndex(1)
            self.quality_remove_duplicate_lines.setChecked(False)
            self.quality_merge_fragments.setChecked(False)
            self.quality_simplify_collinear.setChecked(False)
            self.quality_remove_short_vertices.setChecked(False)
            self.quality_standardize_layers.setChecked(False)
        self._update_quality_controls()

    def _update_quality_controls(self):
        self.quality_join_tolerance.setEnabled(self.quality_merge_fragments.isChecked())
        self.quality_collinear_tolerance.setEnabled(
            self.quality_simplify_collinear.isChecked()
        )
        self.quality_min_segment_length.setEnabled(
            self.quality_remove_short_vertices.isChecked()
        )

    def _setup_image_to_cad_tab(self):
        """Configure the local, no-API standardized image-to-CAD workflow."""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.image_file_input = QLineEdit()
        self.image_file_input.setPlaceholderText("选择俯视平面效果图（PNG / JPG / JPEG）")
        self.btn_browse_image = QPushButton("浏览图片...")
        self.btn_browse_image.clicked.connect(self._browse_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_file_input, stretch=1)
        image_row.addWidget(self.btn_browse_image)
        form.addRow("输入 AI 效果图:", image_row)

        self.image_conversion_mode = QComboBox()
        self.image_conversion_mode.addItem("彩色分区 CAD（建筑/道路/绿地）", "color_regions")
        self.image_conversion_mode.addItem("黑白线稿 CAD（自动识别黑/白底色）", "black_white_linework")
        self.image_conversion_mode.addItem(
            "原图 + 彩色语义引导图（道路/建筑范围更可靠）",
            "semantic_guide",
        )
        self.image_conversion_mode.currentIndexChanged.connect(self._update_image_mode_controls)
        self.image_conversion_mode.setToolTip(
            "彩色模式直接识别标准色；黑白模式自动提取线条；"
            "语义引导模式保留原图作锁定底图，只读取另一张同尺寸标准色图片中的对象范围"
        )
        form.addRow("图片转 CAD 模式:", self.image_conversion_mode)

        self.image_semantic_guide_input = QLineEdit()
        self.image_semantic_guide_input.setPlaceholderText(
            "选择与原图像素尺寸完全一致的标准颜色引导图"
        )
        self.btn_browse_semantic_guide = QPushButton("浏览引导图...")
        self.btn_browse_semantic_guide.clicked.connect(self._browse_semantic_guide)
        self.btn_edit_semantic_guide = QPushButton("新建/编辑引导图...")
        self.btn_edit_semantic_guide.setToolTip(
            "在软件内直接给道路、建筑、绿地、水体和停车范围涂标准色；"
            "原图只读，保存后自动填入本页。"
        )
        self.btn_edit_semantic_guide.clicked.connect(self._edit_semantic_guide)
        self.image_semantic_guide_row = QWidget()
        semantic_guide_layout = QHBoxLayout(self.image_semantic_guide_row)
        semantic_guide_layout.setContentsMargins(0, 0, 0, 0)
        semantic_guide_layout.addWidget(self.image_semantic_guide_input, stretch=1)
        semantic_guide_layout.addWidget(self.btn_browse_semantic_guide)
        semantic_guide_layout.addWidget(self.btn_edit_semantic_guide)
        self.lbl_image_semantic_guide = QLabel("语义引导图:")
        form.addRow(self.lbl_image_semantic_guide, self.image_semantic_guide_row)

        self.image_reference_width = QDoubleSpinBox()
        self.image_reference_width.setRange(0.0, 1000000.0)
        self.image_reference_width.setDecimals(2)
        self.image_reference_width.setValue(0.0)
        self.image_reference_width.setSpecialValueText("必须填写（例如 100 m）")
        self.image_reference_width.setSuffix(" m")
        self.image_reference_width.setToolTip("请填写图片中整个场地实际宽度；系统不会猜测比例")
        form.addRow("场地实际宽度:", self.image_reference_width)

        self.image_color_tolerance = QSpinBox()
        self.image_color_tolerance.setRange(5, 150)
        self.image_color_tolerance.setValue(55)
        self.image_color_tolerance.setSuffix(" 色差")
        self.image_color_tolerance.setToolTip("效果图颜色不够标准时可适当调大；过大可能把不同区域混在一起")
        form.addRow("颜色识别容差:", self.image_color_tolerance)

        self.image_min_component_pixels = QSpinBox()
        self.image_min_component_pixels.setRange(4, 1000000)
        self.image_min_component_pixels.setValue(80)
        self.image_min_component_pixels.setSuffix(" 像素")
        self.image_min_component_pixels.setToolTip("过滤很小的噪点；细小建筑或停车位需要适当调小")
        form.addRow("最小识别区域:", self.image_min_component_pixels)

        self.image_line_threshold = QSpinBox()
        self.image_line_threshold.setRange(20, 250)
        self.image_line_threshold.setValue(220)
        self.image_line_threshold.setSuffix(" 灰度")
        self.image_line_threshold.setToolTip("仅黑白线稿模式使用；数值越大，越容易识别浅灰色线条")
        form.addRow("黑白线条阈值:", self.image_line_threshold)

        self.image_line_polarity = QComboBox()
        self.image_line_polarity.addItem("自动判断底色（推荐）", "auto")
        self.image_line_polarity.addItem("白底黑线", "dark_on_light")
        self.image_line_polarity.addItem("黑底白线", "light_on_dark")
        self.image_line_polarity.setToolTip(
            "自动模式根据图片边缘的主要底色判断；识别错误时可以手动指定"
        )
        form.addRow("线稿底色:", self.image_line_polarity)

        self.image_detail_level = QComboBox()
        self.image_detail_level.addItem("标准（速度较快）", "standard")
        self.image_detail_level.addItem("精细（推荐）", "fine")
        self.image_detail_level.addItem("极精细（处理较慢）", "ultra")
        self.image_detail_level.setCurrentIndex(1)
        self.image_detail_level.setToolTip(
            "黑白线稿模式使用更高处理分辨率和更少的线条简化；图片越大，处理时间越长"
        )
        form.addRow("线稿细节级别:", self.image_detail_level)

        self.image_optimize_linework = QCheckBox(
            "自动整理线条（连接短段、保护旋转建筑、归并树木/停车位并拟合规则曲线）"
        )
        self.image_optimize_linework.setChecked(True)
        self.image_optimize_linework.setToolTip(
            "推荐开启。精细/极精细模式会按方向连接可安全合并的短线，"
            "把重复小圆形符号和成组停车位转换为块，并输出建筑/景观候选图层；候选仍需人工确认"
        )
        form.addRow("", self.image_optimize_linework)

        self.image_focus_site_only = QCheckBox("只识别主要基地，忽略外围道路和图框噪声")
        self.image_focus_site_only.setChecked(True)
        self.image_focus_site_only.setToolTip(
            "适合带城市外围道路、图框或留白的参考图；系统会根据主要非道路区域自动限定识别范围"
        )
        form.addRow("", self.image_focus_site_only)

        self.image_use_knowledge_assist = QCheckBox(
            "使用已确认的精修 CAD 知识辅助校正（推荐）"
        )
        self.image_use_knowledge_assist.setChecked(True)
        self.image_use_knowledge_assist.setToolTip(
            "只使用标记为 user_curated 的人工精修 DXF。仅对尺寸相近的建筑、停车位和树木候选做保守吸附；没有样本时保持原算法"
        )
        form.addRow("", self.image_use_knowledge_assist)

        self.image_create_knowledge_card = QCheckBox(
            "生成轻量 Markdown 图纸知识卡（推荐，不复制原图）"
        )
        self.image_create_knowledge_card.setChecked(True)
        self.image_create_knowledge_card.setToolTip(
            "只保存原图指纹、比例依据、识别摘要、复核状态和成果路径；不会把图片嵌入知识卡"
        )
        self.image_create_knowledge_card.stateChanged.connect(
            self._update_knowledge_controls
        )
        form.addRow("", self.image_create_knowledge_card)

        self.image_knowledge_project_type = QComboBox()
        self.image_knowledge_project_type.addItems(
            [
                "待确认",
                "居住区总平面",
                "校园规划",
                "公园与绿地",
                "城市设计",
                "道路与交通",
                "其他规划图",
            ]
        )
        self.image_knowledge_project_type.setToolTip("用于以后按作业或规划类型查找相似知识卡")
        form.addRow("知识卡图纸类型:", self.image_knowledge_project_type)

        self.image_knowledge_tags = QLineEdit()
        self.image_knowledge_tags.setPlaceholderText("可选，例如：住宅、曲线道路、停车位（逗号分隔）")
        self.image_knowledge_tags.setToolTip("标签只用于本地检索，不会上传")
        form.addRow("本地检索标签:", self.image_knowledge_tags)

        self.image_collect_cad_sample = QCheckBox(
            "收藏本次 DXF 为候选 CAD 样本（可选，会复制一份文件）"
        )
        self.image_collect_cad_sample.setChecked(False)
        self.image_collect_cad_sample.setToolTip(
            "只在本次结果确实值得保留时勾选。生成结果先标为未复核候选；人工精修后才能作为确认样本"
        )
        form.addRow("", self.image_collect_cad_sample)
        self._update_knowledge_controls()
        self._update_image_mode_controls()

        info = QLabel(
            "🖼️ 适合导入：俯视、正交、无透视的平面图。彩色图使用低饱和度标准分区；"
            "黑白图支持白底黑线或黑底白线。自动整理会连接安全短段、识别旋转建筑、归并重复树木/停车位，并把候选对象分层。"
            "道路边界复杂时可选“原图 + 彩色语义引导图”：原图保持不变，引导图只负责告诉系统哪里是道路、建筑或绿地。"
            "默认还会生成一份不嵌入原图的轻量 Markdown 知识卡。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #74766F; font-size: 12px;")
        form.addRow(info)

        warning = QLabel(
            "⚠️ 这是“效果图转概念草图”，不是自动识别真实建筑的审批 CAD。阴影、文字、透视、树木纹理和复杂材质"
            "可能被识别为噪点；所有名称含 CANDIDATE 的图层都必须逐一确认。整个过程不需要 API，原图不会被修改。"
            "只有主动勾选时才会复制 CAD 候选样本；更推荐完成精修后用结果区的“收藏精修 CAD”。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #A6814D; font-size: 12px;")
        form.addRow(warning)
        self._add_scrollable_tab(tab, "9. AI 效果图转 CAD")

    def _setup_sketchup_tab(self):
        """Configure the lightweight, local CAD-to-SketchUp handoff."""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(12, 12, 12, 12)

        self.sketchup_building_layers = QLineEdit(
            "BUILDING, CONCEPT_BUILDING, AI_BUILDING, BW_BUILDING_CANDIDATE"
        )
        self.sketchup_building_layers.setToolTip(
            "这些图层中的闭合轮廓会被视为建筑；多个图层请用逗号分隔"
        )
        form.addRow("建筑图层名称:", self.sketchup_building_layers)

        building_schedule_row = QHBoxLayout()
        self.btn_sketchup_building_schedule = QPushButton("逐栋设置高度与模型样式…")
        self.btn_sketchup_building_schedule.setToolTip(
            "从当前 DXF 只读列出建筑，可为不同建筑分别设置楼层、层高、类型、屋顶和精度"
        )
        self.btn_sketchup_building_schedule.clicked.connect(
            self.configure_sketchup_buildings_signal.emit
        )
        building_schedule_row.addWidget(self.btn_sketchup_building_schedule)
        self.lbl_sketchup_building_schedule = QLabel("未单独设置；全部使用下方全局参数")
        self.lbl_sketchup_building_schedule.setWordWrap(True)
        building_schedule_row.addWidget(self.lbl_sketchup_building_schedule, stretch=1)
        form.addRow("逐栋参数:", building_schedule_row)

        self.sketchup_floors = QSpinBox()
        self.sketchup_floors.setRange(0, 200)
        self.sketchup_floors.setValue(0)
        self.sketchup_floors.setSpecialValueText("二维（不生成高度）")
        self.sketchup_floors.setToolTip(
            "0 表示只生成二维可编辑线面；需要体量时请填写真实楼层数"
        )
        form.addRow("建筑楼层数:", self.sketchup_floors)

        self.sketchup_floor_height = QDoubleSpinBox()
        self.sketchup_floor_height.setRange(0.0, 20.0)
        self.sketchup_floor_height.setDecimals(2)
        self.sketchup_floor_height.setSingleStep(0.1)
        self.sketchup_floor_height.setValue(0.0)
        self.sketchup_floor_height.setSpecialValueText("未指定")
        self.sketchup_floor_height.setSuffix(" m")
        self.sketchup_floor_height.setToolTip(
            "生成三维建筑时必须明确填写标准层高；系统不会自动猜测"
        )
        form.addRow("标准层高:", self.sketchup_floor_height)

        self.sketchup_model_detail = QComboBox()
        self.sketchup_model_detail.addItem("课程作业（推荐）", "course")
        self.sketchup_model_detail.addItem("快速体量（最省内存）", "massing")
        self.sketchup_model_detail.addItem("汇报模型（更多立面细节）", "presentation")
        self.sketchup_model_detail.setToolTip(
            "课程作业会生成入口、复用雨棚、基座、楼层线、屋顶、共享窗和轻量树木；汇报模型还增加住宅阳台、屋顶设备、街灯和完整场地边缘细节；快速体量只保留最轻体块"
        )
        form.addRow("模型精度:", self.sketchup_model_detail)

        self.sketchup_road_design = QComboBox()
        self.sketchup_road_design.addItem("跟随模型精度（推荐）", "auto")
        self.sketchup_road_design.addItem("完整街道（人行道 + 边线 + 箭头 + 街灯）", "complete")
        self.sketchup_road_design.addItem("基础车行道（路缘 + 标线）", "basic")
        self.sketchup_road_design.addItem("关闭道路细化（仅保留 CAD 面）", "off")
        self.sketchup_road_design.setToolTip(
            "只影响闭合、接近矩形的 ROAD 道路面；不规则道路会安全保留原 CAD 轮廓。"
            "完整街道是教学与汇报表达预设，并非规范符合性证明。"
        )
        form.addRow("道路建模:", self.sketchup_road_design)

        self.sketchup_centerline_corridor = QCheckBox(
            "明确中心线生成概念道路带（宽度需复核）"
        )
        self.sketchup_centerline_corridor.setChecked(False)
        self.sketchup_centerline_corridor.setToolTip(
            "仅对 ROAD_CENTERLINE / ROAD_AXIS / CENTERLINE 图层中的 ARC、SPLINE 或开放线生效；"
            "道路宽度可使用下方明确输入的总宽度；填 0 使用知识库默认值，生成后仍必须人工复核。普通线条不会自动变成道路。"
        )
        form.addRow("中心线道路带:", self.sketchup_centerline_corridor)

        self.sketchup_centerline_confidence_policy = QComboBox()
        self.sketchup_centerline_confidence_policy.addItem(
            "仅高可信候选生成实体（推荐）", "trusted_only"
        )
        self.sketchup_centerline_confidence_policy.addItem(
            "全部候选生成实体（需逐条复核）", "all"
        )
        self.sketchup_centerline_confidence_policy.setToolTip(
            "推荐模式会把置信度低于 0.65 的图像识别道路保留为中心线线索，"
            "但不生成有宽度的道路实体；手工绘制且没有识别置信度的道路中心线不受影响。"
        )
        self.sketchup_centerline_confidence_policy.setEnabled(False)
        self.sketchup_centerline_corridor.toggled.connect(
            self.sketchup_centerline_confidence_policy.setEnabled
        )
        form.addRow("候选可信度:", self.sketchup_centerline_confidence_policy)

        self.sketchup_centerline_width = QDoubleSpinBox()
        self.sketchup_centerline_width.setRange(0.0, 60.0)
        self.sketchup_centerline_width.setDecimals(1)
        self.sketchup_centerline_width.setSingleStep(0.5)
        self.sketchup_centerline_width.setValue(0.0)
        self.sketchup_centerline_width.setSpecialValueText(
            "使用知识库默认宽度（6.0 m）"
        )
        self.sketchup_centerline_width.setSuffix(" m")
        self.sketchup_centerline_width.setToolTip(
            "输入概念道路总宽度（包含两侧人行道）；推荐按题目或现状资料填写。"
            "4–60 m 有效，填 0 使用知识库默认值，结果仍需专业复核。"
        )
        self.sketchup_centerline_corridor.toggled.connect(
            self.sketchup_centerline_width.setEnabled
        )
        self.sketchup_centerline_width.setEnabled(False)
        form.addRow("中心线道路带总宽:", self.sketchup_centerline_width)

        self.sketchup_building_type = QComboBox()
        self.sketchup_building_type.addItem("按项目类型自动判断", "auto")
        self.sketchup_building_type.addItem("居住建筑", "residential")
        self.sketchup_building_type.addItem("办公建筑", "office")
        self.sketchup_building_type.addItem("商业建筑", "commercial")
        self.sketchup_building_type.addItem("校园建筑", "campus")
        self.sketchup_building_type.addItem("通用建筑", "generic")
        self.sketchup_building_type.setToolTip(
            "决定窗宽、窗高和立面模数；自动模式会优先读取项目类型"
        )
        form.addRow("建筑类型:", self.sketchup_building_type)

        self.sketchup_roof_type = QComboBox()
        self.sketchup_roof_type.addItem("平屋顶 + 女儿墙", "flat")
        self.sketchup_roof_type.addItem("双坡屋顶", "gable")
        self.sketchup_roof_type.addItem("四坡屋顶", "hip")
        self.sketchup_roof_type.setToolTip(
            "坡屋顶适用于四边形建筑；其他复杂轮廓会安全退回平屋顶"
        )
        form.addRow("屋顶形式:", self.sketchup_roof_type)

        self.sketchup_incremental_update = QCheckBox(
            "重复导入时只更新变化对象，并保护已锁定的手工调整"
        )
        self.sketchup_incremental_update.setChecked(True)
        self.sketchup_incremental_update.setToolTip(
            "推荐开启。可在 SketchUp 的扩展程序菜单中锁定重点建筑，后续导入不会覆盖"
        )
        form.addRow("减少返工:", self.sketchup_incremental_update)

        self.sketchup_include_open = QCheckBox("同时交接道路中心线、边界线等开放线条")
        self.sketchup_include_open.setChecked(True)
        form.addRow("开放线条:", self.sketchup_include_open)

        self.sketchup_include_blocks = QCheckBox("保留 INSERT 与嵌套 INSERT 为可编辑分组")
        self.sketchup_include_blocks.setChecked(True)
        self.sketchup_include_blocks.setToolTip(
            "推荐开启。树木块会复用三维树；PT_PLANTER、PT_PARASOL、PT_CROSSWALK、"
            "PT_TRAFFIC_LIGHT 可分别调用花池、遮阳伞、斑马线和交通灯组件。普通 PT_CROSSWALK "
            "会按最近的可信道路自动校正方向；弯道和环岛会使用局部切线；明确命名为 ROAD_CENTERLINE "
            "的开放 ARC/SPLINE 也可辅助方向。圆形道路只有放在 ROUNDABOUT 或“环岛”图层时才生成环带，"
            "不会把中央岛填成实心圆。需要完全保留 CAD 角度时使用 PT_CROSSWALK_FIXED。"
            "其他块保留父子分组关系"
        )
        form.addRow("块参照:", self.sketchup_include_blocks)

        self.sketchup_include_faces = QCheckBox("交接 3DFACE / SOLID / TRACE 三维面")
        self.sketchup_include_faces.setChecked(True)
        self.sketchup_include_faces.setToolTip(
            "适合已有简单三维场地或体块面；非平面或损坏的面仍可能退化为边线"
        )
        form.addRow("三维面:", self.sketchup_include_faces)

        self.sketchup_include_text = QCheckBox("交接 TEXT / MTEXT 为 SketchUp 标签（可选）")
        self.sketchup_include_text.setChecked(False)
        self.sketchup_include_text.setToolTip(
            "默认关闭以避免大量标注挤满模型；只在确实需要 CAD 名称时开启"
        )
        form.addRow("CAD 文字:", self.sketchup_include_text)

        knowledge_info = QLabel(
            "内置轻量建模知识库会按建筑类型、模型精度和场地对象选择立面模数、入口、"
            "屋顶、道路边缘、树木细节与性能预算。另含 "
            "9 个许可清晰的 CC0 SketchUp 组件（约 334 KB），按需共享加载，不联网、不用 API；"
            "你的逐栋设置和项目参数始终优先，也不会把学习建议当作审批规范。"
        )
        knowledge_info.setWordWrap(True)
        knowledge_info.setStyleSheet("color: #536F83; font-size: 12px;")
        form.addRow("建模知识库:", knowledge_info)

        info = QLabel(
            "🏙️ 运行后会生成一个轻量 .ptsu.json 模型交接文件和一个可安装的 .rbz 插件。"
            "插件在 SketchUp 内把建筑、地块、绿地、道路、水体和停车对象生成独立分组与 PT_* 标签，"
            "并保留稳定对象编号、原 DXF 图层和 handle。课程作业模式还会自动生成楼层线、屋顶、共享窗、"
            "入口雨棚、建筑基座、轻量三维树木以及具有微小高差的道路/绿地/水体/停车面；"
            "道路预设可选择仅保留 CAD 面、基础车行道或完整街道；完整街道会为接近矩形的道路生成"
            "双侧人行道、端部不断开的路缘、道路边线、中心虚线、双向箭头与共享街灯；"
            "不规则道路不会被强行矩形化；满足边界稳定条件的弯道会沿局部帧细化；"
            "明确命名为 ROUNDABOUT 或“环岛”的圆形道路会生成保留中央空腔的环带。"
            "PT_CROSSWALK 会把斑马线长条自动对齐车行方向；交叉口歧义、宽度仅为概念估计或无法匹配时"
            "保留 CAD 角度并提示复核。汇报模式还会增加住宅阳台和屋顶设备；"
            "重复导入只更新变化对象，已锁定的手工调整会受到保护。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #607A6A; font-size: 12px;")
        form.addRow(info)

        warning = QLabel(
            "⚠️ 投影坐标项目必须先点击顶部“🧭”启用场地附近的建模原点，否则会被阻断。"
            "原始 DXF 只读；HATCH 填充、材质、外部参照和复杂网格实体暂不自动重建。"
            "这项功能完全在本机运行，不需要 API，也不会把 SketchUp 打包进本软件。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #A6814D; font-size: 12px;")
        form.addRow(warning)
        self._add_scrollable_tab(tab, "10. CAD → SketchUp 模型交接")

    def _update_image_mode_controls(self):
        """Keep mode-specific controls clear for non-technical users."""
        if not hasattr(self, "image_conversion_mode"):
            return
        is_linework = self.image_conversion_mode.currentData() == "black_white_linework"
        is_semantic_guide = self.image_conversion_mode.currentData() == "semantic_guide"
        self.image_color_tolerance.setEnabled(not is_linework)
        self.image_focus_site_only.setEnabled(not is_linework)
        self.image_line_threshold.setEnabled(is_linework)
        self.image_line_polarity.setEnabled(is_linework)
        self.image_detail_level.setEnabled(is_linework)
        self.image_optimize_linework.setEnabled(is_linework)
        self.lbl_image_semantic_guide.setVisible(is_semantic_guide)
        self.image_semantic_guide_row.setVisible(is_semantic_guide)

    def _update_knowledge_controls(self):
        """Keep optional CAD curation subordinate to the lightweight card."""
        if not hasattr(self, "image_create_knowledge_card"):
            return
        enabled = self.image_create_knowledge_card.isChecked()
        self.image_knowledge_project_type.setEnabled(enabled)
        self.image_knowledge_tags.setEnabled(enabled)
        self.image_collect_cad_sample.setEnabled(enabled)
        if not enabled:
            self.image_collect_cad_sample.setChecked(False)

    def _add_scrollable_tab(self, content: QWidget, title: str):
        """Put each task form in its own vertical scroll area.

        The workbench can be displayed on a short laptop screen.  Without a
        per-tab scroll area, long forms and explanatory labels are compressed
        into overlapping rows instead of remaining readable.
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(content)
        # QLabel's word-wrapped height can be under-reported inside a
        # QFormLayout.  Preserve its calculated height so the last lines are
        # not clipped when the page becomes scrollable.
        for label in content.findChildren(QLabel):
            if label.wordWrap():
                label.setMinimumHeight(label.sizeHint().height())
        content.adjustSize()
        self.tabs.addTab(scroll, title)

    def _browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择俯视平面效果图",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*.*)",
        )
        if file_path:
            self.image_file_input.setText(file_path)

    def _browse_semantic_guide(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择标准颜色语义引导图",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*.*)",
        )
        if file_path:
            self.image_semantic_guide_input.setText(file_path)

    def _edit_semantic_guide(self, review_overlay_path: str | None = None):
        """Open the local, source-locked semantic-guide painter."""
        from PySide6.QtWidgets import QDialog, QMessageBox

        source_value = self.image_file_input.text().strip()
        source_path = Path(source_value).resolve() if source_value else None
        if source_path is None or not source_path.is_file():
            QMessageBox.information(
                self,
                "请先选择原图",
                "请先在上方选择一张 PNG、JPG 或 BMP 原始底图，再创建语义引导图。"
                "原图会保持只读，不会被编辑器修改。",
            )
            return
        guide_value = self.image_semantic_guide_input.text().strip()
        guide_path = Path(guide_value).resolve() if guide_value else None
        if guide_path is not None and not guide_path.is_file():
            guide_path = None
        try:
            from planning_toolbox.gui.semantic_guide_editor import SemanticGuideEditorDialog

            dialog = SemanticGuideEditorDialog(
                source_path,
                guide_path,
                self,
                review_overlay_path=review_overlay_path,
            )
        except Exception as exc:
            QMessageBox.warning(self, "无法打开引导图编辑器", str(exc))
            return
        if dialog.exec() == QDialog.Accepted and dialog.saved_path:
            self.image_semantic_guide_input.setText(dialog.saved_path)

    def _on_standard_profile_changed(self, index: int):
        profile_id = self.concept_standard_profile.itemData(index)
        if not profile_id:
            return
        profile = get_standards_profile(profile_id)
        self.lbl_concept_standard.setText(
            f"📚 {profile.description} 依据：{profile.reference_summary()}"
            " 数值仍需结合项目所在地规划条件和项目类型确认。"
        )

    def _on_drafting_profile_changed(self, index: int):
        profile_id = self.layer_drafting_profile.itemData(index)
        if not profile_id:
            return
        profile = get_drafting_profile(profile_id)
        self.lbl_layer_drafting_profile.setText(
            f"📚 {profile.description}\n"
            f"依据索引：{'、'.join(profile.reference_codes)}。"
            "软件只报告辅助一致性，不代表法定审查或审批通过。"
        )

    def _update_layer_drafting_controls(self, enabled: bool):
        self.layer_drafting_profile.setEnabled(bool(enabled))
        self.lbl_layer_drafting_profile.setEnabled(bool(enabled))

    def _on_gis_mode_changed(self, index: int):
        mode = self.gis_mode_combo.itemData(index) or "dxf_to_geojson"
        is_import = mode in {"geojson_to_dxf", "vector_to_dxf"}
        needs_adapter = mode in {"vector_to_dxf", "dxf_to_gpkg"}
        self.lbl_geojson.setVisible(is_import)
        self.geojson_file_input.setVisible(is_import)
        self.btn_browse_geojson.setVisible(is_import)
        self.lbl_gis_unit.setVisible(is_import)
        self.combo_gis_unit.setVisible(is_import)

        if mode == "geojson_to_dxf":
            self.lbl_geojson.setText("GeoJSON 文件:")
            self.geojson_file_input.setPlaceholderText("请选择要导入的 GeoJSON 文件...")
            self.btn_browse_geojson.setText("选择 GeoJSON...")
            self.gis_notice.setText(
                "🛑 CRS 安全阻断提示: 若 GeoJSON 声明为 WGS84 经纬度坐标，系统将拒绝直接导入。\n"
                "请先在 QGIS 或 ArcGIS 中转换为适合测距和面积计算的平面坐标系 (如 CGCS2000 高斯投影)。"
            )
        elif mode == "vector_to_dxf":
            self.lbl_geojson.setText("GPKG / SHP 文件:")
            self.geojson_file_input.setPlaceholderText("请选择 GeoPackage (.gpkg) 或 Shapefile (.shp)...")
            self.btn_browse_geojson.setText("选择 GPKG / SHP...")
            from planning_toolbox.gis.vector_bridge import adapter_status_text

            self.gis_notice.setText(
                "🧭 将按顶部“项目设置”中的投影坐标自动对齐后生成 DXF。\n"
                + adapter_status_text()
            )
        elif mode == "dxf_to_gpkg":
            from planning_toolbox.gis.vector_bridge import adapter_status_text

            self.gis_notice.setText(
                "🧭 将按顶部“项目设置”中的投影坐标生成带空间索引的 GeoPackage。"
                "原始 DXF 始终只读。\n" + adapter_status_text()
            )
        else:
            self.gis_notice.setText(
                "⚠️ CRS 提示: 当前未进行 CRS 坐标转换。请不要把本地 CAD 坐标直接当作真实经纬度使用。"
            )
        if needs_adapter:
            self.gis_notice.setToolTip(
                "优先使用电脑已有的 ArcGIS Pro；没有时再检测 QGIS/GDAL。"
            )
        else:
            self.gis_notice.setToolTip("")

    def _browse_geojson(self):
        mode = self.gis_mode_combo.currentData()
        if mode == "vector_to_dxf":
            title = "选择 GeoPackage 或 Shapefile"
            file_filter = "GIS 矢量文件 (*.gpkg *.shp);;GeoPackage (*.gpkg);;Shapefile (*.shp)"
        else:
            title = "选择矢量 GeoJSON 文件"
            file_filter = "GeoJSON 矢量文件 (*.geojson *.json)"
        file_path, _ = QFileDialog.getOpenFileName(
            self, title, "", file_filter
        )
        if file_path:
            self.geojson_file_input.setText(file_path)

    def _browse_batch_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择 DXF 文件夹")
        if folder:
            self.batch_folder_input.setText(folder)

    def _apply_preset(self, index: int):
        preset_id = self.preset_combo.itemData(index)
        if preset_id != "learning_example":
            return
        preset = get_rule_preset(preset_id)
        self.spin_floors.setValue(preset.floors or 0)
        self.spin_setback.setValue(preset.setback_m)
        self.lbl_preflight.setText(
            f"已填入{preset.name}：{preset.description}正式项目请根据实际规划条件修改。"
        )
        self.lbl_preflight.setObjectName("BadgeWarning")
        self.lbl_preflight.setStyle(self.lbl_preflight.style())

    def get_project_state(self) -> Dict[str, Any]:
        """Return all user-entered task settings in a JSON-friendly form."""
        return {
            "current_tab_index": self.tabs.currentIndex(),
            "parcel_layer": self.parcel_layer_input.text(),
            "indicator_floors": self.spin_floors.value(),
            "indicator_building_layer": self.ind_b_layer.text(),
            "indicator_green_layer": self.ind_g_layer.text(),
            "validate_setback": self.spin_setback.value(),
            "validate_parcel_layer": self.val_p_layer.text(),
            "validate_building_layer": self.val_b_layer.text(),
            "validate_fallback_index": self.combo_fallback.currentIndex(),
            "gis_mode_index": self.gis_mode_combo.currentIndex(),
            "geojson_file": self.geojson_file_input.text(),
            "gis_unit_index": self.combo_gis_unit.currentIndex(),
            "batch_folder": self.batch_folder_input.text(),
            "batch_task_index": self.batch_task_combo.currentIndex(),
            "batch_floors": self.batch_floors.value(),
            "concept_standard_profile": self.concept_standard_profile.currentData(),
            "concept_layout_style": self.concept_layout_style.currentData(),
            "concept_building_count": self.concept_building_count.value(),
            "concept_coverage": self.concept_coverage.value(),
            "concept_setback": self.concept_setback.value(),
            "concept_building_gap": self.concept_building_gap.value(),
            "concept_access_width": self.concept_access_width.value(),
            "concept_floors": self.concept_floors.value(),
            "concept_parking_ratio": self.concept_parking_ratio.value(),
            "concept_parcel_layer": self.concept_parcel_layer.text(),
            "concept_fallback_index": self.concept_fallback.currentIndex(),
            "layer_use_china_standard": self.layer_use_china_standard.isChecked(),
            "layer_drafting_profile": self.layer_drafting_profile.currentData(),
            "quality_repair_profile": self.quality_repair_profile.currentData(),
            "quality_remove_duplicates_index": self.quality_remove_duplicates.currentIndex(),
            "quality_close_near_index": self.quality_close_near.currentIndex(),
            "quality_tolerance": self.quality_tolerance.value(),
            "quality_remove_duplicate_lines": self.quality_remove_duplicate_lines.isChecked(),
            "quality_merge_fragments": self.quality_merge_fragments.isChecked(),
            "quality_join_tolerance": self.quality_join_tolerance.value(),
            "quality_simplify_collinear": self.quality_simplify_collinear.isChecked(),
            "quality_collinear_tolerance": self.quality_collinear_tolerance.value(),
            "quality_remove_short_vertices": self.quality_remove_short_vertices.isChecked(),
            "quality_min_segment_length": self.quality_min_segment_length.value(),
            "quality_standardize_layers": self.quality_standardize_layers.isChecked(),
            "image_file": self.image_file_input.text(),
            "image_conversion_mode": self.image_conversion_mode.currentData(),
            "image_semantic_guide_file": self.image_semantic_guide_input.text(),
            "image_reference_width": self.image_reference_width.value(),
            "image_color_tolerance": self.image_color_tolerance.value(),
            "image_min_component_pixels": self.image_min_component_pixels.value(),
            "image_line_threshold": self.image_line_threshold.value(),
            "image_line_polarity": self.image_line_polarity.currentData(),
            "image_detail_level": self.image_detail_level.currentData(),
            "image_optimize_linework": self.image_optimize_linework.isChecked(),
            "image_focus_site_only": self.image_focus_site_only.isChecked(),
            "image_use_knowledge_assist": self.image_use_knowledge_assist.isChecked(),
            "image_create_knowledge_card": self.image_create_knowledge_card.isChecked(),
            "image_knowledge_project_type": self.image_knowledge_project_type.currentText(),
            "image_knowledge_tags": self.image_knowledge_tags.text(),
            "image_collect_cad_sample": self.image_collect_cad_sample.isChecked(),
            "sketchup_building_layers": self.sketchup_building_layers.text(),
            "sketchup_floors": self.sketchup_floors.value(),
            "sketchup_floor_height": self.sketchup_floor_height.value(),
            "sketchup_model_detail": self.sketchup_model_detail.currentData(),
            "sketchup_road_design": self.sketchup_road_design.currentData(),
            "sketchup_centerline_corridor": self.sketchup_centerline_corridor.isChecked(),
            "sketchup_centerline_confidence_policy": self.sketchup_centerline_confidence_policy.currentData(),
            "sketchup_centerline_width": self.sketchup_centerline_width.value(),
            "sketchup_building_type": self.sketchup_building_type.currentData(),
            "sketchup_roof_type": self.sketchup_roof_type.currentData(),
            "sketchup_incremental_update": self.sketchup_incremental_update.isChecked(),
            "sketchup_include_open": self.sketchup_include_open.isChecked(),
            "sketchup_include_blocks": self.sketchup_include_blocks.isChecked(),
            "sketchup_include_faces": self.sketchup_include_faces.isChecked(),
            "sketchup_include_text": self.sketchup_include_text.isChecked(),
            "sketchup_building_overrides": self.get_sketchup_building_overrides(),
        }

    def apply_project_state(self, state: Dict[str, Any]):
        """Restore saved task settings while tolerating older project files."""
        self.parcel_layer_input.setText(str(state.get("parcel_layer", "PARCEL")))
        self.spin_floors.setValue(int(state.get("indicator_floors", 0)))
        self.ind_b_layer.setText(str(state.get("indicator_building_layer", "BUILDING")))
        self.ind_g_layer.setText(str(state.get("indicator_green_layer", "GREEN")))
        self.spin_setback.setValue(float(state.get("validate_setback", 5.0)))
        self.val_p_layer.setText(str(state.get("validate_parcel_layer", "PARCEL")))
        self.val_b_layer.setText(str(state.get("validate_building_layer", "BUILDING")))
        self.combo_fallback.setCurrentIndex(int(state.get("validate_fallback_index", 0)))
        self.gis_mode_combo.setCurrentIndex(int(state.get("gis_mode_index", 0)))
        self.geojson_file_input.setText(str(state.get("geojson_file", "")))
        self.combo_gis_unit.setCurrentIndex(int(state.get("gis_unit_index", 0)))
        self.batch_folder_input.setText(str(state.get("batch_folder", "")))
        self.batch_task_combo.setCurrentIndex(int(state.get("batch_task_index", 0)))
        self.batch_floors.setValue(int(state.get("batch_floors", 0)))

        profile_id = state.get("concept_standard_profile")
        if profile_id:
            profile_index = self.concept_standard_profile.findData(profile_id)
            if profile_index >= 0:
                self.concept_standard_profile.setCurrentIndex(profile_index)
        self.concept_building_count.setValue(int(state.get("concept_building_count", 1)))
        layout_style = state.get("concept_layout_style", "organic")
        layout_index = self.concept_layout_style.findData(layout_style)
        if layout_index >= 0:
            self.concept_layout_style.setCurrentIndex(layout_index)
        self.concept_coverage.setValue(float(state.get("concept_coverage", 25.0)))
        self.concept_setback.setValue(float(state.get("concept_setback", 5.0)))
        self.concept_building_gap.setValue(float(state.get("concept_building_gap", 0.0)))
        self.concept_access_width.setValue(float(state.get("concept_access_width", 0.0)))
        self.concept_floors.setValue(int(state.get("concept_floors", 0)))
        self.concept_parking_ratio.setValue(float(state.get("concept_parking_ratio", 0.0)))
        self.concept_parcel_layer.setText(str(state.get("concept_parcel_layer", "PARCEL")))
        self.concept_fallback.setCurrentIndex(int(state.get("concept_fallback_index", 0)))
        self.layer_use_china_standard.setChecked(
            bool(state.get("layer_use_china_standard", True))
        )
        drafting_profile_id = state.get(
            "layer_drafting_profile", "china_coursework_general"
        )
        drafting_profile_index = self.layer_drafting_profile.findData(
            drafting_profile_id
        )
        if drafting_profile_index >= 0:
            self.layer_drafting_profile.setCurrentIndex(drafting_profile_index)
        self._update_layer_drafting_controls(
            self.layer_use_china_standard.isChecked()
        )
        quality_profile_index = self.quality_repair_profile.findData(
            state.get("quality_repair_profile", "minimize_manual")
        )
        if quality_profile_index >= 0:
            self.quality_repair_profile.setCurrentIndex(quality_profile_index)
        self.quality_remove_duplicates.setCurrentIndex(int(state.get("quality_remove_duplicates_index", 0)))
        self.quality_close_near.setCurrentIndex(int(state.get("quality_close_near_index", 0)))
        self.quality_tolerance.setValue(float(state.get("quality_tolerance", 0.01)))
        self.quality_remove_duplicate_lines.setChecked(
            bool(state.get("quality_remove_duplicate_lines", True))
        )
        self.quality_merge_fragments.setChecked(bool(state.get("quality_merge_fragments", True)))
        self.quality_join_tolerance.setValue(float(state.get("quality_join_tolerance", 0.05)))
        self.quality_simplify_collinear.setChecked(
            bool(state.get("quality_simplify_collinear", True))
        )
        self.quality_collinear_tolerance.setValue(
            float(state.get("quality_collinear_tolerance", 0.01))
        )
        self.quality_remove_short_vertices.setChecked(
            bool(state.get("quality_remove_short_vertices", True))
        )
        self.quality_min_segment_length.setValue(
            float(state.get("quality_min_segment_length", 0.01))
        )
        self.quality_standardize_layers.setChecked(
            bool(state.get("quality_standardize_layers", True))
        )
        self._update_quality_controls()
        self.image_file_input.setText(str(state.get("image_file", "")))
        self.image_semantic_guide_input.setText(
            str(state.get("image_semantic_guide_file", ""))
        )
        mode_index = self.image_conversion_mode.findData(
            state.get("image_conversion_mode", "color_regions")
        )
        if mode_index >= 0:
            self.image_conversion_mode.setCurrentIndex(mode_index)
        self.image_reference_width.setValue(float(state.get("image_reference_width", 0.0)))
        self.image_color_tolerance.setValue(int(state.get("image_color_tolerance", 55)))
        self.image_min_component_pixels.setValue(int(state.get("image_min_component_pixels", 80)))
        self.image_line_threshold.setValue(int(state.get("image_line_threshold", 220)))
        polarity_index = self.image_line_polarity.findData(
            state.get("image_line_polarity", "auto")
        )
        if polarity_index >= 0:
            self.image_line_polarity.setCurrentIndex(polarity_index)
        detail_index = self.image_detail_level.findData(
            state.get("image_detail_level", "fine")
        )
        if detail_index >= 0:
            self.image_detail_level.setCurrentIndex(detail_index)
        self.image_optimize_linework.setChecked(
            bool(state.get("image_optimize_linework", True))
        )
        self.image_focus_site_only.setChecked(bool(state.get("image_focus_site_only", True)))
        self.image_use_knowledge_assist.setChecked(
            bool(state.get("image_use_knowledge_assist", True))
        )
        self.image_create_knowledge_card.setChecked(
            bool(state.get("image_create_knowledge_card", True))
        )
        project_type = str(state.get("image_knowledge_project_type", "待确认"))
        project_type_index = self.image_knowledge_project_type.findText(project_type)
        if project_type_index >= 0:
            self.image_knowledge_project_type.setCurrentIndex(project_type_index)
        self.image_knowledge_tags.setText(str(state.get("image_knowledge_tags", "")))
        self.image_collect_cad_sample.setChecked(
            bool(state.get("image_collect_cad_sample", False))
        )
        self._update_knowledge_controls()
        self.sketchup_building_layers.setText(
            str(
                state.get(
                    "sketchup_building_layers",
                    "BUILDING, CONCEPT_BUILDING, AI_BUILDING, BW_BUILDING_CANDIDATE",
                )
            )
        )
        self.sketchup_floors.setValue(int(state.get("sketchup_floors", 0)))
        self.sketchup_floor_height.setValue(
            float(state.get("sketchup_floor_height", 0.0))
        )
        detail_index = self.sketchup_model_detail.findData(
            state.get("sketchup_model_detail", "course")
        )
        if detail_index >= 0:
            self.sketchup_model_detail.setCurrentIndex(detail_index)
        road_design_index = self.sketchup_road_design.findData(
            state.get("sketchup_road_design", "auto")
        )
        if road_design_index >= 0:
            self.sketchup_road_design.setCurrentIndex(road_design_index)
        self.sketchup_centerline_corridor.setChecked(
            bool(state.get("sketchup_centerline_corridor", False))
        )
        confidence_policy_index = self.sketchup_centerline_confidence_policy.findData(
            state.get("sketchup_centerline_confidence_policy", "trusted_only")
        )
        if confidence_policy_index >= 0:
            self.sketchup_centerline_confidence_policy.setCurrentIndex(
                confidence_policy_index
            )
        self.sketchup_centerline_width.setValue(
            float(state.get("sketchup_centerline_width", 0.0))
        )
        building_type_index = self.sketchup_building_type.findData(
            state.get("sketchup_building_type", "auto")
        )
        if building_type_index >= 0:
            self.sketchup_building_type.setCurrentIndex(building_type_index)
        roof_index = self.sketchup_roof_type.findData(
            state.get("sketchup_roof_type", "flat")
        )
        if roof_index >= 0:
            self.sketchup_roof_type.setCurrentIndex(roof_index)
        self.sketchup_incremental_update.setChecked(
            bool(state.get("sketchup_incremental_update", True))
        )
        self.sketchup_include_open.setChecked(
            bool(state.get("sketchup_include_open", True))
        )
        self.sketchup_include_blocks.setChecked(
            bool(state.get("sketchup_include_blocks", True))
        )
        self.sketchup_include_faces.setChecked(
            bool(state.get("sketchup_include_faces", True))
        )
        self.sketchup_include_text.setChecked(
            bool(state.get("sketchup_include_text", False))
        )
        self.set_sketchup_building_overrides(
            state.get("sketchup_building_overrides", {})
        )
        self.tabs.setCurrentIndex(int(state.get("current_tab_index", 0)))

    def set_sketchup_building_overrides(self, values: Any) -> None:
        """Store only JSON-friendly per-building mappings from the dialog/project."""
        cleaned: Dict[str, Dict[str, Any]] = {}
        if isinstance(values, dict):
            for key, value in values.items():
                if str(key).strip() and isinstance(value, dict):
                    cleaned[str(key)] = dict(value)
        self._sketchup_building_overrides = cleaned
        count = len(cleaned)
        self.lbl_sketchup_building_schedule.setText(
            f"已保存 {count} 条逐栋设置；未设置建筑仍使用下方全局参数"
            if count
            else "未单独设置；全部使用下方全局参数"
        )

    def get_sketchup_building_overrides(self) -> Dict[str, Dict[str, Any]]:
        return {key: dict(value) for key, value in self._sketchup_building_overrides.items()}

    def set_preflight_status(self, message: str, level: str = "info"):
        """Show a plain-language readiness message below the task tabs."""
        object_name = {
            "success": "BadgeSuccess",
            "warning": "BadgeWarning",
            "error": "BadgeError",
            "info": "BadgeInfo",
        }.get(level, "BadgeInfo")
        self.lbl_preflight.setText(message)
        self.lbl_preflight.setObjectName(object_name)
        self.lbl_preflight.setStyle(self.lbl_preflight.style())

    def _on_run_clicked(self):
        idx = self.tabs.currentIndex()
        if idx == 0:
            task_type = "parcel"
            params = {"target_layer": self.parcel_layer_input.text().strip()}
        elif idx == 1:
            task_type = "indicator"
            floors = self.spin_floors.value()
            params = {
                "floors": floors if floors > 0 else None,
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
            gis_mode = self.gis_mode_combo.currentData() or "dxf_to_geojson"
            if gis_mode in {"dxf_to_geojson", "dxf_to_gpkg"}:
                task_type = "gis_export"
                params = {
                    "output_format": "gpkg" if gis_mode == "dxf_to_gpkg" else "geojson",
                    "requires_project_crs": gis_mode == "dxf_to_gpkg",
                }
            else:
                task_type = "gis_import"
                unit_map = {0: "m", 1: "cm", 2: "mm", 3: "ft", 4: "in"}
                params = {
                    "geojson_path": self.geojson_file_input.text().strip(),
                    "unit": unit_map.get(self.combo_gis_unit.currentIndex(), "m"),
                    "use_vector_bridge": gis_mode == "vector_to_dxf",
                    "requires_project_crs": gis_mode == "vector_to_dxf",
                }
        elif idx == 4:
            batch_task = "parcel" if self.batch_task_combo.currentIndex() == 0 else "indicator"
            floors = self.batch_floors.value()
            task_type = "batch"
            params = {
                "input_dir": self.batch_folder_input.text().strip(),
                "batch_task": batch_task,
                "floors": floors if floors > 0 else None,
            }
        elif idx == 5:
            fallback_map = {0: None, 1: "m", 2: "cm", 3: "mm", 4: "ft"}
            task_type = "concept_plan"
            params = {
                "building_count": self.concept_building_count.value(),
                "layout_style": self.concept_layout_style.currentData(),
                "coverage_ratio": self.concept_coverage.value() / 100.0,
                "setback_m": self.concept_setback.value(),
                "building_gap_m": self.concept_building_gap.value(),
                "access_width_m": self.concept_access_width.value(),
                "standards_profile_id": self.concept_standard_profile.currentData(),
                "floors": self.concept_floors.value() or None,
                "parking_ratio": self.concept_parking_ratio.value() or None,
                "parcel_layer": self.concept_parcel_layer.text().strip(),
                "fallback_unit": fallback_map.get(self.concept_fallback.currentIndex()),
            }
        elif idx == 6:
            task_type = "layer_standardize"
            params = {
                "use_china_standard": self.layer_use_china_standard.isChecked(),
                "drafting_profile_id": self.layer_drafting_profile.currentData(),
            }
        elif idx == 7:
            task_type = "quality_check"
            repair_profile = self.quality_repair_profile.currentData()
            params = {
                "repair_profile": repair_profile,
                "remove_duplicates": self.quality_remove_duplicates.currentIndex() == 0,
                "close_near_closed": self.quality_close_near.currentIndex() == 0,
                "near_closed_tolerance": self.quality_tolerance.value(),
                "remove_duplicate_lines": self.quality_remove_duplicate_lines.isChecked(),
                "merge_connected_fragments": self.quality_merge_fragments.isChecked(),
                "join_tolerance": self.quality_join_tolerance.value(),
                "simplify_collinear_vertices": self.quality_simplify_collinear.isChecked(),
                "collinear_tolerance": self.quality_collinear_tolerance.value(),
                "remove_short_vertices": self.quality_remove_short_vertices.isChecked(),
                "min_segment_length": self.quality_min_segment_length.value(),
                "standardize_layers": self.quality_standardize_layers.isChecked(),
                "require_known_units": repair_profile == "minimize_manual",
            }
        elif idx == 8:
            task_type = "image_to_dxf"
            params = {
                "image_path": self.image_file_input.text().strip(),
                "conversion_mode": self.image_conversion_mode.currentData(),
                "semantic_guide_path": self.image_semantic_guide_input.text().strip(),
                "reference_width_m": self.image_reference_width.value(),
                "color_tolerance": self.image_color_tolerance.value(),
                "min_component_pixels": self.image_min_component_pixels.value(),
                "line_threshold": self.image_line_threshold.value(),
                "line_polarity": self.image_line_polarity.currentData(),
                "detail_level": self.image_detail_level.currentData(),
                "optimize_linework": self.image_optimize_linework.isChecked(),
                "focus_site_only": self.image_focus_site_only.isChecked(),
                "use_knowledge_assist": self.image_use_knowledge_assist.isChecked(),
                "create_knowledge_card": self.image_create_knowledge_card.isChecked(),
                "knowledge_project_type": self.image_knowledge_project_type.currentText(),
                "knowledge_tags": self.image_knowledge_tags.text().strip(),
                "collect_cad_sample": self.image_collect_cad_sample.isChecked(),
            }
        elif idx == 9:
            task_type = "sketchup_export"
            params = {
                "building_layers": self.sketchup_building_layers.text().strip(),
                "floors": self.sketchup_floors.value(),
                "floor_height_m": self.sketchup_floor_height.value(),
                "model_detail_level": self.sketchup_model_detail.currentData(),
                "road_design_preset": self.sketchup_road_design.currentData(),
                "centerline_corridor": self.sketchup_centerline_corridor.isChecked(),
                "centerline_confidence_policy": self.sketchup_centerline_confidence_policy.currentData(),
                "centerline_width_m": self.sketchup_centerline_width.value(),
                "building_type": self.sketchup_building_type.currentData(),
                "roof_type": self.sketchup_roof_type.currentData(),
                "incremental_update": self.sketchup_incremental_update.isChecked(),
                "include_open_linework": self.sketchup_include_open.isChecked(),
                "include_blocks": self.sketchup_include_blocks.isChecked(),
                "include_faces": self.sketchup_include_faces.isChecked(),
                "include_text": self.sketchup_include_text.isChecked(),
                "building_overrides": self.get_sketchup_building_overrides(),
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
            self._update_run_button_label()
