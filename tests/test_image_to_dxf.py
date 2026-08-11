from pathlib import Path
from math import cos, radians, sin
import json

import ezdxf
import numpy as np
import pytest
from PIL import Image, ImageDraw
from shapely.geometry import LineString

from planning_toolbox.cad.planning.image_to_dxf import (
    _merge_road_centerline_candidates,
    convert_image_to_dxf,
)
from planning_toolbox.utils.file_integrity import sha256_file


def _make_standardized_image(path: Path) -> None:
    image = Image.new("RGB", (240, 160), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, 228, 148), outline=(204, 204, 198), width=2)
    draw.rectangle((35, 35, 100, 75), fill=(198, 119, 119))
    draw.rounded_rectangle((125, 35, 205, 78), radius=8, fill=(198, 119, 119))
    draw.rectangle((30, 95, 215, 112), fill=(151, 151, 145))
    draw.ellipse((50, 118, 105, 143), fill=(126, 165, 142))
    draw.rectangle((125, 118, 180, 143), fill=(118, 157, 184))
    image.save(path)


def test_road_centerline_network_merge_is_trusted_width_compatible_and_bounded():
    lines = [
        LineString([(0.0, 0.0), (20.0, 0.0)]),
        LineString([(22.0, 0.2), (42.0, 0.2)]),
        LineString([(44.0, 0.3), (64.0, 0.3)]),
        LineString([(66.0, 0.3), (86.0, 0.3)]),
    ]
    merged, widths, confidences, stats = _merge_road_centerline_candidates(
        lines,
        widths_m=[8.0, 8.4, 8.2, 16.0],
        confidences=[0.88, 0.82, 0.48, 0.91],
        pixel_size_m=0.25,
    )

    assert len(merged) == 3
    assert stats["input_line_count"] == 4
    assert stats["output_line_count"] == 3
    assert stats["joined_fragment_count"] == 1
    assert stats["trusted_input_count"] == 3
    assert stats["review_input_count"] == 1
    assert stats["maximum_bridge_gap_m"] <= 3.0
    assert confidences[0] >= 0.65
    assert confidences[1] == pytest.approx(0.48)
    assert widths[2] == pytest.approx(16.0)
    assert merged[0].length > 40.0

    with pytest.raises(ValueError, match="数量不一致"):
        _merge_road_centerline_candidates(lines, [8.0], [0.8], 0.25)


def test_trusted_road_junction_snap_connects_only_bounded_unambiguous_endpoints():
    lines = [
        LineString([(0.0, 0.0), (30.0, 0.0)]),
        LineString([(15.0, 10.0), (15.0, 0.8)]),
        LineString([(30.8, 0.0), (45.0, 0.0)]),
        LineString([(15.0, -5.0), (15.0, -0.4)]),
    ]
    merged, _widths, _confidences, stats = _merge_road_centerline_candidates(
        lines,
        widths_m=[12.0, 6.0, 6.0, 6.0],
        confidences=[0.90, 0.84, 0.82, 0.40],
        pixel_size_m=0.25,
    )

    assert len(merged) == 4
    assert tuple(merged[0].coords[-1]) == pytest.approx((30.4, 0.0))
    assert tuple(merged[1].coords[-1]) == pytest.approx((15.0, 0.0))
    assert tuple(merged[2].coords[0]) == pytest.approx((30.4, 0.0))
    assert tuple(merged[3].coords[-1]) == pytest.approx((15.0, -0.4))
    assert stats["junction_endpoint_cluster_count"] == 1
    assert stats["junction_t_connection_count"] == 1
    assert stats["junction_snap_count"] == 2
    assert stats["trusted_network_component_count_before"] == 3
    assert stats["trusted_network_component_count_after"] == 1
    assert stats["maximum_junction_snap_distance_m"] <= 1.0


