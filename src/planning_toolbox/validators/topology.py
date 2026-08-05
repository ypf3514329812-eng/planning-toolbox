from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from shapely.geometry import Polygon, LineString
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry

@dataclass
class TopologyValidationResult:
    entity_index: int
    layer: str
    status: str            # 'VALID', 'OPEN', 'INVALID_GEOMETRY', 'ZERO_AREA'
    vertex_count: int
    error_message: Optional[str] = None
    is_simple: bool = True
    is_closed: bool = True

def validate_polyline_topology(entity, entity_index: int) -> TopologyValidationResult:
    """
    Validates a single DXF LWPOLYLINE or POLYLINE entity for topological integrity.
    Checks: vertex count, closure, self-intersection, validity.
    """
    layer = str(getattr(entity.dxf, "layer", "0"))
    pts, is_closed, _ = points_from_dxf_polyline(entity)

    if len(pts) < 3:
        return TopologyValidationResult(
            entity_index=entity_index,
            layer=layer,
            status="INVALID_GEOMETRY",
            vertex_count=len(pts),
            error_message="Polyline has fewer than 3 vertices.",
            is_simple=False,
            is_closed=is_closed
        )

    # Check line simplicity (self-intersection)
    line = LineString(pts + [pts[0]])
    is_simple = line.is_simple

    status, poly, err_msg = parse_parcel_geometry(pts, is_closed)

    return TopologyValidationResult(
        entity_index=entity_index,
        layer=layer,
        status=status,
        vertex_count=len(pts),
        error_message=err_msg,
        is_simple=is_simple,
        is_closed=is_closed
    )
