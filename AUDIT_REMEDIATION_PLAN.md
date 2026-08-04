# Planning Toolbox — AUDIT REMEDIATION PLAN (RC1 Stable Gate)

Based on the independent technical audit documented in `CODEX_PROJECT_AUDIT.md`.

## Remediation Item Matrix

| Codex Finding ID | Severity | Description | Affected Files | Proposed Fix | Regression Test | Evidence Artifact | Status |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **P1-01** | P1 | Low-level API (`process_parcels`, `read_dxf_parcels`) defaults to `fallback_unit="m"`, `strict_unit_check=False` | `calculator.py`<br>`dxf_reader.py` | Change API function parameter defaults to `fallback_unit=None`, `strict_unit_check=True`. If unit is unknown and no explicit fallback is provided, raise `UnitError` (BLOCKED). | `tests/test_units.py`<br>(UNIT-001 to UNIT-005) | `pytest_output.txt` | **IN_PROGRESS** |
| **P1-02** | P1 | Nested rings (outer polygon containing inner polygon) are parsed as separate parcels and summed, producing false total area | `parser.py`<br>`calculator.py`<br>`parcel.py` | Add `detect_nested_rings()` geometry check. Flag contained inner rings with status `NESTED_RING_DETECTED`, set error msg, exclude from `VALID` sum, and report in summary. | `tests/test_parcel_calculator.py`<br>(RING-001 to RING-005) | `pytest_output.txt`<br>`sample_output_report.txt` | **IN_PROGRESS** |
| **P2-02** | P2 | Arc Bulge geometry handling lacks permanent regression tests and documentation of discretization tolerance | `tests/test_bulge_geometry.py`<br>`parser.py` | Create permanent test suite with 7 math-based theoretical bulge tests (positive/negative 90°, multiple bulges, >180°, mixed straight+curve, CW/CCW). Document `flattening(distance=0.01)` approximation in parcel model. | `tests/test_bulge_geometry.py`<br>(BULGE-001 to BULGE-007) | `pytest_output.txt` | **IN_PROGRESS** |
| **P1-03 / P2-03** | P1/P2 | Low-level output writers (`export_labeled_dxf`, `standardize_dxf_layers`) do not block `output_path == source_path` | `dxf_writer.py`<br>`manager.py` | Add explicit path collision check: if `Path(output_path).resolve() == Path(source_path).resolve()`, raise `ValueError`. | `tests/test_parcel_calculator.py`<br>(SAFE-001 to SAFE-003) | `pytest_output.txt` | **IN_PROGRESS** |
| **P2-03-B** | P2 | Git working tree pollution from generated files and version metadata sync | `.gitignore`<br>`pyproject.toml`<br>`README.md` | Add `sample_data/output/` and `scratch/` to `.gitignore`. Sync version tags and README instructions. | `git status` check | `git_status.txt` | **IN_PROGRESS** |