def test_image_to_dxf_traces_layers_and_preserves_source(tmp_path):
    image_path = tmp_path / "ai_site_plan.png"
    _make_standardized_image(image_path)
    before = sha256_file(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=120.0,
        color_tolerance=20,
        min_component_pixels=20,
    )

    output_dxf = Path(result["output_files"][0][1])
    preview = Path(result["output_files"][1][1])
    report = Path(result["output_files"][2][1])
    assert output_dxf.exists()
    assert Path(result["dxf_file"]) == output_dxf.resolve()
    assert preview.exists()
    assert report.exists()
    assert Path(result["semantic_scene_file"]).exists()
    quality_baseline = Path(result["quality_baseline_file"])
    assert quality_baseline.is_file()
    quality_payload = json.loads(quality_baseline.read_text(encoding="utf-8"))
    assert quality_payload["workflow"] == "image_to_cad"
    assert quality_payload["inputs"]["source_sha256"] == before
    assert quality_payload["outputs"]["dxf_sha256"] == sha256_file(output_dxf)
    assert quality_payload["summary"]["status"] == "review_required"
    assert quality_payload["summary"]["blocked_count"] == 0
    quality_review = Path(result["quality_baseline"]["review_path"])
    assert quality_review.is_file()
    review_text = quality_review.read_text(encoding="utf-8-sig")
    assert "总体结论：需人工复核" in review_text
    assert "人工几何复核" in review_text
    assert result["quality_baseline"]["review_items"]
    assert result["output_files"][-2][1] == str(quality_review)
    assert result["output_files"][-1][1] == str(quality_baseline)
    assert result["semantic_scene_summary"]["semantic_object_count"] >= 4
    assert result["task_type"] == "image_to_dxf"
    assert result["region_counts"]["AI_BUILDING"] >= 2
    assert result["region_counts"]["AI_GREEN"] >= 1
    assert result["region_counts"]["AI_WATER"] >= 1
    assert sha256_file(image_path) == before

    doc = ezdxf.readfile(output_dxf)
    layers = {layer.dxf.name for layer in doc.layers}
    assert {"AI_BUILDING", "AI_ROAD", "AI_GREEN", "AI_WATER", "AI_LABEL", "AI_FRAME"} <= layers
    converted_layers = {
        entity.dxf.layer
        for entity in doc.modelspace()
        if str(entity.dxf.layer).startswith("AI_")
    }
    assert {"AI_BUILDING", "AI_ROAD", "AI_GREEN", "AI_WATER"} <= converted_layers
    assert "concept vectorization" in report.read_text(encoding="utf-8").lower()


def test_semantic_guide_uses_original_as_locked_lineage_and_preserves_both_images(
    tmp_path,
):
    source = tmp_path / "black_white_underlay.png"
    underlay = Image.new("RGB", (360, 240), (255, 255, 255))
    source_draw = ImageDraw.Draw(underlay)
    source_draw.rectangle((45, 45, 150, 115), outline=(20, 20, 20), width=3)
    source_draw.rounded_rectangle(
        (35, 155, 325, 190), radius=12, outline=(20, 20, 20), width=3
    )
    underlay.save(source)

    guide = tmp_path / "semantic_guide.png"
    guide_image = Image.new("RGB", underlay.size, (250, 250, 250))
    guide_draw = ImageDraw.Draw(guide_image)
    guide_draw.rectangle((45, 45, 150, 115), fill=(198, 119, 119))
    guide_draw.rounded_rectangle(
        (35, 155, 325, 190), radius=12, fill=(151, 151, 145)
    )
    guide_image.save(guide)
    source_hash = sha256_file(source)
    guide_hash = sha256_file(guide)

    result = convert_image_to_dxf(
        source,
        output_dir=tmp_path / "guided_output",
        reference_width_m=180.0,
        color_tolerance=20,
        min_component_pixels=20,
        conversion_mode="semantic_guide",
        semantic_guide_path=guide,
    )

    assert result["conversion_mode"] == "semantic_guide"
    assert result["semantic_guide_file"] == str(guide.resolve())
    assert result["semantic_guide_sha256"] == guide_hash
    assert result["region_counts"]["AI_BUILDING"] == 1
    assert result["region_counts"]["AI_ROAD"] == 1
    assert sha256_file(source) == source_hash
    assert sha256_file(guide) == guide_hash
    assert Path(result["output_files"][4][1]).is_file()

    sidecar = json.loads(
        Path(result["semantic_scene_file"]).read_text(encoding="utf-8")
    )
    assert sidecar["source"]["source_image_path"] == str(source.resolve())
    assert sidecar["source"]["source_image_sha256"] == source_hash
    assert sidecar["source"]["semantic_guide_path"] == str(guide.resolve())
    assert sidecar["source"]["semantic_guide_sha256"] == guide_hash
    assert sidecar["source"]["conversion_mode"] == "semantic_guide"

    wrong_size = tmp_path / "wrong_size_guide.png"
    Image.new("RGB", (359, 240), (151, 151, 145)).save(wrong_size)
    with pytest.raises(ValueError, match="像素尺寸完全一致"):
        convert_image_to_dxf(
            source,
            output_dir=tmp_path / "wrong_size_output",
            reference_width_m=180.0,
            conversion_mode="semantic_guide",
            semantic_guide_path=wrong_size,
        )


