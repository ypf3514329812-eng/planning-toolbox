from pathlib import Path
from typing import List, Any, Dict
import ezdxf
from planning_toolbox.core.models.parcel import Parcel

def export_labeled_dxf(
    doc: Any,
    parcels: List[Parcel],
    output_path: Path | str,
    annotation_config: Dict[str, Any]
) -> Path:
    """
    Saves a new DXF file with parcel IDs and areas annotated inside each valid parcel.
    Does NOT modify or overwrite the original document file directly.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    layer_name = annotation_config.get("layer_name", "PARCEL_LABEL")
    text_height = annotation_config.get("text_height", 2.5)
    show_ha = annotation_config.get("show_ha", True)
    show_m2 = annotation_config.get("show_m2", False)

    # Ensure layer exists in document
    if layer_name not in doc.layers:
        doc.layers.add(name=layer_name, color=2)  # Color 2 = Yellow

    msp = doc.modelspace()

    for parcel in parcels:
        if parcel.status != "VALID" or not parcel.label_point:
            continue
        
        x, y = parcel.label_point
        lines = [parcel.parcel_id]
        if show_ha:
            lines.append(f"{parcel.area_ha:.2f} ha")
        if show_m2:
            lines.append(f"{parcel.area_m2:.1f} m²")

        text_content = "\\P".join(lines)  # ezdxf MTEXT paragraph separator is \P

        # Create MTEXT entity centered at label_point (attachment_point 5 = Middle Center)
        mtext = msp.add_mtext(text_content, dxfattribs={
            'layer': layer_name,
            'char_height': text_height,
            'attachment_point': 5,
        })
        mtext.set_location(insert=(x, y, 0.0))

    doc.saveas(out_file)
    return out_file
