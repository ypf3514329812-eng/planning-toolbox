"""数据检查区 (Data Inspection Zone Widget)."""
from typing import Dict, Any
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
)
from PySide6.QtCore import Qt

class InspectionZoneWidget(QFrame):
    """
    数据检查区：展示 DXF 单位、图层匹配、多段线数量、未闭合线数及嵌套环前置检测。
    包含未知单位时的红框警告提醒。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoneFrame")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        # 标题
        title = QLabel("图纸数据检查 (DXF Data Inspection)")
        title.setObjectName("ZoneTitle")
        layout.addWidget(title)

        # 卡片网格
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        # 1. DXF 单位
        grid.addWidget(QLabel("DXF 单位 ($INSUNITS):"), 0, 0)
        self.lbl_unit = QLabel("等待选择图纸...")
        self.lbl_unit.setObjectName("BadgeWarning")
        grid.addWidget(self.lbl_unit, 0, 1)

        # 2. 图层检测
        grid.addWidget(QLabel("已匹配标准图层:"), 0, 2)
        self.lbl_layers = QLabel("PARCEL [-]  BUILDING [-]  GREEN [-]")
        grid.addWidget(self.lbl_layers, 0, 3)

        # 3. 多段线实体数
        grid.addWidget(QLabel("多段线总数:"), 1, 0)
        self.lbl_polylines = QLabel("-")
        grid.addWidget(self.lbl_polylines, 1, 1)

        # 4. 有效闭合数
        grid.addWidget(QLabel("有效闭合多边形:"), 1, 2)
        self.lbl_closed = QLabel("-")
        grid.addWidget(self.lbl_closed, 1, 3)

        # 5. 未闭合数
        grid.addWidget(QLabel("未闭合多段线:"), 2, 0)
        self.lbl_open = QLabel("-")
        grid.addWidget(self.lbl_open, 2, 1)

        # 6. 嵌套环/孔洞数
        grid.addWidget(QLabel("嵌套环/孔洞歧义:"), 2, 2)
        self.lbl_nested = QLabel("-")
        grid.addWidget(self.lbl_nested, 2, 3)

        layout.addLayout(grid)

        # 未知单位红色警告框
        self.warning_box = QLabel(
            "⚠️ 无法确认 DXF 单位，系统将阻止面积和距离计算。\n"
            "请先在 AutoCAD 中使用 UNITS 命令将图纸单位设为【米】，或在任务选项中指定回退单位。"
        )
        self.warning_box.setStyleSheet(
            "background-color: #4a1515; color: #ff9999; border: 1px solid #993333; "
            "border-radius: 6px; padding: 8px; font-weight: bold; margin-top: 6px;"
        )
        self.warning_box.setWordWrap(True)
        self.warning_box.hide()  # 默认隐藏
        layout.addWidget(self.warning_box)

    def update_inspection(self, info: Dict[str, Any]):
        """根据 dxf_inspector 的扫描字典更新数据检查区 UI。"""
        if not info.get("exists") or not info.get("valid_dxf"):
            self.clear_inspection()
            if info.get("exists") and not info.get("valid_dxf"):
                self.lbl_unit.setText("文件非合法 DXF")
                self.lbl_unit.setObjectName("BadgeError")
                self.lbl_unit.setStyle(self.lbl_unit.style())
            return

        # 单位
        unit_cn = info.get("unit_display_cn", "未知")
        unit_known = info.get("unit_known", False)
        self.lbl_unit.setText(unit_cn)
        self.lbl_unit.setObjectName("BadgeSuccess" if unit_known else "BadgeError")
        self.lbl_unit.setStyle(self.lbl_unit.style())

        # 隐/显未知单位警告框
        if not unit_known:
            self.warning_box.show()
        else:
            self.warning_box.hide()

        # 图层标记
        p_tag = "PARCEL [✓]" if info.get("has_parcel_layer") else "PARCEL [✗]"
        b_tag = "BUILDING [✓]" if info.get("has_building_layer") else "BUILDING [✗]"
        g_tag = "GREEN [✓]" if info.get("has_green_layer") else "GREEN [✗]"
        self.lbl_layers.setText(f"{p_tag}   {b_tag}   {g_tag}")

        # 数值
        self.lbl_polylines.setText(str(info.get("total_polylines", 0)))
        self.lbl_closed.setText(str(info.get("valid_closed", 0)))
        
        open_n = info.get("open_polylines", 0)
        self.lbl_open.setText(f"{open_n} 个" if open_n > 0 else "0 个")
        self.lbl_open.setStyleSheet("color: #ff9999;" if open_n > 0 else "color: #e0e0e6;")

        nested_n = info.get("nested_ring_count", 0)
        self.lbl_nested.setText(f"{nested_n} 组" if nested_n > 0 else "0 组")
        self.lbl_nested.setStyleSheet("color: #ffcc66;" if nested_n > 0 else "color: #e0e0e6;")

    def clear_inspection(self):
        self.lbl_unit.setText("等待选择图纸...")
        self.lbl_unit.setObjectName("BadgeWarning")
        self.lbl_unit.setStyle(self.lbl_unit.style())
        self.lbl_layers.setText("PARCEL [-]  BUILDING [-]  GREEN [-]")
        self.lbl_polylines.setText("-")
        self.lbl_closed.setText("-")
        self.lbl_open.setText("-")
        self.lbl_nested.setText("-")
        self.warning_box.hide()
