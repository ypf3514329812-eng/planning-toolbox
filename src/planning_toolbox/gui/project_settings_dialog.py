"""Beginner-friendly metadata editor for the GIS-CAD-SU project chain."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from planning_toolbox.project.chain_manifest import (
    CRSDefinition,
    ChainManifest,
    LocalOrigin,
)


PROJECT_TYPES = (
    ("coursework", "普通规划课程作业"),
    ("residential", "居住区规划"),
    ("urban_design", "城市设计"),
    ("campus", "校园规划"),
    ("territorial", "国土空间规划"),
    ("custom", "其他 / 自定义"),
)

CRS_KINDS = (
    ("unknown", "暂未确认"),
    ("projected", "投影坐标（适合面积和距离）"),
    ("local", "本地工程坐标"),
    ("geographic", "经纬度坐标（不能直接量算）"),
)


class ProjectSettingsDialog(QDialog):
    """Edit only lightweight metadata; no GIS engine is loaded here."""

    def __init__(self, manifest: ChainManifest, parent=None):
        super().__init__(parent)
        self._source_manifest = manifest
        self.setWindowTitle("GIS–CAD–SU 全链路项目设置")
        self.setMinimumWidth(590)
        self.resize(650, 560)
        self._init_ui()
        self._load_manifest(manifest)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("建立统一的全链路项目坐标")
        title.setObjectName("DialogTitle")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #566D8E;")
        layout.addWidget(title)

        intro = QLabel(
            "这里只保存项目名称、坐标系、CAD 单位和 SketchUp 本地原点，不会复制图纸，"
            "也不会加载 QGIS 或 SketchUp。设置后，GIS、CAD 和三维模型才能稳定对齐。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #74766F;")
        layout.addWidget(intro)

        form_frame = QFrame()
        form_frame.setObjectName("ZoneFrame")
        form = QFormLayout(form_frame)
        form.setContentsMargins(14, 14, 14, 14)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("例如：城市设计课程作业 A")
        form.addRow("项目名称：", self.project_name)

        self.project_type = QComboBox()
        for value, label in PROJECT_TYPES:
            self.project_type.addItem(label, value)
        form.addRow("项目类型：", self.project_type)

        self.crs_code = QLineEdit()
        self.crs_code.setPlaceholderText("例如：4547；不确定时可以暂时留空")
        self.crs_code.setToolTip("填写 EPSG 编号即可，不需要输入 EPSG: 前缀")
        self.crs_code.textChanged.connect(self._update_validation_hint)
        form.addRow("项目坐标 EPSG：", self.crs_code)

        self.crs_name = QLineEdit()
        self.crs_name.setPlaceholderText("例如：CGCS2000 / 3-degree Gauss-Kruger CM 114E")
        form.addRow("坐标系名称：", self.crs_name)

        self.crs_kind = QComboBox()
        for value, label in CRS_KINDS:
            self.crs_kind.addItem(label, value)
        self.crs_kind.currentIndexChanged.connect(self._update_validation_hint)
        form.addRow("坐标类型：", self.crs_kind)

        self.cad_unit = QComboBox()
        for unit, label in (("m", "米 m（规划推荐）"), ("mm", "毫米 mm"), ("cm", "厘米 cm"), ("ft", "英尺 ft"), ("in", "英寸 in")):
            self.cad_unit.addItem(label, unit)
        form.addRow("CAD 图纸单位：", self.cad_unit)

        self.origin_enabled = QCheckBox("为 SketchUp 使用近原点坐标（推荐）")
        self.origin_enabled.toggled.connect(self._set_origin_enabled)
        form.addRow("本地建模原点：", self.origin_enabled)

        self.origin_x = self._coordinate_spin()
        form.addRow("原点 X / Easting：", self.origin_x)
        self.origin_y = self._coordinate_spin()
        form.addRow("原点 Y / Northing：", self.origin_y)
        self.origin_z = self._coordinate_spin()
        form.addRow("原点高程 Z：", self.origin_z)

        self.origin_rotation = QDoubleSpinBox()
        self.origin_rotation.setRange(-360.0, 360.0)
        self.origin_rotation.setDecimals(4)
        self.origin_rotation.setSuffix("°")
        self.origin_rotation.setToolTip("本地 X 轴相对项目 X 轴的逆时针旋转角度")
        form.addRow("模型旋转角：", self.origin_rotation)

        layout.addWidget(form_frame)

        self.validation_hint = QLabel()
        self.validation_hint.setWordWrap(True)
        self.validation_hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.validation_hint)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("保存项目设置")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self._accept_if_valid)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    @staticmethod
    def _coordinate_spin() -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(-1_000_000_000.0, 1_000_000_000.0)
        widget.setDecimals(4)
        widget.setGroupSeparatorShown(True)
        widget.setSuffix(" m")
        return widget

    def _load_manifest(self, manifest: ChainManifest) -> None:
        self.project_name.setText(manifest.name if manifest.name != "未命名项目" else "")
        self._select_data(self.project_type, manifest.project_type)
        self.crs_code.setText(str(manifest.crs.code) if manifest.crs.code is not None else "")
        self.crs_name.setText(manifest.crs.name)
        self._select_data(self.crs_kind, manifest.crs.kind)
        self._select_data(self.cad_unit, manifest.cad_unit)
        self.origin_enabled.setChecked(manifest.local_origin.enabled)
        self.origin_x.setValue(manifest.local_origin.easting)
        self.origin_y.setValue(manifest.local_origin.northing)
        self.origin_z.setValue(manifest.local_origin.elevation)
        self.origin_rotation.setValue(manifest.local_origin.rotation_deg)
        self._set_origin_enabled(manifest.local_origin.enabled)
        self._update_validation_hint()

    @staticmethod
    def _select_data(widget: QComboBox, value: str) -> None:
        index = widget.findData(value)
        widget.setCurrentIndex(index if index >= 0 else 0)

    def _set_origin_enabled(self, enabled: bool) -> None:
        for widget in (self.origin_x, self.origin_y, self.origin_z, self.origin_rotation):
            widget.setEnabled(enabled)

    def _read_epsg_code(self) -> int | None:
        text = self.crs_code.text().strip().upper().removeprefix("EPSG:").strip()
        if not text:
            return None
        if not text.isdigit() or int(text) <= 0:
            raise ValueError("EPSG 编号应当是正整数，例如 4547。")
        return int(text)

    def _update_validation_hint(self) -> None:
        kind = self.crs_kind.currentData()
        code_text = self.crs_code.text().strip().upper().removeprefix("EPSG:").strip()
        if code_text == "3857":
            self.validation_hint.setText(
                "🛑 EPSG:3857 适合网络地图显示，不适合课程作业中的精确面积和距离。"
                "请改用项目所在地适用的 CGCS2000 投影坐标或本地工程坐标。"
            )
            self.validation_hint.setStyleSheet("color: #A96761; font-weight: 600;")
            return
        if kind == "geographic":
            self.validation_hint.setText(
                "🛑 经纬度坐标不能直接用于面积、距离和 SketchUp 建模。可以先保存项目，"
                "但进入分析前必须在后续 GIS 步骤转换为投影坐标。"
            )
            self.validation_hint.setStyleSheet("color: #A96761; font-weight: 600;")
        elif kind in {"projected", "local"}:
            self.validation_hint.setText(
                "✅ 坐标类型适合全链路量算。正式计算前，系统仍会核对单位和 EPSG 信息。"
            )
            self.validation_hint.setStyleSheet("color: #607A6A; font-weight: 600;")
        else:
            self.validation_hint.setText(
                "⚠️ 坐标尚未确认。项目可以保存，但 GIS 转换、面积和三维对齐前必须补充。"
            )
            self.validation_hint.setStyleSheet("color: #A6814D; font-weight: 600;")

    def build_manifest(self) -> ChainManifest:
        """Return an updated manifest without mutating the original."""
        project_name = self.project_name.text().strip() or "未命名项目"
        code = self._read_epsg_code()
        kind = str(self.crs_kind.currentData())
        if code in {4326, 4490} and kind == "projected":
            raise ValueError("EPSG:4326 和 EPSG:4490 是经纬度坐标，请将坐标类型改为“经纬度坐标”。")
        crs = CRSDefinition(
            authority="EPSG",
            code=code,
            name=self.crs_name.text().strip(),
            kind=kind,
            linear_unit="m",
        )
        origin = LocalOrigin(
            enabled=self.origin_enabled.isChecked(),
            easting=self.origin_x.value(),
            northing=self.origin_y.value(),
            elevation=self.origin_z.value(),
            rotation_deg=self.origin_rotation.value(),
        )
        return self._source_manifest.with_updates(
            name=project_name,
            project_type=str(self.project_type.currentData()),
            crs=crs.to_dict(),
            cad_unit=str(self.cad_unit.currentData()),
            local_origin=origin.to_dict(),
        )

    def _accept_if_valid(self) -> None:
        try:
            self._result_manifest = self.build_manifest()
        except ValueError as exc:
            self.validation_hint.setText(f"🛑 {exc}")
            self.validation_hint.setStyleSheet("color: #A96761; font-weight: 600;")
            return
        self.accept()

    def result_manifest(self) -> ChainManifest:
        if hasattr(self, "_result_manifest"):
            return self._result_manifest
        return self.build_manifest()
