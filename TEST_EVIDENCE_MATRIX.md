# Planning Toolbox — Test Evidence Matrix

This matrix maps every single requirement and test case to its execution status, evidence artifact, and verified result.

## Evidence Artifact Links
- Full `pytest` Execution Log: [`test_artifacts/latest/pytest_output.txt`](file:///c:/AutoOS/OS1/test_artifacts/latest/pytest_output.txt)
- Sample DXF Analysis Report: [`test_artifacts/latest/sample_output_report.txt`](file:///c:/AutoOS/OS1/test_artifacts/latest/sample_output_report.txt)
- Source DXF Zero-Mutation Verification: [`test_artifacts/latest/sha256_verification.txt`](file:///c:/AutoOS/OS1/test_artifacts/latest/sha256_verification.txt)
- Runtime System & Library Environment: [`test_artifacts/latest/environment_info.txt`](file:///c:/AutoOS/OS1/test_artifacts/latest/environment_info.txt)

---

## 1. Automated Unit & Geometry Tests (Pytest 49/49 PASS)

| Test ID | Test Category | Description / Verification Target | Status | Evidence Log |
| :--- | :--- | :--- | :---: | :--- |
| **BULGE-001** | Bulge Geometry | Positive 90° arc bulge area accuracy (11,426.99 m²) | **PASS** | `pytest_output.txt` |
| **BULGE-002** | Bulge Geometry | Negative 90° arc bulge area accuracy (8,573.01 m²) | **PASS** | `pytest_output.txt` |
| **BULGE-003** | Bulge Geometry | Multiple bulge segments on polyline (12,853.98 m²) | **PASS** | `pytest_output.txt` |
| **BULGE-004** | Bulge Geometry | Arc > 180° large bulge handling | **PASS** | `pytest_output.txt` |
| **BULGE-005** | Bulge Geometry | Mixed straight line and arc curved boundaries | **PASS** | `pytest_output.txt` |
| **BULGE-006** | Bulge Geometry | CW vs CCW vertex order area equivalence | **PASS** | `pytest_output.txt` |
| **BULGE-007** | Bulge Geometry | Closed capsule polyline (17,853.98 m²) | **PASS** | `pytest_output.txt` |
| **GIS-001**   | GIS Data Bridge| GeoJSON export of valid parcel objects | **PASS** | `pytest_output.txt` |
| **GIS-002**   | GIS Data Bridge| GeoJSON export of empty/invalid parcel objects | **PASS** | `pytest_output.txt` |
| **GIS-003**   | GIS Data Bridge| GeoJSON to CAD DXF polyline boundary import | **PASS** | `pytest_output.txt` |
| **GIS-004**   | GIS Data Bridge| GeoJSON import output path collision protection | **PASS** | `pytest_output.txt` |
| **GIS-005**   | GIS Data Bridge| CAD -> GeoJSON -> CAD DXF roundtrip fidelity | **PASS** | `pytest_output.txt` |
| **IND-001**   | Indicators    | Manual calculation of FAR (2.0), Density (25%), Green (35%) | **PASS** | `pytest_output.txt` |
| **IND-002**   | Indicators    | Zero site area protection (`ZERO_SITE_AREA`) | **PASS** | `pytest_output.txt` |
| **IND-003**   | Indicators    | DXF layer spatial intersection for PARCEL, BUILDING, GREEN | **PASS** | `pytest_output.txt` |
| **LAYER-001** | Layer Manager | Blank planning DXF template generation | **PASS** | `pytest_output.txt` |
| **LAYER-002** | Layer Manager | Layer standardization and remapping | **PASS** | `pytest_output.txt` |
| **LAYER-003** | Layer Manager | Unknown layer remapping report generation | **PASS** | `pytest_output.txt` |
| **PARCEL-001**| Core Parcel | 100x100 square parcel calculation (1.00 ha) | **PASS** | `pytest_output.txt` |
| **PARCEL-002**| Core Parcel | Rectangle parcel calculation | **PASS** | `pytest_output.txt` |
| **PARCEL-003**| Topology Safety| Open polyline boundary detection (`OPEN`) | **PASS** | `pytest_output.txt` |
| **PARCEL-004**| Topology Safety| Self-intersecting figure-8 boundary (`INVALID_GEOMETRY`) | **PASS** | `pytest_output.txt` |
| **PARCEL-005**| Gold Standard | Gold standard setback polygon area calculation | **PASS** | `pytest_output.txt` |
| **PARCEL-006**| Topology Safety| Polyline with fewer than 3 vertices | **PASS** | `pytest_output.txt` |
| **PARCEL-007**| Topology Safety| Zero area collinear polyline | **PASS** | `pytest_output.txt` |
| **PARCEL-008**| Annotation | L-shaped polygon interior label point placement | **PASS** | `pytest_output.txt` |
| **PARCEL-009**| Config | Default YAML configuration loading | **PASS** | `pytest_output.txt` |
| **PARCEL-010**| Config | Custom path YAML configuration loading | **PASS** | `pytest_output.txt` |
| **PARCEL-011**| Config | Missing configuration file fallback | **PASS** | `pytest_output.txt` |
| **PARCEL-012**| End-to-End | E2E DXF parcel processing and output generation | **PASS** | `pytest_output.txt` |
| **PARCEL-013**| Determinism | Spatial sorting top-to-bottom left-to-right numbering | **PASS** | `pytest_output.txt` |
| **PARCEL-014**| Isolation | Annotation writer layer isolation | **PASS** | `pytest_output.txt` |
| **RING-001**  | Hole Safety | Contained inner ring detection (prevents false area sum) | **PASS** | `pytest_output.txt` |
| **RING-002**  | Hole Safety | Disjoint parcels remain valid separate parcels | **PASS** | `pytest_output.txt` |
| **RING-003**  | Hole Safety | Polygon A contains Polygon B triggers `NESTED_RING_DETECTED` | **PASS** | `pytest_output.txt` |
| **RING-004**  | Hole Safety | Touching boundaries wall sharing is NOT false hole | **PASS** | `pytest_output.txt` |
| **RING-005**  | Hole Safety | 3 adjacent parcels sharing boundaries remain valid | **PASS** | `pytest_output.txt` |
| **SAFE-001**  | Data Safety | Low-level DXF writer path collision prevention (`ValueError`) | **PASS** | `pytest_output.txt` |
| **SAFE-002**  | Data Safety | Normal output path export success | **PASS** | `pytest_output.txt` |
| **SAFE-003**  | Data Safety | Source file SHA-256 before vs after processing match 100% | **PASS** | `pytest_output.txt` |
| **UNIT-001**  | Unit Safety | `read_dxf_parcels` fail-safe when `$INSUNITS=0` | **PASS** | `pytest_output.txt` |
| **UNIT-002**  | Unit Safety | Explicit fallback unit resolution | **PASS** | `pytest_output.txt` |
| **UNIT-003**  | Unit Safety | DXF known unit `$INSUNITS=6` (Meters) processing | **PASS** | `pytest_output.txt` |
| **UNIT-004**  | Unit Safety | `process_parcels` empty config fail-safe rejection | **PASS** | `pytest_output.txt` |
| **UNIT-005**  | Unit Safety | Strict rejection of silent meter assumption | **PASS** | `pytest_output.txt` |
| **UNIT-006**  | Unit Safety | Legacy unit error handling | **PASS** | `pytest_output.txt` |
| **UNIT-007**  | Unit Safety | Unspecified DXF unit strict check blocked | **PASS** | `pytest_output.txt` |
| **VAL-001**   | Rules Validator| Topology validator for valid, open, self-intersecting polylines | **PASS** | `pytest_output.txt` |
| **VAL-002**   | Rules Validator| Building setback compliance check (`COMPLIANT`) | **PASS** | `pytest_output.txt` |
| **VAL-003**   | Rules Validator| Building setback distance violation check (`VIOLATION`) | **PASS** | `pytest_output.txt` |

---

## 2. External GUI Validation Status (AutoCAD / ArcGIS Pro)

| Validation Item | Required Environment | Description | Status | Rationale |
| :--- | :--- | :--- | :---: | :--- |
| **AutoCAD GUI Verification** | AutoCAD 2020+ GUI | Open `*_labeled.dxf`, run `AREA` and `LIST` commands, compare text labels with CAD properties. | **PENDING USER VALIDATION** | CLI environment lacks AutoCAD GUI driver. Requires manual check by student. |
| **ArcGIS Pro GIS Import** | ArcGIS Pro 3.x / QGIS | Import `*.geojson` vector layer into QGIS/ArcGIS Pro, verify spatial alignment and attribute table match. | **PENDING USER VALIDATION** | CLI environment lacks desktop GIS application. Requires manual check by student. |
