"""PySide6 桌面 GUI 工作台单元与集成测试套件."""
import os
import shutil
import pytest
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from planning_toolbox.gui.utils.dxf_inspector import inspect_dxf_file
from planning_toolbox.gui.workers.task_worker import TaskWorker
from planning_toolbox.gui.main_window import PlanningToolboxMainWindow
from planning_toolbox.gui.resources import gui_asset_path
from planning_toolbox.gui.single_instance import acquire_single_instance, release_single_instance
from planning_toolbox.gui.help_dialog import HelpDialog
from planning_toolbox.gui.assignment_guide import AssignmentGuideDialog
from planning_toolbox.gui.project_settings_dialog import ProjectSettingsDialog
from planning_toolbox.gui.workflow_dialog import FullChainWorkflowDialog
from planning_toolbox.gui.workflow import WORKFLOW_STAGES, mark_stage_complete
from planning_toolbox.gui.widgets.task_zone import TaskZoneWidget
from planning_toolbox.gui.widgets.result_zone import ResultZoneWidget
from planning_toolbox.project.chain_manifest import ChainManifest, new_chain_manifest

@pytest.fixture(scope="module")
def qapp():
    """提供单个 PySide6 QApplication 供测试使用。"""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"  # 无头模式运行
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_gui_icon_is_stable_and_available(qapp):
    """桌面版和源码版都应使用同一份项目图标。"""
    icon_path = gui_asset_path("planning_toolbox.ico")
    assert icon_path.exists()

    window = PlanningToolboxMainWindow()
    assert window.windowIcon().isNull() is False
    window.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows named mutex test")
def test_single_instance_guard_rejects_duplicate_before_gui_load():
    """A repeated launch must be rejected before heavy GUI modules load."""
    mutex_name = f"Local\\PlanningToolbox_Test_{os.getpid()}"
    first_handle = acquire_single_instance(mutex_name)
    assert first_handle is not None
    try:
        assert acquire_single_instance(mutex_name) is None
    finally:
        release_single_instance(first_handle)

    replacement_handle = acquire_single_instance(mutex_name)
    assert replacement_handle is not None
    release_single_instance(replacement_handle)

def test_dxf_inspector_sample_file():
    """测试 DXF 预检扫描工具对 sample_parcels.dxf 的准确性。"""
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    info = inspect_dxf_file(sample_dxf)

    assert info["exists"] is True
    assert info["valid_dxf"] is True
    assert info["unit_known"] is True
    assert info["unit_name_en"] == "Meters"
    assert info["has_parcel_layer"] is True
    assert info["has_building_layer"] is True
    assert info["has_green_layer"] is True
    assert info["total_polylines"] == 11
    assert info["valid_closed"] == 10
    assert info["open_polylines"] == 1
    assert info["nested_ring_count"] == 0

def test_dxf_inspector_nonexistent_file():
    """测试 DXF 预检扫描不存在的文件。"""
    info = inspect_dxf_file("nonexistent.dxf")
    assert info["exists"] is False

def test_gui_main_window_instantiation(qapp):
    """测试主窗口与 4 大区域 Widget 的正常实例化。"""
    window = PlanningToolboxMainWindow()
    assert window.windowTitle().startswith("Planning Toolbox 规划分析工作台")
    assert window.file_zone is not None
    assert window.inspection_zone is not None
    assert window.task_zone is not None
    assert window.result_zone is not None
    assert window.open_project_button is not None
    assert window.save_project_button is not None
    assert window.project_setup_button is not None
    assert window.workflow_button is not None
    assert window.comparison_button is not None
    assert window.result_zone.btn_result_export is not None
    assert window.result_zone.btn_assignment_package is not None
    window.result_zone.start_task("测试任务")
    assert "任务启动" in window.result_zone.log_edit.toPlainText()

def test_help_dialog_is_available_for_beginner_users(qapp):
    """The main window exposes a reusable Chinese tutorial dialog."""
    window = PlanningToolboxMainWindow()
    assert window.help_button is not None
    window._open_help()
    assert isinstance(window.help_dialog, HelpDialog)
    assert window.help_dialog.isVisible()
    assert window.help_dialog.tabs.count() == 5
    assert "DXF" in window.help_dialog.tabs.widget(0).toHtml()
    assert "保存项目" in window.help_dialog.tabs.widget(0).toHtml()
    assert "导出 Excel/PDF/图片" in window.help_dialog.tabs.widget(2).toHtml()
    assert "方案对比" in window.help_dialog.tabs.widget(1).toHtml()
    help_html = "".join(
        window.help_dialog.tabs.widget(index).toHtml()
        for index in range(window.help_dialog.tabs.count())
    )
    assert ".ptscene.json" in help_html
    assert "PT_UNDERLAY" in help_html
    window.help_dialog.close()


def test_assignment_guide_is_available_for_coursework_users(qapp):
    """The workbench exposes task-specific steps without requiring an API."""
    window = PlanningToolboxMainWindow()
    assert window.assignment_button is not None
    window._open_assignment_guide()
    assert isinstance(window.assignment_guide, AssignmentGuideDialog)
    assert window.assignment_guide.isVisible()
    assert window.assignment_guide.combo.count() == 6
    assert "建议步骤" in window.assignment_guide.browser.toPlainText()
    window.assignment_guide.close()


