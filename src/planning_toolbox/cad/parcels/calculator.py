import csv
from pathlib import Path
from typing import List, Dict, Any, Tuple
from planning_toolbox.core.models.parcel import Parcel
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry, get_interior_label_point
from planning_toolbox.cad.io.dxf_reader import read_dxf_parcels
from planning_toolbox.cad.annotation.dxf_writer import export_labeled_dxf

def process_parcels(
    dxf_path: Path | str,
    config: Dict[str, Any],
    output_dir: Path | str | None = None
) -> Tuple[List[Parcel], Path, Path, Path]:
    """
    Main processing pipeline for DXF Parcel Recognition & Calculation.
    
    Returns:
      (parcels, labeled_dxf_path, csv_report_path, summary_report_path)
    """
    dxf_path = Path(dxf_path)
    output_dir_path = Path(output_dir) if output_dir else Path(config.get("output", {}).get("dir", "output"))
    output_dir_path.mkdir(parents=True, exist_ok=True)

    parcel_cfg = config.get("parcel", {})
    input_layers = parcel_cfg.get("input_layers", ["PARCEL"])
    fallback_unit = parcel_cfg.get("fallback_unit", "m")
    strict_unit = parcel_cfg.get("strict_unit_check", False)
    prefix = parcel_cfg.get("id_prefix", "P")
    digits = parcel_cfg.get("id_digits", 3)

    # 1. Read DXF
    doc, entities_info, unit_name, area_scale = read_dxf_parcels(
        dxf_path=dxf_path,
        target_layers=input_layers,
        fallback_unit=fallback_unit,
        strict_unit_check=strict_unit
    )

    scanned_entities_count = len(entities_info)

    # 2. Parse Geometries
    raw_parcels = []
    for idx, info in enumerate(entities_info):
        ent = info["entity"]
        layer = info["layer"]
        pts, is_closed = points_from_dxf_polyline(ent)
        status, poly, err_msg = parse_parcel_geometry(pts, is_closed)

        raw_area = poly.area if poly else 0.0
        area_m2 = raw_area * area_scale
        area_ha = area_m2 / 10000.0
        label_pt = get_interior_label_point(poly) if poly else None

        parcel = Parcel(
            parcel_id="",  # Assigned deterministically after sorting
            source_layer=layer,
            status=status,
            raw_area=raw_area,
            area_m2=area_m2,
            area_ha=area_ha,
            geometry=poly,
            label_point=label_pt,
            error_message=err_msg
        )
        raw_parcels.append(parcel)

    # 3. Deterministic Sorting & ID Assignment
    # Sort valid parcels by min_y (top to bottom), then min_x (left to right)
    def sort_key(p: Parcel):
        if p.geometry:
            minx, miny, maxx, maxy = p.geometry.bounds
            return (-maxy, minx)
        return (float('inf'), float('inf'))

    valid_parcels = [p for p in raw_parcels if p.status == "VALID"]
    invalid_parcels = [p for p in raw_parcels if p.status != "VALID"]

    valid_parcels.sort(key=sort_key)

    all_parcels: List[Parcel] = []
    for i, p in enumerate(valid_parcels, start=1):
        p.parcel_id = f"{prefix}{i:0{digits}d}"
        all_parcels.append(p)

    for i, p in enumerate(invalid_parcels, start=1):
        p.parcel_id = f"{prefix}_ERR_{i:02d}"
        all_parcels.append(p)

    # 4. Generate Output CSV
    stem = dxf_path.stem
    csv_path = output_dir_path / f"{stem}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "parcel_id", "source_layer", "area_m2", "area_ha", "geometry_status", "error_message"
        ])
        writer.writeheader()
        for p in all_parcels:
            writer.writerow(p.to_dict())

    # 5. Generate Labeled DXF
    labeled_dxf_path = output_dir_path / f"{stem}_labeled.dxf"
    export_labeled_dxf(
        doc=doc,
        parcels=valid_parcels,
        output_path=labeled_dxf_path,
        annotation_config=parcel_cfg.get("annotation", {})
    )

    # 6. Generate Summary Text Report
    open_count = sum(1 for p in raw_parcels if p.status == "OPEN")
    invalid_geom_count = sum(1 for p in raw_parcels if p.status in ("INVALID_GEOMETRY", "ZERO_AREA"))
    valid_count = len(valid_parcels)
    total_valid_m2 = sum(p.area_m2 for p in valid_parcels)
    total_valid_ha = sum(p.area_ha for p in valid_parcels)

    report_path = output_dir_path / f"{stem}_report.txt"
    report_content = (
        f"=== Planning Toolbox Parcel Analysis Report ===\n"
        f"Source DXF: {dxf_path.name}\n"
        f"Detected Unit: {unit_name}\n"
        f"-----------------------------------------------\n"
        f"DXF entities scanned: {scanned_entities_count}\n"
        f"Parcel candidates: {len(raw_parcels)}\n"
        f"Valid closed parcels: {valid_count}\n"
        f"Open polylines: {open_count}\n"
        f"Invalid geometry: {invalid_geom_count}\n"
        f"-----------------------------------------------\n"
        f"Total valid area:\n"
        f"  {total_valid_m2:,.2f} m²\n"
        f"  {total_valid_ha:,.4f} ha\n"
        f"===============================================\n"
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return all_parcels, labeled_dxf_path, csv_path, report_path
