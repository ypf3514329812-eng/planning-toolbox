"""Optional, read-only bridge between lightweight GeoJSON and GDAL formats.

Planning Toolbox never embeds QGIS/GDAL in its base desktop package.  If the
user already has QGIS, OSGeo4W or ``ogr2ogr`` installed, this module invokes
that local executable in a subprocess.  Source files are checksummed before
and after every conversion and are never used as output targets.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterable, Sequence

from planning_toolbox.gis.crs import normalize_crs_identifier
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


_VECTOR_INPUT_SUFFIXES = {".gpkg", ".shp", ".geojson", ".json"}


class GISAdapterUnavailableError(RuntimeError):
    """Raised when no local GDAL/QGIS conversion executable is available."""


class GISConversionError(RuntimeError):
    """Raised when the external vector conversion does not complete safely."""


@dataclass(frozen=True)
class OGRConversionResult:
    output_path: Path
    source_sha256: str
    adapter_path: Path
    command: tuple[str, ...]


def _candidate_installations() -> Iterable[Path]:
    """Yield only explicit or conventional system locations (never user scans)."""

    for env_name in ("QGIS_PREFIX_PATH", "OSGEO4W_ROOT"):
        value = os.environ.get(env_name)
        if value:
            root = Path(value)
            yield root / "bin" / "ogr2ogr.exe"
            yield root / "ogr2ogr.exe"

    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(env_name)
        if not value:
            continue
        root = Path(value)
        yield root / "OSGeo4W" / "bin" / "ogr2ogr.exe"
        for qgis_dir in sorted(root.glob("QGIS*"), reverse=True):
            if qgis_dir.is_dir():
                yield qgis_dir / "bin" / "ogr2ogr.exe"


def find_ogr2ogr(explicit_path: Path | str | None = None) -> Path | None:
    """Find a local ogr2ogr executable without loading GIS libraries."""

    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if candidate.is_dir():
            candidate = candidate / ("ogr2ogr.exe" if os.name == "nt" else "ogr2ogr")
        if candidate.is_file():
            return candidate.resolve()
        return None

    on_path = shutil.which("ogr2ogr") or shutil.which("ogr2ogr.exe")
    if on_path:
        return Path(on_path).resolve()
    for candidate in _candidate_installations():
        if candidate.is_file():
            return candidate.resolve()
    return None


def require_ogr2ogr(explicit_path: Path | str | None = None) -> Path:
    executable = find_ogr2ogr(explicit_path)
    if executable is None:
        raise GISAdapterUnavailableError(
            "未检测到本机 QGIS/GDAL 转换组件。现有 GeoJSON↔DXF 仍可使用；如需 GPKG/SHP，"
            "请安装 QGIS（会自带 ogr2ogr），然后重新打开 Planning Toolbox。"
        )
    return executable


def _validate_source(path: Path | str, suffixes: set[str]) -> Path:
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"GIS 源文件不存在：{source}")
    if source.suffix.lower() not in suffixes:
        supported = "、".join(sorted(suffixes))
        raise GISConversionError(f"不支持的 GIS 文件类型；当前支持：{supported}")
    return source


def _validate_output(path: Path | str, suffix: str, source: Path) -> Path:
    output = Path(path).resolve()
    if output.suffix.lower() != suffix:
        raise GISConversionError(f"输出文件必须使用 {suffix} 扩展名。")
    if output == source:
        raise GISConversionError("输入文件与输出文件不能相同；系统禁止覆盖原始 GIS 数据。")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _safe_layer_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", str(value).strip()).strip("_")
    return name[:63] or "planning_features"


def build_vector_to_geojson_command(
    executable: Path | str,
    source: Path | str,
    output: Path | str,
    *,
    target_crs: str,
    source_crs: str | None = None,
    layer_name: str | None = None,
) -> list[str]:
    command = [
        str(executable),
        "-f",
        "GeoJSON",
        "-overwrite",
        "-lco",
        "RFC7946=NO",
    ]
    if source_crs:
        command.extend(["-s_srs", normalize_crs_identifier(source_crs)])
    command.extend(["-t_srs", normalize_crs_identifier(target_crs)])
    command.extend([str(output), str(source)])
    if layer_name:
        command.append(str(layer_name))
    return command


def build_geojson_to_gpkg_command(
    executable: Path | str,
    source: Path | str,
    output: Path | str,
    *,
    source_crs: str,
    layer_name: str,
) -> list[str]:
    return [
        str(executable),
        "-f",
        "GPKG",
        "-overwrite",
        "-a_srs",
        normalize_crs_identifier(source_crs),
        "-nln",
        _safe_layer_name(layer_name),
        "-lco",
        "SPATIAL_INDEX=YES",
        str(output),
        str(source),
    ]


def _run_command(command: Sequence[str], timeout_seconds: int = 300) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            list(command),
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise GISConversionError("GIS 格式转换超过 5 分钟，已安全停止。") from exc
    except OSError as exc:
        raise GISConversionError(f"无法启动本机 GIS 转换组件：{exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "未知错误").strip()
        raise GISConversionError(f"GIS 格式转换失败：{detail}")


def _annotate_geojson(path: Path, crs_identifier: str) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GISConversionError("转换结果不是有效的 GeoJSON 文件。") from exc
    if not isinstance(data, dict):
        raise GISConversionError("转换结果缺少有效的 GeoJSON 根对象。")
    metadata = data.setdefault("planning_toolbox_metadata", {})
    if isinstance(metadata, dict):
        metadata.update(
            {
                "coordinate_reference_system": crs_identifier,
                "coordinate_units": "m",
                "coordinate_transform_applied": True,
            }
        )
    data["crs"] = {
        "type": "name",
        "properties": {"name": crs_identifier},
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def convert_vector_to_geojson(
    source_path: Path | str,
    output_geojson: Path | str,
    *,
    target_crs: str,
    source_crs: str | None = None,
    layer_name: str | None = None,
    ogr2ogr_path: Path | str | None = None,
) -> OGRConversionResult:
    """Read a GIS dataset and write a projected temporary GeoJSON copy."""

    source = _validate_source(source_path, _VECTOR_INPUT_SUFFIXES)
    output = _validate_output(output_geojson, ".geojson", source)
    executable = require_ogr2ogr(ogr2ogr_path)
    source_sha256 = sha256_file(source)
    command = build_vector_to_geojson_command(
        executable,
        source,
        output,
        target_crs=target_crs,
        source_crs=source_crs,
        layer_name=layer_name,
    )
    _run_command(command)
    if not output.is_file():
        raise GISConversionError("GIS 转换组件未生成预期的 GeoJSON 文件。")
    _annotate_geojson(output, normalize_crs_identifier(target_crs))
    assert_file_unchanged(source, source_sha256)
    return OGRConversionResult(output, source_sha256, executable, tuple(command))


def convert_geojson_to_gpkg(
    source_geojson: Path | str,
    output_gpkg: Path | str,
    *,
    source_crs: str,
    layer_name: str = "planning_parcels",
    ogr2ogr_path: Path | str | None = None,
) -> OGRConversionResult:
    """Write a GeoPackage copy while preserving the source GeoJSON."""

    source = _validate_source(source_geojson, {".geojson", ".json"})
    output = _validate_output(output_gpkg, ".gpkg", source)
    executable = require_ogr2ogr(ogr2ogr_path)
    source_sha256 = sha256_file(source)
    command = build_geojson_to_gpkg_command(
        executable,
        source,
        output,
        source_crs=source_crs,
        layer_name=layer_name,
    )
    _run_command(command)
    if not output.is_file():
        raise GISConversionError("GIS 转换组件未生成预期的 GeoPackage 文件。")
    assert_file_unchanged(source, source_sha256)
    return OGRConversionResult(output, source_sha256, executable, tuple(command))


__all__ = [
    "GISAdapterUnavailableError",
    "GISConversionError",
    "OGRConversionResult",
    "build_geojson_to_gpkg_command",
    "build_vector_to_geojson_command",
    "convert_geojson_to_gpkg",
    "convert_vector_to_geojson",
    "find_ogr2ogr",
    "require_ogr2ogr",
]
