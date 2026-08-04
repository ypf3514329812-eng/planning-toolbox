# Planning Toolbox Test Report

## Overall 状态
PASS

## Git
- **Branch**: main
- **Commit**: `ce39215`
- **Working tree**: Clean
- **Recovery point**: Tags `v0.1.0-mvp1`, `v0.1.1-optimized`

## Environment
- **Python**: 3.13.9 (Windows 11 x64)
- **OS**: Windows
- **Dependencies**: ezdxf (1.4.4), shapely (2.1.2), pyyaml (6.0.3), pytest (8.4.2)
- **Path Dependencies**: Zero machine-specific absolute paths or unrecorded environment variables.

## Automated Tests
- **Total**: 15
- **Passed**: 15
- **Failed**: 0
- **Skipped**: 0
- **Warnings**: 0
- **Execution time**: 1.92 s

## End-to-End Test
- **Input**: `sample_data/sample_parcels.dxf`
- **Output**: 
  - `output/sample_parcels_labeled.dxf`
  - `output/sample_parcels.csv`
  - `output/sample_parcels_report.txt`
- **Result**: PASS (3 valid parcels processed, 2 errors identified, total 2.8573 ha, original file untouched).

## Geometry Accuracy
- **GS-001 (100m x 100m Square)**: $10,000.00\,\text{m}^2$ ($1.0000\text{ ha}$) — PASS
- **GS-002 (200m x 50m Rectangle)**: $10,000.00\,\text{m}^2$ ($1.0000\text{ ha}$) — PASS
- **GS-003 (5m Setback Interior)**: $8,100.00\,\text{m}^2$ — PASS
- **Bulge Arc Geometry (90° Arc)**: $8,573.39\,\text{m}^2$ — PASS (<0.001% tolerance vs mathematical theoretical area)

## Error Handling
- **未闭合 Polyline**: PASS (Status reported as `OPEN`, area calculation refused)
- **Self-Intersecting / Bow-tie Polygon**: PASS (Status reported as `INVALID_GEOMETRY`, area calculation refused)
- **Empty DXF**: PASS (Gracefully processed 0 entities without crash)
- **Missing Target Layer**: PASS (Safely ignored non-matching layers)
- **Unknown Units**: PASS (`strict_unit_check` raised `UnitError` on $INSUNITS=0)
- **Non-parcel Layers (ROAD, BUILDING, TEXT)**: PASS (Layers filtered strictly, non-parcel entities ignored)

## Output Validation
- **CSV**: Field names (`parcel_id`, `source_layer`, `area_m2`, `area_ha`, `geometry_status`, `error_message`), `utf-8-sig` BOM encoding for Excel, float precision rounded.
- **DXF**: `output/sample_parcels_labeled.dxf` successfully reopened with ezdxf; layer `PARCEL_LABEL` created with yellow MTEXT labels at interior polygon points.
- **Report**: Human-readable text report accurately formatted.

## Regression
- **状态**: PASS (All 15 unit and integration tests passing).

## Performance
- **10 parcels**: 0.079 s
- **100 parcels**: 0.139 s
- **1000 parcels**: 0.886 s (<1 second total processing time)

## Known Limitations
- Nested CAD Blocks (INSERT / BLOCK references) containing polylines require exploding prior to boundary extraction (planned for Phase 2).
- Polyline3D entities are ignored in favor of 2D LWPOLYLINE / POLYLINE.

## Bugs Found
- **P0**: None
- **P1**: None
- **P2**: None
- **P3**: None

## Fixes Made
- Commit `ce39215`: Added missing `__init__.py` files across all subpackages, added bulge fallback logging warning, set strict unit check default, updated CLI flags, expanded test suite to 15 cases.

## Codex Required?
NO
