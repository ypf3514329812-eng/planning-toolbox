"""Beginner-friendly per-building settings for CAD-to-SketchUp handoff."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from planning_toolbox.project.chain_manifest import ChainManifest
from planning_toolbox.sketchup import inspect_sketchup_buildings


_TYPE_LABELS = {
    "auto": "按项目自动判断",
    "residential": "居住建筑",
    "office": "办公建筑",
    "commercial": "商业建筑",
    "campus": "校园建筑",
    "generic": "通用建筑",
}
_ROOF_LABELS = {"flat": "平屋顶", "gable": "双坡屋顶", "hip": "四坡屋顶"}
_DETAIL_LABELS = {
    "massing": "快速体量",
    "course": "课程作业",
    "presentation": "汇报模型",
}


class BuildingScheduleDialog(QDialog):
    """Edit independent modeling parameters without exposing IDs to users."""

    def __init__(
        self,
        dxf_path: Path | str,
        chain_manifest: ChainManifest,
        building_layers: Sequence[str] | str | None,
        existing_overrides: Mapping[str, Mapping[str, Any]] | None = None,
        global_defaults: Mapping[str, Any] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("逐栋建筑参数表")
        self.resize(920, 650)
        self.setMinimumSize(760, 520)
        self._defaults = dict(global_defaults or {})
        catalog = inspect_sketchup_buildings(
            dxf_path, chain_manifest, building_layers
        )
        self._buildings = list(catalog["buildings"])
        self._overrides = self._canonicalize_existing(existing_overrides or {})
        self._init_ui(Path(dxf_path))
        self._populate_table()

    def _canonicalize_existing(
        self, values: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        by_id = {item["object_id"]: item for item in self._buildings}
        by_handle = {
            str(item["source_handle"]).upper(): item for item in self._buildings
        }
        result: dict[str, dict[str, Any]] = {}
        for raw_key, raw_value in values.items():
            if not isinstance(raw_value, Mapping):
                continue
            value = dict(raw_value)
            building = by_id.get(str(raw_key)) or by_id.get(
                str(value.get("object_id", ""))
            )
            if building is None:
                building = by_handle.get(
                    str(value.get("source_handle", "")).upper()
                )
            key = str(building["object_id"] if building else raw_key)
            if building:
                value.update(
                    {
                        "object_id": building["object_id"],
                        "source_handle": building["source_handle"],
                        "source_layer": building["source_layer"],
                        "display_name": building["display_name"],
                    }
                )
            result[key] = value
        return result

    def _init_ui(self, dxf_path: Path) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("为不同建筑分别设置高度、用途、屋顶和模型精度")
        title.setObjectName("ZoneTitle")
        layout.addWidget(title)

        intro = QLabel(
            f"当前图纸：{dxf_path.name}。列表只读取建筑图层中的顶层闭合轮廓，不会修改原 DXF。"
            "未单独设置的建筑继续使用第 10 项页面中的全局参数。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["建筑", "图层", "CAD 编号", "图元", "当前设置"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._load_selected_settings)
        layout.addWidget(self.table, stretch=1)

        selection_row = QHBoxLayout()
        select_all = QPushButton("全选建筑")
        select_all.clicked.connect(self.table.selectAll)
        selection_row.addWidget(select_all)
        self.selection_label = QLabel("请先在上表选择一栋或多栋建筑")
        self.selection_label.setWordWrap(True)
        selection_row.addWidget(self.selection_label, stretch=1)
        layout.addLayout(selection_row)

        form = QFormLayout()
        self.floors = QSpinBox()
        self.floors.setRange(0, 200)
        self.floors.setSpecialValueText("二维（不生成高度）")
        self.floors.setValue(int(self._defaults.get("floors", 0)))
        form.addRow("所选建筑楼层数:", self.floors)

        self.floor_height = QDoubleSpinBox()
        self.floor_height.setRange(0.0, 20.0)
        self.floor_height.setDecimals(2)
        self.floor_height.setSingleStep(0.1)
        self.floor_height.setSuffix(" m")
        self.floor_height.setSpecialValueText("未指定")
        self.floor_height.setValue(float(self._defaults.get("floor_height_m", 0.0)))
        form.addRow("所选建筑标准层高:", self.floor_height)

        self.building_type = QComboBox()
        for value, label in _TYPE_LABELS.items():
            self.building_type.addItem(label, value)
        self._set_combo(self.building_type, self._defaults.get("building_type", "auto"))
        form.addRow("所选建筑类型:", self.building_type)

        self.roof_type = QComboBox()
        for value, label in _ROOF_LABELS.items():
            self.roof_type.addItem(label, value)
        self._set_combo(self.roof_type, self._defaults.get("roof_type", "flat"))
        form.addRow("所选建筑屋顶:", self.roof_type)

        self.detail_level = QComboBox()
        for value, label in _DETAIL_LABELS.items():
            self.detail_level.addItem(label, value)
        self._set_combo(
            self.detail_level, self._defaults.get("model_detail_level", "course")
        )
        form.addRow("所选建筑精度:", self.detail_level)
        layout.addLayout(form)

        action_row = QHBoxLayout()
        apply_button = QPushButton("应用到选中建筑")
        apply_button.setObjectName("PrimaryButton")
        apply_button.clicked.connect(self._apply_to_selected)
        action_row.addWidget(apply_button)
        reset_button = QPushButton("恢复选中建筑为全局默认")
        reset_button.clicked.connect(self._reset_selected)
        action_row.addWidget(reset_button)
        layout.addLayout(action_row)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存逐栋参数")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _set_combo(combo: QComboBox, value: Any) -> None:
        index = combo.findData(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._buildings))
        for row, building in enumerate(self._buildings):
            values = (
                building["display_name"],
                building["source_layer"],
                building["source_handle"],
                building["source_type"],
                self._setting_summary(building),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, building["object_id"])
                self.table.setItem(row, column, item)
        self._refresh_summary()

    def _setting_summary(self, building: Mapping[str, Any]) -> str:
        value = self._overrides.get(str(building["object_id"]))
        if value is None:
            return "使用全局默认"
        floors = int(value.get("floors", 0))
        if floors > 0:
            height = float(value.get("floor_height_m", 0.0))
            mass = f"{floors} 层 × {height:g} m"
        else:
            mass = "二维"
        return " · ".join(
            (
                mass,
                _TYPE_LABELS.get(str(value.get("building_type", "auto")), "通用建筑"),
                _ROOF_LABELS.get(str(value.get("roof_type", "flat")), "平屋顶"),
                _DETAIL_LABELS.get(
                    str(value.get("model_detail_level", "course")), "课程作业"
                ),
            )
        )

    def _selected_buildings(self) -> list[dict[str, Any]]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self._buildings[row] for row in rows]

    def _load_selected_settings(self) -> None:
        selected = self._selected_buildings()
        self.selection_label.setText(
            f"已选择 {len(selected)} 栋；点击“应用”会把下方设置批量写入所选建筑。"
            if selected
            else "请先在上表选择一栋或多栋建筑"
        )
        if len(selected) != 1:
            return
        value = self._overrides.get(selected[0]["object_id"])
        if value is None:
            return
        self.floors.setValue(int(value.get("floors", 0)))
        self.floor_height.setValue(float(value.get("floor_height_m", 0.0)))
        self._set_combo(self.building_type, value.get("building_type", "auto"))
        self._set_combo(self.roof_type, value.get("roof_type", "flat"))
        self._set_combo(
            self.detail_level, value.get("model_detail_level", "course")
        )

    def _apply_to_selected(self) -> None:
        selected = self._selected_buildings()
        if not selected:
            QMessageBox.information(self, "尚未选择建筑", "请先在表格中选择建筑。")
            return
        if self.floors.value() > 0 and self.floor_height.value() <= 0:
            QMessageBox.warning(
                self,
                "标准层高未填写",
                "所选建筑需要生成三维体量，请填写大于 0 的标准层高。",
            )
            return
        for building in selected:
            key = str(building["object_id"])
            self._overrides[key] = {
                "object_id": key,
                "source_handle": building["source_handle"],
                "source_layer": building["source_layer"],
                "display_name": building["display_name"],
                "floors": self.floors.value(),
                "floor_height_m": self.floor_height.value(),
                "building_type": self.building_type.currentData(),
                "roof_type": self.roof_type.currentData(),
                "model_detail_level": self.detail_level.currentData(),
            }
        self._refresh_rows(selected)

    def _reset_selected(self) -> None:
        selected = self._selected_buildings()
        if not selected:
            QMessageBox.information(self, "尚未选择建筑", "请先在表格中选择建筑。")
            return
        for building in selected:
            self._overrides.pop(str(building["object_id"]), None)
        self._refresh_rows(selected)

    def _refresh_rows(self, buildings: Sequence[Mapping[str, Any]]) -> None:
        ids = {str(item["object_id"]) for item in buildings}
        for row, building in enumerate(self._buildings):
            if str(building["object_id"]) in ids:
                self.table.item(row, 4).setText(self._setting_summary(building))
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        current_ids = {str(item["object_id"]) for item in self._buildings}
        configured = sum(1 for key in self._overrides if key in current_ids)
        stale = len(self._overrides) - configured
        text = f"当前图纸识别到 {len(self._buildings)} 栋建筑，已单独设置 {configured} 栋。"
        if stale:
            text += f" 另有 {stale} 条来自旧图纸的设置会保留，但导出时会提示未匹配。"
        self.summary_label.setText(text)

    def building_overrides(self) -> dict[str, dict[str, Any]]:
        """Return a detached, JSON-friendly settings dictionary."""
        return deepcopy(self._overrides)

    def building_count(self) -> int:
        return len(self._buildings)


__all__ = ["BuildingScheduleDialog"]