def test_full_chain_workflow_guide_routes_to_existing_tools(qapp, tmp_path):
    """The guide stays lightweight and navigates to existing task pages."""
    window = PlanningToolboxMainWindow()
    window._open_workflow()

    assert isinstance(window.workflow_dialog, FullChainWorkflowDialog)
    assert window.workflow_dialog.isVisible()
    assert window.workflow_dialog.stage_list.count() == 9
    state = mark_stage_complete(window.workflow_state, "setup")
    window.workflow_dialog.set_state(state)
    assert window.workflow_dialog.state()["current_step"] == "source"
    assert window.workflow_dialog.stage_list.currentItem().data(Qt.UserRole) == "source"
    window.workflow_dialog.source_combo.setCurrentIndex(
        window.workflow_dialog.source_combo.findData("image")
    )
    assert window.workflow_dialog.state()["source_kind"] == "image"

    routed = []
    window.workflow_dialog.navigate_requested.connect(
        lambda stage, source: routed.append((stage, source))
    )
    quality_row = [stage.key for stage in WORKFLOW_STAGES].index("quality")
    window.workflow_dialog.stage_list.setCurrentRow(quality_row)
    window.workflow_dialog._navigate()
    assert routed[-1] == ("quality", "image")

    window._navigate_workflow_stage("quality", "dxf")
    assert window.task_zone.tabs.currentIndex() == 7
    window._navigate_workflow_stage("sketchup", "dxf")
    assert window.task_zone.tabs.currentIndex() == 9
    window.workflow_dialog.refresh_context(
        {
            "working_dxf": str(tmp_path / "image_plan.dxf"),
            "lineage_count": 2,
            "semantic_scene_ready": True,
            "semantic_scene_path": str(tmp_path / "image_plan.ptscene.json"),
        }
    )
    assert "语义接力已连接" in window.workflow_dialog.working_file_label.text()
    assert ".ptscene.json" in window.workflow_dialog.working_file_label.toolTip()
    window.workflow_dialog.close()
    window.close()


def test_result_zone_offers_reviewed_dxf_as_next_working_copy(qapp, tmp_path):
    """Generated repair DXF needs one explicit confirmation before adoption."""
    source = tmp_path / "source.dxf"
    repaired = tmp_path / "source_repaired.dxf"
    source.write_text("source", encoding="utf-8")
    repaired.write_text("repair", encoding="utf-8")
    widget = ResultZoneWidget()
    requested = []
    widget.working_dxf_requested.connect(
        lambda path, task: requested.append((path, task))
    )
    widget.show_result(
        {
            "task_type": "quality_check",
            "source_file": str(source),
            "repair": {"output_file": str(repaired)},
            "output_files": [("安全修复 DXF", str(repaired))],
        }
    )

    assert widget.continuation_bar.isHidden() is False
    assert widget.btn_use_working_dxf.isEnabled() is True
    widget.btn_use_working_dxf.click()
    assert requested == [(str(repaired), "quality_check")]
    widget.close()


def test_result_zone_explains_semantic_image_handoff(qapp, tmp_path):
    """Image conversion results should expose what can flow into CAD and SU."""
    scene_file = tmp_path / "plan.ptscene.json"
    scene_file.write_text("{}", encoding="utf-8")
    widget = ResultZoneWidget()
    widget.show_result(
        {
            "task_type": "image_to_dxf",
            "conversion_mode": "black_white_linework",
            "line_count": 30,
            "raw_line_count": 40,
            "reference_width_m": 120.0,
            "semantic_scene_file": str(scene_file),
            "semantic_scene_summary": {
                "semantic_object_count": 8,
                "review_required_count": 8,
                "underlay_entity_count": 22,
            },
        }
    )

    first_column = [
        widget.table.item(row, 0).text()
        for row in range(widget.table.rowCount())
    ]
    assert "全链路语义交接" in first_column
    assert "语义候选已写入" in widget.lbl_warning_banner.text()
    widget.close()


def test_result_zone_shows_semantic_road_network_quality_status(qapp):
    widget = ResultZoneWidget()
    widget.show_result(
        {
            "task_type": "image_to_dxf",
            "conversion_mode": "semantic_guide",
            "reference_width_m": 120.0,
            "region_counts": {
                "AI_BUILDING": 2,
                "AI_ROAD": 4,
                "AI_GREEN": 6,
                "AI_WATER": 0,
                "AI_PARKING": 1,
            },
            "region_areas_m2": {},
            "semantic_road_detection": {
                "region_count_after_gap_heal": 4,
                "network_component_count": 2,
                "healed_region_count": 1,
                "status": "multiple_networks_review",
            },
        }
    )

    first_column = [
        widget.table.item(row, 0).text()
        for row in range(widget.table.rowCount())
    ]
    road_row = first_column.index("道路网络检查")
    assert "网络块 2 个" in widget.table.item(road_row, 2).text()
    assert "多个网络块" in widget.table.item(road_row, 3).text()
    widget.close()


def test_result_zone_shows_source_boundary_alignment_quality(qapp):
    widget = ResultZoneWidget()
    widget.show_result(
        {
            "task_type": "image_to_dxf",
            "conversion_mode": "black_white_linework",
            "reference_width_m": 120.0,
            "alignment_quality": {
                "building": {
                    "mean_boundary_distance_px": 0.8,
                    "status": "aligned",
                },
                "road": {
                    "mean_boundary_distance_px": 3.5,
                    "p90_boundary_distance_px": 11.4,
                    "status": "review_required",
                },
            },
        }
    )

    first_column = [
        widget.table.item(row, 0).text()
        for row in range(widget.table.rowCount())
    ]
    alignment_row = first_column.index("原图边界对齐")
    assert "建筑均值 0.8 px" in widget.table.item(alignment_row, 1).text()
    assert "道路均值 3.5 px" in widget.table.item(alignment_row, 2).text()
    assert "建议先看叠加图" in widget.table.item(alignment_row, 3).text()
    widget.close()


