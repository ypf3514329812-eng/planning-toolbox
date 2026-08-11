"""Small, dependency-free manifest for the GIS-CAD-SU project chain.

The manifest deliberately stores metadata only.  Heavy geometry remains in
GeoPackage/DXF/SketchUp files, while this module keeps their shared coordinate
contract, local modelling origin and stable Planning Toolbox object IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import re
from typing import Any, Dict, Iterable, Mapping, Optional
from uuid import UUID, uuid4, uuid5


CHAIN_SCHEMA_VERSION = 1
_FALLBACK_NAMESPACE = UUID("fb7bd393-1d55-4bc9-84c2-d3a612df6c5f")
_VALID_CRS_KINDS = {"unknown", "projected", "geographic", "local"}
_VALID_CAD_UNITS = {"m", "cm", "mm", "ft", "in"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


@dataclass(frozen=True)
class CRSDefinition:
    """Project-wide coordinate reference system contract.

    ``kind`` is explicit because this lightweight core intentionally does not
    bundle a full EPSG database.  Actual reprojection is delegated to the
    optional GIS adapter in the next phase.
    """

    authority: str = "EPSG"
    code: Optional[int] = None
    name: str = ""
    kind: str = "unknown"
    linear_unit: str = "m"

    def __post_init__(self) -> None:
        if self.kind not in _VALID_CRS_KINDS:
            raise ValueError(f"不支持的坐标系类型：{self.kind}")
        if self.code is not None and int(self.code) <= 0:
            raise ValueError("EPSG 编号必须是正整数。")
        if self.linear_unit not in _VALID_CAD_UNITS:
            raise ValueError(f"不支持的坐标单位：{self.linear_unit}")

    @property
    def identifier(self) -> str:
        if self.code is not None:
            return f"{self.authority.upper()}:{self.code}"
        if self.kind == "local":
            return "LOCAL"
        return "未设置"

    @property
    def metric_ready(self) -> bool:
        """Whether this CRS is suitable for deterministic area/distance work."""
        return (
            self.kind in {"projected", "local"}
            and self.linear_unit == "m"
            and self.code != 3857
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "authority": self.authority,
            "code": self.code,
            "name": self.name,
            "kind": self.kind,
            "linear_unit": self.linear_unit,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "CRSDefinition":
        data = dict(value or {})
        code = data.get("code")
        return cls(
            authority=_clean_text(data.get("authority"), "EPSG").upper(),
            code=int(code) if code not in (None, "") else None,
            name=_clean_text(data.get("name")),
            kind=_clean_text(data.get("kind"), "unknown"),
            linear_unit=_clean_text(data.get("linear_unit"), "m"),
        )


@dataclass(frozen=True)
class LocalOrigin:
    """Reversible projected-coordinate to local-model transformation.

    ``rotation_deg`` is the counter-clockwise rotation of the local X axis
    relative to the project X axis.  Keeping SketchUp geometry close to this
    origin avoids large-coordinate precision and navigation problems.
    """

    enabled: bool = False
    easting: float = 0.0
    northing: float = 0.0
    elevation: float = 0.0
    rotation_deg: float = 0.0

    def __post_init__(self) -> None:
        values = (self.easting, self.northing, self.elevation, self.rotation_deg)
        if not all(math.isfinite(float(item)) for item in values):
            raise ValueError("本地建模原点必须填写有限数值。")

    def to_local(self, x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
        """Convert project coordinates to local model coordinates."""
        dx = float(x) - self.easting
        dy = float(y) - self.northing
        dz = float(z) - self.elevation
        angle = math.radians(self.rotation_deg)
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return (
            dx * cosine + dy * sine,
            -dx * sine + dy * cosine,
            dz,
        )

    def to_project(self, x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
        """Convert local model coordinates back to project coordinates."""
        angle = math.radians(self.rotation_deg)
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return (
            float(x) * cosine - float(y) * sine + self.easting,
            float(x) * sine + float(y) * cosine + self.northing,
            float(z) + self.elevation,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "easting": self.easting,
            "northing": self.northing,
            "elevation": self.elevation,
            "rotation_deg": self.rotation_deg,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "LocalOrigin":
        data = dict(value or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            easting=float(data.get("easting", 0.0)),
            northing=float(data.get("northing", 0.0)),
            elevation=float(data.get("elevation", 0.0)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
        )


@dataclass(frozen=True)
class ChainAsset:
    """Reference to one external source or result without embedding it."""

    asset_id: str
    stage: str
    role: str
    path: str
    file_format: str = ""
    sha256: str = ""
    crs_identifier: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "asset_id": self.asset_id,
            "stage": self.stage,
            "role": self.role,
            "path": self.path,
            "file_format": self.file_format,
            "sha256": self.sha256,
            "crs_identifier": self.crs_identifier,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChainAsset":
        data = dict(value)
        return cls(
            asset_id=_clean_text(data.get("asset_id")),
            stage=_clean_text(data.get("stage")),
            role=_clean_text(data.get("role")),
            path=_clean_text(data.get("path")),
            file_format=_clean_text(data.get("file_format")),
            sha256=_clean_text(data.get("sha256")),
            crs_identifier=_clean_text(data.get("crs_identifier")),
        )


@dataclass(frozen=True)
class ChainManifest:
    """Serializable source of truth for one Planning Toolbox project."""

    project_id: str
    name: str = "未命名项目"
    project_type: str = "coursework"
    schema_version: int = CHAIN_SCHEMA_VERSION
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    crs: CRSDefinition = field(default_factory=CRSDefinition)
    cad_unit: str = "m"
    local_origin: LocalOrigin = field(default_factory=LocalOrigin)
    workflow_stage: str = "project_setup"
    assets: tuple[ChainAsset, ...] = ()
    object_registry: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            UUID(self.project_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("项目 ID 不是有效 UUID。") from exc
        if self.schema_version != CHAIN_SCHEMA_VERSION:
            raise ValueError(f"暂不支持全链路清单版本 {self.schema_version}。")
        if self.cad_unit not in _VALID_CAD_UNITS:
            raise ValueError(f"不支持的 CAD 单位：{self.cad_unit}")

    @property
    def configured(self) -> bool:
        return self.name != "未命名项目" or self.crs.kind != "unknown"

    def with_updates(self, **changes: Any) -> "ChainManifest":
        payload = self.to_dict()
        payload.update(changes)
        payload["updated_at"] = _now_iso()
        return ChainManifest.from_dict(payload)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "name": self.name,
            "project_type": self.project_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "crs": self.crs.to_dict(),
            "cad_unit": self.cad_unit,
            "local_origin": self.local_origin.to_dict(),
            "workflow_stage": self.workflow_stage,
            "assets": [asset.to_dict() for asset in self.assets],
            "object_registry": {key: dict(value) for key, value in self.object_registry.items()},
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChainManifest":
        data = dict(value)
        registry = data.get("object_registry", {})
        if not isinstance(registry, Mapping):
            raise ValueError("全链路对象登记表格式无效。")
        assets = data.get("assets", [])
        if not isinstance(assets, Iterable) or isinstance(assets, (str, bytes, Mapping)):
            raise ValueError("全链路文件登记表格式无效。")
        return cls(
            schema_version=int(data.get("schema_version", CHAIN_SCHEMA_VERSION)),
            project_id=_clean_text(data.get("project_id")),
            name=_clean_text(data.get("name"), "未命名项目"),
            project_type=_clean_text(data.get("project_type"), "coursework"),
            created_at=_clean_text(data.get("created_at"), _now_iso()),
            updated_at=_clean_text(data.get("updated_at"), _now_iso()),
            crs=CRSDefinition.from_dict(data.get("crs")),
            cad_unit=_clean_text(data.get("cad_unit"), "m"),
            local_origin=LocalOrigin.from_dict(data.get("local_origin")),
            workflow_stage=_clean_text(data.get("workflow_stage"), "project_setup"),
            assets=tuple(ChainAsset.from_dict(item) for item in assets),
            object_registry={str(key): dict(item) for key, item in registry.items()},
        )


def new_chain_manifest(
    name: str = "未命名项目",
    project_type: str = "coursework",
    *,
    project_id: str | None = None,
) -> ChainManifest:
    """Create a new lightweight project manifest."""
    return ChainManifest(
        project_id=project_id or str(uuid4()),
        name=_clean_text(name, "未命名项目"),
        project_type=_clean_text(project_type, "coursework"),
    )


def make_stable_object_id(project_id: str, object_kind: str, source_key: str) -> str:
    """Create a deterministic ID that can travel through GIS, CAD and SU.

    The source key should be an existing GIS feature ID, a preserved DXF
    entity key, or another stable identifier.  Display IDs are intentionally
    short while the full UUID can always be recomputed.
    """
    try:
        namespace = UUID(str(project_id))
    except (ValueError, TypeError, AttributeError):
        namespace = uuid5(_FALLBACK_NAMESPACE, str(project_id))
    kind = re.sub(r"[^A-Z0-9]+", "", str(object_kind).upper())[:8] or "OBJECT"
    key = _clean_text(source_key)
    if not key:
        raise ValueError("生成稳定对象编号时必须提供来源编号。")
    digest = uuid5(namespace, f"{kind}:{key}").hex[:16].upper()
    return f"PT-{kind}-{digest}"
