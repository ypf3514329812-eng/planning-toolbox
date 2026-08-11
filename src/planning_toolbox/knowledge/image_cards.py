"""Create small Markdown knowledge cards from image-to-CAD results.

The catalog deliberately stores no image bytes, thumbnails, contours, or model
weights.  A card is a human-readable index that points to the original source
and records its SHA-256 digest, explicit scale, conversion settings, candidate
counts, and review state.  Images remain on disk and are loaded only by the
conversion workflow when the user asks for them.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from collections import Counter
from math import hypot
from typing import Any, Iterable

import yaml

from planning_toolbox import __version__
from planning_toolbox.utils.file_integrity import sha256_file


SCHEMA_VERSION = 1
REVIEW_STATUSES = {
    "machine_candidate",
    "user_confirmed",
    "needs_correction",
    "rejected",
}

_LAYER_LABELS = {
    "AI_BUILDING": "建筑分区",
    "AI_ROAD": "道路分区",
    "AI_GREEN": "绿地分区",
    "AI_WATER": "水体分区",
    "AI_PARKING": "停车分区",
    "BW_LINEWORK": "普通线条",
    "BW_CLOSED": "闭合轮廓",
    "BW_DETAIL": "细节线条",
    "BW_BUILDING_CANDIDATE": "建筑候选",
    "BW_TREE_CANDIDATE": "树木候选",
    "BW_PARKING_CANDIDATE": "停车位候选",
    "BW_LANDSCAPE_CANDIDATE": "景观圆弧候选",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    return cleaned[:80] or "planning_image"


def _normalize_tags(tags: Iterable[str] | str | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        values = re.split(r"[,，;；\n]+", tags)
    else:
        values = list(tags)
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = str(value).strip()
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            result.append(tag[:40])
    return result[:20]


def _pair(value: Any) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            pass
    return 0, 0


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        try:
            count = int(item)
        except (TypeError, ValueError):
            continue
        if count:
            result[str(key)] = count
    return result


def _float_mapping(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        try:
            amount = float(item)
        except (TypeError, ValueError):
            continue
        if amount:
            result[str(key)] = round(amount, 4)
    return result


def _output_records(result: dict[str, Any]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for item in result.get("output_files", []):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        label, output_path = str(item[0]), str(item[1])
        if label and output_path:
            records.append({"label": label, "path": str(Path(output_path).resolve())})
    return records


def _configuration(result: dict[str, Any]) -> dict[str, Any]:
    mode = str(result.get("conversion_mode", "color_regions"))
    config: dict[str, Any] = {
        "conversion_mode": mode,
        "reference_width_m": round(_number(result.get("reference_width_m")), 6),
        "minimum_component_pixels": int(result.get("min_component_pixels", 0) or 0),
        "focus_site_only": bool(result.get("focus_site_only", False)),
    }
    if mode == "black_white_linework":
        config.update(
            {
                "line_threshold": int(result.get("line_threshold", 0) or 0),
                "line_polarity": str(result.get("line_polarity_detected", "unknown")),
                "trace_method": str(result.get("trace_method", "unknown")),
                "line_simplify_factor": round(
                    _number(result.get("line_simplify_factor")), 6
                ),
                "optimization_enabled": bool(result.get("optimization_enabled", False)),
            }
        )
    else:
        config["color_tolerance"] = int(result.get("color_tolerance", 0) or 0)
    return config


def _read_front_matter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("该文件不是 Planning Toolbox Markdown 知识卡。")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise ValueError("知识卡的 Markdown 元数据不完整。")
    metadata = yaml.safe_load(text[4:closing]) or {}
    if not isinstance(metadata, dict):
        raise ValueError("知识卡元数据格式无效。")
    return metadata, text[closing + 5 :]


def read_image_knowledge_card(path: Path | str) -> dict[str, Any]:
    """Read one card without opening or decoding its source image."""
    card_path = Path(path).resolve()
    metadata, body = _read_front_matter(card_path)
    return {"path": str(card_path), "metadata": metadata, "body": body}


def _render_candidate_table(
    counts: dict[str, int], areas: dict[str, float]
) -> list[str]:
    lines = [
        "| 识别内容 | CAD 图层 | 数量 | 估算面积（m²） | 可信度说明 |",
        "|---|---|---:|---:|---|",
    ]
    if not counts:
        lines.append("| 暂无结构化对象 | - | 0 | - | 需查看转换报告 |")
        return lines
    for layer, count in counts.items():
        area = areas.get(layer)
        area_text = f"{area:.2f}" if area is not None else "-"
        confidence = "机器候选，待人工确认" if "CANDIDATE" in layer else "依赖标准色板，待人工确认"
        lines.append(
            f"| {_LAYER_LABELS.get(layer, layer)} | `{layer}` | {count} | "
            f"{area_text} | {confidence} |"
        )
    return lines


def _render_markdown(metadata: dict[str, Any]) -> str:
    yaml_text = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    counts = _int_mapping(metadata.get("recognition", {}).get("counts"))
    areas = _float_mapping(metadata.get("recognition", {}).get("areas_m2"))
    config = metadata.get("conversion", {})
    width, height = _pair(metadata.get("image", {}).get("size_px"))
    outputs = metadata.get("outputs", [])
    cad_references = metadata.get("cad_references", [])

    lines = [
        "---",
        yaml_text,
        "---",
        "",
        f"# {metadata.get('title', '图纸知识卡')}",
        "",
        "> 本卡是机器生成的学习索引，不是审批、测绘或施工结论。它不包含原图像素，也不能代替 CAD 几何复核。",
        "",
        "## 来源与尺度",
        "",
        f"- 原图：`{metadata.get('source', {}).get('name', '')}`",
        f"- 原图路径：`{metadata.get('source', {}).get('path', '')}`",
        f"- SHA-256：`{metadata.get('source', {}).get('sha256', '')}`",
        f"- 零修改校验：{metadata.get('source', {}).get('integrity_status', 'unknown')}",
        f"- 图片尺寸：{width} × {height} 像素",
        f"- 用户明确提供的场地宽度：{config.get('reference_width_m', 0):g} m",
        "- 坐标说明：图片局部平面坐标，未声明地理坐标系，不能直接与真实 GIS 坐标叠加。",
        "",
        "## 机器识别摘要",
        "",
        *_render_candidate_table(counts, areas),
        "",
        "## 可信度边界",
        "",
        "- 当前识别置信度尚未通过固定真值数据集校准，因此不提供虚假的百分比。",
        "- 建筑、树木、停车位、道路和景观对象均属于候选；名称或用途需要用户确认。",
        "- 比例尺来自用户填写的场地宽度；宽度错误会同步影响全部尺寸和面积。",
        "- 规范合规、容积率、退线和最终图层仍须使用确认后的 CAD 几何另行计算。",
        "",
        "## 建议复核步骤",
        "",
        "1. 对照原图和 CAD 预览，先检查图框、文字和阴影是否被误识别。",
        "2. 逐层核对建筑、道路、绿地、水体、树木和停车位候选。",
        "3. 确认场地实际宽度以及 CAD 单位为米。",
        "4. 只将人工确认过的候选移入正式图层，再进行面积和退线计算。",
        "5. 确认无误后，可把 `review_status` 更新为 `user_confirmed`。",
        "",
        "## 关联成果",
        "",
    ]
    if outputs:
        for output in outputs:
            lines.append(f"- {output.get('label', '输出文件')}：`{output.get('path', '')}`")
    else:
        lines.append("- 暂无关联输出文件。")
    lines.extend(["", "## 精选 CAD 参考样本", ""])
    if cad_references:
        lines.extend(
            [
                "| 样本 | 单位 | 图元数 | 复核状态 | 文件 |",
                "|---|---|---:|---|---|",
            ]
        )
        for reference in cad_references:
            lines.append(
                f"| {reference.get('title', 'CAD 参考样本')} | "
                f"{reference.get('unit_name', 'unknown')} | "
                f"{reference.get('entity_count', 0)} | "
                f"{reference.get('review_status', 'candidate_unreviewed')} | "
                f"`{reference.get('path', '')}` |"
            )
        lines.append("")
        lines.append(
            "仅 `user_curated` 样本可作为个人绘图参考；`candidate_unreviewed` 仍须在 CAD 中人工精修和确认。"
        )
    else:
        lines.append("- 当前知识卡没有复制 CAD。只有用户主动收藏的少量样本才会占用额外磁盘空间。")
    lines.extend(
        [
            "",
            "## 轻量化说明",
            "",
            "本文件仅保存文本元数据和文件路径，不嵌入原图、缩略图、像素矩阵或模型权重。系统检索本卡时不会加载原图。",
            "",
        ]
    )
    return "\n".join(lines)


def create_image_knowledge_card(
    result: dict[str, Any],
    output_dir: Path | str,
    *,
    project_type: str = "待确认",
    tags: Iterable[str] | str | None = None,
    expected_source_sha256: str | None = None,
) -> dict[str, Any]:
    """Create or update a deterministic, low-memory Markdown knowledge card.

    When ``expected_source_sha256`` was captured before conversion, the card
    records a true before/after zero-mutation verification.  Otherwise it only
    states that the current file matches the digest returned by the converter.
    """
    if result.get("task_type") != "image_to_dxf":
        raise ValueError("只有图转 CAD 结果可以生成图片知识卡。")
    source_value = result.get("source_file")
    if not source_value:
        raise ValueError("图转 CAD 结果缺少原图路径。")
    source = Path(str(source_value)).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"找不到知识卡对应的原图：{source}")

    current_sha256 = sha256_file(source)
    result_sha256 = str(result.get("source_sha256", "")).lower()
    expected = str(expected_source_sha256 or "").lower()
    if result_sha256 and current_sha256 != result_sha256:
        raise RuntimeError("原图指纹与转换结果不一致，知识卡已停止生成。")
    if expected and current_sha256 != expected:
        raise RuntimeError("原图在图转 CAD 处理期间发生变化，知识卡已停止生成。")
    integrity_status = (
        "verified_unchanged_during_conversion"
        if expected
        else "verified_at_card_creation"
    )

    configuration = _configuration(result)
    signature_payload = json.dumps(
        {
            "source_sha256": current_sha256,
            "configuration": configuration,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config_digest = hashlib.sha256(signature_payload).hexdigest()[:10]
    card_id = f"ptkc-{current_sha256[:12]}-{config_digest}"
    card_dir = Path(output_dir).resolve() / "knowledge_cards"
    card_dir.mkdir(parents=True, exist_ok=True)
    card_path = card_dir / f"{_safe_stem(source.stem)}_{card_id}.md"

    previous: dict[str, Any] = {}
    if card_path.exists():
        try:
            previous, _ = _read_front_matter(card_path)
        except (OSError, ValueError, yaml.YAMLError):
            previous = {}
    normalized_tags = _normalize_tags(tags)
    previous_tags = _normalize_tags(previous.get("tags"))
    merged_tags = _normalize_tags([*previous_tags, *normalized_tags])
    incoming_project_type = str(project_type).strip() or "待确认"
    if incoming_project_type == "待确认" and previous.get("project_type"):
        incoming_project_type = str(previous["project_type"])
    review_status = str(previous.get("review_status", "machine_candidate"))
    if review_status not in REVIEW_STATUSES:
        review_status = "machine_candidate"

    image_width, image_height = _pair(result.get("image_size"))
    counts = _int_mapping(result.get("region_counts"))
    areas = _float_mapping(result.get("region_areas_m2"))
    now = _utc_now()
    metadata: dict[str, Any] = {
        "schema": "planning-toolbox-image-knowledge-card",
        "schema_version": SCHEMA_VERSION,
        "card_id": card_id,
        "title": f"{source.stem} · 图纸知识卡",
        "project_type": incoming_project_type,
        "tags": merged_tags,
        "review_status": review_status,
        "review_note": str(previous.get("review_note", "")),
        "authority": "learning_candidate_not_approval",
        "confidence_status": "not_calibrated",
        "created_at_utc": str(previous.get("created_at_utc", now)),
        "updated_at_utc": now,
        "algorithm_version": __version__,
        "source": {
            "name": source.name,
            "path": str(source),
            "sha256": current_sha256,
            "size_bytes": source.stat().st_size,
            "integrity_status": integrity_status,
            "embedded_in_card": False,
        },
        "image": {
            "size_px": [image_width, image_height],
            "aspect_ratio": round(image_width / image_height, 6) if image_height else None,
            "loaded_during_catalog_search": False,
        },
        "spatial_reference": {
            "type": "local_image_plane_unreferenced",
            "crs": None,
            "distance_area_allowed_before_review": False,
        },
        "conversion": configuration,
        "recognition": {
            "counts": counts,
            "areas_m2": areas,
            "total_candidates": sum(counts.values()),
            "semantics_confirmed": review_status == "user_confirmed",
        },
        "knowledge_assist": result.get("knowledge_assist", {}),
        "outputs": _output_records(result),
        "cad_references": previous.get("cad_references", []),
    }
    card_text = _render_markdown(metadata)
    temporary = card_path.with_suffix(".md.tmp")
    temporary.write_text(card_text, encoding="utf-8", newline="\n")
    temporary.replace(card_path)
    return {
        "card_id": card_id,
        "card_path": str(card_path),
        "size_bytes": card_path.stat().st_size,
        "source_sha256": current_sha256,
        "integrity_status": integrity_status,
        "review_status": review_status,
    }


def _inspect_dxf_reference(path: Path) -> dict[str, Any]:
    """Inspect one explicitly selected DXF; import ezdxf only on demand."""
    import ezdxf

    from shapely.geometry import Polygon

    unit_names = {
        0: "unknown",
        1: "in",
        2: "ft",
        4: "mm",
        5: "cm",
        6: "m",
    }
    doc = ezdxf.readfile(path)
    unit_code = int(doc.header.get("$INSUNITS", 0) or 0)
    unit_to_m = {
        1: 0.0254,
        2: 0.3048,
        4: 0.001,
        5: 0.01,
        6: 1.0,
    }.get(unit_code)
    layer_names = [str(layer.dxf.name) for layer in doc.layers]
    building_pairs: list[tuple[float, float]] = []
    parking_pairs: list[tuple[float, float]] = []
    tree_radii: list[float] = []

    def layer_has(layer: str, keywords: tuple[str, ...]) -> bool:
        normalized = layer.upper().replace("-", "_")
        return any(keyword in normalized for keyword in keywords)

    def rotated_dimensions(points: list[tuple[float, float]]) -> tuple[float, float] | None:
        if len(points) < 3:
            return None
        polygon = Polygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty or polygon.area <= 0:
            return None
        rectangle_points = list(polygon.minimum_rotated_rectangle.exterior.coords)[:4]
        if len(rectangle_points) != 4:
            return None
        lengths = [
            hypot(
                rectangle_points[(index + 1) % 4][0] - rectangle_points[index][0],
                rectangle_points[(index + 1) % 4][1] - rectangle_points[index][1],
            )
            for index in range(4)
        ]
        major, minor = max(lengths), min(lengths)
        if major <= 0 or minor <= 0:
            return None
        return major, minor

    if unit_to_m is not None:
        for entity in doc.modelspace():
            layer = str(entity.dxf.get("layer", "0"))
            entity_type = entity.dxftype()
            if entity_type == "LWPOLYLINE" and bool(entity.closed):
                points = [
                    (float(point[0]), float(point[1]))
                    for point in entity.get_points("xy")
                ]
                dimensions = rotated_dimensions(points)
                if dimensions is None:
                    continue
                major_m, minor_m = (
                    dimensions[0] * unit_to_m,
                    dimensions[1] * unit_to_m,
                )
                if layer_has(
                    layer,
                    ("BUILD", "BLDG", "ARCH", "JZ", "建筑"),
                ):
                    building_pairs.append((major_m, minor_m))
                elif layer_has(layer, ("PARK", "STALL", "车位", "停车")):
                    parking_pairs.append((major_m, minor_m))
            elif entity_type == "INSERT":
                block_name = str(entity.dxf.get("name", "")).upper()
                xscale = abs(float(entity.dxf.get("xscale", 1.0))) * unit_to_m
                yscale = abs(float(entity.dxf.get("yscale", 1.0))) * unit_to_m
                if "PARK" in block_name or layer_has(
                    layer, ("PARK", "STALL", "车位", "停车")
                ):
                    parking_pairs.append((max(xscale, yscale), min(xscale, yscale)))
                elif "TREE" in block_name or layer_has(
                    layer, ("TREE", "绿化", "树木")
                ):
                    tree_radii.append((xscale + yscale) / 2.0)
            elif entity_type == "CIRCLE" and layer_has(
                layer, ("TREE", "绿化", "树木")
            ):
                tree_radii.append(abs(float(entity.dxf.radius)) * unit_to_m)

    def compact_pairs(values: list[tuple[float, float]]) -> list[dict[str, Any]]:
        rounded = [
            (round(max(major, minor), 2), round(min(major, minor), 2))
            for major, minor in values
            if major > 0 and minor > 0
        ]
        return [
            {"major_m": major, "minor_m": minor, "count": count}
            for (major, minor), count in Counter(rounded).most_common(32)
        ]

    rounded_radii = [round(radius, 2) for radius in tree_radii if radius > 0]
    dimension_profile = {
        "metric_ready": unit_to_m is not None,
        "building_sizes_m": compact_pairs(building_pairs),
        "parking_sizes_m": compact_pairs(parking_pairs),
        "tree_radii_m": [
            {"radius_m": radius, "count": count}
            for radius, count in Counter(rounded_radii).most_common(16)
        ],
        "source_counts": {
            "buildings": len(building_pairs),
            "parking_stalls": len(parking_pairs),
            "trees": len(tree_radii),
        },
    }
    return {
        "unit_code": unit_code,
        "unit_name": unit_names.get(unit_code, f"INSUNITS_{unit_code}"),
        "units_known": unit_code != 0,
        "entity_count": sum(1 for _ in doc.modelspace()),
        "layer_count": len(layer_names),
        "layers": layer_names[:100],
        "layers_truncated": len(layer_names) > 100,
        "quality_profile": dimension_profile,
    }


def attach_cad_reference_to_card(
    card_path: Path | str,
    dxf_path: Path | str,
    *,
    title: str = "精选 CAD 参考样本",
    review_status: str = "candidate_unreviewed",
) -> dict[str, Any]:
    """Copy one explicitly selected DXF beside a card and record its lineage.

    This is intentionally opt-in.  The source DXF is hashed before and after
    inspection/copying, and only the copied library asset may be managed later.
    """
    if review_status not in {"candidate_unreviewed", "user_curated"}:
        raise ValueError("CAD 样本状态必须是 candidate_unreviewed 或 user_curated。")
    source = Path(dxf_path).resolve()
    if not source.is_file() or source.suffix.lower() != ".dxf":
        raise ValueError("请选择有效的 DXF 文件作为 CAD 参考样本。")
    card = Path(card_path).resolve()
    metadata, _ = _read_front_matter(card)
    if metadata.get("schema") != "planning-toolbox-image-knowledge-card":
        raise ValueError("CAD 样本只能附加到 Planning Toolbox 图片知识卡。")

    source_hash_before = sha256_file(source)
    inspection = _inspect_dxf_reference(source)
    source_hash_after = sha256_file(source)
    if source_hash_before != source_hash_after:
        raise RuntimeError("CAD 源文件在检查期间发生变化，系统已停止收藏。")

    reference_id = f"cadref-{source_hash_before[:16]}"
    asset_dir = card.parent / "cad_samples"
    asset_dir.mkdir(parents=True, exist_ok=True)
    destination = asset_dir / (
        f"{reference_id}_{_safe_stem(source.stem)}.dxf"
    )
    if source != destination:
        temporary = destination.with_suffix(".dxf.tmp")
        shutil.copy2(source, temporary)
        if sha256_file(temporary) != source_hash_before:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("CAD 样本复制校验失败，未写入知识库。")
        temporary.replace(destination)

    references = metadata.get("cad_references", [])
    if not isinstance(references, list):
        references = []
    reference = {
        "reference_id": reference_id,
        "title": str(title).strip() or "精选 CAD 参考样本",
        "path": str(destination),
        "source_path": str(source),
        "sha256": source_hash_before,
        "size_bytes": destination.stat().st_size,
        "review_status": review_status,
        "source_integrity": "verified_unchanged_during_copy",
        "added_at_utc": _utc_now(),
        **inspection,
    }
    references = [
        item for item in references
        if isinstance(item, dict) and item.get("reference_id") != reference_id
    ]
    references.append(reference)
    metadata["cad_references"] = references
    metadata["updated_at_utc"] = _utc_now()
    card_text = _render_markdown(metadata)
    temporary_card = card.with_suffix(".md.tmp")
    temporary_card.write_text(card_text, encoding="utf-8", newline="\n")
    temporary_card.replace(card)
    return reference


def build_image_to_cad_quality_profile(
    knowledge_root: Path | str,
    *,
    project_type: str = "待确认",
    conversion_mode: str = "black_white_linework",
    limit: int = 100,
) -> dict[str, Any]:
    """Build a compact correction profile from user-curated DXF references.

    Candidate/unreviewed CAD files are never used to alter generated geometry.
    The returned profile contains only small metric descriptors and provenance,
    not source images or full CAD entities.
    """
    requested_type = str(project_type).strip() or "待确认"
    if requested_type == "待确认":
        return {
            "enabled": False,
            "profile_id": "",
            "project_type": requested_type,
            "conversion_mode": conversion_mode,
            "matched_card_ids": [],
            "matched_reference_ids": [],
            "matched_card_count": 0,
            "curated_cad_count": 0,
            "building_sizes_m": [],
            "parking_sizes_m": [],
            "tree_radii_m": [],
            "expected_source_counts": [],
            "authority": "user_curated_local_cad",
            "geometry_policy": "near_match_snap_only",
            "disabled_reason": "project_type_required",
        }
    filter_type = requested_type
    cards = list_image_knowledge_cards(
        knowledge_root,
        project_type=filter_type,
        limit=limit,
    )
    building_sizes: list[dict[str, Any]] = []
    parking_sizes: list[dict[str, Any]] = []
    tree_radii: list[dict[str, Any]] = []
    source_counts: list[dict[str, int]] = []
    card_ids: list[str] = []
    reference_ids: list[str] = []

    for item in cards:
        metadata = item.get("metadata", {})
        if metadata.get("conversion", {}).get("conversion_mode") != conversion_mode:
            continue
        accepted_in_card = False
        for reference in metadata.get("cad_references", []):
            if not isinstance(reference, dict):
                continue
            if reference.get("review_status") != "user_curated":
                continue
            profile = reference.get("quality_profile", {})
            if not isinstance(profile, dict) or not profile.get("metric_ready"):
                continue
            building_sizes.extend(profile.get("building_sizes_m", []))
            parking_sizes.extend(profile.get("parking_sizes_m", []))
            tree_radii.extend(profile.get("tree_radii_m", []))
            counts = profile.get("source_counts", {})
            if isinstance(counts, dict):
                source_counts.append(
                    {
                        "buildings": int(counts.get("buildings", 0) or 0),
                        "parking_stalls": int(counts.get("parking_stalls", 0) or 0),
                        "trees": int(counts.get("trees", 0) or 0),
                    }
                )
            reference_ids.append(str(reference.get("reference_id", "")))
            accepted_in_card = True
        if accepted_in_card:
            card_ids.append(str(metadata.get("card_id", "")))

    def merge_pairs(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counter: Counter[tuple[float, float]] = Counter()
        for value in values:
            try:
                pair = (
                    round(float(value["major_m"]), 2),
                    round(float(value["minor_m"]), 2),
                )
                counter[pair] += max(1, int(value.get("count", 1)))
            except (KeyError, TypeError, ValueError):
                continue
        return [
            {"major_m": major, "minor_m": minor, "count": count}
            for (major, minor), count in counter.most_common(48)
        ]

    radius_counter: Counter[float] = Counter()
    for value in tree_radii:
        try:
            radius_counter[round(float(value["radius_m"]), 2)] += max(
                1, int(value.get("count", 1))
            )
        except (KeyError, TypeError, ValueError):
            continue
    merged_radii = [
        {"radius_m": radius, "count": count}
        for radius, count in radius_counter.most_common(24)
    ]
    merged_buildings = merge_pairs(building_sizes)
    merged_parking = merge_pairs(parking_sizes)
    enabled = bool(merged_buildings or merged_parking or merged_radii)
    signature = json.dumps(
        {
            "cards": sorted(card_ids),
            "references": sorted(reference_ids),
            "buildings": merged_buildings,
            "parking": merged_parking,
            "trees": merged_radii,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "enabled": enabled,
        "profile_id": f"ptkp-{hashlib.sha256(signature).hexdigest()[:16]}",
        "project_type": requested_type,
        "conversion_mode": conversion_mode,
        "matched_card_ids": sorted(filter(None, set(card_ids))),
        "matched_reference_ids": sorted(filter(None, set(reference_ids))),
        "matched_card_count": len(set(filter(None, card_ids))),
        "curated_cad_count": len(set(filter(None, reference_ids))),
        "building_sizes_m": merged_buildings,
        "parking_sizes_m": merged_parking,
        "tree_radii_m": merged_radii,
        "expected_source_counts": source_counts[:50],
        "authority": "user_curated_local_cad",
        "geometry_policy": "near_match_snap_only",
    }


def list_image_knowledge_cards(
    knowledge_root: Path | str,
    *,
    query: str = "",
    project_type: str | None = None,
    review_status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search card metadata without loading any referenced source image."""
    root = Path(knowledge_root).resolve()
    if not root.exists():
        return []
    needle = query.strip().casefold()
    found: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            metadata, _ = _read_front_matter(path)
        except (OSError, ValueError, yaml.YAMLError):
            continue
        if metadata.get("schema") != "planning-toolbox-image-knowledge-card":
            continue
        if project_type and str(metadata.get("project_type")) != project_type:
            continue
        if review_status and str(metadata.get("review_status")) != review_status:
            continue
        searchable = " ".join(
            [
                str(metadata.get("title", "")),
                str(metadata.get("project_type", "")),
                " ".join(_normalize_tags(metadata.get("tags"))),
                str(metadata.get("source", {}).get("name", "")),
            ]
        ).casefold()
        if needle and needle not in searchable:
            continue
        found.append({"path": str(path), "metadata": metadata})
        if len(found) >= max(1, int(limit)):
            break
    return found


def update_image_knowledge_card_review(
    path: Path | str,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    """Update only the review state of a generated card."""
    if status not in REVIEW_STATUSES:
        raise ValueError(f"不支持的复核状态：{status}")
    card_path = Path(path).resolve()
    metadata, _ = _read_front_matter(card_path)
    metadata["review_status"] = status
    metadata["review_note"] = str(note).strip()
    metadata["updated_at_utc"] = _utc_now()
    recognition = metadata.setdefault("recognition", {})
    recognition["semantics_confirmed"] = status == "user_confirmed"
    card_text = _render_markdown(metadata)
    temporary = card_path.with_suffix(".md.tmp")
    temporary.write_text(card_text, encoding="utf-8", newline="\n")
    temporary.replace(card_path)
    return read_image_knowledge_card(card_path)