def test_result_zone_shows_road_centerline_candidates(qapp):
    widget = ResultZoneWidget()
    widget.show_result(
        {
            "task_type": "image_to_dxf",
            "conversion_mode": "black_white_linework",
            "reference_width_m": 120.0,
            "road_centerline_candidate_count": 3,
            "road_centerline_width_m": 10.0,
            "road_centerline_review_required_count": 1,
        }
    )

    first_column = [
        widget.table.item(row, 0).text()
        for row in range(widget.table.rowCount())
    ]
    centerline_row = first_column.index("道路中心线候选")
    assert widget.table.item(centerline_row, 1).text() == "3 条"
    assert "可接力 SketchUp" in widget.table.item(centerline_row, 2).text()
    assert "高可信 2 条，需复核 1 条" in widget.table.item(centerline_row, 3).text()
    assert "建议总宽 10 m" in widget.table.item(centerline_row, 3).text()
    assert "叠加图" in widget.table.item(centerline_row, 3).text()
    widget.close()


def test_result_zone_offers_one_click_road_repair_from_image_result(qapp, tmp_path):
    source = tmp_path / "source.png"
    guide = tmp_path / "source_semantic_guide_template.png"
    source.write_bytes(b"source")
    guide.write_bytes(b"guide")
    widget = ResultZoneWidget()
    captured = []
    widget.road_repair_requested.connect(
        lambda source_path, guide_path, review_path: captured.append(
            (source_path, guide_path, review_path)
        )
    )
    widget.show_result(
        {
            "task_type": "image_to_dxf",
            "conversion_mode": "black_white_linework",
            "source_file": str(source),
            "semantic_guide_template_file": str(guide),
            "road_centerline_candidate_count": 2,
        }
    )

    assert widget.btn_edit_road_guide.isEnabled() is True
    widget.btn_edit_road_guide.click()
    assert captured == [(str(source), str(guide), "")]
    widget.close()


def test_result_zone_offers_direct_sketchup_handoff_from_image_result(qapp, tmp_path):
    dxf = tmp_path / "converted.dxf"
    dxf.write_bytes(b"dxf")
    widget = ResultZoneWidget()
    captured = []
    widget.sketchup_handoff_requested.connect(
        lambda path, count, review_count: captured.append(
            (path, count, review_count)
        )
    )
    widget.show_result(
        {
            "task_type": "image_to_dxf",
            "dxf_file": str(dxf),
            "road_centerline_candidate_count": 4,
            "road_centerline_review_required_count": 1,
            "output_files": [("DXF", str(dxf))],
        }
    )

    assert widget.btn_continue_sketchup.isEnabled() is True
    widget.btn_continue_sketchup.click()
    assert captured == [(str(dxf), 4, 1)]
    widget.close()


def test_main_window_routes_road_repair_into_semantic_guide_editor(qapp, tmp_path):
    source = tmp_path / "source.png"
    guide = tmp_path / "guide.png"
    source.write_bytes(b"source")
    guide.write_bytes(b"guide")
    window = PlanningToolboxMainWindow()
    calls = []
    window.task_zone._edit_semantic_guide = (
        lambda review_overlay_path=None: calls.append(review_overlay_path)
    )

    window._open_road_repair_editor(str(source), str(guide))

    assert window.task_zone.task_selector.currentIndex() == 8
    assert window.task_zone.image_file_input.text() == str(source.resolve())
    assert window.task_zone.image_semantic_guide_input.text() == str(guide.resolve())
    assert window.task_zone.image_conversion_mode.currentData() == "semantic_guide"
    assert calls == [None]
    window.close()


def test_main_window_routes_image_result_directly_to_sketchup(qapp, tmp_path):
    dxf = tmp_path / "converted.dxf"
    dxf.write_bytes(b"dxf")
    window = PlanningToolboxMainWindow()

    window._open_sketchup_handoff(str(dxf), 5, 2)

    assert window.file_zone.get_dxf_path() == str(dxf.resolve())
    assert window.task_zone.task_selector.currentIndex() == 9
    assert window.task_zone.sketchup_centerline_corridor.isChecked() is True
    assert (
        window.task_zone.sketchup_centerline_confidence_policy.currentData()
        == "trusted_only"
    )
    assert "高可信 3 条" in window.task_zone.lbl_preflight.text()
    assert "待复核 2 条" in window.task_zone.lbl_preflight.text()
    window.close()


def test_result_zone_shows_sketchup_top_level_bundle_without_error(qapp):
    """The SU result must distinguish raw source geometry from editable groups."""
    widget = ResultZoneWidget()
    widget.show_result(
        {
            "task_type": "sketchup_export",
            "handoff_file": "site.ptsu.json",
            "plugin_file": "PlanningToolbox_SketchUp_Importer.rbz",
            "object_count": 2464,
            "top_level_object_count": 26,
            "building_count": 8,
            "floors": 6,
            "floor_height_m": 3.0,
            "semantic_scene_validated": True,
            "semantic_review_required_count": 25,
            "underlay_bundle_count": 1,
            "underlay_source_entity_count": 2439,
            "road_centerline_full_path_resampled_count": 13,
            "building_layer_semantics_count": 5,
            "building_layer_floor_semantics_count": 4,
            "building_layer_total_height_semantics_count": 2,
            "course_model_readiness": {
                "passed_count": 7,
                "item_count": 9,
                "review_count": 2,
                "review_labels": ["建筑层次", "停车表达"],
            },
        }
    )

    assert widget.kpi_parcels.val_label.text() == "26"
    first_column = [
        widget.table.item(row, 0).text()
        for row in range(widget.table.rowCount())
    ]
    semantic_row = first_column.index("全链路语义")
    assert "2439 条参考线 → 1 个锁定底图组" in widget.table.item(
        semantic_row, 2
    ).text()
    road_coverage_row = first_column.index("道路全长覆盖")
    assert widget.table.item(road_coverage_row, 1).text() == "完整取样 13 条"
    assert "不截尾" in widget.table.item(road_coverage_row, 3).text()
    layer_semantics_row = first_column.index("建筑图层参数接力")
    assert widget.table.item(layer_semantics_row, 1).text() == "明确参数 5 栋"
    readiness_row = first_column.index("课程基础模型检查")
    assert widget.table.item(readiness_row, 1).text() == "通过 7/9 项"
    assert "建筑层次、停车表达" in widget.table.item(readiness_row, 2).text()
    assert "课程模型待完善：建筑层次、停车表达" in widget.lbl_warning_banner.text()
    widget.close()


