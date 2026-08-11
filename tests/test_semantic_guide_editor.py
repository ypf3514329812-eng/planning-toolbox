import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from planning_toolbox.cad.planning.semantic_palette import SEMANTIC_GUIDE_PALETTE
from planning_toolbox.cad.planning.image_to_dxf import convert_image_to_dxf
from planning_toolbox.gui.semantic_guide_editor import SemanticGuideCanvas
from planning_toolbox.gui.widgets.task_zone import TaskZoneWidget
from planning_toolbox.utils.file_integrity import sha256_file


@pytest.fixture(scope="module")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_semantic_guide_editor_saves_exact_pixel_road_without_mutating_source(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    Image.new("RGB", (96, 64), (255, 255, 255)).save(source)
    before = sha256_file(source)

    canvas = SemanticGuideCanvas(source)
    canvas.set_brush("AI_ROAD")
    canvas.set_brush_size(11)
    canvas.apply_stroke(QPoint(14, 30), QPoint(78, 30))
    output = Path(canvas.save_png(tmp_path / "manual_guide.png"))

    assert output.is_file()
    assert sha256_file(source) == before
    image = QImage(str(output)).convertToFormat(QImage.Format_RGB32)
    assert image.size() == QImage(str(source)).size()
    assert image.pixelColor(48, 30).getRgb()[:3] == SEMANTIC_GUIDE_PALETTE["AI_ROAD"]
    assert image.pixelColor(2, 2).getRgb()[:3] == (255, 255, 255)

    converted = convert_image_to_dxf(
        source,
        output_dir=tmp_path / "converted",
        reference_width_m=96.0,
        color_tolerance=20,
        min_component_pixels=5,
        conversion_mode="semantic_guide",
        semantic_guide_path=output,
    )
    assert converted["region_counts"]["AI_ROAD"] == 1


def test_semantic_guide_editor_rejects_different_pixel_size(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    wrong_guide = tmp_path / "wrong.png"
    Image.new("RGB", (96, 64), (255, 255, 255)).save(source)
    Image.new("RGB", (95, 64), (255, 255, 255)).save(wrong_guide)

    with pytest.raises(ValueError, match="像素尺寸完全一致"):
        SemanticGuideCanvas(source, wrong_guide)


def test_semantic_guide_editor_keeps_review_overlay_out_of_saved_guide(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    overlay = tmp_path / "road_review_overlay.png"
    Image.new("RGB", (96, 64), (255, 255, 255)).save(source)
    overlay_image = Image.new("RGB", (96, 64), (255, 255, 255))
    overlay_image.putpixel((24, 24), (205, 74, 64))
    overlay_image.save(overlay)
    before = sha256_file(source)

    canvas = SemanticGuideCanvas(source, review_overlay_path=overlay)
    assert canvas._review_overlay_item is not None
    output = Path(canvas.save_png(tmp_path / "guide_without_overlay.png"))
    saved = QImage(str(output)).convertToFormat(QImage.Format_RGB32)

    assert saved.size() == QImage(str(source)).size()
    assert saved.pixelColor(24, 24).getRgb()[:3] == (255, 255, 255)
    assert sha256_file(source) == before


def test_semantic_guide_editor_rejects_different_review_overlay_size(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    wrong_overlay = tmp_path / "wrong_overlay.png"
    Image.new("RGB", (96, 64), (255, 255, 255)).save(source)
    Image.new("RGB", (95, 64), (255, 255, 255)).save(wrong_overlay)

    with pytest.raises(ValueError, match="道路复核叠加图必须与原图像素尺寸完全一致"):
        SemanticGuideCanvas(source, review_overlay_path=wrong_overlay)


def test_road_path_is_one_undoable_operation_and_can_be_redone(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    Image.new("RGB", (120, 80), (255, 255, 255)).save(source)
    before = sha256_file(source)

    canvas = SemanticGuideCanvas(source)
    canvas.set_draw_mode("road_path")
    canvas.set_brush_size(7)
    canvas.add_path_point(QPoint(12, 38))
    canvas.add_path_point(QPoint(58, 38))
    canvas.add_path_point(QPoint(100, 52))
    assert canvas.path_point_count == 3
    assert canvas.finish_path() is True
    assert canvas.history_depth == 1
    assert canvas._guide_image.pixelColor(35, 38).getRgb()[:3] == SEMANTIC_GUIDE_PALETTE["AI_ROAD"]

    assert canvas.undo() is True
    assert canvas._guide_image.pixelColor(35, 38).getRgb()[:3] == (255, 255, 255)
    assert canvas.redo() is True
    assert canvas._guide_image.pixelColor(35, 38).getRgb()[:3] == SEMANTIC_GUIDE_PALETTE["AI_ROAD"]
    assert sha256_file(source) == before


def test_image_task_exposes_in_app_semantic_guide_editor(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    Image.new("RGB", (96, 64), (255, 255, 255)).save(source)
    widget = TaskZoneWidget()
    widget.image_file_input.setText(str(source))
    widget.image_conversion_mode.setCurrentIndex(
        widget.image_conversion_mode.findData("semantic_guide")
    )

    assert widget.image_semantic_guide_row.isHidden() is False
    assert widget.btn_edit_semantic_guide.isHidden() is False
    assert "软件内直接" in widget.btn_edit_semantic_guide.toolTip()
    widget.close()


def test_semantic_guide_reports_nearby_road_gap_for_manual_review(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    guide = tmp_path / "guide.png"
    Image.new("RGB", (120, 80), (255, 255, 255)).save(source)
    guide_image = Image.new("RGB", (120, 80), (255, 255, 255))
    guide_draw = ImageDraw.Draw(guide_image)
    road_color = SEMANTIC_GUIDE_PALETTE["AI_ROAD"]
    guide_draw.rectangle((10, 30, 39, 38), fill=road_color)
    guide_draw.rectangle((45, 30, 72, 38), fill=road_color)
    guide_image.save(guide)

    result = convert_image_to_dxf(
        source,
        output_dir=tmp_path / "converted",
        reference_width_m=120.0,
        color_tolerance=20,
        min_component_pixels=5,
        conversion_mode="semantic_guide",
        semantic_guide_path=guide,
    )

    road_detection = result["semantic_road_detection"]
    assert road_detection["network_component_count"] == 2
    assert road_detection["nearby_gap_suggestion_count"] == 1
    assert road_detection["status"] == "nearby_gaps_review"


def test_semantic_guide_heals_only_small_road_junction_gaps(qapp, tmp_path):
    source = tmp_path / "underlay.png"
    guide = tmp_path / "guide.png"
    Image.new("RGB", (120, 80), (255, 255, 255)).save(source)
    guide_image = Image.new("RGB", (120, 80), (255, 255, 255))
    guide_draw = ImageDraw.Draw(guide_image)
    road_color = SEMANTIC_GUIDE_PALETTE["AI_ROAD"]
    guide_draw.rectangle((10, 30, 39, 38), fill=road_color)
    guide_draw.rectangle((43, 30, 72, 38), fill=road_color)
    guide_image.save(guide)

    result = convert_image_to_dxf(
        source,
        output_dir=tmp_path / "converted",
        reference_width_m=120.0,
        color_tolerance=20,
        min_component_pixels=5,
        conversion_mode="semantic_guide",
        semantic_guide_path=guide,
    )

    assert result["region_counts"]["AI_ROAD"] == 1
    assert result["region_counts"]["AI_BUILDING"] == 0
    road_detection = result["semantic_road_detection"]
    assert road_detection["region_count_before_gap_heal"] == 2
    assert road_detection["region_count_after_gap_heal"] == 1
    assert road_detection["healed_region_count"] == 1
    assert road_detection["network_component_count"] == 1
    assert road_detection["status"] == "single_network"
