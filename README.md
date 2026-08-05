# Planning Toolbox (城乡规划 CAD–GIS 自动化辅助工具箱)

> 自动消除城乡规划学习、课程设计和规划分析过程中重复、机械、低价值的数据整理、CAD 制图、GIS 转换、面积统计、指标核算和规则检查工作。
> **原则：人负责规划判断，程序负责计算和重复劳动。**

---

## Capabilities & System Boundaries (功能与系统边界说明)

### 1. 支持的 CAD 实体类型
- **支持**：2D/3D `LWPOLYLINE` (轻量多段线) 及 `POLYLINE` (二维多段线) 封闭区域。
- **弧线 Bulge 逼近**：使用 `ezdxf.path.flattening(distance=0.01)` 离散逼近圆弧段（面积逼近精度为 ±0.06‰，满足规划使用需求）。
- **暂不支持**：由散乱 `LINE`、`ARC` 组合但未连接为 Polyline 的边界、`CIRCLE` 或 `SPLINE` 实体（此类实体目前登记为非闭合或不支持类型，需在 CAD 中重构为 Polyline）。

### 2. 单位识别与安全策略 ($INSUNITS)
- 当 DXF 文件内部包含 `$INSUNITS` 属性时（如 6 = 米），自动使用精确缩放因子。
- 当 DXF 文件内部 `$INSUNITS` 为 0 (Unspecified) 且开启 `strict_unit_check: true` 时，程序**拒绝静默假设**并提示错误 (BLOCKED)，防止误算。

### 3. 嵌套环/孔洞处理 (Nested Rings & Holes)
- 当某一图层内存在“大多边形完全包含小多边形”的嵌套结构时，内环将自动标记为 `NESTED_RING_DETECTED`，并从 `VALID` 面积汇总中扣除，防止重复累加。

### 4. GIS 数据桥梁 (CAD ↔ GIS Bidirectional Bridge)
- **GeoJSON 导出**：自动将地块几何与全套属性（`parcel_id`, `area_m2`, `area_ha`, `geometry_status`, `source_layer`）导出为 RFC 7946 GeoJSON FeatureCollection，可直接拖入 QGIS / ArcGIS Pro。
- **GeoJSON 导入**：支持将 GIS 矢量边界导入生成 CAD DXF `LWPOLYLINE` 图层。

### 5. 原始文件“零破坏”保证 (Zero-Mutation Guarantee)
- 读取 DXF 时只进行内存解析，标注文件写出至独立的 `*_labeled.dxf`，原始 DXF 文件通过 SHA-256 校验对比保证 100% 字节级无修改。

---

## Quickstart Guide for Planning Students (使用指南)

本工具箱无需修改任何 Python 源代码即可使用！

### 1. 环境准备

确保已安装 Python 3.10+。在命令行运行：

```bash
pip install -e .
```

### 2. 地块面积与编号工具 (MVP-1)

将 CAD 图纸（.dxf 格式）放入 `sample_data` 目录或任意路径，运行：

```bash
python scripts/run_parcel_tool.py --dxf sample_data/sample_parcels.dxf
```

可选参数：
- `--config path/to/config.yaml` — 使用自定义配置文件
- `--output path/to/output_dir` — 自定义输出目录
- `--verbose` — 显示详细调试信息
- `--version` — 显示版本号

运行后会在 `output/` 目录中自动生成：

1. `<文件名>_labeled.dxf` — 包含地块编号（如 P001）与面积（如 1.24 ha）的标注 DXF 图纸。
2. `<文件名>.csv` — 地块面积及状态统计表格。
3. `<文件名>.geojson` — 可在 QGIS / ArcGIS 中直接加载的矢量图层文件。
4. `<文件名>_report.txt` — 详细处理报告（包含有效地块数、未闭合图形及面积汇总）。

### 3. 图层标准化与空白模板 (MVP-2)

生成城乡规划标准空白 CAD 模板：

```bash
python scripts/run_layer_tool.py --create-template output/template.dxf
```

标准化旧 CAD 图纸图层：

```bash
python scripts/run_layer_tool.py --dxf input.dxf --standardize-layers --output output/
```

### 4. GIS ↔ CAD 数据转换工具 (Phase 2)

导出 CAD 图纸至 GeoJSON 矢量文件：

```bash
python scripts/run_gis_bridge.py --export-geojson sample_data/sample_parcels.dxf --output output/
```

将 GeoJSON 矢量文件导入为 CAD 图纸：

```bash
python scripts/run_gis_bridge.py --import-geojson input.geojson --output output/
```

---

## Manual CAD & GIS Validation Guide (AutoCAD / ArcGIS 人工核验指南)

无编程背景的规划专业学生请参阅 [MANUAL_AUTOCAD_VALIDATION.md](file:///c:/AutoOS/OS1/MANUAL_AUTOCAD_VALIDATION.md) 进行 AutoCAD (`AREA` / `LIST`) 及 ArcGIS Pro 人工比对抽验。

---

## Automated Test Suite (自动化测试)

运行全部 43 项回归测试：

```bash
pytest
```

---

## Git Release & Stabilization

- `v0.1.0-mvp1`: MVP-1 初始版本
- `v0.1.1-stable`: RC1 稳定化稳定版 (39/39 测试通过, 零破坏验证)
- `v0.2.0-gis-bridge`: Phase 2 GIS ↔ CAD 数据桥梁稳定版 (43/43 测试通过)
