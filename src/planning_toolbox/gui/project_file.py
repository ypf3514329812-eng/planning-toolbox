"""Save and load local Planning Toolbox coursework projects."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict
from uuid import UUID, uuid5

from planning_toolbox.project.chain_manifest import ChainManifest, new_chain_manifest


PROJECT_FORMAT = "planning-toolbox-project"
PROJECT_VERSION = 2
SUPPORTED_PROJECT_VERSIONS = {1, PROJECT_VERSION}
_LEGACY_PROJECT_NAMESPACE = UUID("9ff26669-e665-42a7-bf92-17402fa408b4")


def _legacy_manifest(project_path: Path) -> ChainManifest:
    """Create a stable full-chain identity when opening a version-1 project."""
    legacy_id = str(uuid5(_LEGACY_PROJECT_NAMESPACE, str(project_path).casefold()))
    return new_chain_manifest(name=project_path.stem, project_id=legacy_id)


def save_project(path: Path | str, state: Dict[str, Any]) -> Path:
    """Write a human-readable UTF-8 project file without copying source data."""
    project_path = Path(path).resolve()
    project_path.parent.mkdir(parents=True, exist_ok=True)
    saved_state = dict(state)
    manifest_value = saved_state.pop("chain_manifest", None)
    if isinstance(manifest_value, ChainManifest):
        manifest = manifest_value
    elif isinstance(manifest_value, dict):
        manifest = ChainManifest.from_dict(manifest_value)
    elif manifest_value is None:
        manifest = new_chain_manifest(name=project_path.stem)
    else:
        raise ValueError("全链路项目清单格式无效，无法保存项目。")
    payload = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "chain_manifest": manifest.to_dict(),
        "state": saved_state,
    }
    project_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return project_path


def load_project(path: Path | str) -> Dict[str, Any]:
    """Load and validate a local project file."""
    project_path = Path(path).resolve()
    if not project_path.exists():
        raise FileNotFoundError(f"项目文件不存在：{project_path}")
    try:
        payload = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("项目文件无法读取或格式损坏，请选择 .ptx 项目文件。") from exc
    if payload.get("format") != PROJECT_FORMAT:
        raise ValueError("这不是 Planning Toolbox 项目文件。")
    version = payload.get("version")
    if version not in SUPPORTED_PROJECT_VERSIONS:
        raise ValueError(f"项目文件版本 {payload.get('version')} 暂不支持。")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("项目文件缺少有效的工作区内容。")
    loaded_state = dict(state)
    if version == 1:
        manifest = _legacy_manifest(project_path)
    else:
        manifest_value = payload.get("chain_manifest")
        if not isinstance(manifest_value, dict):
            raise ValueError("项目文件缺少有效的全链路项目清单。")
        manifest = ChainManifest.from_dict(manifest_value)
    loaded_state["chain_manifest"] = manifest.to_dict()
    return loaded_state
