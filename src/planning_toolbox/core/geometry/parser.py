from typing import Tuple, Optional, List
import math
from shapely.geometry import Polygon, Point, LineString
from shapely.validation import explain_validity

def points_from_dxf_polyline(entity) -> Tuple[List[Tuple[float, float]], bool]:
    """
    Extracts 2D points and closed state from an ezdxf LWPOLYLINE or POLYLINE entity.
    Handles bulges (arc segments) cleanly.
    """
    is_closed = getattr(entity, "is_closed", False)
    
    # Try using ezdxf path module if available for arc bulge expansion
    try:
        import ezdxf.path
        path = ezdxf.path.make_path(entity)
        # Flatten path to vertices
        vertices = [ (p.x, p.y) for p in path.flattening(distance=0.01) ]
        if len(vertices) > 1 and math.hypot(vertices[0][0] - vertices[-1][0], vertices[0][1] - vertices[-1][1]) < 1e-5:
            # Drop redundant duplicate last point if closed
            vertices.pop()
            is_closed = True
        return vertices, is_closed
    except Exception:
        # Fallback to direct vertex reading
        if entity.dxftype() == 'LWPOLYLINE':
            pts = [(v[0], v[1]) for v in entity.get_points(format='xy')]
        elif entity.dxftype() == 'POLYLINE':
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        else:
            pts = []
        
        if len(pts) > 2:
            if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-5:
                pts.pop()
                is_closed = True
        return pts, is_closed

def parse_parcel_geometry(pts: List[Tuple[float, float]], is_closed: bool) -> Tuple[str, Optional[Polygon], Optional[str]]:
    """
    Validates polyline points and builds a Shapely Polygon.
    Returns (status, polygon_obj, error_message).
    Status can be: 'VALID', 'OPEN', 'INVALID_GEOMETRY', 'ZERO_AREA'
    """
    if len(pts) < 3:
        return ("INVALID_GEOMETRY", None, "Polyline has fewer than 3 vertices.")
    
    if not is_closed:
        # Check if first and last points are identical within 1e-4
        if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
            return ("OPEN", None, "Polyline boundary is not closed.")
    
    # Check line self-intersection (LineString is_simple)
    line = LineString(pts + [pts[0]])
    if not line.is_simple:
        return ("INVALID_GEOMETRY", None, "Self-intersecting polyline boundary.")

    try:
        poly = Polygon(pts)
        if not poly.is_valid:
            reason = explain_validity(poly)
            return ("INVALID_GEOMETRY", None, f"Invalid geometry topology: {reason}")
        
        if poly.area <= 1e-6:
            return ("ZERO_AREA", None, "Polygon has zero or negligible area.")
            
        return ("VALID", poly, None)
    except Exception as e:
        return ("INVALID_GEOMETRY", None, f"Geometry parsing error: {str(e)}")

def get_interior_label_point(poly: Polygon) -> Tuple[float, float]:
    """
    Returns a 2D coordinate inside the polygon.
    Uses representative_point() which is guaranteed to lie within the geometry.
    """
    pt = poly.representative_point()
    return (pt.x, pt.y)
