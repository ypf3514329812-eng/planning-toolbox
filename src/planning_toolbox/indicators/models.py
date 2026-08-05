from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class PlanningParcelIndicators:
    """
    Data model for urban planning parcel development indicators.
    """
    parcel_id: str
    site_area_m2: float                      # 用地面积 (m²)
    site_area_ha: float                      # 用地面积 (ha)
    building_footprint_m2: float = 0.0       # 建筑占地面积 / 建筑基底面积 (m²)
    total_building_m2: float = 0.0           # 总建筑面积 (m²)
    green_area_m2: float = 0.0               # 绿化/绿地面积 (m²)
    max_building_height_m: float = 0.0       # 最大建筑高度 (m)

    # Derived Urban Planning Indicators
    far: float = 0.0                         # 容积率 (Floor Area Ratio)
    building_density_pct: float = 0.0        # 建筑密度 (%)
    green_ratio_pct: float = 0.0             # 绿地率 (%)
    status: str = "VALID"
    error_message: Optional[str] = None

    def compute_derived_metrics(self) -> None:
        """
        Computes FAR, Building Density (%), and Green Ratio (%) based on site area.
        Handles zero site area safely.
        """
        if self.site_area_m2 <= 1e-6:
            self.far = 0.0
            self.building_density_pct = 0.0
            self.green_ratio_pct = 0.0
            self.status = "ZERO_SITE_AREA"
            self.error_message = "Site area is zero or negligible. Cannot compute indicators."
            return

        self.site_area_ha = self.site_area_m2 / 10000.0
        self.far = round(self.total_building_m2 / self.site_area_m2, 2)
        self.building_density_pct = round((self.building_footprint_m2 / self.site_area_m2) * 100.0, 2)
        self.green_ratio_pct = round((self.green_area_m2 / self.site_area_m2) * 100.0, 2)
        self.status = "VALID"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parcel_id": self.parcel_id,
            "site_area_m2": round(self.site_area_m2, 2),
            "site_area_ha": round(self.site_area_ha, 4),
            "building_footprint_m2": round(self.building_footprint_m2, 2),
            "total_building_m2": round(self.total_building_m2, 2),
            "green_area_m2": round(self.green_area_m2, 2),
            "far": self.far,
            "building_density_pct": self.building_density_pct,
            "green_ratio_pct": self.green_ratio_pct,
            "status": self.status,
            "error_message": self.error_message or ""
        }
