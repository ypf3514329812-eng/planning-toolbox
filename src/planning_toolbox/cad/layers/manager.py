from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml
import ezdxf
from planning_toolbox.cad.layers.template import ensure_linetype

PACKAGE_LAYERS_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "layers.yaml"
PACKAGE_CHINA_DRAFTING_CONFIG_PATH = (
    Path(__file__).parent.parent.parent / "config" / "china_drafting_layers.yaml"
)

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


def load_drafting_layer_config(profile_id: str) -> Dict[str, Any]:
    """Load a filtered Chinese drafting-assistance layer profile.

    The full layer library remains data-only and lightweight.  A task receives
    only the layers relevant to the selected profile, so a residential drawing
    is not filled with unrelated territorial-spatial-planning layers.
    """
    from planning_toolbox.rules.drafting import (
        get_drafting_profile,
        get_drafting_reference,
    )

    profile = get_drafting_profile(profile_id)
    if not PACKAGE_CHINA_DRAFTING_CONFIG_PATH.is_file():
        raise FileNotFoundError(
            f"中国制图辅助配置不存在: {PACKAGE_CHINA_DRAFTING_CONFIG_PATH}"
        )
    with open(PACKAGE_CHINA_DRAFTING_CONFIG_PATH, "r", encoding="utf-8") as stream:
        library = yaml.safe_load(stream) or {}
    library_layers = library.get("layers", {})
    missing = [name for name in profile.all_layers if name not in library_layers]
    if missing:
        raise ValueError(f"中国制图辅助配置缺少图层: {', '.join(missing)}")
    references = [get_drafting_reference(code) for code in profile.reference_codes]
    return {
        "schema": library.get("schema", ""),
        "style_authority": library.get("style_authority", ""),
        "unit": library.get("unit", "m"),
        "profile": {
            "profile_id": profile.profile_id,
            "name": profile.name,
            "description": profile.description,
            "required_layers": list(profile.required_layers),
            "recommended_layers": list(profile.recommended_layers),
            "require_projected_crs_review": profile.require_projected_crs_review,
            "references": [
                {
                    "code": reference.code,
                    "name": reference.name,
                    "authority": reference.authority,
                    "status": reference.status,
                    "effective_date": reference.effective_date,
                    "scope": reference.scope,
                    "source_url": reference.source_url,
                    "note": reference.note,
                }
                for reference in references
            ],
        },
        "layers": {
            name: dict(library_layers[name])
            for name in profile.all_layers
        },
    }

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


def standardize_document_layers(
    doc,
    layer_config: Dict[str, Any],
) -> Tuple[Dict[str, int], List[str]]:
    """Standardize modelspace layers in an already-open DXF document.

    This shared in-memory operation lets the layer tool and the quality-repair
    workflow apply the same alias rules without reading or writing the source
    file twice.
    """
    layers_spec = layer_config.get("layers", {})
    alias_map = build_alias_map(layers_spec)

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
                linetype=linetype,
            )
        else:
            # This operates only on an output copy (or an explicitly requested
            # in-memory repair document).  Align existing standard layers as
            # well as newly created ones so the compliance check is meaningful.
            layer = doc.layers.get(std_name)
            layer.dxf.color = int(color)
            layer.dxf.lineweight = int(lineweight)
            layer.dxf.linetype = str(linetype)

    remapped_counts: Dict[str, int] = {std_name: 0 for std_name in layers_spec}
    unmapped_layers_set = set()
    for entity in doc.modelspace():
        orig_layer = str(entity.dxf.layer)
        target_std_layer = alias_map.get(orig_layer.upper())
        if target_std_layer is None:
            unmapped_layers_set.add(orig_layer)
            continue
        if orig_layer != target_std_layer:
            entity.dxf.layer = target_std_layer
            remapped_counts[target_std_layer] += 1

    return remapped_counts, sorted(unmapped_layers_set)

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
    total_entities = len(doc.modelspace())
    remapped_counts, unmapped_layers = standardize_document_layers(doc, layer_config)

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
    profile = layer_config.get("profile", {})
    profile_lines = ""
    if profile:
        reference_codes = ", ".join(
            str(item.get("code", "")) for item in profile.get("references", [])
        )
        profile_lines = (
            f"Drafting assistance profile: {profile.get('name', '')}\n"
            f"Profile id: {profile.get('profile_id', '')}\n"
            f"Reference index: {reference_codes}\n"
            "Compliance meaning: assistive consistency only; not statutory approval.\n"
        )
    report_content = (
        f"=== Planning Toolbox CAD Layer Report ===\n"
        f"Source DXF: {path.name}\n"
        f"Total DXF Entities Scanned: {total_entities}\n"
        f"{profile_lines}"
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
