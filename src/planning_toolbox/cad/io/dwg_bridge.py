"""Optional, local-only DWG to DXF bridge using ODA File Converter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class DwgConverterUnavailable(RuntimeError):
    """Raised when the optional desktop converter is not installed."""


def _next_output_path(output_dir: Path, stem: str) -> Path:
    candidate = output_dir / f"{stem}_from_dwg.dxf"
    if not candidate.exists():
        return candidate
    for number in range(2, 10_000):
        candidate = output_dir / f"{stem}_from_dwg_{number}.dxf"
        if not candidate.exists():
            return candidate
    raise FileExistsError("无法为 DWG 转换结果生成安全的新文件名。")


def oda_converter_available() -> bool:
    """Return whether the local ODA File Converter can be used by ezdxf."""
    from ezdxf.addons import odafc

    return bool(odafc.is_installed())


def convert_dwg_to_dxf(
    source_path: Path | str,
    output_dir: Path | str,
    *,
    version: str = "R2018",
) -> Dict[str, Any]:
    """Convert a DWG into a new DXF copy without uploading or overwriting it."""
    import ezdxf
    from ezdxf.addons import odafc

    from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file

    source = Path(source_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"DWG 文件不存在：{source}")
    if source.suffix.lower() != ".dwg":
        raise ValueError("DWG 导入助手只接受 .dwg 文件。")
    if not odafc.is_installed():
        raise DwgConverterUnavailable(
            "当前电脑未检测到 ODA File Converter。请先安装免费的 ODA File Converter，"
            "然后重新打开 Planning Toolbox；该流程完全在本机运行，不需要 API。"
        )

    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = _next_output_path(output_root, source.stem)
    source_sha256 = sha256_file(source)
    odafc.convert(source, output_path, version=version, audit=True, replace=False)
    # Validate that the produced file can actually be consumed by this app.
    converted = ezdxf.readfile(output_path)
    assert_file_unchanged(source, source_sha256)
    return {
        "task_type": "dwg_convert",
        "source_file": str(source),
        "source_sha256": source_sha256,
        "converted_dxf": str(output_path),
        "dxf_version": str(converted.dxfversion),
        "entity_count": len(converted.modelspace()),
        "converter": "ODA File Converter (local desktop)",
        "output_files": [("DWG 转换 DXF", str(output_path))],
    }
