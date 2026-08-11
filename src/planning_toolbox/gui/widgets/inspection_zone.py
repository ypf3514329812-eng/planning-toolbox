"""数据检查区 (Data Inspection Zone Widget with Hero Stat Cards)."""
from typing import Dict, Any
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout
)
from PySide6.QtCore import Qt

class InspectionZoneWidget(QFrame):
    """
    数据检查区：使用英雄数值卡片 (Hero Stat Cards) 展示 DXF 单位、图层匹配及拓扑实体明细。
    已知单位显示绿色绿带，未知单位激活高亮红色阻断告警。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoneFrame")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        # 标题
        title = QLabel("图纸预检与拓扑状态 (DXF Inspection)")
        title.setObjectName("ZoneTitle")
        layout.addWidget(title)

        # 1. Separate units and semantic layers so the summary remains
        # readable when the inspection zone occupies half of the window.
        unit_box = QHBoxLayout()
        unit_box.addWidget(QLabel("DXF 图纸单位:"))
        self.lbl_unit = QLabel("等待选择图纸...")
        self.lbl_unit.setObjectName("BadgeWarning")
        unit_box.addWidget(self.lbl_unit)
        unit_box.addStretch()
        layout.addLayout(unit_box)

        layer_box = QHBoxLayout()
        layer_box.addWidget(QLabel("识别图层:"))
        self.lbl_layers = QLabel("PARCEL [0]   BUILDING [0]   GREEN [0]")
        self.lbl_layers.setStyleSheet("font-weight: 700; color: #7189AA;")
        self.lbl_layers.setWordWrap(True)
        layer_box.addWidget(self.lbl_layers, stretch=1)
        layout.addLayout(layer_box)

        # 2. 4 个 Hero 数值卡片 (QFrame#KpiCard)
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        # 卡片 1: 多段线总数
        self.card_total = self._create_kpi_card("多段线", "-", "📏")
        cards_layout.addWidget(self.card_total)

        # 卡片 2: 有效闭合数
        self.card_closed = self._create_kpi_card("有效闭合", "-", "🟢")
        cards_layout.addWidget(self.card_closed)

        # 卡片 3: 未闭合线数
        self.card_open = self._create_kpi_card("未闭合", "-", "🔴")
        cards_layout.addWidget(self.card_open)

        # 卡片 4: 嵌套环/孔洞歧义
        self.card_nested = self._create_kpi_card("孔洞歧义", "-", "⚠️")
        cards_layout.addWidget(self.card_nested)

        layout.addLayout(cards_layout)

        # 3. 未知单位红色警告框
        self.warning_box = QLabel(
            "🛑 单位安全阻断警告: 无法确认 DXF 单位 ($INSUNITS=0)。\n"
            "系统已自动阻止面积和距离计算。请先在 AutoCAD 中使用 UNITS 命令将图纸单位设为【米】，或在任务配置中选择单位回退值。"
        )
        self.warning_box.setStyleSheet(
            "background-color: #F4DDDA; color: #9B5C57; border: 1px solid #D6A19A; "
            "border-radius: 6px; padding: 8px; font-weight: 700; font-size: 12px; margin-top: 4px;"
        )
        self.warning_box.setWordWrap(True)
        self.warning_box.hide()  # 默认隐藏
        layout.addWidget(self.warning_box)

    def _create_kpi_card(self, label_text: str, default_val: str, icon_str: str) -> QFrame:
        card = QFrame()
        card.setObjectName("KpiCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(8, 6, 8, 6)
        c_layout.setSpacing(2)

        lbl_title = QLabel(f"{icon_str} {label_text}")
        lbl_title.setObjectName("KpiLabel")

        lbl_val = QLabel(default_val)
        lbl_val.setObjectName("KpiValue")
        lbl_val.setAlignment(Qt.AlignLeft)

        c_layout.addWidget(lbl_title)
        c_layout.addWidget(lbl_val)
        card.value_label = lbl_val  # 快捷引用
        return card

    def update_inspection(self, info: Dict[str, Any]):
        """根据 dxf_inspector 的扫描字典更新卡片数值与单位指示。"""
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

        # 显/隐单位警告框
        if not unit_known:
            self.warning_box.show()
        else:
            self.warning_box.hide()

        # 图层明细
        counts = info.get("layer_counts", {})
        p_count = counts.get("PARCEL", 0)
        b_count = counts.get("BUILDING", 0)
        g_count = counts.get("GREEN", 0)

        p_tag = f"PARCEL [{p_count}]" if info.get("has_parcel_layer") else "PARCEL [0]"
        b_tag = f"BUILDING [{b_count}]" if info.get("has_building_layer") else "BUILDING [0]"
        g_tag = f"GREEN [{g_count}]" if info.get("has_green_layer") else "GREEN [0]"
        self.lbl_layers.setText(f"{p_tag}   {b_tag}   {g_tag}")

        # KPI 卡片更新
        self.card_total.value_label.setText(str(info.get("total_polylines", 0)))
        self.card_closed.value_label.setText(str(info.get("valid_closed", 0)))
        
        open_n = info.get("open_polylines", 0)
        self.card_open.value_label.setText(str(open_n))
        self.card_open.value_label.setStyleSheet("color: #A96761;" if open_n > 0 else "color: #607A6A;")

        nested_n = info.get("nested_ring_count", 0)
        self.card_nested.value_label.setText(str(nested_n))
        self.card_nested.value_label.setStyleSheet("color: #A6814D;" if nested_n > 0 else "color: #607A6A;")

    def clear_inspection(self):
        self.lbl_unit.setText("等待选择图纸...")
        self.lbl_unit.setObjectName("BadgeWarning")
        self.lbl_unit.setStyle(self.lbl_unit.style())
        self.lbl_layers.setText("PARCEL [0]   BUILDING [0]   GREEN [0]")
        self.card_total.value_label.setText("-")
        self.card_closed.value_label.setText("-")
        self.card_open.value_label.setText("-")
        self.card_open.value_label.setStyleSheet("color: #607A6A;")
        self.card_nested.value_label.setText("-")
        self.card_nested.value_label.setStyleSheet("color: #607A6A;")
        self.warning_box.hide()
