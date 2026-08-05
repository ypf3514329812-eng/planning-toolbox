from dataclasses import dataclass
from typing import Optional, List, Tuple
from shapely.geometry import Polygon

@dataclass
class SetbackCheckResult:
    parcel_id: str
    required_setback_m: float
    building_inside_setback: bool
    violations_count: int
    min_distance_m: float
    status: str                       # 'COMPLIANT', 'VIOLATION', 'NO_BUILDING'
    error_message: Optional[str] = None

def check_building_setback(
    parcel_polygon: Polygon,
    building_polygons: List[Polygon],
    required_setback_m: float,
    parcel_id: str = "P001"
) -> SetbackCheckResult:
    """
    Checks whether building footprints satisfy the required setback distance (建筑退线距离)
    from the parcel boundary red line (用地红线).
    
    Computes setback polygon using negative buffer:
      setback_polygon = parcel_polygon.buffer(-required_setback_m)
      
    If any building footprint extends outside the setback polygon, it is flagged as a VIOLATION.
    """
    if not building_polygons:
        return SetbackCheckResult(
            parcel_id=parcel_id,
            required_setback_m=required_setback_m,
            building_inside_setback=False,
            violations_count=0,
            min_distance_m=0.0,
            status="NO_BUILDING",
            error_message="No building footprints found within parcel."
        )

    # Compute interior setback boundary polygon
    setback_poly = parcel_polygon.buffer(-required_setback_m)
    if setback_poly.is_empty:
        return SetbackCheckResult(
            parcel_id=parcel_id,
            required_setback_m=required_setback_m,
            building_inside_setback=False,
            violations_count=len(building_polygons),
            min_distance_m=0.0,
            status="VIOLATION",
            error_message=f"Required setback ({required_setback_m}m) exceeds total parcel dimension."
        )

    violations = 0
    min_dist_to_boundary = float("inf")

    for b_poly in building_polygons:
        # Distance from building to parcel boundary
        dist = b_poly.distance(parcel_polygon.exterior)
        if dist < min_dist_to_boundary:
            min_dist_to_boundary = dist

        # Check if building footprint is completely contained within the setback polygon
        if not setback_poly.contains(b_poly):
            violations += 1

    if violations > 0:
        return SetbackCheckResult(
            parcel_id=parcel_id,
            required_setback_m=required_setback_m,
            building_inside_setback=False,
            violations_count=violations,
            min_distance_m=round(min_dist_to_boundary, 2),
            status="VIOLATION",
            error_message=f"{violations} building footprint(s) violate the {required_setback_m}m setback requirement (Min dist: {min_dist_to_boundary:.2f}m)."
        )

    return SetbackCheckResult(
        parcel_id=parcel_id,
        required_setback_m=required_setback_m,
        building_inside_setback=True,
        violations_count=0,
        min_distance_m=round(min_dist_to_boundary, 2),
        status="COMPLIANT"
    )
