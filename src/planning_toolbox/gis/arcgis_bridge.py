"""Optional ArcGIS Pro adapter executed in an isolated subprocess."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from planning_toolbox.gis.crs import normalize_crs_identifier
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


class ArcGISAdapterUnavailableError(RuntimeError):
    """Raised when ArcGIS Pro's Python environment cannot be found."""


class ArcGISConversionError(RuntimeError):
    """Raised when an ArcPy subprocess reports a conversion failure."""


@dataclass(frozen=True)
class ArcGISConversionResult:
    output_path: Path
    source_sha256: str
    python_path: Path
    command: tuple[str, ...]
    details: dict[str, Any]


def _candidate_arcgis_homes():
    env_home = os.environ.get("ARCGIS_PRO_HOME")
    if env_home:
        yield Path(env_home)
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    yield Path(program_files) / "ArcGIS" / "Pro"
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        yield Path(local_app_data) / "Programs" / "ArcGIS" / "Pro"
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\ESRI\ArcGISPro") as key:
                install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                if install_dir:
                    yield Path(install_dir)
        except (OSError, FileNotFoundError, ImportError):
            pass


def _python_from_home(home: Path) -> Path:
    return home / "bin" / "Python" / "envs" / "arcgispro-py3" / "python.exe"


def find_arcgis_python(explicit_path: Path | str | None = None) -> Path | None:
    """Find ArcGIS Pro Python using explicit and conventional install locations."""

    if explicit_path:
        candidate = Path(explicit_path).expanduser()
        if candidate.is_dir():
            direct = candidate / "python.exe"
            nested = _python_from_home(candidate)
            candidate = direct if direct.is_file() else nested
        return candidate.resolve() if candidate.is_file() else None
    for home in _candidate_arcgis_homes():
        candidate = _python_from_home(home)
        if candidate.is_file():
            return candidate.resolve()
    return None


def require_arcgis_python(explicit_path: Path | str | None = None) -> Path:
    python_path = find_arcgis_python(explicit_path)
    if python_path is None:
        raise ArcGISAdapterUnavailableError(
            "未检测到 ArcGIS Pro 后台 Python。请确认 ArcGIS Pro 已完整安装，或改用 QGIS/GDAL 适配器。"
        )
    return python_path


def _worker_script_path() -> Path:
    candidates = [Path(__file__).with_name("arcpy_worker.py")]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.insert(0, Path(bundle_root) / "planning_toolbox" / "gis" / "arcpy_worker.py")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ArcGISConversionError("安装包缺少 ArcGIS Pro 转换助手，请重新安装 Planning Toolbox。")


def _epsg_code(identifier: str) -> int:
    normalized = normalize_crs_identifier(identifier)
    authority, code = normalized.split(":", 1)
    if authority != "EPSG":
        raise ArcGISConversionError("ArcGIS Pro 自动桥接当前只接受 EPSG 坐标编号。")
    return int(code)


def _safe_layer_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", str(value).strip()).strip("_")
    return name[:63] or "planning_features"


def build_arcgis_worker_command(
    python_path: Path | str,
    worker_path: Path | str,
    mode: str,
    *,
    source: Path | str,
    output: Path | str,
    epsg: int,
    scratch: Path | str,
    layer_name: str = "",
) -> list[str]:
    command = [
        str(python_path),
        str(worker_path),
        mode,
        "--source",
        str(source),
        "--output",
        str(output),
        "--epsg",
        str(int(epsg)),
        "--scratch",
        str(scratch),
    ]
    if layer_name:
        command.extend(["--layer", str(layer_name)])
    return command


