"""Safe, repeatable batch analysis for a folder of DXF drawings."""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from planning_toolbox.cad.parcels.calculator import process_parcels
from planning_toolbox.config import load_config
from planning_toolbox.indicators.calculator import process_dxf_indicators
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


SUPPORTED_BATCH_TASKS = ("parcel", "indicator")


def _validate_batch_inputs(input_dir: Path, task_type: str, floors: Optional[float]) -> List[Path]:
    if task_type not in SUPPORTED_BATCH_TASKS:
        supported = ", ".join(SUPPORTED_BATCH_TASKS)
        raise ValueError(f"批量任务暂不支持：{task_type}。当前支持：{supported}")
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"输入文件夹不存在：{input_dir}")
    if task_type == "indicator" and (floors is None or floors <= 0):
        raise ValueError("批量指标计算必须明确填写正数楼层倍数。")
    paths = sorted(input_dir.glob("*.dxf"), key=lambda path: path.name.lower())
    if not paths:
        raise ValueError(f"输入文件夹中没有找到 DXF 文件：{input_dir}")
    return paths


def analyze_dxf_batch(
    input_dir: Path | str,
    output_dir: Path | str,
    task_type: str = "parcel",
    floors: Optional[float] = None,
    config_path: Path | str | None = None,
) -> Dict[str, Any]:
    """Analyze every DXF in a folder and write one CSV summary.

    Each source file receives its own output subfolder. A failed file is
    recorded in the summary and does not prevent the remaining files from
    being processed.
    """
    input_path = Path(input_dir).resolve()
    output_path = Path(output_dir).resolve()
    paths = _validate_batch_inputs(input_path, task_type, floors)
    output_path.mkdir(parents=True, exist_ok=True)

    base_config = load_config(config_path)
    if task_type == "indicator":
        base_config = {**base_config, "default_floors": floors}

    items: List[Dict[str, Any]] = []
    for dxf_path in paths:
        item_output = output_path / dxf_path.stem
        item_output.mkdir(parents=True, exist_ok=True)
        source_sha256 = sha256_file(dxf_path)
        item: Dict[str, Any] = {
            "source_file": str(dxf_path),
            "source_sha256": source_sha256,
            "task_type": task_type,
            "status": "SUCCESS",
            "message": "",
            "valid_count": 0,
            "total_ha": 0.0,
            "report_file": "",
        }
        try:
            if task_type == "parcel":
                parcels, _, _, report_file = process_parcels(
                    dxf_path, base_config, item_output
                )
                valid = [parcel for parcel in parcels if parcel.status == "VALID"]
                item["valid_count"] = len(valid)
                item["total_ha"] = sum(parcel.area_ha for parcel in valid)
            else:
                results, _, report_file = process_dxf_indicators(
                    dxf_path, config=base_config, output_dir=item_output
                )
                item["valid_count"] = len(results)
                item["total_ha"] = sum(result.site_area_ha for result in results)
            assert_file_unchanged(dxf_path, source_sha256)
            item["report_file"] = str(report_file)
        except Exception as exc:
            item["status"] = "FAILED"
            item["message"] = str(exc)
        items.append(item)

    summary_file = output_path / "batch_summary.csv"
    with summary_file.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "source_file",
                "source_sha256",
                "task_type",
                "status",
                "valid_count",
                "total_ha",
                "report_file",
                "message",
            ],
        )
        writer.writeheader()
        writer.writerows(items)

    return {
        "task_type": task_type,
        "input_dir": str(input_path),
        "output_dir": str(output_path),
        "processed_count": len(items),
        "success_count": sum(item["status"] == "SUCCESS" for item in items),
        "failed_count": sum(item["status"] == "FAILED" for item in items),
        "items": items,
        "summary_file": str(summary_file),
        "floors": floors,
    }
