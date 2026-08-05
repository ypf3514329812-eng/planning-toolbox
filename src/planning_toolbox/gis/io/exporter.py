import json
from pathlib import Path
from typing import List, Dict, Any, Union
import shapely.geometry
from planning_toolbox.core.models.parcel import Parcel

def export_parcels_to_geojson(
    parcels: List[Parcel],
    output_path: Union[Path, str],
    crs_name: str = "EPSG:4326"
) -> Path:
    """
    Exports a list of Parcel objects to an RFC 7946 compliant GeoJSON FeatureCollection file.
    
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
                "area_m2": round(parcel.area_m2, 2),
                "area_ha": round(parcel.area_ha, 4),
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
        "crs": {
            "type": "name",
            "properties": {
                "name": f"urn:ogc:def:crs:OGC:1.3:CRS84" if crs_name in ("EPSG:4326", "WGS84") else crs_name
            }
        },
        "features": features
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)

    return out_file
