"""Lightweight semantic sidecar shared by image, CAD, GIS and SketchUp stages.

The sidecar intentionally stores no full geometry.  DXF/GeoPackage/SKP remain
the geometry authorities; this file only preserves role mappings, confidence,
review state and source lineage so downstream tools do not have to guess a
layer's meaning again.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import ezdxf

from planning_toolbox.project.chain_manifest import make_stable_object_id
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


SEMANTIC_SCENE_FORMAT = "planning-toolbox-semantic-scene"
SEMANTIC_SCENE_SCHEMA_VERSION = 1
PRESENTATION_FILL_APPID = "PT_PRESENTATION_FILL"
VALID_SEMANTIC_ROLES = {
    "building",
    "parcel",
    "green",
    "road",
    "water",
    "parking",
    "underlay",
    "other",
}


_EXACT_IMAGE_LAYER_RULES: dict[str, dict[str, Any]] = {
    "AI_BUILDING": {
        "role": "building",
        "confidence": 0.90,
        "basis": "standard_color_region",
    },
    "AI_ROAD": {
        "role": "road",
        "confidence": 0.88,
        "basis": "standard_color_region",
    },
    "AI_GREEN": {
        "role": "green",
        "confidence": 0.88,
        "basis": "standard_color_region",
    },
    "AI_WATER": {
        "role": "water",
        "confidence": 0.88,
        "basis": "standard_color_region",
    },
    "AI_PARKING": {
        "role": "parking",
        "confidence": 0.82,
        "basis": "standard_color_region",
    },
    "BW_BUILDING_CANDIDATE": {
        "role": "building",
        "confidence": 0.72,
        "basis": "black_white_geometry_candidate",
    },
    "BW_ROAD_CANDIDATE": {
        "role": "road",
        "confidence": 0.62,
        "basis": "paired_line_corridor_candidate",
    },
    "BW_TREE_CANDIDATE": {
        "role": "green",
        "confidence": 0.76,
        "basis": "repeated_tree_symbol_candidate",
    },
    "BW_PARKING_CANDIDATE": {
        "role": "parking",
        "confidence": 0.70,
        "basis": "repeated_parking_symbol_candidate",
    },
    "BW_LANDSCAPE_CANDIDATE": {
        "role": "green",
        "confidence": 0.64,
        "basis": "landscape_ellipse_candidate",
    },
    "BW_LINEWORK": {
        "role": "underlay",
        "confidence": 0.0,
        "basis": "reference_linework_only",
    },
    "BW_CLOSED": {
        "role": "underlay",
        "confidence": 0.0,
        "basis": "reference_linework_only",
    },
    "BW_DETAIL": {
        "role": "underlay",
        "confidence": 0.0,
        "basis": "reference_linework_only",
    },
    "BW_FRAME": {
        "role": "underlay",
        "confidence": 0.0,
        "basis": "reference_frame_only",
    },
    "AI_FRAME": {
        "role": "underlay",
        "confidence": 0.0,
        "basis": "reference_frame_only",
    },
    "AI_LABEL": {
        "role": "underlay",
        "confidence": 0.0,
        "basis": "reference_annotation_only",
    },
}


_CANONICAL_LAYER_TOKENS: tuple[tuple[str, str], ...] = (
    ("BUILDING", "building"),
    ("PARCEL", "parcel"),
    ("BOUNDARY", "parcel"),
    ("REDLINE", "parcel"),
    ("ROAD", "road"),
    ("GREEN", "green"),
    ("LANDSCAPE", "green"),
    ("TREE", "green"),
    ("WATER", "water"),
    ("PARKING", "parking"),
)


def is_presentation_fill_entity(entity: Any) -> bool:
    """Return whether a DXF entity is a removable display-only semantic fill."""
    if entity.dxftype() != "HATCH":
        return False
    try:
        return bool(entity.has_xdata(PRESENTATION_FILL_APPID))
    except (AttributeError, ezdxf.DXFError):
        return False


def semantic_scene_path_for_dxf(dxf_path: Path | str) -> Path:
    """Return the deterministic sidecar path adjacent to a DXF."""
    return Path(dxf_path).resolve().with_suffix(".ptscene.json")


def _layer_rule(layer_name: str) -> dict[str, Any]:
    normalized = str(layer_name or "0").strip().upper()
    exact = _EXACT_IMAGE_LAYER_RULES.get(normalized)
    if exact is not None:
        return {**exact, "review_required": True}
    for token, role in _CANONICAL_LAYER_TOKENS:
        if token in normalized:
            return {
                "role": role,
                "confidence": 0.96,
                "basis": "canonical_cad_layer",
                "review_required": False,
            }
    return {
        "role": "other",
        "confidence": 0.0,
        "basis": "unclassified_layer",
        "review_required": True,
    }


def _validated_scene_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(value)
    if payload.get("format") != SEMANTIC_SCENE_FORMAT:
        raise ValueError("该文件不是 Planning Toolbox 全链路语义场景文件。")
    if int(payload.get("schema_version", 0)) != SEMANTIC_SCENE_SCHEMA_VERSION:
        raise ValueError("当前版本暂不支持该语义场景文件版本。")
    rules = payload.get("layer_rules")
    if not isinstance(rules, Mapping):
        raise ValueError("语义场景缺少有效的图层规则。")
    for layer, rule in rules.items():
        if not str(layer).strip() or not isinstance(rule, Mapping):
            raise ValueError("语义场景图层规则格式无效。")
        if str(rule.get("role", "")) not in VALID_SEMANTIC_ROLES:
            raise ValueError(f"语义场景包含未知对象类型：{rule.get('role')}。")
    return payload


def build_semantic_scene_from_dxf(
    dxf_path: Path | str,
    output_path: Path | str | None = None,
    *,
    source_image_path: Path | str | None = None,
    source_image_sha256: str = "",
    semantic_guide_path: Path | str | None = None,
    semantic_guide_sha256: str = "",
    reference_width_m: float | None = None,
    conversion_mode: str = "",
    parent_scene_path: Path | str | None = None,
    parent_dxf_sha256: str = "",
) -> dict[str, Any]:
    """Create a compact semantic sidecar from a generated or standardized DXF."""
    source = Path(dxf_path).resolve()
    if not source.is_file() or source.suffix.lower() != ".dxf":
        raise FileNotFoundError(f"找不到有效的 DXF 文件：{source}")
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else semantic_scene_path_for_dxf(source)
    )
    if destination == source:
        raise ValueError("语义场景文件不能覆盖原始 DXF。")
    if not destination.name.lower().endswith(".ptscene.json"):
        raise ValueError("语义场景文件必须使用 .ptscene.json 扩展名。")

    dxf_hash = sha256_file(source)
    doc = ezdxf.readfile(source)
    layer_counts: Counter[str] = Counter()
    entity_type_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    presentation_fill_counts: Counter[str] = Counter()
    registry: list[dict[str, Any]] = []
    scene_namespace = source_image_sha256.strip() or dxf_hash

    for index, entity in enumerate(doc.modelspace()):
        layer = str(entity.dxf.get("layer", "0") or "0").strip()
        normalized_layer = layer.upper()
        entity_type_counts[entity.dxftype()] += 1
        if is_presentation_fill_entity(entity):
            presentation_fill_counts[normalized_layer] += 1
            continue
        handle = str(entity.dxf.get("handle", "") or f"INDEX-{index}")
        rule = _layer_rule(normalized_layer)
        role = str(rule["role"])
        layer_counts[normalized_layer] += 1
        role_counts[role] += 1
        if role in {"underlay", "other"}:
            continue
        registry.append(
            {
                "id": make_stable_object_id(
                    scene_namespace,
                    role,
                    f"{normalized_layer}:{handle}",
                ),
                "source_handle": handle,
                "source_type": entity.dxftype(),
                "source_layer": layer,
                "role": role,
                "confidence": float(rule["confidence"]),
                "review_status": "pending" if rule["review_required"] else "layer_confirmed",
            }
        )

    present_layers = sorted(set(layer_counts) | set(presentation_fill_counts))
    layer_rules = {
        layer: {
            **_layer_rule(layer),
            "entity_count": int(layer_counts[layer]),
            "presentation_fill_count": int(presentation_fill_counts[layer]),
        }
        for layer in present_layers
    }
    underlay_layers = sorted(
        layer for layer, rule in layer_rules.items() if rule["role"] == "underlay"
    )
    review_required_count = sum(
        count
        for layer, count in layer_counts.items()
        if bool(layer_rules[layer]["review_required"])
        and layer_rules[layer]["role"] not in {"underlay", "other"}
    )
    image_path = Path(source_image_path).resolve() if source_image_path else None
    guide_path = Path(semantic_guide_path).resolve() if semantic_guide_path else None
    if guide_path:
        if not guide_path.is_file():
            raise FileNotFoundError(f"找不到语义引导图：{guide_path}")
        expected_guide_hash = semantic_guide_sha256.strip().lower()
        actual_guide_hash = sha256_file(guide_path).lower()
        if not expected_guide_hash or expected_guide_hash != actual_guide_hash:
            raise ValueError("语义引导图指纹不匹配，请重新执行图片转 CAD。")
    payload = {
        "format": SEMANTIC_SCENE_FORMAT,
        "schema_version": SEMANTIC_SCENE_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "Planning Toolbox",
        "source": {
            "dxf_path": str(source),
            "dxf_sha256": dxf_hash,
            "source_image_path": str(image_path) if image_path else "",
            "source_image_sha256": source_image_sha256.strip(),
            "semantic_guide_path": str(guide_path) if guide_path else "",
            "semantic_guide_sha256": semantic_guide_sha256.strip(),
            "conversion_mode": str(conversion_mode).strip(),
            "reference_width_m": (
                float(reference_width_m) if reference_width_m is not None else None
            ),
        },
        "coordinate_contract": {
            "unit": "m",
            "scale_source": "user_reference_width" if reference_width_m else "dxf_units",
            "crs_status": "local_image_calibration" if image_path else "inherited_from_project",
            "measurement_requires_review": bool(image_path),
        },
        "lineage": {
            "parent_scene_path": (
                str(Path(parent_scene_path).resolve()) if parent_scene_path else ""
            ),
            "parent_dxf_sha256": str(parent_dxf_sha256).strip(),
        },
        "layer_rules": layer_rules,
        "underlay_layers": underlay_layers,
        "object_registry": registry,
        "summary": {
            "source_entity_count": int(
                sum(layer_counts.values()) + sum(presentation_fill_counts.values())
            ),
            "semantic_object_count": len(registry),
            "presentation_fill_count": int(sum(presentation_fill_counts.values())),
            "underlay_entity_count": int(role_counts["underlay"]),
            "unclassified_entity_count": int(role_counts["other"]),
            "review_required_count": int(review_required_count),
            "role_counts": dict(sorted(role_counts.items())),
            "entity_type_counts": dict(sorted(entity_type_counts.items())),
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert_file_unchanged(source, dxf_hash)
    return {
        "path": str(destination),
        "sha256": sha256_file(destination),
        "summary": payload["summary"],
        "layer_rules": layer_rules,
        "underlay_layers": underlay_layers,
    }


def propagate_semantic_scene_to_derived_dxf(
    source_dxf: Path | str,
    derived_dxf: Path | str,
) -> dict[str, Any] | None:
    """Rebuild a source-validated sidecar for a repaired/standardized DXF copy."""
    parent = load_semantic_scene_for_dxf(source_dxf)
    if parent is None:
        return None
    source_meta = dict(parent.get("source", {}))
    return build_semantic_scene_from_dxf(
        derived_dxf,
        source_image_path=source_meta.get("source_image_path") or None,
        source_image_sha256=str(source_meta.get("source_image_sha256", "")),
        semantic_guide_path=source_meta.get("semantic_guide_path") or None,
        semantic_guide_sha256=str(source_meta.get("semantic_guide_sha256", "")),
        reference_width_m=source_meta.get("reference_width_m"),
        conversion_mode=str(source_meta.get("conversion_mode", "")),
        parent_scene_path=parent["file_path"],
        parent_dxf_sha256=str(source_meta.get("dxf_sha256", "")),
    )


def load_semantic_scene_for_dxf(dxf_path: Path | str) -> dict[str, Any] | None:
    """Load and source-validate an adjacent semantic sidecar, when present."""
    source = Path(dxf_path).resolve()
    sidecar = semantic_scene_path_for_dxf(source)
    if not sidecar.is_file():
        return None
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取全链路语义场景文件，请重新生成图片转 CAD 结果。") from exc
    payload = _validated_scene_payload(value)
    expected_hash = str(payload.get("source", {}).get("dxf_sha256", "")).strip()
    actual_hash = sha256_file(source)
    if not expected_hash or expected_hash.lower() != actual_hash.lower():
        raise ValueError(
            "语义场景与当前 DXF 不匹配，已阻止使用过期图层含义。请重新生成语义交接文件。"
        )
    payload["file_path"] = str(sidecar)
    payload["file_sha256"] = sha256_file(sidecar)
    return payload


__all__ = [
    "SEMANTIC_SCENE_FORMAT",
    "SEMANTIC_SCENE_SCHEMA_VERSION",
    "PRESENTATION_FILL_APPID",
    "VALID_SEMANTIC_ROLES",
    "build_semantic_scene_from_dxf",
    "load_semantic_scene_for_dxf",
    "is_presentation_fill_entity",
    "propagate_semantic_scene_to_derived_dxf",
    "semantic_scene_path_for_dxf",
]
