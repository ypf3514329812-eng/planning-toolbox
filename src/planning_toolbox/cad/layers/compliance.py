"""Read-only checks for a selected Chinese drafting-assistance profile."""

from collections import Counter
import json
from pathlib import Path
from typing import Any, Dict, Iterable

import ezdxf


def _normalized_linetype(value: Any) -> str:
    return str(value or "CONTINUOUS").upper()


def audit_dxf_drafting_compliance(
    dxf_path: Path | str,
    layer_config: Dict[str, Any],
    *,
    output_dir: Path | str | None = None,
    unmapped_layers: Iterable[str] = (),
) -> Dict[str, Any]:
    """Check units, required layers and layer styles without editing a DXF.

    DXF does not reliably carry a geodetic CRS declaration.  Profiles that
    require CGCS2000/projected-coordinate review therefore always expose that
    item as a human-review warning instead of silently reporting compliance.
    """
    path = Path(dxf_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"DXF 文件不存在: {path}")
    doc = ezdxf.readfile(path)
    profile = dict(layer_config.get("profile", {}))
    layers_spec = layer_config.get("layers", {})
    required_layers = list(profile.get("required_layers", []))
    entity_counts = Counter(str(entity.dxf.layer) for entity in doc.modelspace())
    present_layers = {str(layer.dxf.name) for layer in doc.layers}

    unit_code = int(doc.header.get("$INSUNITS", 0) or 0)
    blockers = []
    warnings = []
    passed = []
    if unit_code == 0:
        blockers.append("DXF 单位未知（$INSUNITS=0），不能可靠核对米制图层与尺寸。")
        unit_name = "unknown"
    elif unit_code == 6:
        passed.append("DXF 单位已明确为米。")
        unit_name = "m"
    else:
        unit_name = f"INSUNITS={unit_code}"
        warnings.append(
            f"DXF 单位不是米（$INSUNITS={unit_code}）；规划总平面通常应确认单位换算。"
        )

    missing_required = [name for name in required_layers if name not in present_layers]
    empty_required = [
        name for name in required_layers
        if name in present_layers and entity_counts.get(name, 0) == 0
    ]
    if missing_required:
        warnings.append("缺少必备辅助图层：" + "、".join(missing_required))
    else:
        passed.append("所选模板的必备图层均已创建。")
    if empty_required:
        warnings.append(
            "以下必备图层当前为空，请确认是否确实不需要：" + "、".join(empty_required)
        )

    style_mismatches = []
    for name, expected in layers_spec.items():
        if name not in present_layers:
            continue
        layer = doc.layers.get(name)
        actual = {
            "color": int(layer.dxf.color),
            "lineweight": int(layer.dxf.lineweight),
            "linetype": _normalized_linetype(layer.dxf.linetype),
        }
        target = {
            "color": int(expected.get("color", 7)),
            "lineweight": int(expected.get("lineweight", 18)),
            "linetype": _normalized_linetype(expected.get("linetype", "Continuous")),
        }
        if actual != target:
            style_mismatches.append({"layer": name, "actual": actual, "expected": target})
    if style_mismatches:
        warnings.append(f"有 {len(style_mismatches)} 个标准图层样式与所选模板不一致。")
    else:
        passed.append("已创建图层的颜色、线宽和线型与辅助模板一致。")

    unmapped = sorted({str(item) for item in unmapped_layers if str(item) not in {"0", "Defpoints"}})
    if unmapped:
        warnings.append(f"仍有 {len(unmapped)} 个自定义图层需要人工判断。")
    if profile.get("require_projected_crs_review"):
        warnings.append(
            "DXF 未提供可可靠机读的地理坐标系声明；请人工确认CGCS2000、"
            "高斯-克吕格投影、分带和高程基准。"
        )

    status = "blocked" if blockers else ("review_required" if warnings else "pass")
    result = {
        "schema": "planning-toolbox-drafting-compliance-v1",
        "meaning": "assistive_consistency_not_statutory_approval",
        "profile_id": profile.get("profile_id", "legacy_basic"),
        "profile_name": profile.get("name", "基础图层配置"),
        "status": status,
        "unit_code": unit_code,
        "unit_name": unit_name,
        "required_layer_count": len(required_layers),
        "present_required_layer_count": len(required_layers) - len(missing_required),
        "populated_required_layer_count": sum(
            1 for name in required_layers if entity_counts.get(name, 0) > 0
        ),
        "missing_required_layers": missing_required,
        "empty_required_layers": empty_required,
        "style_mismatches": style_mismatches,
        "unmapped_layers": unmapped,
        "blockers": blockers,
        "warnings": warnings,
        "passed": passed,
        "references": list(profile.get("references", [])),
    }

    out_root = Path(output_dir).resolve() if output_dir else path.parent
    out_root.mkdir(parents=True, exist_ok=True)
    report_path = out_root / f"{path.stem}_china_drafting_check.txt"
    json_path = out_root / f"{path.stem}_china_drafting_check.json"
    lines = [
        "=== Planning Toolbox 中国规划制图辅助检查 ===",
        f"文件：{path.name}",
        f"模板：{result['profile_name']} ({result['profile_id']})",
        f"结论：{status}",
        "含义：仅检查所选辅助模板的一致性，不代表法定审查或审批通过。",
        f"单位：{unit_name} ($INSUNITS={unit_code})",
        f"必备图层：{result['present_required_layer_count']}/{result['required_layer_count']} 已创建，"
        f"{result['populated_required_layer_count']} 个含图元",
        "",
        "[阻断项]",
        *(f"- {item}" for item in blockers),
        *("- 无" for _ in range(1) if not blockers),
        "",
        "[待人工确认]",
        *(f"- {item}" for item in warnings),
        *("- 无" for _ in range(1) if not warnings),
        "",
        "[已通过]",
        *(f"- {item}" for item in passed),
        *("- 无" for _ in range(1) if not passed),
        "",
        "[依据索引]",
    ]
    for reference in result["references"]:
        lines.append(
            f"- {reference.get('code', '')}《{reference.get('name', '')}》；"
            f"状态：{reference.get('status', '')}；来源：{reference.get('source_url', '')}"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result["report_path"] = str(report_path)
    result["json_path"] = str(json_path)
    return result