def test_main_window_adopts_generated_dxf_and_records_lineage(qapp, tmp_path):
    """Adoption changes only the current input pointer and keeps a bounded lineage."""
    source = tmp_path / "source.dxf"
    repaired = tmp_path / "source_repaired.dxf"
    shutil.copy2("sample_data/sample_parcels.dxf", source)
    shutil.copy2("sample_data/sample_parcels.dxf", repaired)
    window = PlanningToolboxMainWindow()
    window.file_zone.set_dxf_path(str(source))

    assert window._adopt_working_dxf(
        str(repaired), "quality_check", automatic=False
    )
    assert window.file_zone.get_dxf_path() == str(repaired.resolve())
    assert window.workflow_state["working_dxf"] == str(repaired.resolve())
    assert window.workflow_state["dxf_lineage"][-1]["source_path"] == str(source.resolve())
    assert window.workflow_state["dxf_lineage"][-1]["mode"] == "confirmed"
    window.close()


def test_main_window_project_round_trip_restores_workspace(qapp, tmp_path):
    """Project buttons restore paths and task parameters without rerunning work."""
    window = PlanningToolboxMainWindow()
    missing_dxf = tmp_path / "coursework.dxf"
    project_path = tmp_path / "coursework.ptx"
    window.file_zone.set_dxf_path(str(missing_dxf))
    window.file_zone.set_output_dir(str(tmp_path / "results"))
    window.task_zone.tabs.setCurrentIndex(1)
    window.task_zone.spin_floors.setValue(6)
    window.chain_manifest = new_chain_manifest("全链路课程作业", "urban_design").with_updates(
        crs={
            "authority": "EPSG",
            "code": 4547,
            "name": "CGCS2000 投影坐标",
            "kind": "projected",
            "linear_unit": "m",
        },
        cad_unit="m",
    )
    saved_project_id = window.chain_manifest.project_id
    window.workflow_state = mark_stage_complete(window.workflow_state, "quality")

    assert window._save_project_to_path(project_path)
    window.file_zone.set_output_dir("other-output")
    window.task_zone.spin_floors.setValue(0)
    assert window._load_project_from_path(project_path)

    assert window.file_zone.get_dxf_path() == str(missing_dxf)
    assert window.file_zone.get_output_dir() == str(tmp_path / "results")
    assert window.task_zone.tabs.currentIndex() == 1
    assert window.task_zone.spin_floors.value() == 6
    assert window.chain_manifest.project_id == saved_project_id
    assert window.chain_manifest.crs.code == 4547
    assert "quality" in window.workflow_state["completed_steps"]
    assert "EPSG:4547" in window.subtitle.text()
    window.close()


def test_project_settings_dialog_builds_lightweight_coordinate_contract(qapp):
    dialog = ProjectSettingsDialog(new_chain_manifest())
    dialog.project_name.setText("居住区课程作业")
    dialog.crs_code.setText("4547")
    dialog.crs_name.setText("CGCS2000 投影坐标")
    dialog.crs_kind.setCurrentIndex(dialog.crs_kind.findData("projected"))
    dialog.origin_enabled.setChecked(True)
    dialog.origin_x.setValue(385000.0)
    dialog.origin_y.setValue(3456000.0)

    manifest = dialog.build_manifest()

    assert isinstance(manifest, ChainManifest)
    assert manifest.name == "居住区课程作业"
    assert manifest.crs.metric_ready is True
    assert manifest.local_origin.enabled is True
    assert manifest.local_origin.easting == pytest.approx(385000.0)
    dialog.close()


def test_main_window_scrolls_on_short_screens(qapp):
    """The workbench keeps content readable instead of clipping it when short."""
    window = PlanningToolboxMainWindow()
    window.resize(960, 680)
    window.show()
    qapp.processEvents()

    assert window.scroll_area.objectName() == "MainScrollArea"
    assert window.scroll_area.verticalScrollBar().maximum() > 0
    assert window.middle_splitter.orientation() == Qt.Vertical
    assert window.scroll_area.horizontalScrollBar().maximum() == 0
    assert window.result_zone.minimumHeight() == 390
    window.close()