def test_image_to_dxf_requires_explicit_scale(tmp_path):
    image_path = tmp_path / "plain.png"
    _make_standardized_image(image_path)

    with pytest.raises(ValueError, match="宽度"):
        convert_image_to_dxf(image_path, output_dir=tmp_path / "output")


def test_image_to_dxf_can_focus_on_main_site_and_drop_outer_road(tmp_path):
    image_path = tmp_path / "site_with_outer_road.png"
    image = Image.new("RGB", (320, 220), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 319, 18), fill=(151, 151, 145))
    draw.rectangle((18, 35, 300, 200), fill=(126, 165, 142))
    draw.rectangle((70, 65, 125, 100), fill=(198, 119, 119))
    draw.rectangle((35, 125, 280, 145), fill=(151, 151, 145))
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=160.0,
        color_tolerance=20,
        min_component_pixels=20,
        focus_site_only=True,
    )

    assert result["focus_site_only"] is True
    assert result["focus_applied"] is True
    assert result["region_counts"]["AI_BUILDING"] == 1
    assert result["region_counts"]["AI_GREEN"] == 1
    assert result["region_counts"]["AI_ROAD"] == 1
    report = Path(result["output_files"][2][1]).read_text(encoding="utf-8")
    assert "Focus site only: yes" in report
    assert "Focus applied: yes" in report


def test_image_to_dxf_black_white_linework_mode(tmp_path):
    image_path = tmp_path / "black_white_plan.png"
    image = Image.new("RGB", (240, 160), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 220, 140), outline=(20, 20, 20), width=3)
    draw.rectangle((60, 45, 115, 85), outline=(20, 20, 20), width=2)
    draw.line((30, 110, 200, 100), fill=(20, 20, 20), width=2)
    image.save(image_path)
    before = sha256_file(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=120.0,
        min_component_pixels=8,
        conversion_mode="black_white_linework",
        line_threshold=220,
    )

    assert result["conversion_mode"] == "black_white_linework"
    assert result["line_count"] > 0
    assert sha256_file(image_path) == before
    output_dxf = Path(result["output_files"][0][1])
    preview = Path(result["output_files"][1][1])
    report = Path(result["output_files"][2][1])
    assert output_dxf.exists()
    assert preview.exists()
    assert report.exists()
    assert Path(result["semantic_scene_file"]).exists()
    assert result["semantic_scene_summary"]["underlay_entity_count"] > 0
    doc = ezdxf.readfile(output_dxf)
    layers = {layer.dxf.name for layer in doc.layers}
    assert {"BW_LINEWORK", "BW_FRAME"} <= layers
    assert any(entity.dxf.layer == "BW_LINEWORK" for entity in doc.modelspace())
    assert "Extracted line contours:" in report.read_text(encoding="utf-8")


