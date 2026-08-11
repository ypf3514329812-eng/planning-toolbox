"""Local assignment-package exporter for beginner coursework workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Any, Dict, Iterable, Tuple


def _category_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        return "01_CAD"
    if suffix in {".csv", ".geojson", ".json", ".xlsx"}:
        return "02_数据表"
    if suffix in {".txt", ".md", ".html", ".pdf"}:
        return "03_报告"
    if suffix in {".png", ".jpg", ".jpeg", ".svg"}:
        return "04_预览图"
    return "05_其他"


def _unique_target(directory: Path, name: str) -> Path:
    target = directory / name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def build_assignment_package(
    output_dir: Path | str,
    task_name: str,
    result: Dict[str, Any],
) -> Tuple[Path, Path]:
    """Copy generated outputs into a timestamped coursework package and zip it."""
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    package_dir = root / f"作业包_{timestamp}"
    package_dir.mkdir(parents=True, exist_ok=False)

    copied_files = []
    for label, raw_path in result.get("output_files", []):
        source = Path(raw_path)
        if not source.exists() or not source.is_file():
            continue
        category_dir = package_dir / _category_for(source)
        category_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_target(category_dir, source.name)
        shutil.copy2(source, target)
        copied_files.append((label, source.name, target.relative_to(package_dir)))

    source_file = result.get("source_file", "")
    source_sha = result.get("source_sha256", "")
    standards_name = result.get("standards_profile_name", "自定义/地方条件")
    standards = "；".join(result.get("standards_references", ()))

    manifest_path = package_dir / "00_作业包说明.txt"
    with manifest_path.open("w", encoding="utf-8") as manifest:
        manifest.write("Planning Toolbox 作业辅助结果包\n")
        manifest.write("================================\n")
        manifest.write(f"任务类型：{task_name}\n")
        manifest.write(f"输入 DXF：{source_file}\n")
        manifest.write(f"输入文件 SHA-256：{source_sha}\n")
        manifest.write(f"规范依据框架：{standards_name}\n")
        manifest.write(f"参考标准：{standards or '未指定'}\n")
        manifest.write("\n生成文件：\n")
        for label, original_name, relative_path in copied_files:
            manifest.write(f"- {label}：{original_name} -> {relative_path}\n")
        manifest.write("\n提交前人工检查：\n")
        manifest.write("1. 核对图层、单位、坐标系和输入文件是否正确。\n")
        manifest.write("2. 在 CAD 中检查建筑、道路、停车和标注是否需要调整。\n")
        manifest.write("3. 按项目所在地规划条件和最新版标准复核，不把概念草图当作审批成果。\n")
        manifest.write("4. 按老师要求补充设计说明、分析过程和个人判断。\n")

    summary_path = package_dir / "00_结果摘要.txt"
    with summary_path.open("w", encoding="utf-8") as summary:
        summary.write("本次任务关键结果\n")
        summary.write("================\n")
        for key, value in result.items():
            if key in {"output_files", "source_file", "source_sha256", "standards_references"}:
                continue
            summary.write(f"{key}: {value}\n")

    archive_base = root / f"{package_dir.name}"
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=package_dir))
    return package_dir, archive_path
