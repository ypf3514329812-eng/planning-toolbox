# Planning Toolbox Test Report (真实性审计版)

## Overall 状态
**PASS WITH LIMITATIONS**  
(所有已测 CLI/Python 算法与端到端 DXF 生成 100% 真实通过；AutoCAD GUI 人工打开验证标记为 NOT TESTED / PENDING，等待用户双查)

---

## 1. Mandatory Audit Questions (强制自检问答)

1. **真实运行过代码吗？**  
   YES — 已在命令行真实调用脚本与测试模块。
2. **真实运行过 pytest 吗？**  
   YES
3. **完整 pytest 命令是什么？**  
   `python -m pytest -v`
4. **Exit code 是多少？**  
   `0`
5. **真实 DXF 是否参与测试？**  
   YES
6. **DXF 属于哪种类型？**  
   `SAMPLE` (`sample_data/sample_parcels.dxf`) & `SYNTHETIC` (测试导出的规范几何 DXF)
7. **输出 DXF 是否重新读取？**  
   YES — 已使用 ezdxf 重新读取 `output/sample_parcels_labeled.dxf` 并检验层级与 MTEXT 数量。
8. **是否在 AutoCAD 中人工验证？**  
   NO — 当前 CLI 执行环境中无 AutoCAD 进程。标记为 `AutoCAD manual validation: NOT TESTED / PENDING`。
9. **是否存在未验证能力？**  
   YES — ArcGIS 兼容性、AutoCAD 交互控制。
10. **是否存在推测性结论？**  
    YES — 假设无单位 DXF 在配置 `fallback_unit: m` 时为米制。标记为 `ASSUMPTION`。

---

## 2. Evidence-Based Status (基于证据的分类验证)

### VERIFIED (已真实验证的事实)
- **GS-001 (100m x 100m Square)**: Expected = $10,000.00\,\text{m}^2$, Actual = $10,000.00\,\text{m}^2$, Error = $0.00\,\text{m}^2$, Tolerance = $\pm 0.01\,\text{m}^2$ (E1, PASS).
- **GS-002 (200m x 50m Rectangle)**: Expected = $10,000.00\,\text{m}^2$, Actual = $10,000.00\,\text{m}^2$, Error = $0.00\,\text{m}^2$, Tolerance = $\pm 0.01\,\text{m}^2$ (E1, PASS).
- **GS-003 (5m Setback Interior)**: Expected = $8,100.00\,\text{m}^2$, Actual = $8,100.00\,\text{m}^2$, Error = $0.00\,\text{m}^2$, Tolerance = $\pm 0.01\,\text{m}^2$ (E1, PASS).
- **Bulge Arc Geometry (90° Arc)**: Expected = $8,573.39\,\text{m}^2$, Actual = $8,573.39\,\text{m}^2$, Error = $<0.01\,\text{m}^2$, Tolerance = $\pm 0.10\,\text{m}^2$ (E1, PASS).
- **Unclosed Polyline Handling**: Status reported as `OPEN`, area computation refused (E1, PASS).
- **Self-Intersecting Polyline Handling**: Status reported as `INVALID_GEOMETRY`, area computation refused (E1, PASS).
- **Strict Unit Enforcement**: `UnitError` raised when DXF `$INSUNITS=0` and strict check is enabled (E1, PASS).
- **Non-Destructive File Protection**: Original DXF timestamp and file size unchanged (E3, PASS).
- **CAD Template Generation**: 8 standard layers created with specified colors/lineweights (E2, PASS).
- **Layer Normalization**: Remapped alias layers to system standard layers (E3, PASS).
- **Performance**: 1000 parcels processed in 0.886 seconds (E3, PASS).

### NOT VERIFIED / PENDING (尚未验证的项目)
- **AutoCAD Manual GUI Inspection**: NOT TESTED / PENDING (需用户在 AutoCAD 中双查标签显示与字体样式)。
- **ArcGIS Pro GIS Compatibility**: NOT TESTED (GIS Bridge 功能规划在 Phase 2)。

### ASSUMPTION (采用的假设)
- 假定未声明单位且未开启 `strict_unit_check` 的 DXF 图纸单位为米。

### KNOWN LIMITATION (已知能力限制)
- 暂不支持 Polyline3D 实体与嵌套在 Block 块参照内部的多边形边界提取。

---

## 3. Git Evidence (Git 证据)
- **Branch**: main
- **Commit Hash**: `b1c71c075bcf6716d9d6c0b40b95577cc120b032`
- **Working Tree**: Clean
- **Tags**: `v0.1.0-mvp1`, `v0.1.1-optimized`, `v0.2.0-cad-layers`

---

## 4. Test Evidence Matrix Reference
完整测试证据矩阵已存入 [TEST_EVIDENCE_MATRIX.md](file:///c:/AutoOS/OS1/TEST_EVIDENCE_MATRIX.md)，证据文件归档在 `test_artifacts/latest/`。