def test_concept_plan_tab_exposes_beginner_parameters(qapp):
    """The GUI exposes the local concept-plan generator without an API key."""
    widget = TaskZoneWidget()
    assert widget.tabs.count() == 10
    assert widget.tabs.tabText(5) == "6. 方案草图生成"
    assert widget.tabs.tabText(6) == "7. CAD 图层标准化"
    assert widget.tabs.tabText(7) == "8. 图纸质量增强检查"
    assert widget.tabs.tabText(8) == "9. AI 效果图转 CAD"
    assert widget.tabs.tabText(9) == "10. CAD → SketchUp 模型交接"
    assert widget.tabs.tabBar().isHidden()
    assert widget.task_selector.count() == 10
    widget.task_selector.setCurrentIndex(8)
    assert widget.tabs.currentIndex() == 8
    assert "AI 效果图转 CAD" in widget.btn_run.text()
    assert isinstance(widget.tabs.widget(5), QScrollArea)
    assert isinstance(widget.tabs.widget(8), QScrollArea)
    assert widget.concept_building_count.value() == 1
    assert widget.concept_coverage.value() == pytest.approx(25.0)
    assert widget.concept_setback.value() == pytest.approx(5.0)
    assert widget.concept_building_gap.value() == pytest.approx(0.0)
    assert widget.concept_access_width.value() == pytest.approx(0.0)
    assert widget.concept_standard_profile.currentData() == "custom_local"
    assert widget.concept_standard_profile.count() == 3
    assert widget.layer_use_china_standard.isChecked() is True
    assert widget.layer_drafting_profile.currentData() == "china_coursework_general"
    assert widget.layer_drafting_profile.count() == 3
    assert "不代表法定审查" in widget.lbl_layer_drafting_profile.text()
    assert widget.concept_floors.value() == 0
    assert widget.concept_parking_ratio.value() == pytest.approx(0.0)
    assert widget.image_reference_width.value() == pytest.approx(0.0)
    assert widget.image_focus_site_only.isChecked() is True
    assert widget.image_conversion_mode.currentData() == "color_regions"
    assert widget.image_conversion_mode.count() == 3
    assert widget.image_semantic_guide_row.isHidden() is True
    assert widget.image_line_threshold.value() == 220
    assert widget.image_line_polarity.currentData() == "auto"
    assert widget.image_detail_level.currentData() == "fine"
    assert widget.image_optimize_linework.isChecked() is True
    assert widget.image_use_knowledge_assist.isChecked() is True
    assert widget.image_create_knowledge_card.isChecked() is True
    assert widget.image_knowledge_project_type.currentText() == "待确认"
    assert widget.image_collect_cad_sample.isChecked() is False
    assert widget.image_collect_cad_sample.isEnabled() is True
    assert widget.quality_repair_profile.currentData() == "minimize_manual"
    assert widget.quality_merge_fragments.isChecked() is True
    assert widget.quality_simplify_collinear.isChecked() is True
    assert widget.quality_standardize_layers.isChecked() is True
    widget.quality_repair_profile.setCurrentIndex(2)
    assert widget.quality_merge_fragments.isChecked() is False
    assert widget.quality_remove_duplicates.currentIndex() == 1
    widget.quality_repair_profile.setCurrentIndex(0)
    widget.image_conversion_mode.setCurrentIndex(1)
    assert widget.image_line_threshold.isEnabled() is True
    assert widget.image_line_polarity.isEnabled() is True
    assert widget.image_detail_level.isEnabled() is True
    assert widget.image_optimize_linework.isEnabled() is True
    assert widget.image_color_tolerance.isEnabled() is False
    assert widget.image_focus_site_only.isEnabled() is False
    widget.image_conversion_mode.setCurrentIndex(2)
    assert widget.image_conversion_mode.currentData() == "semantic_guide"
    assert widget.image_semantic_guide_row.isHidden() is False
    assert widget.image_color_tolerance.isEnabled() is True
    assert widget.image_line_threshold.isEnabled() is False
    widget.image_semantic_guide_input.setText("C:/course/guide.png")
    state = widget.get_project_state()
    assert state["image_semantic_guide_file"] == "C:/course/guide.png"
    widget.image_create_knowledge_card.setChecked(False)
    assert widget.image_collect_cad_sample.isEnabled() is False


def test_gis_tab_exposes_lightweight_and_extended_vector_modes(qapp, tmp_path):
    """The same compact GIS tab supports GeoJSON plus optional GPKG/SHP workflows."""
    widget = TaskZoneWidget()
    assert widget.gis_mode_combo.count() == 4
    assert widget.gis_mode_combo.itemData(0) == "dxf_to_geojson"
    assert widget.gis_mode_combo.itemData(1) == "geojson_to_dxf"
    assert widget.gis_mode_combo.itemData(2) == "vector_to_dxf"
    assert widget.gis_mode_combo.itemData(3) == "dxf_to_gpkg"

    captured = []
    widget.run_task_signal.connect(lambda task_type, params: captured.append((task_type, params)))
    widget.tabs.setCurrentIndex(3)
    widget.gis_mode_combo.setCurrentIndex(2)
    source = tmp_path / "coursework.gpkg"
    widget.geojson_file_input.setText(str(source))
    widget._on_run_clicked()
    assert captured[-1][0] == "gis_import"
    assert captured[-1][1]["use_vector_bridge"] is True
    assert captured[-1][1]["requires_project_crs"] is True
    assert any(name in widget.gis_notice.text() for name in ("ArcGIS Pro", "QGIS/GDAL"))

    widget.gis_mode_combo.setCurrentIndex(3)
    widget._on_run_clicked()
    assert captured[-1][0] == "gis_export"
    assert captured[-1][1]["output_format"] == "gpkg"
    assert captured[-1][1]["requires_project_crs"] is True


def test_gis_geojson_worker_writes_the_selected_dxf_unit(qapp, tmp_path):
    """Regression: the GUI worker passes target_unit instead of an invalid keyword."""
    import json
    import ezdxf

    source = tmp_path / "projected.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "crs": {"type": "name", "properties": {"name": "EPSG:4547"}},
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [10, 0], [10, 5], [0, 5], [0, 0]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    worker = TaskWorker(
        "gis_import",
        {
            "geojson_path": str(source),
            "output_dir": str(tmp_path),
            "unit": "m",
        },
    )
    results = []
    worker.finished_signal.connect(results.append)
    worker._run_gis_import_task()

    assert results[0]["imported_polygons"] == 1
    output = Path(results[0]["output_files"][0][1])
    assert ezdxf.readfile(output).header["$INSUNITS"] == 6


def test_task_worker_parcel_execution(qapp):
    """测试 TaskWorker 线程后台执行 parcel 任务。"""
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    params = {
        "dxf_path": str(sample_dxf),
        "output_dir": "output/gui_test"
    }

    worker = TaskWorker("parcel", params)
    
    finished_data = {}
    def on_finished(res):
        finished_data.update(res)

    worker.finished_signal.connect(on_finished)
    worker.run()  # 直接同步调用 run() 校验算法结果

    assert finished_data.get("task_type") == "parcel"
    assert finished_data.get("valid_count") == 3
    assert finished_data.get("open_count") == 1
    assert finished_data.get("total_ha") == pytest.approx(2.23, abs=1e-2)

