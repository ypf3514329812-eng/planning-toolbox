"""Regression coverage for lazy loading and broader CAD compatibility."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import ezdxf
from matplotlib.figure import Figure
import pytest

from planning_toolbox.cad.io.dwg_bridge import (
    DwgConverterUnavailable,
    convert_dwg_to_dxf,
)
from planning_toolbox.cad.quality import scan_dxf_quality
from planning_toolbox.gui.repair_comparison import render_repair_difference


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_knowledge_catalog_import_does_not_load_images_or_cad_engine():
    """Browsing lightweight Markdown cards must not activate raster/CAD stacks."""
    code = r'''
import json, sys
from planning_toolbox.knowledge.image_cards import list_image_knowledge_cards
loaded = {
    name: any(module == name or module.startswith(name + ".") for module in sys.modules)
    for name in ["PIL", "numpy", "skimage", "ezdxf", "shapely"]
}
print(json.dumps(loaded))
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = json.loads(completed.stdout.strip())
    assert loaded == {
        "PIL": False,
        "numpy": False,
        "skimage": False,
        "ezdxf": False,
        "shapely": False,
    }


def test_idle_main_window_keeps_heavy_optional_modules_unloaded():
    code = r'''
import json, os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from planning_toolbox.gui.main_window import PlanningToolboxMainWindow
app = QApplication([])
window = PlanningToolboxMainWindow()
app.processEvents()
names = ["matplotlib", "skimage", "scipy", "openpyxl", "reportlab", "ezdxf", "shapely"]
print(json.dumps({name: any(key == name or key.startswith(name + ".") for key in sys.modules) for name in names}))
window.close()
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        check=True,
        capture_output=True,
        text=True,
    )
    loaded = json.loads(completed.stdout.strip().splitlines()[-1])
    assert not any(loaded.values()), loaded


def test_existing_package_level_api_remains_available_after_lazy_loading():
    code = r'''
import json, sys
import planning_toolbox
before = "ezdxf" in sys.modules
available = callable(planning_toolbox.process_parcels) and callable(planning_toolbox.validate_polyline_topology)
after = "ezdxf" in sys.modules
print(json.dumps({"before": before, "available": available, "after": after}))
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result == {"before": False, "available": True, "after": True}


def test_main_preview_uses_native_qt_canvas_without_loading_matplotlib():
    code = r'''
import json, os, sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from planning_toolbox.gui.main_window import PlanningToolboxMainWindow
app = QApplication([])
window = PlanningToolboxMainWindow()
loop = QEventLoop()
window.result_zone.canvas.preview_loaded.connect(loop.quit)
window.file_zone.set_dxf_path(str(Path("sample_data/sample_parcels.dxf").resolve()))
QTimer.singleShot(10000, loop.quit)
loop.exec()
print(json.dumps({
    "matplotlib": any(key == "matplotlib" or key.startswith("matplotlib.") for key in sys.modules),
    "items": window.result_zone.canvas.geometry_item_count,
    "native": type(window.result_zone.canvas._preview).__name__,
}))
window.close()
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result == {
        "matplotlib": False,
        "items": 11,
        "native": "NativeCADPreviewCanvas",
    }


def test_quality_scan_catalogues_blocks_layouts_and_manual_review_entities(tmp_path):
    path = tmp_path / "complex_plan.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    block = doc.blocks.new("TREE_SYMBOL")
    block.add_circle((0, 0), 1)
    msp = doc.modelspace()
    msp.add_blockref("TREE_SYMBOL", (10, 10))
    msp.add_arc((0, 0), 5, 0, 90)
    msp.add_spline([(0, 0), (3, 4), (6, 0)])
    doc.layout().add_text("TITLE", dxfattribs={"insert": (0, 0)})
    doc.saveas(path)
    before = path.read_bytes()

    result = scan_dxf_quality(path)

    assert result["block_reference_counts"] == {"TREE_SYMBOL": 1}
    assert result["unresolved_block_references"] == []
    assert result["manual_review_entity_counts"]["ARC"] == 1
    assert result["manual_review_entity_counts"]["SPLINE"] == 1
    assert result["paper_space_entity_count"] == 1
    assert path.read_bytes() == before


def test_repair_difference_highlights_replaced_linework(tmp_path):
    before_path = tmp_path / "before.dxf"
    after_path = tmp_path / "after.dxf"
    before = ezdxf.new("R2010")
    before.modelspace().add_line((0, 0), (5, 0))
    before.modelspace().add_line((5, 0), (10, 0))
    before.saveas(before_path)
    after = ezdxf.new("R2010")
    after.modelspace().add_line((0, 0), (10, 0))
    after.saveas(after_path)

    summary = render_repair_difference(Figure(), before_path, after_path)

    assert summary == {
        "unchanged": 0,
        "removed_or_replaced": 2,
        "added_or_replaced": 1,
    }


def test_dwg_bridge_gives_local_install_guidance_without_touching_source(tmp_path, monkeypatch):
    from ezdxf.addons import odafc

    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"AC1032-placeholder")
    before = source.read_bytes()
    monkeypatch.setattr(odafc, "is_installed", lambda: False)

    with pytest.raises(DwgConverterUnavailable, match="ODA File Converter"):
        convert_dwg_to_dxf(source, tmp_path / "output")
    assert source.read_bytes() == before


def test_preview_parser_keeps_common_complex_cad_entities_visible(tmp_path):
    from planning_toolbox.gui.widgets.canvas_widget import DxfPreviewWorker

    path = tmp_path / "preview_complex.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "DETAIL"})
    msp.add_arc((5, 5), 2, 0, 180, dxfattribs={"layer": "DETAIL"})
    msp.add_circle((10, 5), 2, dxfattribs={"layer": "DETAIL"})
    msp.add_ellipse((15, 5), (3, 0), ratio=0.5, dxfattribs={"layer": "DETAIL"})
    msp.add_spline([(20, 0), (22, 4), (25, 0)], dxfattribs={"layer": "DETAIL"})
    block = doc.blocks.new("TREE")
    block.add_circle((0, 0), 1)
    msp.add_blockref("TREE", (30, 5))
    doc.saveas(path)

    captured = {}
    worker = DxfPreviewWorker(path)
    worker.result_ready.connect(
        lambda info, geometry: captured.update(info=info, geometry=geometry)
    )
    worker.run()

    assert captured["info"]["valid_dxf"] is True
    assert len(captured["geometry"]["curves"]) == 2
    assert len(captured["geometry"]["linework"]) == 3
    assert captured["geometry"]["inserts"][0]["name"] == "TREE"


def test_preview_parser_expands_planning_tree_blocks_as_circles(tmp_path):
    from planning_toolbox.gui.widgets.canvas_widget import DxfPreviewWorker

    path = tmp_path / "preview_tree_block.dxf"
    doc = ezdxf.new("R2010")
    block = doc.blocks.new("PT_TREE")
    block.add_circle((0, 0), 1)
    doc.modelspace().add_blockref(
        "PT_TREE",
        (12, 18),
        dxfattribs={"layer": "BW_TREE_CANDIDATE", "xscale": 3.5, "yscale": 3.5},
    )
    doc.saveas(path)

    captured = {}
    worker = DxfPreviewWorker(path)
    worker.result_ready.connect(
        lambda info, geometry: captured.update(info=info, geometry=geometry)
    )
    worker.run()

    assert captured["info"]["valid_dxf"] is True
    assert captured["geometry"]["inserts"] == []
    assert len(captured["geometry"]["curves"]) == 1
    tree = captured["geometry"]["curves"][0]
    assert tree["type"] == "CIRCLE"
    assert tree["center"] == pytest.approx((12.0, 18.0))
    assert tree["radius"] == pytest.approx(3.5)


def test_preview_parser_expands_planning_parking_blocks_as_rectangles(tmp_path):
    from planning_toolbox.gui.widgets.canvas_widget import DxfPreviewWorker

    path = tmp_path / "preview_parking_block.dxf"
    doc = ezdxf.new("R2010")
    block = doc.blocks.new("PT_PARKING_STALL")
    block.add_lwpolyline(
        [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)],
        close=True,
    )
    doc.modelspace().add_blockref(
        "PT_PARKING_STALL",
        (20, 30),
        dxfattribs={
            "layer": "BW_PARKING_CANDIDATE",
            "xscale": 5.0,
            "yscale": 2.5,
            "rotation": 30.0,
        },
    )
    doc.saveas(path)

    captured = {}
    worker = DxfPreviewWorker(path)
    worker.result_ready.connect(
        lambda info, geometry: captured.update(info=info, geometry=geometry)
    )
    worker.run()

    assert captured["info"]["valid_dxf"] is True
    assert captured["geometry"]["inserts"] == []
    assert captured["geometry"]["linework"] == []
    assert len(captured["geometry"]["parking"]) == 1
    assert len(captured["geometry"]["parking"][0]) == 4


def test_preview_parser_renders_image_cad_candidate_layers_semantically(tmp_path):
    from planning_toolbox.gui.widgets.canvas_widget import DxfPreviewWorker

    path = tmp_path / "preview_semantic_candidates.dxf"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (8, 0), (8, 6), (0, 6)],
        close=True,
        dxfattribs={"layer": "BW_BUILDING_CANDIDATE"},
    )
    msp.add_lwpolyline(
        [(0, 10), (20, 10), (20, 15), (0, 15)],
        close=True,
        dxfattribs={"layer": "BW_ROAD_CANDIDATE"},
    )
    msp.add_lwpolyline(
        [(0, 12.5), (20, 12.5)],
        close=False,
        dxfattribs={"layer": "BW_ROAD_CENTERLINE_CANDIDATE"},
    )
    doc.saveas(path)

    captured = {}
    worker = DxfPreviewWorker(path)
    worker.result_ready.connect(
        lambda info, geometry: captured.update(info=info, geometry=geometry)
    )
    worker.run()

    assert captured["info"]["valid_dxf"] is True
    assert len(captured["geometry"]["building"]) == 1
    assert len(captured["geometry"]["road"]) == 1
    assert len(captured["geometry"]["linework"]) == 1
    assert captured["geometry"]["linework"][0]["role"] == "road_centerline"


def test_native_canvas_exports_full_scene_png(tmp_path):
    output = tmp_path / "native_preview.png"
    code = rf'''
import json, os
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from planning_toolbox.gui.widgets.native_canvas_widget import NativeCADPreviewCanvas
app = QApplication([])
canvas = NativeCADPreviewCanvas()
loop = QEventLoop()
canvas.preview_loaded.connect(loop.quit)
canvas.load_dxf_preview(Path(r"{PROJECT_ROOT / 'sample_data' / 'sample_parcels.dxf'}"))
QTimer.singleShot(10000, loop.quit)
loop.exec()
output = canvas.save_png(Path(r"{output}"), max_dimension=1200)
image = QImage(str(output))
print(json.dumps({{
    "items": canvas.geometry_item_count,
    "exists": output.is_file() and output.stat().st_size > 0,
    "valid": not image.isNull(),
    "max_dimension": max(image.width(), image.height()),
    "cancelled": canvas.cancel_preview(wait=True),
}}))
canvas.close()
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result == {
        "items": 11,
        "exists": True,
        "valid": True,
        "max_dimension": 1200,
        "cancelled": True,
    }
