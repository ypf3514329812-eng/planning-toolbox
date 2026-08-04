from dataclasses import dataclass, field
from typing import Optional, Tuple, Any
from shapely.geometry import Polygon, Point

@dataclass
class Parcel:
    parcel_id: str
    source_layer: str
    status: str  # 'VALID', 'OPEN', 'INVALID_GEOMETRY', 'ZERO_AREA'
    raw_area: float = 0.0
    area_m2: float = 0.0
    area_ha: float = 0.0
    geometry: Optional[Polygon] = None
    label_point: Optional[Tuple[float, float]] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "parcel_id": self.parcel_id,
            "source_layer": self.source_layer,
            "area_m2": round(self.area_m2, 2) if self.status == "VALID" else 0.0,
            "area_ha": round(self.area_ha, 4) if self.status == "VALID" else 0.0,
            "geometry_status": self.status,
            "error_message": self.error_message or "",
        }