def test_task_worker_indicator_execution(qapp):
    """测试 TaskWorker 线程后台执行 indicator 任务。"""
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    params = {
        "dxf_path": str(sample_dxf),
        "floors": 6,
        "output_dir": "output/gui_test"
    }

    worker = TaskWorker("indicator", params)
    
    finished_data = {}
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.run()

    assert finished_data.get("task_type") == "indicator"
    assert finished_data.get("parcels_count") == 3
    assert len(finished_data.get("indicators", [])) == 3


def test_image_worker_generates_lightweight_card_and_keeps_source_unchanged(qapp, tmp_path):
    """The GUI workflow catalogs metadata without embedding or copying the image."""
    from PIL import Image, ImageDraw

    from planning_toolbox.utils.file_integrity import sha256_file

    image_path = tmp_path / "knowledge_gui_plan.png"
    image = Image.new("RGB", (240, 160), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((35, 35, 100, 75), fill=(198, 119, 119))
    draw.rectangle((30, 95, 215, 112), fill=(151, 151, 145))
    draw.ellipse((50, 118, 105, 143), fill=(126, 165, 142))
    image.save(image_path)
    before = sha256_file(image_path)

    worker = TaskWorker(
        "image_to_dxf",
        {
            "image_path": str(image_path),
            "output_dir": str(tmp_path / "output"),
            "conversion_mode": "color_regions",
            "reference_width_m": 120.0,
            "color_tolerance": 20,
            "min_component_pixels": 20,
            "create_knowledge_card": True,
            "knowledge_project_type": "居住区总平面",
            "knowledge_tags": "住宅,课程作业",
            "collect_cad_sample": False,
        },
    )
    result = {}
    errors = []
    worker.finished_signal.connect(lambda value: result.update(value))
    worker.error_signal.connect(lambda title, message: errors.append((title, message)))
    worker.run()

    assert errors == []
    assert result["zero_mutation_verified"] is True
    assert sha256_file(image_path) == before
    card_path = Path(result["knowledge_card"]["card_path"])
    assert card_path.exists()
    assert "cad_knowledge_reference" not in result
    assert not (card_path.parent / "cad_samples").exists()

    result_zone = ResultZoneWidget()
    result_zone.show_result(result)
    assert result_zone.btn_curate_cad.isEnabled() is True
    result_zone.close()


def test_image_worker_uses_semantic_guide_without_mutating_either_image(qapp, tmp_path):
    """A guide supplies roles while the original remains the SketchUp underlay."""
    from PIL import Image, ImageDraw

    from planning_toolbox.utils.file_integrity import sha256_file

    source = tmp_path / "guided_underlay.png"
    Image.new("RGB", (320, 220), (255, 255, 255)).save(source)
    guide = tmp_path / "guided_roles.png"
    guide_image = Image.new("RGB", (320, 220), (250, 250, 250))
    draw = ImageDraw.Draw(guide_image)
    draw.rectangle((35, 35, 125, 105), fill=(198, 119, 119))
    draw.rounded_rectangle((20, 145, 300, 180), radius=10, fill=(151, 151, 145))
    guide_image.save(guide)
    source_hash = sha256_file(source)
    guide_hash = sha256_file(guide)

    worker = TaskWorker(
        "image_to_dxf",
        {
            "image_path": str(source),
            "semantic_guide_path": str(guide),
            "output_dir": str(tmp_path / "guided_worker_output"),
            "conversion_mode": "semantic_guide",
            "reference_width_m": 160.0,
            "color_tolerance": 20,
            "min_component_pixels": 20,
            "create_knowledge_card": False,
            "collect_cad_sample": False,
        },
    )
    result = {}
    errors = []
    worker.finished_signal.connect(lambda value: result.update(value))
    worker.error_signal.connect(lambda title, message: errors.append((title, message)))
    worker.run()

    assert errors == []
    assert result["conversion_mode"] == "semantic_guide"
    assert result["semantic_guide_zero_mutation_verified"] is True
    assert result["region_counts"]["AI_BUILDING"] == 1
    assert result["region_counts"]["AI_ROAD"] == 1
    assert sha256_file(source) == source_hash
    assert sha256_file(guide) == guide_hash
    result_zone = ResultZoneWidget()
    result_zone.show_result(result)
    first_column = [
        result_zone.table.item(row, 0).text()
        for row in range(result_zone.table.rowCount())
    ]
    assert "语义引导图" in first_column
    assert "叠加检查图" in result_zone.lbl_warning_banner.text()
    result_zone.close()


def test_task_worker_indicator_requires_floors(qapp, tmp_path):
    """Missing floor input must produce a clear validation error."""
    worker = TaskWorker(
        "indicator",
        {"dxf_path": "sample_data/sample_parcels.dxf", "output_dir": str(tmp_path)},
    )
    errors = []
    worker.error_signal.connect(lambda title, message: errors.append((title, message)))
    worker.run()

    assert errors[0][0] == "参数校验错误"
    assert "楼层倍数" in errors[0][1]


def test_task_worker_batch_execution(qapp, tmp_path):
    """The GUI worker exposes the batch analyzer and returns a summary file."""
    input_dir = tmp_path / "batch_input"
    input_dir.mkdir()
    shutil.copy2("sample_data/sample_parcels.dxf", input_dir / "a.dxf")
    shutil.copy2("sample_data/sample_parcels.dxf", input_dir / "b.dxf")

    worker = TaskWorker(
        "batch",
        {
            "input_dir": str(input_dir),
            "batch_task": "parcel",
            "output_dir": str(tmp_path / "batch_output"),
        },
    )
    finished_data = {}
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.run()

    assert finished_data["task_type"] == "batch"
    assert finished_data["success_count"] == 2
    assert Path(finished_data["output_files"][0][1]).exists()


def test_task_worker_layer_standardize_execution(qapp, tmp_path):
    """The GUI worker exposes layer standardization without mutating the source DXF."""
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    before = sample_dxf.read_bytes()
    worker = TaskWorker(
        "layer_standardize",
        {
            "dxf_path": str(sample_dxf),
            "output_dir": str(tmp_path),
            "use_china_standard": True,
            "drafting_profile_id": "china_coursework_general",
        },
    )
    finished_data = {}
    errors = []
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.error_signal.connect(lambda title, message: errors.append((title, message)))
    worker.run()

    assert not errors
    assert finished_data["task_type"] == "layer_standardize"
    assert finished_data["remapped_total"] >= 0
    assert finished_data["drafting_profile_id"] == "china_coursework_general"
    assert finished_data["drafting_compliance"]["status"] == "review_required"
    assert Path(finished_data["output_files"][0][1]).is_file()
    assert Path(finished_data["output_files"][1][1]).is_file()
    assert Path(finished_data["output_files"][2][1]).is_file()
    assert Path(finished_data["output_files"][3][1]).is_file()
    assert sample_dxf.read_bytes() == before


def test_task_worker_quality_check_execution(qapp, tmp_path):
    """The quality task returns a repaired copy and keeps the source unchanged."""
    import ezdxf

    dxf_path = tmp_path / "quality_input.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for _ in range(2):
        polyline = msp.add_lwpolyline(
            [(0, 0), (10, 0), (10, 10), (0, 10)],
            dxfattribs={"layer": "PARCEL"},
        )
        polyline.close(True)
    msp.add_lwpolyline([(20, 0), (30, 0), (30, 10), (20, 0.005)], dxfattribs={"layer": "PARCEL"})
    msp.add_line((0, 20), (10, 20), dxfattribs={"layer": "ROAD"})
    msp.add_circle((20, 20), 3, dxfattribs={"layer": "SYMBOL"})
    doc.saveas(dxf_path)
    before = dxf_path.read_bytes()

    worker = TaskWorker(
        "quality_check",
        {
            "dxf_path": str(dxf_path),
            "output_dir": str(tmp_path / "quality_output"),
            "near_closed_tolerance": 0.01,
            "remove_duplicates": True,
            "close_near_closed": True,
        },
    )
    finished_data = {}
    errors = []
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.error_signal.connect(lambda title, message: errors.append((title, message)))
    worker.run()

    assert not errors
    assert finished_data["task_type"] == "quality_check"
    assert finished_data["duplicate_count"] == 1
    assert finished_data["near_closed_count"] == 1
    assert finished_data["complex_entity_counts"]["LINE"] == 1
    assert finished_data["complex_entity_counts"]["CIRCLE"] == 1
    assert finished_data["repair"]["removed_duplicates"] == 1
    assert finished_data["repair"]["closed_polylines"] == 1
    assert Path(finished_data["repair"]["output_file"]).is_file()
    assert dxf_path.read_bytes() == before


def test_task_workers_preserve_semantic_scene_through_repair_and_layers(qapp, tmp_path):
    """The recommended image→repair→layers chain must keep validated meanings."""
    import ezdxf

    from planning_toolbox.project.semantic_scene import (
        build_semantic_scene_from_dxf,
        load_semantic_scene_for_dxf,
    )
    from planning_toolbox.utils.file_integrity import sha256_file

    source = tmp_path / "image_plan.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BW_LINEWORK")
    doc.layers.add("BW_BUILDING_CANDIDATE")
    doc.modelspace().add_line(
        (0, 0), (30, 0), dxfattribs={"layer": "BW_LINEWORK"}
    )
    doc.modelspace().add_lwpolyline(
        [(2, 2), (12, 2), (12, 10), (2, 10)],
        close=True,
        dxfattribs={"layer": "BW_BUILDING_CANDIDATE"},
    )
    doc.saveas(source)
    source_hash = sha256_file(source)
    build_semantic_scene_from_dxf(
        source,
        source_image_path=tmp_path / "source.png",
        source_image_sha256="c" * 64,
        reference_width_m=80.0,
        conversion_mode="black_white_linework",
    )

    quality_result = {}
    quality_errors = []
    quality_worker = TaskWorker(
        "quality_check",
        {
            "dxf_path": str(source),
            "output_dir": str(tmp_path / "quality"),
            "near_closed_tolerance": 0.01,
        },
    )
    quality_worker.finished_signal.connect(lambda value: quality_result.update(value))
    quality_worker.error_signal.connect(
        lambda title, message: quality_errors.append((title, message))
    )
    quality_worker.run()

    assert quality_errors == []
    repaired = Path(quality_result["repair"]["output_file"])
    assert Path(quality_result["semantic_scene_file"]).is_file()
    assert load_semantic_scene_for_dxf(repaired) is not None

    layer_result = {}
    layer_errors = []
    layer_worker = TaskWorker(
        "layer_standardize",
        {
            "dxf_path": str(repaired),
            "output_dir": str(tmp_path / "layers"),
            "use_china_standard": False,
        },
    )
    layer_worker.finished_signal.connect(lambda value: layer_result.update(value))
    layer_worker.error_signal.connect(
        lambda title, message: layer_errors.append((title, message))
    )
    layer_worker.run()

    assert layer_errors == []
    standardized = Path(layer_result["output_files"][0][1])
    final_scene = load_semantic_scene_for_dxf(standardized)
    assert final_scene is not None
    assert final_scene["source"]["source_image_sha256"] == "c" * 64
    assert final_scene["summary"]["semantic_object_count"] == 1
    assert final_scene["lineage"]["parent_scene_path"] == quality_result[
        "semantic_scene_file"
    ]
    assert sha256_file(source) == source_hash