def _read_worker_payload(stdout: str) -> dict[str, Any]:
    for line in reversed(str(stdout or "").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "status" in value:
            return value
    raise ArcGISConversionError("ArcGIS Pro 转换进程未返回可识别的结果。")


def _run_worker(command: Sequence[str], timeout_seconds: int = 300) -> dict[str, Any]:
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
        raise ArcGISConversionError("ArcGIS Pro 后台转换超过 5 分钟，已安全停止。") from exc
    except OSError as exc:
        raise ArcGISConversionError(f"无法启动 ArcGIS Pro 后台转换：{exc}") from exc
    payload = _read_worker_payload(completed.stdout)
    if completed.returncode != 0 or payload.get("status") != "ok":
        message = str(payload.get("message") or "未知错误")
        details = str(payload.get("details") or "").strip()
        if details and details not in message:
            message = f"{message}\n{details}"
        raise ArcGISConversionError(f"ArcGIS Pro 转换失败：{message}")
    return payload


def _annotate_geojson(path: Path, crs_identifier: str, details: dict[str, Any]) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArcGISConversionError("ArcGIS Pro 输出不是有效的 GeoJSON。") from exc
    metadata = data.setdefault("planning_toolbox_metadata", {})
    if isinstance(metadata, dict):
        metadata.update(
            {
                "coordinate_reference_system": crs_identifier,
                "coordinate_units": "m",
                "coordinate_transform_applied": True,
                "conversion_adapter": "ArcGIS Pro",
                "arcgis_version": details.get("arcgis_version", ""),
                "geographic_transformation": details.get("geographic_transformation", ""),
            }
        )
    data["crs"] = {"type": "name", "properties": {"name": crs_identifier}}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_paths(source_path: Path | str, output_path: Path | str, output_suffix: str):
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"GIS 源文件不存在：{source}")
    if output.suffix.lower() != output_suffix:
        raise ArcGISConversionError(f"输出文件必须使用 {output_suffix} 扩展名。")
    if source == output:
        raise ArcGISConversionError("输入和输出不能相同；系统禁止覆盖原始 GIS 数据。")
    output.parent.mkdir(parents=True, exist_ok=True)
    return source, output


def convert_vector_to_geojson(
    source_path: Path | str,
    output_geojson: Path | str,
    *,
    target_crs: str,
    layer_name: str | None = None,
    arcgis_python: Path | str | None = None,
) -> ArcGISConversionResult:
    source, output = _validate_paths(source_path, output_geojson, ".geojson")
    if source.suffix.lower() not in {".gpkg", ".shp", ".geojson", ".json"}:
        raise ArcGISConversionError("ArcGIS Pro 适配器仅支持 GPKG、SHP 和 GeoJSON。")
    python_path = require_arcgis_python(arcgis_python)
    worker = _worker_script_path()
    source_sha256 = sha256_file(source)
    crs_identifier = normalize_crs_identifier(target_crs)
    with TemporaryDirectory(prefix="planning-toolbox-arcpy-") as scratch:
        command = build_arcgis_worker_command(
            python_path,
            worker,
            "vector-to-geojson",
            source=source,
            output=output,
            epsg=_epsg_code(crs_identifier),
            scratch=scratch,
            layer_name=layer_name or "",
        )
        details = _run_worker(command)
    if not output.is_file():
        raise ArcGISConversionError("ArcGIS Pro 未生成预期的 GeoJSON 文件。")
    _annotate_geojson(output, crs_identifier, details)
    assert_file_unchanged(source, source_sha256)
    return ArcGISConversionResult(output, source_sha256, python_path, tuple(command), details)


def convert_geojson_to_gpkg(
    source_geojson: Path | str,
    output_gpkg: Path | str,
    *,
    source_crs: str,
    layer_name: str = "planning_parcels",
    arcgis_python: Path | str | None = None,
) -> ArcGISConversionResult:
    source, output = _validate_paths(source_geojson, output_gpkg, ".gpkg")
    if source.suffix.lower() not in {".geojson", ".json"}:
        raise ArcGISConversionError("ArcGIS Pro GeoPackage 导出要求输入为 GeoJSON。")
    python_path = require_arcgis_python(arcgis_python)
    worker = _worker_script_path()
    source_sha256 = sha256_file(source)
    with TemporaryDirectory(prefix="planning-toolbox-arcpy-") as scratch:
        command = build_arcgis_worker_command(
            python_path,
            worker,
            "geojson-to-gpkg",
            source=source,
            output=output,
            epsg=_epsg_code(source_crs),
            scratch=scratch,
            layer_name=_safe_layer_name(layer_name),
        )
        details = _run_worker(command)
    if not output.is_file():
        raise ArcGISConversionError("ArcGIS Pro 未生成预期的 GeoPackage 文件。")
    assert_file_unchanged(source, source_sha256)
    return ArcGISConversionResult(output, source_sha256, python_path, tuple(command), details)


__all__ = [
    "ArcGISAdapterUnavailableError",
    "ArcGISConversionError",
    "ArcGISConversionResult",
    "build_arcgis_worker_command",
    "convert_geojson_to_gpkg",
    "convert_vector_to_geojson",
    "find_arcgis_python",
    "require_arcgis_python",
]
