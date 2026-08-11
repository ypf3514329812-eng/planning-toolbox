"""Lightweight project metadata shared by GIS, CAD and SketchUp workflows."""

from planning_toolbox.project.chain_manifest import (
    CHAIN_SCHEMA_VERSION,
    CRSDefinition,
    ChainAsset,
    ChainManifest,
    LocalOrigin,
    make_stable_object_id,
    new_chain_manifest,
)

_SEMANTIC_EXPORTS = {
    "SEMANTIC_SCENE_FORMAT",
    "SEMANTIC_SCENE_SCHEMA_VERSION",
    "build_semantic_scene_from_dxf",
    "load_semantic_scene_for_dxf",
    "propagate_semantic_scene_to_derived_dxf",
    "semantic_scene_path_for_dxf",
}


def __getattr__(name: str):
    """Load CAD-backed semantic helpers only when a caller requests them."""
    if name not in _SEMANTIC_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    semantic_scene = import_module("planning_toolbox.project.semantic_scene")
    return getattr(semantic_scene, name)

__all__ = [
    "CHAIN_SCHEMA_VERSION",
    "CRSDefinition",
    "ChainAsset",
    "ChainManifest",
    "LocalOrigin",
    "make_stable_object_id",
    "new_chain_manifest",
    "SEMANTIC_SCENE_FORMAT",
    "SEMANTIC_SCENE_SCHEMA_VERSION",
    "build_semantic_scene_from_dxf",
    "load_semantic_scene_for_dxf",
    "propagate_semantic_scene_to_derived_dxf",
    "semantic_scene_path_for_dxf",
]