def test_task_worker_minimum_manual_repair_execution(qapp, tmp_path):
    """The recommended profile merges only safe non-branching fragments."""
    import ezdxf

    dxf_path = tmp_path / "fragmented_input.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("建筑")
    msp = doc.modelspace()
    msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "建筑"})
    msp.add_line((5.02, 0), (10, 0), dxfattribs={"layer": "建筑"})
    doc.saveas(dxf_path)

    worker = TaskWorker(
        "quality_check",
        {
            "dxf_path": str(dxf_path),
            "output_dir": str(tmp_path / "minimum_manual_output"),
            "repair_profile": "minimize_manual",
            "remove_duplicates": True,
            "close_near_closed": True,
            "near_closed_tolerance": 0.01,
            "remove_duplicate_lines": True,
            "merge_connected_fragments": True,
            "join_tolerance": 0.05,
            "simplify_collinear_vertices": True,
            "collinear_tolerance": 0.01,
            "remove_short_vertices": True,
            "min_segment_length": 0.01,
            "standardize_layers": True,
            "require_known_units": True,
        },
    )
    finished_data = {}
    errors = []
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.error_signal.connect(lambda title, message: errors.append((title, message)))
    worker.run()

    assert not errors
    assert finished_data["repair"]["merged_fragment_groups"] == 1
    assert finished_data["repair"]["standardized_layer_count"] == 2
    assert Path(finished_data["repair"]["change_log_file"]).is_file()
    assert len(finished_data["output_files"]) == 3

