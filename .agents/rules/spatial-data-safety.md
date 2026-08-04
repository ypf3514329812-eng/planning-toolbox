# Spatial Data Safety Rule

- **Explicit Units**: Never assume 1 CAD unit = 1 meter without verification. If DXF header unit (`$INSUNITS`) is missing or unknown, require user configuration or prompt.
- **Explicit CRS**: Spatial calculations (distance, area) must verify Coordinate Reference Systems. Never calculate $m^2$ directly in geographic angular coordinates (lat/lon).
- **Topology Safety**: Validate closed polygons, check self-intersections, and handle arc/bulge curve geometry without silent loss of precision.
- **Non-Destructive DXF Editing**: Original CAD files must never be overwritten. Always generate output files (e.g. `*_labeled.dxf`).
