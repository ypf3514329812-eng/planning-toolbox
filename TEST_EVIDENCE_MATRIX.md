# Planning Toolbox Test Evidence Matrix (测试证据矩阵 - v0.1.1-RC1)

> **最高原则**：没有证据的 PASS 不是 PASS。本矩阵真实映射各项功能的技术验证等级、数据来源与证据链。
> **版本标记**：`v0.1.1-RC1` / `PASS WITH LIMITATIONS` (未获 AutoCAD/ArcGIS 手工验证前绝不标为最终 STABLE)。

| Capability (功能能力) | Test ID | Data Type (数据来源) | Level | Command (执行命令) | Exit Code | Expected vs Actual | Tolerance | Evidence File | 状态 Status |
| :--- | :--- | :---: | :---: | :--- | :---: | :--- | :---: | :--- | :---: |
| **Square Parcel Area** | GS-001 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t01_square_parcel` | 0 | Exp: 10000.0 m²<br>Act: 10000.0 m² | ±0.01 m² | `pytest_output.txt` | **PASS** |
| **Rectangle Parcel Area** | GS-002 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t02_rectangle_parcel` | 0 | Exp: 10000.0 m²<br>Act: 10000.0 m² | ±0.01 m² | `pytest_output.txt` | **PASS** |
| **Setback Interior Area** | GS-003 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_gs_003_setback` | 0 | Exp: 8100.0 m²<br>Act: 8100.0 m² | ±0.01 m² | `pytest_output.txt` | **PASS** |
| **Bulge Arc Geometry** | BG-001 | SAMPLE | E1 | `python scratch/test_bulge_accuracy.py` | 0 | Exp: 8573.39 m²<br>Act: 8573.39 m² | ±0.10 m² | Console output | **PASS** |
| **Unclosed Polyline Protection** | ERR-001 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t03_open_polyline` | 0 | Exp: OPEN<br>Act: OPEN | N/A | `pytest_output.txt` | **PASS** |
| **Self-Intersecting Polyline** | ERR-002 | SYNTHETIC | E1 | `pytest tests/test_parcel_calculator.py::test_t04_self_intersecting_polyline` | 0 | Exp: INVALID_GEOMETRY<br>Act: INVALID_GEOMETRY | N/A | `pytest_output.txt` | **PASS** |
| **Fail-Safe Unit Strategy** | UNT-001 | SYNTHETIC | E1 | `pytest tests/test_units.py::test_unspecified_dxf_unit_failsafe_blocked` | 0 | Exp: UnitError (BLOCKED)<br>Act: UnitError (BLOCKED) | N/A | `pytest_output.txt` | **PASS** |
| **End-to-End DXF Parcel Pipeline** | E2E-001 | SAMPLE | E3 | `python scripts/run_parcel_tool.py --dxf sample_data/sample_parcels.dxf` | 0 | Exp: 3 valid, 2 err, 2.8573ha<br>Act: 3 valid, 2 err, 2.8573ha | ±0.0001 ha | `output/sample_parcels.csv`<br>`output/sample_parcels_report.txt` | **PASS** |
| **SHA-256 Zero Destruction** | PRT-001 | SAMPLE | E3 | `python scratch/test_sha256_verification.py` | 0 | Exp: `36bee428...`<br>Act: `36bee428...` | 100% Match | `git_status.txt` | **PASS** |
| **CAD Template Generator** | TPL-001 | SYNTHETIC | E2 | `pytest tests/test_layer_manager.py::test_template_generation` | 0 | Exp: 8 standard layers<br>Act: 8 standard layers | N/A | `output/planning_template.dxf` | **PASS** |
| **CAD Layer Normalization** | LYR-001 | SAMPLE | E3 | `python scripts/run_layer_tool.py --dxf sample_data/sample_parcels.dxf --standardize-layers` | 0 | Exp: 0 unmapped<br>Act: 0 unmapped | N/A | `sample_data/output/sample_parcels_standardized.dxf` | **PASS** |
| **Synthetic Performance** | PERF-01 | SYNTHETIC | E3 | `python scratch/test_performance.py` | 0 | Exp: 1000 synthetic simple parcels<br>Act: 0.886 s | N/A | Console output | **PASS** |
| **AutoCAD Manual GUI Inspection** | MAN-001 | SAMPLE | E0 | N/A (No AutoCAD process in CLI env) | N/A | Pending student manual check | N/A | None | **NOT TESTED** |
| **ArcGIS Pro GUI Inspection** | MAN-002 | SAMPLE | E0 | N/A (No ArcGIS process in CLI env) | N/A | Pending student manual check | N/A | None | **NOT TESTED** |

---

## 证据等级与测试定义说明
- **SYNTHETIC**: 程序算法构造的标准已知几何数据（如 $100\text{m}\times 100\text{m}$ 方形地块）。
- **SAMPLE**: 项目内置测试图纸 `sample_data/sample_parcels.dxf`。
- **1000 synthetic simple parcels benchmark**: 性能测试基于程序生成的简单正方形网格地块，**严禁泛化为真实复杂 CAD 图纸性能**。
- **E0 (Untested / Pending)**: 因缺乏控制 AutoCAD / ArcGIS 外部 GUI 自动化进程的驱动，降级为 `NOT TESTED` / `PENDING`。
