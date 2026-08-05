"""Planning Toolbox (城乡规划 CAD–GIS 自动化辅助工具箱)"""

__version__ = "0.6.0"

# Public API surface
from planning_toolbox.cad.parcels.calculator import process_parcels, detect_nested_rings
from planning_toolbox.indicators.calculator import calculate_parcel_indicators, process_dxf_indicators
from planning_toolbox.gis.io.exporter import export_parcels_to_geojson
from planning_toolbox.gis.io.importer import import_geojson_to_dxf
from planning_toolbox.validators.topology import validate_polyline_topology
from planning_toolbox.validators.setback import check_building_setback
