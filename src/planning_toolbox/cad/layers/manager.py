from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml
import ezdxf
from planning_toolbox.cad.layers.template import ensure_linetype

PACKAGE_LAYERS_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "layers.yaml"

def _find_layers_config_path() -> Path:
    """Find config/layers.yaml relative to package, project root, or package internal config."""
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / "config" / "layers.yaml"
        if candidate.exists():
            return candidate
        current = current.parent

    if PACKAGE_LAYERS_CONFIG_PATH.exists():
        return PACKAGE_LAYERS_CONFIG_PATH

    return Path("config/layers.yaml")

def load_layer_config(config_path: Path | str | None = None) -> Dict[str, Any]:
    """Load layer specification from YAML file."""
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Layer configuration file not found: {path}")
    else:
        path = _find_layers_config_path()
        if not path.exists():
            if PACKAGE_LAYERS_CONFIG_PATH.exists():
                path = PACKAGE_LAYERS_CONFIG_PATH
            else:
                raise FileNotFoundError(f"Layer configuration file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def build_alias_map(layers_spec: Dict[str, Any]) -> Dict[str, str]:
    """
    Builds a case-insensitive mapping dictionary from aliases and Chinese names to standard layer keys.
    e.g. {'地块': 'PARCEL', '地块红线': 'PARCEL', 'PARCEL_BOUND': 'PARCEL'}
    """
    mapping = {}
    for std_name, info in layers_spec.items():
        mapping[std_name.upper()] = std_name
        name_cn = info.get("name_cn")
        if name_cn:
            mapping[name_cn.upper()] = std_name
        aliases = info.get("aliases", [])
        for alias in aliases:
            mapping[str(alias).upper()] = std_name
    return mapping

def standardize_dxf_layers(
    dxf_path: Path | str,
    layer_config: Dict[str, Any],
    output_dir: Path | str | None = None
) -> Tuple[Path, Path, Dict[str, int], List[str]]:
    """
    Standardizes DXF layers by creating missing standard layers and remapping entities on alias layers.
    Saves a new DXF file `*_standardized.dxf` and a layer report `*_layer_report.txt`.
    
    Returns:
      (standardized_dxf_path, layer_report_path, remapped_counts, unmapped_layers)
    """
    path = Path(dxf_path)
    if not path.exists():
        raise FileNotFoundError(f"DXF file not found: {path}")

    out_dir = Path(output_dir) if output_dir else path.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    layers_spec = layer_config.get("layers", {})
    alias_map = build_alias_map(layers_spec)

    # 1. Ensure all standard layers exist in document with correct properties
    for std_name, info in layers_spec.items():
        color = info.get("color", 7)
        lineweight = info.get("lineweight", 18)
        linetype = info.get("linetype", "Continuous")

        ensure_linetype(doc, linetype)

        if std_name not in doc.layers:
            doc.layers.add(
                name=std_name,
                color=color,
                lineweight=lineweight,
                linetype=linetype
            )

    # 2. Remap entities on modelspace
    remapped_counts: Dict[str, int] = {std_name: 0 for std_name in layers_spec}
    unmapped_layers_set = set()
    total_entities = 0

    for entity in msp:
        total_entities += 1
        orig_layer = str(entity.dxf.layer)
        orig_layer_upper = orig_layer.upper()

        if orig_layer_upper in alias_map:
            target_std_layer = alias_map[orig_layer_upper]
            if orig_layer != target_std_layer:
                entity.dxf.layer = target_std_layer
                remapped_counts[target_std_layer] += 1
        else:
            unmapped_layers_set.add(orig_layer)

    unmapped_layers = sorted(list(unmapped_layers_set))

    # 3. Save standardized DXF
    stem = path.stem
    standardized_dxf_path = (out_dir / f"{stem}_standardized.dxf").resolve()

    if standardized_dxf_path == path.resolve():
        raise ValueError(
            f"Output DXF path ({standardized_dxf_path}) cannot be identical to source DXF path ({path.resolve()}). "
            f"Direct overwrite is forbidden for data safety."
        )
    doc.saveas(standardized_dxf_path)

    # 4. Generate Layer Analysis & Remap Report
    report_path = out_dir / f"{stem}_layer_report.txt"
    report_content = (
        f"=== Planning Toolbox CAD Layer Report ===\n"
        f"Source DXF: {path.name}\n"
        f"Total DXF Entities Scanned: {total_entities}\n"
        f"-----------------------------------------\n"
        f"Standard Layers Remapped Entity Counts:\n"
    )
    for std_name, count in remapped_counts.items():
        report_content += f"  {std_name:<15}: {count} entities remapped\n"

    report_content += (
        f"-----------------------------------------\n"
        f"Unmapped Custom Layers Detected ({len(unmapped_layers)}):\n"
    )
    if unmapped_layers:
        for ul in unmapped_layers:
            report_content += f"  - {ul}\n"
    else:
        report_content += "  None (All layers fully standardized!)\n"

    report_content += f"=========================================\n"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return standardized_dxf_path, report_path, remapped_counts, unmapped_layers
