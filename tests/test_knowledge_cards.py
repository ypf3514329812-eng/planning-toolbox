from pathlib import Path

import ezdxf
import pytest

from planning_toolbox.knowledge.image_cards import (
    attach_cad_reference_to_card,
    build_image_to_cad_quality_profile,
    create_image_knowledge_card,
    list_image_knowledge_cards,
    read_image_knowledge_card,
    update_image_knowledge_card_review,
)
from planning_toolbox.utils.file_integrity import sha256_file


def _image_result(image_path: Path, *, width_m: float = 120.0) -> dict:
    return {
        "task_type": "image_to_dxf",
        "conversion_mode": "black_white_linework",
        "source_file": str(image_path),
        "source_sha256": sha256_file(image_path),
        "image_size": (800, 500),
        "reference_width_m": width_m,
        "pixel_size_m": width_m / 800,
        "min_component_pixels": 8,
        "line_threshold": 220,
        "line_polarity_detected": "dark_on_light",
        "trace_method": "centerline",
        "line_simplify_factor": 0.15,
        "optimization_enabled": True,
        "region_counts": {
            "BW_BUILDING_CANDIDATE": 4,
            "BW_TREE_CANDIDATE": 12,
        },
        "region_areas_m2": {},
        "output_files": [],
    }


def test_image_knowledge_card_is_lightweight_and_does_not_embed_image(tmp_path):
    image_path = tmp_path / "规划参考图.png"
    image_path.write_bytes(b"not-decoded-by-knowledge-card" * 200)
    before = sha256_file(image_path)

    card = create_image_knowledge_card(
        _image_result(image_path),
        tmp_path / "output",
        project_type="居住区总平面",
        tags="住宅，曲线道路, 住宅",
        expected_source_sha256=before,
    )

    card_path = Path(card["card_path"])
    assert card_path.exists()
    assert card["size_bytes"] < 50_000
    assert sha256_file(image_path) == before
    text = card_path.read_text(encoding="utf-8")
    assert "embedded_in_card: false" in text
    assert "居住区总平面" in text
    assert "BW_BUILDING_CANDIDATE" in text
    assert "base64" not in text.casefold()

    loaded = read_image_knowledge_card(card_path)
    metadata = loaded["metadata"]
    assert metadata["source"]["integrity_status"] == "verified_unchanged_during_conversion"
    assert metadata["recognition"]["total_candidates"] == 16
    assert metadata["confidence_status"] == "not_calibrated"
    assert metadata["tags"] == ["住宅", "曲线道路"]


def test_image_knowledge_card_rejects_changed_source(tmp_path):
    image_path = tmp_path / "source.png"
    image_path.write_bytes(b"original")
    result = _image_result(image_path)
    before = sha256_file(image_path)
    image_path.write_bytes(b"changed")

    with pytest.raises(RuntimeError, match="指纹|发生变化"):
        create_image_knowledge_card(
            result,
            tmp_path / "output",
            expected_source_sha256=before,
        )


def test_same_image_and_settings_update_one_card_and_preserve_review(tmp_path):
    image_path = tmp_path / "same.png"
    image_path.write_bytes(b"same-image")
    result = _image_result(image_path)
    first = create_image_knowledge_card(result, tmp_path / "output")
    update_image_knowledge_card_review(
        first["card_path"], "user_confirmed", "已逐层与原图核对"
    )

    second = create_image_knowledge_card(result, tmp_path / "output")
    assert second["card_path"] == first["card_path"]
    assert len(list((tmp_path / "output" / "knowledge_cards").glob("*.md"))) == 1
    metadata = read_image_knowledge_card(second["card_path"])["metadata"]
    assert metadata["review_status"] == "user_confirmed"
    assert metadata["review_note"] == "已逐层与原图核对"


def test_different_scale_creates_distinct_card(tmp_path):
    image_path = tmp_path / "scale.png"
    image_path.write_bytes(b"scale-image")
    first = create_image_knowledge_card(
        _image_result(image_path, width_m=100), tmp_path / "output"
    )
    second = create_image_knowledge_card(
        _image_result(image_path, width_m=200), tmp_path / "output"
    )
    assert first["card_id"] != second["card_id"]


