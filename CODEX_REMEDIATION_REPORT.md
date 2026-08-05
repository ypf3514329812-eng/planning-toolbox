# Planning Toolbox — Codex 接手修复报告

日期：2026-08-05  
项目根目录：`C:\AutoOS\OS1`  
基线：`main`，接手时 HEAD 为 `e8fee96375f0fcaa81b89c72d7bebcfd3d2d43e4`

## 已完成的修复

1. **单位安全**
   - `validate` 现在先验证 DXF `$INSUNITS`；未知单位会阻断米制退线计算。
   - 退线距离按 DXF 实际单位换算为米，英尺、厘米等单位不再按“1 CAD 单位 = 1 米”处理。
   - `--fallback-unit` 仅在用户明确提供时启用；负数、非有限退线距离会被拒绝。

2. **GeoJSON 坐标系安全**
   - CAD → GeoJSON 默认不再伪造 `EPSG:4326/CRS84` 声明，输出会标记 CRS、单位和“未进行坐标转换”。
   - GeoJSON → DXF 默认写入未知 `$INSUNITS=0`；只有使用 `--unit m` 等明确指定时才写入 DXF 单位。
   - 声明为 WGS84/经纬度的 GeoJSON 在没有坐标转换能力时直接阻断，避免把经纬度误当作 CAD 米制坐标。

3. **规划指标安全**
   - 建筑和绿地与地块相交后先做并集，重叠轮廓不再重复计面积。
   - DXF 指标计算不再默认假设 6 层；存在建筑轮廓时必须通过 `--floors` 或 `default_floors` 明确指定。
   - 手动指标拒绝负数、非有限数，以及超过地块面积的建筑占地/绿地面积。

4. **嵌套环语义**
   - 独立 DXF 多段线无法可靠区分“孔洞”和“嵌套地块”。涉及嵌套关系的内外环现在全部标记为 `NESTED_RING_DETECTED`，并从面积合计中排除，等待人工确认。

5. **兼容脚本与样例**
   - 同步收紧 `scripts/run_validator_tool.py` 与 `scripts/run_indicators_tool.py`。
   - 退线检查按“建筑与当前地块相交”建立归属，避免其他地块的建筑造成误报；`run_gis_bridge.py` 也支持显式指定导入单位。
   - 修正样例 GeoJSON 的错误 CRS 声明，并更新 README 命令。
   - 重新安装 editable package 后，`pip show planning-toolbox` 已显示 `0.5.0`，位置为 `C:\AutoOS\OS1`。

## 验证结果

- `python -m pytest -v`：**65 passed, 0 failed, 0 skipped**。
- 真实 CLI 验收通过：
  - `planning-toolbox --version`
  - `planning-toolbox parcel --dxf sample_data/sample_parcels.dxf ...`
  - `planning-toolbox indicator --dxf sample_data/sample_parcels.dxf --floors 6 ...`
  - `planning-toolbox validate --dxf sample_data/sample_parcels.dxf --setback 5.0`
  - `planning-toolbox gis export ...`
  - `planning-toolbox gis import ... --unit m`
- 样例导出的 GeoJSON 元数据为 `coordinate_reference_system=UNKNOWN`、`coordinate_units=Meters`，未声明虚假的 WGS84。
- 样例 DXF 的退线结果为 P001/P002/P003 均合规；此前由跨地块建筑混入造成的误报已回归验证。
- 退线计算使用完整地块边界（含孔洞边界），并已加入回归测试。

## 当前边界

Planning Toolbox 目前**不会自动执行 CRS 坐标转换**。如果输入是经纬度 GeoJSON，需先在 GIS 中投影到适合测距/面积计算的坐标系，再导入；不能只修改 CRS 标签。

本次修复尚未提交 Git commit，工作树中的变更均为本次接手修复及其回归测试、文档证据。
