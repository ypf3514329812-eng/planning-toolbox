from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
import ezdxf
from planning_toolbox.core.units.unit_manager import get_dxf_unit_code, resolve_unit, get_area_scale_to_m2

class DXFReadError(Exception):
    pass

def read_dxf_parcels(
    dxf_path: Path | str,
    target_layers: List[Any],
    fallback_unit: Optional[str] = None,
    strict_unit_check: bool = True
) -> Tuple[Any, List[Dict[str, Any]], str, float]:
    """
    Reads a DXF file and extracts candidate parcel polylines from target layers.
    
    Returns:
      (ezdxf_doc, raw_entities_info, unit_name, area_scale_to_m2)
    """
    path = Path(dxf_path)
    if not path.exists():
        raise DXFReadError(f"DXF file not found: {path}")

    try:
        doc = ezdxf.readfile(path)
    except Exception as e:
        raise DXFReadError(f"Failed to parse DXF file {path}: {str(e)}")

    unit_code = get_dxf_unit_code(doc)
    unit_name = resolve_unit(unit_code, fallback_unit=fallback_unit, strict_check=strict_unit_check)
    area_scale = get_area_scale_to_m2(unit_name)

    msp = doc.modelspace()
    target_layers_upper = [str(l).upper() for l in target_layers]

    candidate_entities = []
    for entity in msp:
        if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            layer_name = str(entity.dxf.layer)
            if layer_name.upper() in target_layers_upper or "*" in target_layers_upper:
                candidate_entities.append({
                    "entity": entity,
                    "layer": layer_name
                })

    return doc, candidate_entities, unit_name, area_scale