def test_selected_cad_reference_is_copied_and_inspected_on_demand(tmp_path):
    image_path = tmp_path / "plan.png"
    image_path.write_bytes(b"plan-image")
    card = create_image_knowledge_card(
        _image_result(image_path),
        tmp_path / "output",
        project_type="居住区总平面",
    )

    dxf_path = tmp_path / "人工精修样本.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BUILDING")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (20, 0), (20, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    doc.saveas(dxf_path)
    source_hash = sha256_file(dxf_path)

    reference = attach_cad_reference_to_card(
        card["card_path"],
        dxf_path,
        title="人工精修居住区样本",
        review_status="user_curated",
    )

    copied = Path(reference["path"])
    assert copied.exists()
    assert copied != dxf_path
    assert sha256_file(dxf_path) == source_hash == sha256_file(copied)
    assert reference["unit_name"] == "m"
    assert reference["entity_count"] == 1
    assert "BUILDING" in reference["layers"]
    assert reference["quality_profile"]["metric_ready"] is True
    assert reference["quality_profile"]["building_sizes_m"] == [
        {"major_m": 20.0, "minor_m": 10.0, "count": 1}
    ]
    metadata = read_image_knowledge_card(card["card_path"])["metadata"]
    assert metadata["cad_references"][0]["review_status"] == "user_curated"

    quality_profile = build_image_to_cad_quality_profile(
        Path(card["card_path"]).parent, project_type="居住区总平面"
    )
    assert quality_profile["enabled"] is True
    assert quality_profile["curated_cad_count"] == 1
    assert quality_profile["building_sizes_m"][0]["major_m"] == pytest.approx(20.0)
    pending_profile = build_image_to_cad_quality_profile(
        Path(card["card_path"]).parent, project_type="待确认"
    )
    assert pending_profile["enabled"] is False
    assert pending_profile["disabled_reason"] == "project_type_required"


def test_card_catalog_search_uses_metadata_only(tmp_path):
    first_image = tmp_path / "residential.png"
    second_image = tmp_path / "park.png"
    first_image.write_bytes(b"residential")
    second_image.write_bytes(b"park")
    output = tmp_path / "output"
    create_image_knowledge_card(
        _image_result(first_image), output, project_type="居住区总平面", tags="住宅"
    )
    create_image_knowledge_card(
        _image_result(second_image), output, project_type="公园与绿地", tags="公园"
    )

    found = list_image_knowledge_cards(
        output / "knowledge_cards", query="住宅", project_type="居住区总平面"
    )
    assert len(found) == 1
    assert found[0]["metadata"]["source"]["name"] == "residential.png"
    assert found[0]["metadata"]["image"]["loaded_during_catalog_search"] is False


def test_unreviewed_cad_is_never_used_for_geometry_correction(tmp_path):
    image_path = tmp_path / "candidate.png"
    image_path.write_bytes(b"candidate-image")
    card = create_image_knowledge_card(
        _image_result(image_path),
        tmp_path / "output",
        project_type="居住区总平面",
    )
    dxf_path = tmp_path / "candidate_only.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BUILDING")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (30, 0), (30, 12), (0, 12)],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    doc.saveas(dxf_path)
    attach_cad_reference_to_card(
        card["card_path"],
        dxf_path,
        review_status="candidate_unreviewed",
    )

    profile = build_image_to_cad_quality_profile(
        Path(card["card_path"]).parent,
        project_type="居住区总平面",
    )
    assert profile["enabled"] is False
    assert profile["curated_cad_count"] == 0


