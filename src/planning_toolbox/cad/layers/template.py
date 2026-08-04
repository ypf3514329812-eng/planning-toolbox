from pathlib import Path
from typing import Dict, Any, Optional
import ezdxf

# Standard AutoCAD linetype definitions for ezdxf
STANDARD_LINETYPES = {
    "CENTER": ("_ ____ _ ____ _ ", [1.25, 1.0, -0.25, 0.25, -0.25]),
    "DASHED": ("__ __ __ __ __ ", [0.75, 0.5, -0.25]),
}

def ensure_linetype(doc: Any, name: str):
    """Ensure linetype exists in DXF document."""
    name_upper = name.upper()
    if name_upper in ("CONTINUOUS", "BYLAYER", "BYBLOCK"):
        return
    if name_upper not in doc.linetypes:
        if name_upper in STANDARD_LINETYPES:
            desc, pattern = STANDARD_LINETYPES[name_upper]
            doc.linetypes.new(name_upper, dxfattribs={"description": desc, "pattern": pattern})
        else:
            # Fallback simple dash
            doc.linetypes.new(name_upper, dxfattribs={"description": "_ _ _ ", "pattern": [0.5, 0.25, -0.25]})

def create_planning_template(output_path: Path | str, layer_config: Dict[str, Any]) -> Path:
    """
    Generates a blank CAD DXF template containing all standardized urban planning layers.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # Meters

    layers_spec = layer_config.get("layers", {})
    for layer_key, info in layers_spec.items():
        layer_name = layer_key
        color = info.get("color", 7)
        lineweight = info.get("lineweight", 18)
        linetype = info.get("linetype", "Continuous")

        ensure_linetype(doc, linetype)

        if layer_name not in doc.layers:
            doc.layers.add(
                name=layer_name,
                color=color,
                lineweight=lineweight,
                linetype=linetype
            )

    doc.saveas(out_file)
    return out_file
