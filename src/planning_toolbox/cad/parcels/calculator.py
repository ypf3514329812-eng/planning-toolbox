import csv
from pathlib import Path
from typing import List, Dict, Any, Tuple
from planning_toolbox.core.models.parcel import Parcel
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry, get_interior_label_point
from planning_toolbox.cad.io.dxf_reader import read_dxf_parcels
from planning_toolbox.cad.annotation.dxf_writer import export_labeled_dxf
from planning_toolbox.utils.file_integrity import sha256_file, assert_file_unchanged

def detect_nested_rings(candidate_valid_parcels: List[Parcel]) -> None:
    """
    Detects if any closed parcel ring is completely contained inside another parcel ring.
    Marks every ring involved with status 'NESTED_RING_DETECTED'. A standalone
    DXF ring cannot distinguish a true hole from a deliberately nested parcel,
    so both rings are excluded from totals until a human resolves the meaning.
    Uses bounding box pre-filtering to avoid O(N²) expensive geometry checks.
    """
    nested_pairs = []
    for outer in candidate_valid_parcels:
        if outer.status != "VALID" or not outer.geometry:
            continue
        o_bounds = outer.geometry.bounds  # (minx, miny, maxx, maxy)
        for inner in candidate_valid_parcels:
            if outer is inner or inner.status != "VALID" or not inner.geometry:
                continue
            # Bounding box pre-filter: skip if inner bbox is not within outer bbox
            i_bounds = inner.geometry.bounds
            if (i_bounds[0] < o_bounds[0] or i_bounds[1] < o_bounds[1] or
                    i_bounds[2] > o_bounds[2] or i_bounds[3] > o_bounds[3]):
                continue
            # True containment check (expensive)
            if (outer.geometry.contains(inner.geometry) and
                    not outer.geometry.touches(inner.geometry) and
                    outer.geometry.area > inner.geometry.area):
                nested_pairs.append((outer, inner))

    involved = []
    involved_ids = set()
    for pair in nested_pairs:
        for parcel in pair:
            if id(parcel) not in involved_ids:
                involved.append(parcel)
                involved_ids.add(id(parcel))
    for parcel in involved:
        parcel.status = "NESTED_RING_DETECTED"
        parcel.error_message = (
            "Nested/ambiguous ring detected. "
            "Both rings are excluded from totals because DXF input does not "
            "identify whether this is a hole or an independent nested parcel."
        )

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
    source_sha256_before = sha256_file(dxf_path)
    output_dir_path = Path(output_dir) if output_dir else Path(config.get("output", {}).get("dir", "output"))
    output_dir_path.mkdir(parents=True, exist_ok=True)

    parcel_cfg = config.get("parcel", {})
    input_layers = parcel_cfg.get("input_layers", ["PARCEL"])
    fallback_unit = parcel_cfg.get("fallback_unit", None)
    strict_unit = parcel_cfg.get("strict_unit_check", True)
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
        pts, is_closed, _has_bulge = points_from_dxf_polyline(ent)
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
            error_message=err_msg,
            has_bulge_approximation=_has_bulge
        )
        raw_parcels.append(parcel)

    # 3. Deterministic Sorting & ID Assignment
    def sort_key(p: Parcel):
        if p.geometry:
            minx, miny, maxx, maxy = p.geometry.bounds
            return (-maxy, minx)
        return (float('inf'), float('inf'))

    candidate_valid = [p for p in raw_parcels if p.status == "VALID"]
    invalid_parcels = [p for p in raw_parcels if p.status != "VALID"]

    candidate_valid.sort(key=sort_key)

    # Assign initial IDs to valid candidates before nested ring detection
    for i, p in enumerate(candidate_valid, start=1):
        p.parcel_id = f"{prefix}{i:0{digits}d}"

    # Detect Nested Rings / Holes
    detect_nested_rings(candidate_valid)

    # Re-separate final valid vs nested/invalid parcels
    final_valid_parcels = [p for p in candidate_valid if p.status == "VALID"]
    nested_parcels = [p for p in candidate_valid if p.status == "NESTED_RING_DETECTED"]

    # Re-assign error IDs for non-valid entities
    all_non_valid = invalid_parcels + nested_parcels
    for i, p in enumerate(all_non_valid, start=1):
        p.parcel_id = f"{prefix}_ERR_{i:02d}"

    all_parcels: List[Parcel] = final_valid_parcels + all_non_valid

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

    # 5. Generate Labeled DXF (Label only true valid parcels)
    labeled_dxf_path = output_dir_path / f"{stem}_labeled.dxf"
    export_labeled_dxf(
        doc=doc,
        parcels=final_valid_parcels,
        output_path=labeled_dxf_path,
        annotation_config=parcel_cfg.get("annotation", {})
    )

    # 5.5. Generate GeoJSON Export
    from planning_toolbox.gis.io.exporter import export_parcels_to_geojson
    geojson_path = output_dir_path / f"{stem}.geojson"
    gis_cfg = config.get("gis", {})
    normalize_to_meters = bool(gis_cfg.get("normalize_to_meters", False))
    coordinate_scale = area_scale ** 0.5 if normalize_to_meters else 1.0
    export_parcels_to_geojson(
        all_parcels,
        geojson_path,
        crs_name=gis_cfg.get("crs"),
        coordinate_units="Meters" if normalize_to_meters else unit_name,
        coordinate_scale=coordinate_scale,
    )

    # 6. Generate Summary Text Report
    open_count = sum(1 for p in raw_parcels if p.status == "OPEN")
    invalid_geom_count = sum(1 for p in raw_parcels if p.status in ("INVALID_GEOMETRY", "ZERO_AREA"))
    nested_count = len(nested_parcels)
    valid_count = len(final_valid_parcels)
    total_valid_m2 = sum(p.area_m2 for p in final_valid_parcels)
    total_valid_ha = sum(p.area_ha for p in final_valid_parcels)

    report_path = output_dir_path / f"{stem}_report.txt"
    report_content = (
        f"=== Planning Toolbox Parcel Analysis Report ===\n"
        f"Source DXF: {dxf_path.name}\n"
        f"Source SHA-256: {source_sha256_before}\n"
        f"Detected Unit: {unit_name}\n"
        f"-----------------------------------------------\n"
        f"DXF entities scanned: {scanned_entities_count}\n"
        f"Parcel candidates: {len(raw_parcels)}\n"
        f"Valid closed parcels: {valid_count}\n"
        f"Open polylines: {open_count}\n"
        f"Invalid geometry: {invalid_geom_count}\n"
        f"Nested/ambiguous rings: {nested_count}\n"
        f"-----------------------------------------------\n"
        f"Total valid area:\n"
        f"  {total_valid_m2:,.2f} m²\n"
        f"  {total_valid_ha:,.4f} ha\n"
        f"===============================================\n"
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    assert_file_unchanged(dxf_path, source_sha256_before)

    return all_parcels, labeled_dxf_path, csv_path, report_path