def test_image_to_dxf_black_white_centerline_mode(tmp_path):
    image_path = tmp_path / "centerline_plan.png"
    image = Image.new("RGB", (240, 160), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (20, 20, 220, 140),
        radius=18,
        outline=(20, 20, 20),
        width=4,
    )
    draw.rectangle((70, 55, 120, 95), outline=(20, 20, 20), width=3)
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=120.0,
        min_component_pixels=8,
        max_dimension=2400,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_simplify_factor=0.15,
        line_trace_method="centerline",
    )

    assert result["trace_method"] == "centerline"
    assert result["line_count"] > 0
    assert Path(result["output_files"][1][1]).exists()
    assert Path(result["output_files"][3][1]).exists()
    report = Path(result["output_files"][2][1]).read_text(encoding="utf-8")
    assert "Trace method: centerline" in report


def test_centerline_optimization_reduces_fragments_and_protects_buildings(tmp_path):
    image_path = tmp_path / "optimized_residential_plan.png"
    image = Image.new("RGB", (480, 320), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (25, 25, 455, 295),
        radius=35,
        outline=(20, 20, 20),
        width=4,
    )
    buildings = [(70, 65, 150, 125), (200, 60, 280, 120), (330, 70, 410, 130)]
    for left, top, right, bottom in buildings:
        draw.rectangle((left, top, right, bottom), outline=(20, 20, 20), width=4)
        center_x = (left + right) // 2
        draw.line((center_x, bottom, center_x, 205), fill=(20, 20, 20), width=4)
    draw.line((60, 205, 420, 205), fill=(20, 20, 20), width=4)
    for center_x in range(65, 430, 45):
        draw.ellipse(
            (center_x - 9, 245 - 9, center_x + 9, 245 + 9),
            outline=(20, 20, 20),
            width=3,
        )
    image.save(image_path)
    before = sha256_file(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=180.0,
        min_component_pixels=8,
        max_dimension=2400,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_simplify_factor=0.15,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    assert result["optimization_enabled"] is True
    assert result["raw_line_count"] > result["line_count"]
    assert result["building_candidate_count"] == 3
    assert result["merge_stats"]["joined_fragment_count"] > 0
    assert result["line_layer_counts"]["BW_BUILDING_CANDIDATE"] == 3
    assert sha256_file(image_path) == before

    output_dxf = Path(result["output_files"][0][1])
    doc = ezdxf.readfile(output_dxf)
    candidate_entities = [
        entity
        for entity in doc.modelspace()
        if (
            entity.dxf.layer == "BW_BUILDING_CANDIDATE"
            and entity.dxftype() == "LWPOLYLINE"
        )
    ]
    assert len(candidate_entities) == 3
    assert all(entity.closed for entity in candidate_entities)
    layers = {layer.dxf.name for layer in doc.layers}
    assert {
        "BW_LINEWORK",
        "BW_CLOSED",
        "BW_DETAIL",
        "BW_BUILDING_CANDIDATE",
        "BW_FRAME",
    } <= layers
    report = Path(result["output_files"][2][1]).read_text(encoding="utf-8")
    assert "Automatic linework optimization: yes" in report
    assert "Building candidates: 3" in report


def test_centerline_building_candidates_ignore_small_tree_symbols(tmp_path):
    image_path = tmp_path / "building_and_trees.png"
    image = Image.new("RGB", (400, 300), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((145, 90, 255, 175), outline=(20, 20, 20), width=4)
    for center_x in range(45, 365, 40):
        draw.ellipse(
            (center_x - 8, 235 - 8, center_x + 8, 235 + 8),
            outline=(20, 20, 20),
            width=3,
        )
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=160.0,
        min_component_pixels=8,
        max_dimension=2400,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_simplify_factor=0.15,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    assert result["building_candidate_count"] == 1
    assert result["line_layer_counts"]["BW_BUILDING_CANDIDATE"] == 1
    assert result["tree_candidate_count"] == 8
    assert result["line_layer_counts"]["BW_TREE_CANDIDATE"] == 8
    assert result["vertex_reduction"] > 0

    doc = ezdxf.readfile(Path(result["output_files"][0][1]))
    tree_inserts = [
        entity
        for entity in doc.modelspace()
        if entity.dxftype() == "INSERT" and entity.dxf.layer == "BW_TREE_CANDIDATE"
    ]
    assert len(tree_inserts) == 8
    assert all(entity.dxf.name == "PT_TREE" for entity in tree_inserts)
    assert "PT_TREE" in {block.name for block in doc.blocks}
    assert len(list(doc.blocks["PT_TREE"].query("CIRCLE"))) == 1


def test_centerline_optimization_fits_large_landscape_ellipse(tmp_path):
    image_path = tmp_path / "ellipse_landscape.png"
    image = Image.new("RGB", (500, 350), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((175, 110, 325, 220), outline=(20, 20, 20), width=4)
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=200.0,
        min_component_pixels=8,
        max_dimension=2400,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_simplify_factor=0.15,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    assert result["landscape_candidate_count"] == 1
    assert result["line_layer_counts"]["BW_LANDSCAPE_CANDIDATE"] == 1
    assert result["vertex_reduction"] > 0
    doc = ezdxf.readfile(Path(result["output_files"][0][1]))
    ellipses = [
        entity
        for entity in doc.modelspace()
        if entity.dxftype() == "ELLIPSE"
        and entity.dxf.layer == "BW_LANDSCAPE_CANDIDATE"
    ]
    assert len(ellipses) == 1
    assert 0.5 < float(ellipses[0].dxf.ratio) < 0.9


def test_black_white_linework_auto_detects_light_lines_on_dark_background(tmp_path):
    image_path = tmp_path / "dark_background_plan.png"
    image = Image.new("RGB", (360, 240), (18, 18, 18))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((25, 25, 335, 215), radius=28, outline=(245, 245, 245), width=4)
    draw.rectangle((115, 75, 245, 155), outline=(245, 245, 245), width=4)
    image.save(image_path)
    before = sha256_file(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=180.0,
        min_component_pixels=8,
        max_dimension=1200,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_trace_method="centerline",
        optimize_linework=True,
        line_polarity="auto",
    )

    assert result["line_polarity_requested"] == "auto"
    assert result["line_polarity_detected"] == "light_on_dark"
    assert result["background_luminance"] < 30
    assert result["line_count"] > 0
    assert result["building_candidate_count"] == 1
    assert sha256_file(image_path) == before
    report = Path(result["output_files"][2][1]).read_text(encoding="utf-8")
    assert "Detected line polarity: light_on_dark" in report


def test_centerline_optimization_accepts_rotated_rectangular_building(tmp_path):
    image_path = tmp_path / "rotated_building.png"
    image = Image.new("RGB", (500, 400), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    center_x, center_y = 250.0, 200.0
    half_width, half_height = 70.0, 42.0
    angle = radians(34.0)
    polygon = []
    for local_x, local_y in (
        (-half_width, -half_height),
        (half_width, -half_height),
        (half_width, half_height),
        (-half_width, half_height),
    ):
        polygon.append((
            center_x + local_x * cos(angle) - local_y * sin(angle),
            center_y + local_x * sin(angle) + local_y * cos(angle),
        ))
    draw.line(polygon + [polygon[0]], fill=(20, 20, 20), width=4, joint="curve")
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=200.0,
        min_component_pixels=8,
        max_dimension=1200,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    assert result["building_candidate_count"] == 1
    doc = ezdxf.readfile(Path(result["output_files"][0][1]))
    buildings = [
        entity for entity in doc.modelspace()
        if (
            entity.dxf.layer == "BW_BUILDING_CANDIDATE"
            and entity.dxftype() == "LWPOLYLINE"
        )
    ]
    assert len(buildings) == 1
    assert buildings[0].closed


def test_centerline_optimization_blockifies_repeated_parking_stalls(tmp_path):
    image_path = tmp_path / "repeated_parking_stalls.png"
    image = Image.new("RGB", (800, 500), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index in range(6):
        left = 150 + index * 55
        draw.rectangle((left, 320, left + 22, 364), outline=(20, 20, 20), width=3)
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=240.0,
        min_component_pixels=8,
        max_dimension=1200,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    assert result["parking_candidate_count"] == 6
    assert result["line_layer_counts"]["BW_PARKING_CANDIDATE"] == 6
    doc = ezdxf.readfile(Path(result["output_files"][0][1]))
    parking_inserts = [
        entity for entity in doc.modelspace()
        if entity.dxftype() == "INSERT"
        and entity.dxf.layer == "BW_PARKING_CANDIDATE"
    ]
    assert len(parking_inserts) == 6
    assert all(entity.dxf.name == "PT_PARKING_STALL" for entity in parking_inserts)
    assert len(list(doc.blocks["PT_PARKING_STALL"].query("LWPOLYLINE"))) == 1


def test_repeated_roofs_follow_source_lines_and_create_reviewable_roads(tmp_path):
    image_path = tmp_path / "repeated_roofs_and_road.png"
    image = Image.new("RGB", (900, 600), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    roof_centres = (
        (170, 120), (350, 120), (530, 120),
        (260, 275), (440, 275), (620, 275),
    )
    for center_x, center_y in roof_centres:
        left, top = center_x - 35, center_y - 30
        roof = [
            (left + 20, top), (left + 50, top),
            (left + 50, top + 15), (left + 70, top + 15),
            (left + 70, top + 45), (left + 50, top + 45),
            (left + 50, top + 60), (left + 20, top + 60),
            (left + 20, top + 45), (left, top + 45),
            (left, top + 15), (left + 20, top + 15),
        ]
        draw.line(roof + [roof[0]], fill=(20, 20, 20), width=4, joint="curve")
    draw.rounded_rectangle(
        (80, 450, 820, 484),
        radius=14,
        outline=(20, 20, 20),
        width=4,
    )
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=180.0,
        min_component_pixels=8,
        max_dimension=1200,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_simplify_factor=0.08,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    assert result["building_candidate_count"] == 6
    assert result["building_detection"]["mode"] == "repeated_enclosed_line_following"
    assert result["building_detection"]["fixed_box_expansion_used"] is False
    assert result["road_candidate_count"] >= 1
    assert result["road_detection"]["accepted_path_count"] >= 1
    assert result["road_centerline_candidate_count"] >= 1
    assert result["road_centerline_width_m"] is not None
    assert len(result["road_centerline_confidences"]) == result["road_centerline_candidate_count"]
    assert result["road_centerline_review_required_count"] == result["road_detection"]["centerline_review_required_count"]
    assert set(result["alignment_quality"]) == {"building", "road"}
    assert result["alignment_quality"]["building"]["object_count"] == 6
    assert result["alignment_quality"]["building"]["status"] == "aligned"
    assert result["alignment_quality"]["road"]["object_count"] >= 1
    assert result["line_layer_counts"]["BW_ROAD_CANDIDATE"] >= 1
    assert result["line_layer_counts"]["BW_ROAD_CENTERLINE_CANDIDATE"] >= 1
    assert Path(result["output_files"][5][1]).exists()
    assert Path(result["output_files"][7][1]).exists()
    assert Path(result["output_files"][8][1]).exists()
    assert Path(result["road_review_overlay_file"]).exists()
    report = Path(result["output_files"][2][1]).read_text(encoding="utf-8")
    assert "Building boundary alignment:" in report
    assert "Road boundary alignment:" in report
    assert "Suggested centerline corridor width (m):" in report

    doc = ezdxf.readfile(Path(result["output_files"][0][1]))
    buildings = [
        entity for entity in doc.modelspace()
        if entity.dxftype() == "LWPOLYLINE"
        and entity.dxf.layer == "BW_BUILDING_CANDIDATE"
    ]
    roads = [
        entity for entity in doc.modelspace()
        if entity.dxftype() == "LWPOLYLINE"
        and entity.dxf.layer == "BW_ROAD_CANDIDATE"
    ]
    centerlines = [
        entity for entity in doc.modelspace()
        if entity.dxf.layer == "BW_ROAD_CENTERLINE_CANDIDATE"
    ]
    assert len(buildings) == 6
    assert roads and all(entity.closed for entity in roads)
    assert centerlines and all(not entity.closed for entity in centerlines)
    assert all(entity.has_xdata("PT_ROAD_WIDTH_M") for entity in centerlines)
    assert all(
        any(int(tag.code) == 1040 and float(tag.value) > 0
            for tag in entity.get_xdata("PT_ROAD_WIDTH_M"))
        for entity in centerlines
    )
    assert all(entity.has_xdata("PT_ROAD_CONFIDENCE") for entity in centerlines)
    assert all(entity.has_xdata("PT_ROAD_CANDIDATE_ID") for entity in centerlines)
    assert all(entity.closed for entity in buildings)
    assert all(len(list(entity.get_points("xy"))) >= 8 for entity in buildings)
    presentation_hatches = list(doc.modelspace().query("HATCH"))
    assert len(presentation_hatches) == result["semantic_presentation_fill_count"]
    assert len(presentation_hatches) == len(buildings) + len(roads)
    assert all(entity.transparency >= 0.79 for entity in presentation_hatches)
    assert all(entity.has_xdata("PT_PRESENTATION_FILL") for entity in presentation_hatches)
    assert sum(
        entity.dxf.layer == "BW_BUILDING_FILL"
        for entity in presentation_hatches
    ) == len(buildings)
    assert sum(
        entity.dxf.layer == "BW_ROAD_FILL"
        for entity in presentation_hatches
    ) == len(roads)
    assert doc.layers.get("BW_BUILDING_CANDIDATE").rgb == (198, 119, 119)
    assert doc.layers.get("BW_ROAD_CANDIDATE").rgb == (151, 151, 145)
    assert doc.layers.get("BW_BUILDING_FILL").rgb == (198, 119, 119)
    assert doc.layers.get("BW_ROAD_FILL").rgb == (151, 151, 145)
    assert doc.layers.get("BW_TREE_CANDIDATE").rgb == (126, 165, 142)
    assert doc.layers.get("BW_PARKING_CANDIDATE").rgb == (204, 169, 113)
    assert result["semantic_scene_summary"]["role_counts"]["road"] >= 1


def test_black_white_conversion_creates_exact_pixel_semantic_guide_template(tmp_path):
    image_path = tmp_path / "source_plan.png"
    image = Image.new("RGB", (640, 960), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((120, 160, 300, 340), outline=(0, 0, 0), width=4)
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=160.0,
        min_component_pixels=8,
        max_dimension=320,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    template_path = Path(result["semantic_guide_template_file"])
    assert template_path == Path(result["output_files"][6][1])
    with Image.open(template_path) as template:
        assert template.size == image.size
        template_pixels = np.asarray(template.convert("RGB"))
    assert tuple(template_pixels[0, 0]) == (255, 255, 255)
    assert 205 <= int(template_pixels[160, 120, 0]) <= 215
    assert np.any(np.all(template_pixels == np.asarray((198, 119, 119)), axis=2))
    assert result["semantic_guide_template_prefill_counts"]["AI_BUILDING"] == 1
    report = Path(result["output_files"][2][1]).read_text(encoding="utf-8")
    assert "exact original source pixel dimensions" in report
    assert "automatic building, road, green and parking candidates" in report

    guided = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "guided",
        reference_width_m=160.0,
        min_component_pixels=8,
        max_dimension=320,
        conversion_mode="semantic_guide",
        semantic_guide_path=template_path,
    )
    assert guided["region_counts"]["AI_BUILDING"] == 1


def test_curated_knowledge_can_promote_two_matching_parking_stalls(tmp_path):
    """Two stalls need curated dimensions; one unreviewed box is still insufficient."""
    image_path = tmp_path / "two_parking_stalls.png"
    image = Image.new("RGB", (600, 400), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index in range(2):
        left = 220 + index * 40
        draw.rectangle((left, 270, left + 20, 282), outline=(20, 20, 20), width=3)
    image.save(image_path)
    common = {
        "reference_width_m": 180.0,
        "min_component_pixels": 8,
        "max_dimension": 1200,
        "conversion_mode": "black_white_linework",
        "line_threshold": 220,
        "line_trace_method": "centerline",
        "optimize_linework": True,
    }
    baseline = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "baseline",
        **common,
    )
    assisted = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "assisted",
        knowledge_profile={
            "enabled": True,
            "profile_id": "curated-test",
            "matched_card_count": 1,
            "curated_cad_count": 1,
            "building_sizes_m": [],
            "parking_sizes_m": [{"major_m": 5.0, "minor_m": 2.5, "count": 8}],
            "tree_radii_m": [],
        },
        **common,
    )

    assert baseline["parking_candidate_count"] == 0
    assert assisted["parking_candidate_count"] == 2
    assert assisted["knowledge_assist"]["knowledge_promoted_parking_stalls"] == 2
    assert assisted["knowledge_assist"]["adjusted_parking_stalls"] == 2


def test_detailed_plan_recovers_repeated_roof_cores_and_split_tree_crowns(tmp_path):
    """Dense roof ridges and radial tree spokes should not hide the site objects."""
    image_path = tmp_path / "detailed_residential_symbols.png"
    image = Image.new("RGB", (900, 650), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    for row in range(2):
        for column in range(3):
            center_x = 150 + column * 280
            center_y = 130 + row * 270
            left, right = center_x - 22, center_x + 22
            top, bottom = center_y - 19, center_y + 19
            draw.rectangle((left, top, right, bottom), outline=(0, 0, 0), width=3)
            draw.rectangle(
                (center_x - 4, center_y - 4, center_x + 4, center_y + 4),
                fill=(0, 0, 0),
            )
            for offset in (-32, -20, 0, 20, 32):
                draw.line(
                    (left, center_y, center_x - 65, center_y + offset),
                    fill=(0, 0, 0),
                    width=3,
                )
                draw.line(
                    (right, center_y, center_x + 65, center_y + offset),
                    fill=(0, 0, 0),
                    width=3,
                )
            for offset in (-40, -20, 0, 20, 40):
                draw.line(
                    (center_x, top, center_x + offset, center_y - 60),
                    fill=(0, 0, 0),
                    width=3,
                )
                draw.line(
                    (center_x, bottom, center_x + offset, center_y + 60),
                    fill=(0, 0, 0),
                    width=3,
                )

    for index in range(10):
        center_x = 80 + index * 82
        center_y = 570
        radius = 10
        draw.ellipse(
            (
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
            ),
            outline=(0, 0, 0),
            width=2,
        )
        for spoke in range(8):
            angle = radians(spoke * 45.0)
            draw.line(
                (
                    center_x,
                    center_y,
                    center_x + round(cos(angle) * 8),
                    center_y + round(sin(angle) * 8),
                ),
                fill=(0, 0, 0),
                width=1,
            )
    image.save(image_path)

    result = convert_image_to_dxf(
        image_path,
        output_dir=tmp_path / "output",
        reference_width_m=270.0,
        min_component_pixels=8,
        max_dimension=1200,
        conversion_mode="black_white_linework",
        line_threshold=220,
        line_trace_method="centerline",
        optimize_linework=True,
    )

    assert result["building_detection"]["mode"] == "repeated_roof_symbols"
    assert result["building_candidate_count"] == 6
    assert result["tree_candidate_count"] == 10
    assert result["tree_detection"]["repeated_circle_tree_count"] == 10
