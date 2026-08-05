import json
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import shapely.geometry
from planning_toolbox.core.models.parcel import Parcel

def export_parcels_to_geojson(
    parcels: List[Parcel],
    output_path: Union[Path, str],
    crs_name: Optional[str] = None,
    coordinate_units: Optional[str] = None,
) -> Path:
    """
    Exports a list of Parcel objects to a GeoJSON FeatureCollection file.

    No CRS is declared by default. CAD coordinates are often local/projected
    coordinates, and labeling them as WGS84 without a transformation would
    make the output look valid while placing it in the wrong location. When a
    caller has independently verified the CRS, it may pass ``crs_name``; this
    function labels coordinates but does not transform them.
    
    Includes feature properties:
      - parcel_id
      - source_layer
      - area_m2
      - area_ha
      - geometry_status
      - error_message
      - has_bulge_approximation
      
    Returns:
      Path object pointing to the written .geojson file.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    features: List[Dict[str, Any]] = []
    for parcel in parcels:
        if parcel.geometry and not parcel.geometry.is_empty:
            geom_dict = shapely.geometry.mapping(parcel.geometry)
        else:
            geom_dict = None

        feature = {
            "type": "Feature",
            "properties": {
                "parcel_id": parcel.parcel_id,
                "source_layer": parcel.source_layer,
                "area_m2": round(parcel.area_m2, 2) if parcel.status == "VALID" else 0.0,
                "area_ha": round(parcel.area_ha, 4) if parcel.status == "VALID" else 0.0,
                "geometry_status": parcel.status,
                "error_message": parcel.error_message or "",
                "has_bulge_approximation": parcel.has_bulge_approximation
            },
            "geometry": geom_dict
        }
        features.append(feature)

    geojson_data = {
        "type": "FeatureCollection",
        "name": out_file.stem,
        "planning_toolbox_metadata": {
            "coordinate_reference_system": crs_name or "UNKNOWN",
            "coordinate_units": coordinate_units or "UNKNOWN",
            "coordinate_transform_applied": False,
        },
        "features": features
    }

    if crs_name:
        geojson_data["crs"] = {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
                if crs_name in ("EPSG:4326", "WGS84") else crs_name
            }
        }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)

    return out_file