def test_unknown_unit_curated_cad_cannot_supply_metric_dimensions(tmp_path):
    image_path = tmp_path / "unknown_unit.png"
    image_path.write_bytes(b"unknown-unit-image")
    card = create_image_knowledge_card(
        _image_result(image_path),
        tmp_path / "output",
        project_type="居住区总平面",
    )
    dxf_path = tmp_path / "unknown_unit_refined.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 0
    doc.layers.add("BUILDING")
    doc.modelspace().add_lwpolyline(
        [(0, 0), (20, 0), (20, 8), (0, 8)],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    doc.saveas(dxf_path)
    reference = attach_cad_reference_to_card(
        card["card_path"],
        dxf_path,
        review_status="user_curated",
    )
    assert reference["quality_profile"]["metric_ready"] is False

    profile = build_image_to_cad_quality_profile(
        Path(card["card_path"]).parent,
        project_type="居住区总平面",
    )
    assert profile["enabled"] is False
    assert profile["curated_cad_count"] == 0


def test_curated_cad_profile_improves_near_match_geometry(tmp_path):
    """A curated metric DXF must measurably correct close raster-derived sizes."""
    from PIL import Image, ImageDraw

    from planning_toolbox.cad.planning.image_to_dxf import convert_image_to_dxf

    image_path = tmp_path / "near_match_plan.png"
    image = Image.new("RGB", (800, 500), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((200, 90, 284, 128), outline=(20, 20, 20), width=4)
    for index in range(6):
        left = 160 + index * 34
        draw.rectangle((left, 320, left + 22, 332), outline=(20, 20, 20), width=3)
    for center_x in (120, 170, 220, 270):
        draw.ellipse(
            (center_x - 7, 230 - 7, center_x + 7, 230 + 7),
            outline=(20, 20, 20),
            width=3,
        )
    image.save(image_path)

    card = create_image_knowledge_card(
        _image_result(image_path, width_m=200.0),
        tmp_path / "library",
        project_type="居住区总平面",
    )
    refined_dxf = tmp_path / "refined_standard.dxf"
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("BUILDING")
    doc.layers.add("PARKING")
    doc.layers.add("TREE")
    modelspace = doc.modelspace()
    modelspace.add_lwpolyline(
        [(0, 0), (20, 0), (20, 10), (0, 10)],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    parking_block = doc.blocks.new("PT_PARKING_STALL")
    parking_block.add_lwpolyline(
        [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)], close=True
    )
    for index in range(6):
        modelspace.add_blockref(
            "PT_PARKING_STALL",
            (index * 7.0, 30.0),
            dxfattribs={"layer": "PARKING", "xscale": 5.0, "yscale": 2.5},
        )
    tree_block = doc.blocks.new("PT_TREE")
    tree_block.add_circle((0, 0), 1.0)
    for index in range(4):
        modelspace.add_blockref(
            "PT_TREE",
            (index * 5.0, 50.0),
            dxfattribs={"layer": "TREE", "xscale": 1.5, "yscale": 1.5},
        )
    doc.saveas(refined_dxf)
    attach_cad_reference_to_card(
        card["card_path"],
        refined_dxf,
        review_status="user_curated",
    )
    profile = build_image_to_cad_quality_profile(
        Path(card["card_path"]).parent,
        project_type="居住区总平面",
    )
    assert profile["enabled"] is True
    assert profile["building_sizes_m"][0]["major_m"] == pytest.approx(20.0)
    assert profile["parking_sizes_m"][0]["minor_m"] == pytest.approx(2.5)
    assert profile["tree_radii_m"][0]["radius_m"] == pytest.approx(1.5)

    common = {
        "reference_width_m": 200.0,
        "min_component_pixels": 8,
        "max_dimension": 1200,
        "conversion_mode": "black_white_linework",
        "line_threshold": 220,
        "line_simplify_factor": 0.15,
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
        knowledge_profile=profile,
        **common,
    )

    assert baseline["knowledge_assist"]["profile_found"] is False
    assert assisted["knowledge_assist"]["profile_found"] is True
    assert assisted["knowledge_assist"]["adjusted_buildings"] >= 1
    assert assisted["knowledge_assist"]["adjusted_parking_stalls"] == 6
    assert assisted["knowledge_assist"]["adjustment_count"] > 6
    assert all(
        detail["before_m"] != detail["after_m"]
        for detail in assisted["knowledge_assist"]["details"]
    )

    assisted_doc = ezdxf.readfile(Path(assisted["output_files"][0][1]))
    parking = [
        entity for entity in assisted_doc.modelspace()
        if entity.dxftype() == "INSERT" and entity.dxf.name == "PT_PARKING_STALL"
    ]
    assert len(parking) == 6
    assert all(float(entity.dxf.xscale) == pytest.approx(5.0) for entity in parking)
    assert all(float(entity.dxf.yscale) == pytest.approx(2.5) for entity in parking)
