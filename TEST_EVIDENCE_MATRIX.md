# Planning Toolbox Test Evidence Matrix (测试证据矩阵)

> **最高原则**：没有证据的 PASS 不是 PASS。本矩阵真实映射各项功能的技术验证等级与证据链。

| Capability (功能能力) | Test ID | Data Type | Level | Command | Exit Code | Expected vs Actual | Tolerance | Evidence File | 状态 Status |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- | :---: | :--- | :---: |
| **Square Parcel Area** | GS-001 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t01_square_parcel` | 0 | Exp: 10000.0 m²<br>Act: 10000.0 m² | ±0.01 m² | `pytest_output.txt` | **PASS** |
| **Rectangle Parcel Area** | GS-002 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t02_rectangle_parcel` | 0 | Exp: 10000.0 m²<br>Act: 10000.0 m² | ±0.01 m² | `pytest_output.txt` | **PASS** |
| **Setback Interior Area** | GS-003 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_gs_003_setback` | 0 | Exp: 8100.0 m²<br>Act: 8100.0 m² | ±0.01 m² | `pytest_output.txt` | **PASS** |
| **Bulge Arc Geometry** | BG-001 | SAMPLE | E1 | `python scratch/test_bulge_accuracy.py` | 0 | Exp: 8573.39 m²<br>Act: 8573.39 m² | ±0.10 m² | Console output | **PASS** |
| **Unclosed Polyline** | ERR-001 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t03_open_polyline` | 0 | Exp: OPEN<br>Act: OPEN | N/A | `pytest_output.txt` | **PASS** |
| **Self-Intersecting Polyline** | ERR-002 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t04_self_intersecting_polyline` | 0 | Exp: INVALID_GEOMETRY<br>Act: INVALID_GEOMETRY | N/A | `pytest_output.txt` | **PASS** |
| **Strict Unit Check ($INSUNITS=0)** | UNT-001 | SYNTHETIC | E1 | `pytest tests/test_units.py::test_t08_unknown_unit_handling` | 0 | Exp: UnitError<br>Act: UnitError | N/A | `pytest_output.txt` | **PASS** |
| **End-to-End DXF Parcel Pipeline** | E2E-001 | SAMPLE | E3 | `python scripts/run_parcel_tool.py --dxf sample_data/sample_parcels.dxf` | 0 | Exp: 3 valid, 2 err, 2.8573ha<br>Act: 3 valid, 2 err, 2.8573ha | ±0.0001 ha | `output/sample_parcels.csv`<br>`output/sample_parcels_report.txt` | **PASS** |
| **Original DXF Timestamp Protection** | PRT-001 | SAMPLE | E3 | `pytest tests/test_parcel_calculator.py::test_end_to_end_dxf_processing` | 0 | Exp: mtime unchanged<br>Act: mtime unchanged | 0 ms | `pytest_output.txt` | **PASS** |
| **CAD Template Generator** | TPL-001 | SYNTHETIC | E2 | `pytest tests/test_layer_manager.py::test_template_generation` | 0 | Exp: 8 standard layers<br>Act: 8 standard layers | N/A | `output/planning_template.dxf` | **PASS** |
| **CAD Layer Normalization** | LYR-001 | SAMPLE | E3 | `python scripts/run_layer_tool.py --dxf sample_data/sample_parcels.dxf --standardize-layers` | 0 | Exp: 0 unmapped<br>Act: 0 unmapped | N/A | `sample_data/output/sample_parcels_standardized.dxf` | **PASS** |
| **AutoCAD Manual GUI Inspection** | MAN-001 | SAMPLE | E0 | N/A (No AutoCAD process in CLI env) | N/A | Pending student manual check | N/A | None | **NOT TESTED** |
| **ArcGIS Pro GUI Inspection** | MAN-002 | SAMPLE | E0 | N/A (No ArcGIS process in CLI env) | N/A | Pending student manual check | N/A | None | **NOT TESTED** |

---

## 证据等级说明 (Evidence Level Definition)
- **E0 (Untested / External Pending)**: 代码已编写，但由于缺乏本机的 GUI 外部软件（AutoCAD / ArcGIS Pro）控制能力，标记为 `NOT TESTED` / `PENDING`，等待用户人工在 AutoCAD 中双查。
- **E1 (Unit Tested)**: 经由 pytest 真实运行，捕获 Python 内部逻辑、几何算法及单位校验。
- **E2 (Integration Tested)**: 多个模块间联调（如配置加载 + DXF 图层读写 + 模版生成）。
- **E3 (End-to-End Tested)**: 从磁盘 DXF 输入 -> 提取解析 -> 几何校验 -> CSV/DXF/Report 生成的完整真实文件闭环测试。
- **E4 (External Validation)**: 使用 AutoCAD / ArcGIS 独立命令行或 API 自动化检验（当前环境未配置此自动化驱动，降级为 E0 人工待检）。