def test_task_worker_validate_execution(qapp):
    """测试 TaskWorker 线程后台执行 validate 任务。"""
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    params = {
        "dxf_path": str(sample_dxf),
        "setback_m": 5.0,
        "output_dir": "output/gui_test"
    }

    worker = TaskWorker("validate", params)
    
    finished_data = {}
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.run()

    assert finished_data.get("task_type") == "validate"
    assert finished_data.get("valid_count") == 10
    assert len(finished_data.get("setback_results", [])) == 3
    report_file = Path(finished_data["output_files"][0][1])
    assert report_file.exists()
    assert "Source SHA-256:" in report_file.read_text(encoding="utf-8")


def test_task_worker_validate_converts_units_and_associates_buildings(qapp, tmp_path):
    """GUI validation must use meter conversion and parcel-local buildings."""
    import ezdxf

    dxf_path = tmp_path / "cm_multi_parcel.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 5  # centimeters
    msp = doc.modelspace()

    for points in (
        [(0, 0), (2000, 0), (2000, 2000), (0, 2000)],
        [(4000, 0), (6000, 0), (6000, 2000), (4000, 2000)],
    ):
        parcel = msp.add_lwpolyline(points, dxfattribs={"layer": "PARCEL"})
        parcel.close(True)

    building = msp.add_lwpolyline(
        [(100, 100), (1900, 100), (1900, 1900), (100, 1900)],
        dxfattribs={"layer": "BUILDING"},
    )
    building.close(True)
    doc.saveas(dxf_path)

    worker = TaskWorker(
        "validate",
        {"dxf_path": str(dxf_path), "setback_m": 5.0, "output_dir": str(tmp_path)},
    )
    finished_data = {}
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.run()

    results = finished_data["setback_results"]
    assert results[0]["status"] == "VIOLATION"  # 1m distance < 5m requirement
    assert results[0]["min_distance_m"] == pytest.approx(1.0)
    assert results[1]["status"] == "NO_BUILDING"


def test_task_worker_real_qthread_execution(qapp, tmp_path):
    """The GUI worker must execute through QThread.start(), not only run()."""
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    worker = TaskWorker(
        "indicator",
        {"dxf_path": str(sample_dxf), "floors": 6, "output_dir": str(tmp_path)},
    )
    finished_data = {}
    loop = QEventLoop()
    worker.finished_signal.connect(lambda res: finished_data.update(res))
    worker.finished.connect(loop.quit)
    worker.start()
    loop.exec()

    assert worker.isFinished()
    assert finished_data.get("task_type") == "indicator"


def test_indicator_floors_are_unset_by_default(qapp):
    """The GUI must not silently submit a default floor multiplier."""
    widget = TaskZoneWidget()
    assert widget.spin_floors.value() == 0
    assert widget.spin_floors.specialValueText() == "未指定（必须填写）"


def test_task_zone_example_preset_is_explicitly_labeled(qapp):
    """The beginner preset fills examples without presenting them as standards."""
    widget = TaskZoneWidget()
    widget.preset_combo.setCurrentIndex(1)

    assert widget.spin_floors.value() == 6
    assert widget.spin_setback.value() == pytest.approx(5.0)
    assert "不代表法定规范" in widget.lbl_preflight.text()
    assert widget.lbl_preflight.objectName() == "BadgeWarning"

def test_dxf_inspector_layer_counts():
    """测试 DXF 预检扫描工具返回图层实体明细数量。"""
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    info = inspect_dxf_file(sample_dxf)

    counts = info.get("layer_counts", {})
    assert counts.get("PARCEL") == 4
    assert counts.get("BUILDING") == 4
    assert counts.get("GREEN") == 3

def test_file_zone_load_sample(qapp):
    """测试 FileZoneWidget 一键加载示例图纸按钮。"""
    window = PlanningToolboxMainWindow()
    loop = QEventLoop()
    window.result_zone.canvas.preview_loaded.connect(loop.quit)
    window.file_zone._load_sample()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    dxf_path = window.file_zone.get_dxf_path()
    assert "sample_parcels.dxf" in dxf_path
    assert window.file_zone.lbl_status.text() == "✓ 文件存在"

def test_cad_canvas_preview_rendering(qapp):
    """测试 CADPreviewCanvas 2D 画布渲染。"""
    from planning_toolbox.gui.widgets.canvas_widget import CADPreviewCanvas
    canvas = CADPreviewCanvas()
    sample_dxf = Path("sample_data/sample_parcels.dxf")
    loop = QEventLoop()
    canvas.preview_loaded.connect(loop.quit)
    canvas.load_dxf_preview(sample_dxf)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert canvas.ax is not None
    assert len(canvas.ax.patches) == 10  # 3 parcels + 4 buildings + 3 greens = 10 patches
