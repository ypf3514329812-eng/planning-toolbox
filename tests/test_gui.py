"""PySide6 桌面 GUI 工作台单元与集成测试套件."""
import os
import pytest
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from planning_toolbox.gui.utils.dxf_inspector import inspect_dxf_file
from planning_toolbox.gui.workers.task_worker import TaskWorker
from planning_toolbox.gui.main_window import PlanningToolboxMainWindow

@pytest.fixture(scope="module")
def qapp():
    """提供单个 PySide6 QApplication 供测试使用。"""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"  # 无头模式运行
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

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
    window.file_zone._load_sample()
    dxf_path = window.file_zone.get_dxf_path()
    assert "sample_parcels.dxf" in dxf_path
    assert window.file_zone.lbl_status.text() == "✓ 文件存在"
