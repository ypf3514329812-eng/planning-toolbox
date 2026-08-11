from pathlib import Path
from typing import Dict, Any, Optional
import ezdxf

# Standard AutoCAD linetype definitions for ezdxf
STANDARD_LINETYPES = {
    "CENTER": ("_ ____ _ ____ _ ", [1.25, 1.0, -0.25, 0.25, -0.25]),
    "DASHED": ("__ __ __ __ __ ", [0.75, 0.5, -0.25]),
    "DASHDOT": ("__ . __ . __ . ", [1.0, 0.5, -0.2, 0.0, -0.2]),
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

def ensure_planning_symbol_blocks(doc: Any) -> tuple[str, ...]:
    """Create a small editable vector-symbol library without inserting it."""
    created = []
    if "PT_NORTH_ARROW" not in doc.blocks:
        block = doc.blocks.new("PT_NORTH_ARROW")
        block.add_circle((0, 0), 5.0, dxfattribs={"layer": "0"})
        block.add_line((0, -4), (0, 6), dxfattribs={"layer": "0"})
        block.add_solid(
            [(-1.4, 2.0), (1.4, 2.0), (0, 6.0), (0, 6.0)],
            dxfattribs={"layer": "0"},
        )
        created.append("PT_NORTH_ARROW")
    if "PT_SCALE_BAR_100M" not in doc.blocks:
        block = doc.blocks.new("PT_SCALE_BAR_100M")
        for start in (0.0, 25.0, 50.0, 75.0):
            block.add_lwpolyline(
                [(start, 0), (start + 25, 0), (start + 25, 3), (start, 3)],
                close=True,
                dxfattribs={"layer": "0"},
            )
        for tick in (0.0, 25.0, 50.0, 75.0, 100.0):
            block.add_line((tick, -1), (tick, 4), dxfattribs={"layer": "0"})
        created.append("PT_SCALE_BAR_100M")
    if "PT_ENTRANCE" not in doc.blocks:
        block = doc.blocks.new("PT_ENTRANCE")
        block.add_lwpolyline(
            [(-4, -2), (0, 0), (-4, 2)],
            dxfattribs={"layer": "0"},
        )
        block.add_line((0, 0), (6, 0), dxfattribs={"layer": "0"})
        created.append("PT_ENTRANCE")
    if "PT_TREE" not in doc.blocks:
        block = doc.blocks.new("PT_TREE")
        block.add_circle((0, 0), 1.5, dxfattribs={"layer": "0"})
        block.add_line((-1.05, 0), (1.05, 0), dxfattribs={"layer": "0"})
        block.add_line((0, -1.05), (0, 1.05), dxfattribs={"layer": "0"})
        created.append("PT_TREE")
    if "PT_PARKING_STALL" not in doc.blocks:
        block = doc.blocks.new("PT_PARKING_STALL")
        block.add_lwpolyline(
            [(-2.5, -1.25), (2.5, -1.25), (2.5, 1.25), (-2.5, 1.25)],
            close=True,
            dxfattribs={"layer": "0"},
        )
        created.append("PT_PARKING_STALL")
    return tuple(created)


def create_planning_template(
    output_path: Path | str,
    layer_config: Dict[str, Any],
    *,
    include_symbol_blocks: bool = True,
) -> Path:
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

    if include_symbol_blocks:
        ensure_planning_symbol_blocks(doc)

    doc.saveas(out_file)
    return out_file
