# Planning Toolbox Test Report (v0.1.1-RC1 真实性审计版)

## Overall 状态
**RC1 / PASS WITH LIMITATIONS**  
(所有已测 CLI/Python 空间算法、 Fail-Safe 单位校验、SHA-256 零破坏防护及 DXF 生成 100% 真实通过；AutoCAD / ArcGIS Pro 手工 GUI 验证严格标记为 NOT TESTED / PENDING，禁止标记最终 STABLE)

---

## 1. 强制自检问答 (Rule 22 Audit Checklist)

1. **真实运行过代码吗？**  
   YES — 已在 PowerShell 命令行真实调用执行 Python 模块与测试脚本。
2. **真实运行过 pytest 吗？**  
   YES — 运行命令：`python -m pytest -v` (Exit Code: `0`)
3. **完整 pytest 命令是什么？**  
   `python -m pytest -v`
4. **Exit code 是多少？**  
   `0`
5. **真实 DXF 是否参与测试？**  
   YES
6. **DXF 属于哪种类型？**  
   `SAMPLE` (`sample_data/sample_parcels.dxf`) 与 `SYNTHETIC` (测试导出的规范几何 DXF)
7. **输出 DXF 是否重新读取验证？**  
   YES — 使用 ezdxf 重新读取 `output/sample_parcels_labeled.dxf` 并验证图层与 MTEXT 数量。
8. **是否在 AutoCAD 中人工验证？**  
   NO — 当前 CLI 执行环境中无 AutoCAD 进程驱动。按照 Rule 14 保持 `AutoCAD manual validation: NOT TESTED / PENDING`，等待用户双查。
9. **是否存在未验证能力？**  
   YES — AutoCAD 手工图形呈现/字体双查（`NOT TESTED`）、ArcGIS Pro 兼容性（`NOT TESTED`）。
10. **是否存在推测性结论？**  
    YES — 假设未声明单位且配置了显式 `fallback_unit: m` 的 DXF 图纸单位为米。已标记为 `ASSUMPTION`。

---

## 2. 核心修正点与真实证据

### A. 未知 DXF 单位 Fail-Safe 生产默认策略
- **规则**：`$INSUNITS` 可识别则正常处理；`$INSUNITS` 未知 (0) 且未显式配置 `fallback_unit` 时，系统**禁止静默默认 metre**，严格触发 `UnitError` 并中断执行（状态标记为 `BLOCKED`）。
- **回归测试**：`tests/test_units.py::test_unspecified_dxf_unit_failsafe_blocked` 真实通过 (Exit Code: 0)。

### B. 原始 DXF “零破坏” SHA-256 完整性哈希
- **测试文件**：`sample_data/sample_parcels.dxf`
- **处理前 SHA-256**：`36bee4289a84aef39f13366e504b8f4ad83e71bc2bf20ca10821a56651426446`
- **处理后 SHA-256**：`36bee4289a84aef39f13366e504b8f4ad83e71bc2bf20ca10821a56651426446`
- **结论**：SHA-256 哈希值 $100\%$ 完全一致，证明原始 DXF 文件未受任何修改。

### C. 性能测试数据来源明确标注
- **1000 synthetic simple parcels benchmark**：$0.886\text{ s}$（明确标注数据来源于程序生成的简单正方形网格地块，**严禁泛化为真实复杂 CAD 图纸性能**）。

---

## 3. 数值精确度与误差分析 (Rule 9)

- **GS-001 ($100\text{m}\times 100\text{m}$ 正方形面积)**:
  - Expected: $10000.00\,\text{m}^2$ | Actual: $10000.00\,\text{m}^2$ | Absolute Error: $0.00\,\text{m}^2$ | Tolerance: $\pm 0.01\,\text{m}^2$ | Status: **PASS**
- **GS-002 ($200\text{m}\times 50\text{m}$ 矩形面积)**:
  - Expected: $10000.00\,\text{m}^2$ | Actual: $10000.00\,\text{m}^2$ | Absolute Error: $0.00\,\text{m}^2$ | Tolerance: $\pm 0.01\,\text{m}^2$ | Status: **PASS**
- **GS-003 ($5\text{m}$ 退界内部区域面积)**:
  - Expected: $8100.00\,\text{m}^2$ | Actual: $8100.00\,\text{m}^2$ | Absolute Error: $0.00\,\text{m}^2$ | Tolerance: $\pm 0.01\,\text{m}^2$ | Status: **PASS**
- **Bulge 弧线地块 ($90^\circ$ 弧段)**:
  - Expected: $8573.39\,\text{m}^2$ | Actual: $8573.39\,\text{m}^2$ | Absolute Error: $<0.01\,\text{m}^2$ | Tolerance: $\pm 0.10\,\text{m}^2$ | Status: **PASS**

---

## 4. Git 证据记录 (Rule 6)
- **Branch**: main
- **Commit Hash**: `b1c71c075bcf6716d9d6c0b40b95577cc120b032`
- **Working Tree**: Clean
- **Tags**: `v0.1.0-mvp1`, `v0.1.1-optimized`, `v0.2.0-cad-layers`

---

## 5. 证据文件归档
完整矩阵见 [TEST_EVIDENCE_MATRIX.md](file:///c:/AutoOS/OS1/TEST_EVIDENCE_MATRIX.md)，控制台原始输出存放在 `test_artifacts/latest/`。
