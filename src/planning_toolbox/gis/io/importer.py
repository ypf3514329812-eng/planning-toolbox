import json
import logging
from pathlib import Path
from typing import Union, List, Tuple, Dict, Any
import ezdxf
import shapely.geometry

logger = logging.getLogger("planning_toolbox")

class GISImportError(Exception):
    """Raised when GeoJSON parsing or import fails."""
    pass

def import_geojson_to_dxf(
    geojson_path: Union[Path, str],
    output_dxf_path: Union[Path, str],
    target_layer: str = "PARCEL_FROM_GIS"
) -> Tuple[Path, Dict[str, Any]]:
    """
    Imports vector boundary polygons from a GeoJSON file into a DXF drawing.
    Converts GeoJSON Polygon and MultiPolygon geometries into LWPOLYLINE entities.
    
    Returns:
      (output_path, import_stats)
      import_stats contains: total_features, imported_polygons, skipped_unsupported, skipped_errors
    """
    src_file = Path(geojson_path).resolve()
    if not src_file.exists():
        raise GISImportError(f"GeoJSON source file not found: {src_file}")

    out_file = Path(output_dxf_path).resolve()
    if out_file == src_file:
        raise ValueError(
            f"Output DXF path ({out_file}) cannot be identical to source GeoJSON path ({src_file}). "
            f"Direct overwrite is forbidden for data safety."
        )

    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(src_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise GISImportError(f"Failed to parse GeoJSON file {src_file}: {str(e)}")

    features = data.get("features", []) if data.get("type") == "FeatureCollection" else [data]

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # Meters
    if target_layer not in doc.layers:
        doc.layers.add(name=target_layer, color=3)  # Color 3 = Green

    msp = doc.modelspace()
    polyline_count = 0
    skipped_unsupported = 0
    skipped_errors = 0

    for feat_idx, feat in enumerate(features):
        geom_dict = feat.get("geometry")
        if not geom_dict:
            logger.warning(f"Feature #{feat_idx}: 几何体为空，已跳过。")
            skipped_errors += 1
            continue

        geom_type = geom_dict.get("type", "unknown")
        try:
            poly_obj = shapely.geometry.shape(geom_dict)
        except Exception as e:
            logger.warning(f"Feature #{feat_idx}: 几何体解析失败 ({geom_type}): {e}，已跳过。")
            skipped_errors += 1
            continue

        # Extract coordinates for Polygons and MultiPolygons
        polygons: List[Any] = []
        if isinstance(poly_obj, shapely.geometry.Polygon):
            polygons.append(poly_obj)
        elif isinstance(poly_obj, shapely.geometry.MultiPolygon):
            polygons.extend(poly_obj.geoms)
        else:
            logger.warning(
                f"Feature #{feat_idx}: 不支持的几何类型 '{geom_type}'，"
                f"仅支持 Polygon/MultiPolygon。已跳过。"
            )
            skipped_unsupported += 1
            continue

        for poly in polygons:
            # Exterior ring
            exterior_pts: List[Tuple[float, float]] = [(p[0], p[1]) for p in poly.exterior.coords]
            if len(exterior_pts) > 2:
                # Remove redundant duplicate closing point if present
                if (
                    abs(exterior_pts[0][0] - exterior_pts[-1][0]) < 1e-5 and
                    abs(exterior_pts[0][1] - exterior_pts[-1][1]) < 1e-5
                ):
                    exterior_pts.pop()
                lw = msp.add_lwpolyline(exterior_pts, dxfattribs={"layer": target_layer})
                lw.close(True)
                polyline_count += 1

            # Interior rings (holes)
            for interior in poly.interiors:
                interior_pts = [(p[0], p[1]) for p in interior.coords]
                if len(interior_pts) > 2:
                    if (
                        abs(interior_pts[0][0] - interior_pts[-1][0]) < 1e-5 and
                        abs(interior_pts[0][1] - interior_pts[-1][1]) < 1e-5
                    ):
                        interior_pts.pop()
                    lw = msp.add_lwpolyline(interior_pts, dxfattribs={"layer": target_layer})
                    lw.close(True)
                    polyline_count += 1

    import_stats = {
        "total_features": len(features),
        "imported_polygons": polyline_count,
        "skipped_unsupported": skipped_unsupported,
        "skipped_errors": skipped_errors,
    }

    if skipped_unsupported > 0 or skipped_errors > 0:
        logger.warning(
            f"GeoJSON 导入完成: {polyline_count} 个多边形已导入, "
            f"{skipped_unsupported} 个不支持类型已跳过, "
            f"{skipped_errors} 个解析错误已跳过。"
        )

    doc.saveas(out_file)
    return out_file, import_stats
