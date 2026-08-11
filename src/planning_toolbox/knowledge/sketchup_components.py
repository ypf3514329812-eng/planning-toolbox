"""Validated catalogue for the lightweight SketchUp component library.

The catalogue supports audited CC0 SKP files and native procedural components
created by the bundled Ruby extension. Native components keep the resource
pack small while adding reusable planning objects.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
from importlib import resources
import json
from pathlib import PurePosixPath
from typing import Any, Mapping


COMPONENT_CATALOG_SCHEMA_VERSION = 1
_CATALOG_ASSET = "sketchup_component_catalog.json"
_REFERENCE_ASSET = "sketchup_reference_patterns.json"
_PLUGIN_PACKAGE = "planning_toolbox.sketchup"
_COMPONENT_ROOT = PurePosixPath(
    "plugin/planning_toolbox_sketchup/components"
)


def _component_resource(file_name: str):
    resource = resources.files(_PLUGIN_PACKAGE)
    for part in (*_COMPONENT_ROOT.parts, file_name):
        resource = resource.joinpath(part)
    return resource


def _validate_catalog(data: Mapping[str, Any]) -> None:
    if int(data.get("schema_version", 0)) != COMPONENT_CATALOG_SCHEMA_VERSION:
        raise ValueError("SketchUp 组件目录版本不受支持。")
    if not str(data.get("catalog_id", "")).strip() or not str(data.get("version", "")).strip():
        raise ValueError("SketchUp 组件目录缺少编号或版本。")
    policy = data.get("runtime_policy", {})
    if not isinstance(policy, Mapping):
        raise ValueError("SketchUp 组件目录缺少运行策略。")
    if policy.get("network_required") is not False or policy.get("api_required") is not False:
        raise ValueError("内置 SketchUp 组件不得依赖网络或 API。")
    if set(policy.get("allow_licenses", [])) != {"CC0-1.0"}:
        raise ValueError("内置组件当前只允许许可证明确的 CC0 资源。")

    sources = data.get("sources", [])
    if not isinstance(sources, list) or len(sources) < 3:
        raise ValueError("SketchUp 组件目录缺少可追溯来源。")
    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("SketchUp 组件来源格式无效。")
        source_id = str(source.get("id", "")).strip()
        if not source_id or source_id in source_ids:
            raise ValueError("SketchUp 组件来源编号为空或重复。")
        source_ids.add(source_id)
        if source.get("license") != "CC0-1.0":
            raise ValueError(f"组件来源 {source_id} 不是允许的 CC0 许可证。")
        if not str(source.get("url", "")).startswith("https://"):
            raise ValueError(f"组件来源 {source_id} 缺少安全来源链接。")

    components = data.get("components", [])
    if not isinstance(components, list) or not components:
        raise ValueError("SketchUp 组件目录没有可用组件。")
    asset_ids: set[str] = set()
    total_bytes = 0
    for item in components:
        if not isinstance(item, Mapping):
            raise ValueError("SketchUp 组件记录格式无效。")
        asset_id = str(item.get("asset_id", "")).strip()
        if not asset_id or asset_id in asset_ids:
            raise ValueError("SketchUp 组件编号为空或重复。")
        asset_ids.add(asset_id)
        if item.get("source_id") not in source_ids:
            raise ValueError(f"组件 {asset_id} 引用了未知来源。")
        generator = str(item.get("native_generator", "")).strip()
        file_name = str(item.get("skp_file", "")).strip()
        declared_size = int(item.get("skp_size_bytes", 0))
        if generator:
            if not file_name or not file_name.endswith(".skp") or declared_size <= 0:
                # Native generators still point at a small audited SKP snapshot
                # so older plugin versions can load a compatible fallback.
                raise ValueError(f"原生组件 {asset_id} 缺少兼容 SKP 快照。")
        else:
            pure_name = PurePosixPath(file_name)
            if pure_name.name != file_name or pure_name.suffix.lower() != ".skp":
                raise ValueError(f"组件 {asset_id} 的 SKP 文件名无效。")
        if declared_size <= 0 or declared_size > int(
            policy.get("component_file_budget_bytes", 8_000_000)
        ):
            raise ValueError(f"组件 {asset_id} 超出单文件资源预算。")
        resource = _component_resource(file_name)
        raw = resource.read_bytes()
        digest = hashlib.sha256(raw).hexdigest().upper()
        if len(raw) != declared_size or digest != str(item.get("skp_sha256", "")).upper():
            raise ValueError(f"组件 {asset_id} 文件大小或 SHA-256 与目录不一致。")
        bounds = item.get("target_bounds_m")
        if (
            not isinstance(bounds, list)
            or len(bounds) != 3
            or any(isinstance(value, bool) or float(value) <= 0 for value in bounds)
        ):
            raise ValueError(f"组件 {asset_id} 缺少有效目标尺寸。")
        total_bytes += declared_size

    if total_bytes != int(policy.get("bundled_component_total_bytes", -1)):
        raise ValueError("SketchUp 组件总大小与目录声明不一致。")
    if total_bytes > int(policy.get("bundled_component_budget_bytes", 0)):
        raise ValueError("SketchUp 内置组件超过轻量总预算。")


@lru_cache(maxsize=1)
def _load_cached() -> dict[str, Any]:
    asset = resources.files("planning_toolbox.knowledge").joinpath(_CATALOG_ASSET)
    data = json.loads(asset.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("SketchUp 组件目录必须是 JSON 对象。")
    _validate_catalog(data)
    return data


def load_sketchup_component_catalog() -> dict[str, Any]:
    return deepcopy(_load_cached())


def get_sketchup_component(asset_id: str) -> dict[str, Any]:
    normalized = str(asset_id or "").strip().lower()
    for item in _load_cached()["components"]:
        if item["asset_id"] == normalized:
            return deepcopy(item)
    raise ValueError(f"未知 SketchUp 组件：{normalized or '空值'}。")


def get_component_placement_rule(rule_name: str) -> dict[str, Any]:
    name = str(rule_name or "").strip()
    rules = _load_cached()["placement_rules"]
    if name not in rules:
        raise ValueError(f"未知 SketchUp 组件放置规则：{name or '空值'}。")
    return deepcopy(rules[name])


def sketchup_component_catalog_summary() -> dict[str, Any]:
    data = _load_cached()
    references = _load_reference_patterns_cached()
    automatic = sum(bool(item.get("automatic_use")) for item in data["components"])
    return {
        "id": data["catalog_id"],
        "version": data["version"],
        "schema_version": data["schema_version"],
        "component_count": len(data["components"]),
        "automatic_component_count": automatic,
        "source_count": len(data["sources"]),
        "license": "CC0-1.0 + PT-NATIVE-1.0",
        "total_bytes": data["runtime_policy"]["bundled_component_total_bytes"],
        "budget_bytes": data["runtime_policy"]["bundled_component_budget_bytes"],
        "load_mode": data["runtime_policy"]["load_mode"],
        "network_required": False,
        "api_required": False,
        "fallback": data["runtime_policy"]["fallback"],
        "native_component_count": sum(
            bool(item.get("native_generator")) for item in data["components"]
        ),
        "resource_budget_bytes": data["runtime_policy"].get(
            "bundled_component_budget_bytes", 0
        ),
        "reference_index_version": references["version"],
        "reference_pattern_count": len(references["patterns"]),
    }


@lru_cache(maxsize=1)
def _load_reference_patterns_cached() -> dict[str, Any]:
    asset = resources.files("planning_toolbox.knowledge").joinpath(_REFERENCE_ASSET)
    data = json.loads(asset.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or int(data.get("schema_version", 0)) != 1:
        raise ValueError("SketchUp 参考模式索引版本不受当前 Planning Toolbox 支持。")
    patterns = data.get("patterns", [])
    if not isinstance(patterns, list) or not patterns:
        raise ValueError("SketchUp 参考模式索引为空。")
    ids: set[str] = set()
    for item in patterns:
        if not isinstance(item, Mapping):
            raise ValueError("SketchUp 参考模式记录格式无效。")
        pattern_id = str(item.get("id", "")).strip()
        if not pattern_id or pattern_id in ids:
            raise ValueError("SketchUp 参考模式编号为空或重复。")
        ids.add(pattern_id)
        if not str(item.get("title", "")).strip() or not str(item.get("visual_type", "")).strip():
            raise ValueError(f"参考模式 {pattern_id} 缺少标题或视觉类型。")
        if not isinstance(item.get("tags"), list) or not item["tags"]:
            raise ValueError(f"参考模式 {pattern_id} 缺少标签。")
        if not str(item.get("geometry_recipe", "")).strip():
            raise ValueError(f"参考模式 {pattern_id} 缺少几何生成要点。")
        if not str(item.get("source_page", "")).startswith("https://"):
            raise ValueError(f"参考模式 {pattern_id} 缺少可追溯来源页面。")
    return data


def load_sketchup_reference_patterns() -> dict[str, Any]:
    return deepcopy(_load_reference_patterns_cached())


def get_sketchup_reference_pattern(pattern_id: str) -> dict[str, Any]:
    normalized = str(pattern_id or "").strip().lower()
    for item in _load_reference_patterns_cached()["patterns"]:
        if str(item["id"]).lower() == normalized:
            return deepcopy(item)
    raise ValueError(f"未知 SketchUp 参考模式：{normalized or '空值'}。")


__all__ = [
    "COMPONENT_CATALOG_SCHEMA_VERSION",
    "get_sketchup_reference_pattern",
    "get_component_placement_rule",
    "get_sketchup_component",
    "load_sketchup_component_catalog",
    "load_sketchup_reference_patterns",
    "sketchup_component_catalog_summary",
]
