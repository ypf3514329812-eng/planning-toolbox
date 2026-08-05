import csv
import math
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union
import shapely.geometry
from shapely.ops import unary_union
from planning_toolbox.core.models.parcel import Parcel
from planning_toolbox.indicators.models import PlanningParcelIndicators
from planning_toolbox.cad.io.dxf_reader import read_dxf_parcels
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry

def calculate_parcel_indicators(
    parcel_id: str,
    site_area_m2: float,
    building_footprint_m2: float = 0.0,
    total_building_m2: float = 0.0,
    green_area_m2: float = 0.0,
    max_height_m: float = 0.0
) -> PlanningParcelIndicators:
    """
    Computes urban planning indicators (FAR, Building Density %, Green Ratio %) for a single parcel.
    """
    values = {
        "site_area_m2": site_area_m2,
        "building_footprint_m2": building_footprint_m2,
        "total_building_m2": total_building_m2,
        "green_area_m2": green_area_m2,
        "max_height_m": max_height_m,
    }
    for name, value in values.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite, non-negative number.")
    if site_area_m2 > 0 and building_footprint_m2 > site_area_m2 + 1e-6:
        raise ValueError("building_footprint_m2 cannot exceed site_area_m2.")
    if site_area_m2 > 0 and green_area_m2 > site_area_m2 + 1e-6:
        raise ValueError("green_area_m2 cannot exceed site_area_m2.")

    ind = PlanningParcelIndicators(
        parcel_id=parcel_id,
        site_area_m2=site_area_m2,
        site_area_ha=site_area_m2 / 10000.0 if site_area_m2 > 0 else 0.0,
        building_footprint_m2=building_footprint_m2,
        total_building_m2=total_building_m2,
        green_area_m2=green_area_m2,
        max_building_height_m=max_height_m
    )
    ind.compute_derived_metrics()
    return ind


def process_dxf_indicators(
    dxf_path: Union[Path, str],
    config: Optional[Dict[str, Any]] = None,
    output_dir: Optional[Union[Path, str]] = None
) -> Tuple[List[PlanningParcelIndicators], Path, Path]:
    """
    Scans a DXF file for parcel boundaries and internal building/green polylines.
    Computes site areas, building footprints, green areas, FAR, Building Density %, and Green Ratio %.
    
    Generates:
      - CSV summary report
      - Text summary report
      
    Returns:
      (indicators_list, csv_path, report_path)
    """
    path = Path(dxf_path)
    out_dir = Path(output_dir) if output_dir else path.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_cfg = dict(config or {})
    parcel_cfg = base_cfg.get("parcel", {})
    cfg = {**parcel_cfg, **base_cfg}
    parcel_layer = cfg.get("parcel_layer", "PARCEL")
    building_layer = cfg.get("building_layer", "BUILDING")
    green_layer = cfg.get("green_layer", "GREEN")
    default_floors = cfg.get("default_floors")
    if default_floors is not None:
        if not isinstance(default_floors, (int, float)) or not math.isfinite(default_floors) or default_floors <= 0:
            raise ValueError("default_floors must be a positive, finite number when provided.")

    fallback_unit = cfg.get("fallback_unit", None)
    strict_unit = cfg.get("strict_unit_check", True)

    doc, entities_info, unit_name, scale = read_dxf_parcels(
        dxf_path=path,
        target_layers=[parcel_layer, building_layer, green_layer],
        fallback_unit=fallback_unit,
        strict_unit_check=strict_unit
    )

    parcel_geoms: List[Tuple[str, shapely.geometry.Polygon]] = []
    building_geoms: List[shapely.geometry.Polygon] = []
    green_geoms: List[shapely.geometry.Polygon] = []

    # Separate entities by layer
    for info in entities_info:
        ent = info["entity"]
        layer_upper = info["layer"].upper()
        pts, is_closed, _ = points_from_dxf_polyline(ent)
        status, poly, _ = parse_parcel_geometry(pts, is_closed)

        if status == "VALID" and poly:
            if layer_upper == parcel_layer.upper():
                parcel_geoms.append((f"P{len(parcel_geoms)+1:03d}", poly))
            elif layer_upper == building_layer.upper():
                building_geoms.append(poly)
            elif layer_upper == green_layer.upper():
                green_geoms.append(poly)

    if building_geoms and default_floors is None:
        raise ValueError(
            "DXF 指标计算发现建筑轮廓，但未提供楼层数；请通过 --floors 或配置项 default_floors 明确指定。"
        )

    results: List[PlanningParcelIndicators] = []

    for pid, p_poly in parcel_geoms:
        site_area = p_poly.area * scale

        # Calculate building footprint inside this parcel (bbox pre-filter)
        p_bounds = p_poly.bounds  # (minx, miny, maxx, maxy)
        building_pieces = []
        for b_poly in building_geoms:
            bb = b_poly.bounds
            # Skip if bounding boxes don't overlap
            if bb[2] < p_bounds[0] or bb[0] > p_bounds[2] or bb[3] < p_bounds[1] or bb[1] > p_bounds[3]:
                continue
            if p_poly.intersects(b_poly):
                inter = p_poly.intersection(b_poly)
                if not inter.is_empty:
                    building_pieces.append(inter)
        b_footprint = unary_union(building_pieces).area * scale if building_pieces else 0.0

        # Calculate green area inside this parcel (bbox pre-filter)
        green_pieces = []
        for g_poly in green_geoms:
            gb = g_poly.bounds
            if gb[2] < p_bounds[0] or gb[0] > p_bounds[2] or gb[3] < p_bounds[1] or gb[1] > p_bounds[3]:
                continue
            if p_poly.intersects(g_poly):
                inter = p_poly.intersection(g_poly)
                if not inter.is_empty:
                    green_pieces.append(inter)
        g_area = unary_union(green_pieces).area * scale if green_pieces else 0.0

        total_b_area = b_footprint * default_floors if default_floors is not None else 0.0

        ind = calculate_parcel_indicators(
            parcel_id=pid,
            site_area_m2=site_area,
            building_footprint_m2=b_footprint,
            total_building_m2=total_b_area,
            green_area_m2=g_area
        )
        results.append(ind)

    # Write CSV Report
    stem = path.stem
    csv_path = out_dir / f"{stem}_indicators.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = [
            "parcel_id", "site_area_m2", "site_area_ha", "building_footprint_m2",
            "total_building_m2", "green_area_m2", "far", "building_density_pct",
            "green_ratio_pct", "status", "error_message"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())

    # Write Text Report
    report_path = out_dir / f"{stem}_indicators_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"=== Planning Toolbox Urban Indicators Report ===\n")
        f.write(f"Source File: {path.name}\n")
        f.write(f"Parcels Analyzed: {len(results)}\n")
        f.write(f"Detected CAD unit: {unit_name}\n")
        f.write(f"Area scale to square meters: {scale:g}\n")
        if default_floors is not None:
            f.write(f"Building floor multiplier: {default_floors:g} (explicit input)\n")
        else:
            f.write("Building floor multiplier: not applicable (no building footprints)\n")
        f.write(f"---------------------------------------------------\n")
        for r in results:
            f.write(
                f"[{r.parcel_id}] 用地面积: {r.site_area_m2:,.2f} m² ({r.site_area_ha:.4f} ha) | "
                f"FAR (容积率): {r.far:.2f} | "
                f"密度: {r.building_density_pct:.2f}% | "
                f"绿地率: {r.green_ratio_pct:.2f}%\n"
            )
        f.write(f"===================================================\n")

    return results, csv_path, report_path
