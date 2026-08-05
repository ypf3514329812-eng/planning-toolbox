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

### 5. 规划指标自动核算 (Planning Indicators Engine)
- **指标范围**：容积率 (FAR)、建筑密度 (Building Density %)、绿地率 (Green Ratio %) 及用地面积分类统计。
- **CAD 自动相交分析**：自动对 `PARCEL`、`BUILDING`、`GREEN` 图层的多边形空间求交，计算各地块内部建筑占地与绿地面积。

### 6. 拓扑与建筑退线规则检查 (Rules & Topology Validators)
- **拓扑检查**：自动扫描 CAD 图纸中的开放边界 (`OPEN`)、自交多边形 (`INVALID_GEOMETRY`) 及少于 3 顶点的退化图形。
- **退线检查**：根据输入的建筑退线要求（如 5.0m），自动校验建筑基底是否越过用地红线退线边界。

### 7. 原始文件“零破坏”保证 (Zero-Mutation Guarantee)
- 读取 DXF 时只进行内存解析，标注文件写出至独立的 `*_labeled.dxf`，原始 DXF 文件通过 SHA-256 校验对比保证 100% 字节级无修改。

---

## Quickstart Guide for Planning Students (使用指南)

本工具箱无需修改任何 Python 源代码即可使用！提供**图形化桌面工作台 (GUI)** 与 **命令行工具 (CLI)** 两种使用方式。

### 1. 环境准备与安装

确保已安装 Python 3.10+。在项目根目录下运行：

```bash
pip install -e .
```

---

### 2. Windows 本地图形化桌面工作台 (`v0.6.0-desktop-ui`)

专为无编程背景的规划专业学生打造，提供简洁直观的图形化操作界面：

```bash
planning-toolbox-gui
```
*(或在项目根目录运行: `python scripts/run_gui.py`)*

#### 界面四大区域:
1. **文件与输出位置区**: 选择输入 DXF 文件与输出结果存储目录。原始 DXF 文件享有 100% 只读保护。
2. **图纸数据检查区**: 自动扫描 DXF 单位 ($INSUNITS)、`PARCEL` / `BUILDING` / `GREEN` 图层、多段线总数、未闭合线数及嵌套环前置警告。若单位未知，自动触发红色高亮拦截。
3. **分析任务与参数区**:
   - **地块面积与编号**: 自动识别图层、编号、标注导出。
   - **规划指标计算**: 输入必填楼层数，自动求交统计 FAR、建筑密度与绿地率。
   - **拓扑与退线检查**: 输入退线要求米数 (如 5.0m)，按地块归属校验建筑退线。
   - **GIS 导出/导入**: GeoJSON 矢量导出与 DXF 回导入（含坐标系非经纬度阻断保护）。
4. **分析结果与报告区**: 实时进度条、指标卡片与表格、一键打开输出文件夹与生成文件。

#### 独立 Windows `.exe` 单文件打包:
若需要在未安装 Python 环境的 Windows 电脑上运行，可以编译生成单文件 `PlanningToolbox.exe`：
```bash
python scripts/package_exe.py
```
打包成功后，可在 `dist/PlanningToolbox.exe` 找到独立的双击运行程序。

---

### 3. 统一命令行工具 (`planning-toolbox`)

#### A. 地块面积与编号工具 (Parcel Calculator)
扫描 DXF 中的地块边界，计算面积、自动编号并标注导出：
```bash
planning-toolbox parcel --dxf sample_data/sample_parcels.dxf --output output/
```

#### B. 图层标准化与空白模板 (Layer Standardization & Template)
生成城乡规划标准空白 CAD 模板：
```bash
planning-toolbox layer template --output output/template.dxf
```
标准化已有 CAD 图纸图层：
```bash
planning-toolbox layer standardize --dxf input.dxf --output output/
```

#### C. GIS ↔ CAD 数据转换 (GIS Data Bridge)
导出 CAD 图纸至 GeoJSON 矢量文件：
```bash
planning-toolbox gis export --dxf sample_data/sample_parcels.dxf --output output/
```
将 GeoJSON 矢量文件导入为 CAD DXF 图纸：
```bash
planning-toolbox gis import --geojson sample_data/sample_parcels.geojson --output output/ --unit m
```

#### D. 规划指标自动核算 (Planning Indicators)
分析 CAD DXF 中的 `PARCEL`、`BUILDING`、`GREEN` 图层，核算容积率 (FAR)、建筑密度与绿地率：
```bash
planning-toolbox indicator --dxf sample_data/sample_parcels.dxf --floors 6 --output output/
```

#### E. 规则与拓扑检查 (Rules & Topology Validator)
自动扫描 CAD 拓扑错误（未闭合、自交）及建筑退线合规性（如退线 5.0m）：
```bash
planning-toolbox validate --dxf sample_data/sample_parcels.dxf --setback 5.0
```

---

## Windows 环境常见问题与故障排查

1. **`UNITS` 未设置警告 (`ERR_UNIT_UNKNOWN`)**
   - 当 CAD 图纸单位未明确设置 ($INSUNITS = 0) 时，工具箱将拦截执行以防误算。
   - **解决办法**：优先在 AutoCAD 中打开图纸，输入 `UNITS` 命令将插入缩放单位设为【米】，重新保存 DXF；或在界面退线参数中显式选择单位回退值。

2. **PowerShell 权限问题**
   - 若在 Windows PowerShell 中出现“禁止运行脚本”提示，请以管理员身份打开 PowerShell 并运行：
     `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## Manual CAD & GIS Validation Guide (AutoCAD / ArcGIS 人工核验指南)

无编程背景的规划专业学生请参阅 [MANUAL_AUTOCAD_VALIDATION.md](file:///c:/AutoOS/OS1/MANUAL_AUTOCAD_VALIDATION.md) 进行 AutoCAD (`AREA` / `LIST`) 及 ArcGIS Pro 人工比对抽验。

---

## Automated Test Suite (自动化测试)

运行全部 71 项回归测试：

```bash
pytest
```

---

## Git Release & Stabilization

- `v0.1.0-mvp1`: MVP-1 初始版本
- `v0.1.1-stable`: RC1 稳定化稳定版 (39/39 测试通过, 零破坏验证)
- `v0.2.0-gis-bridge`: Phase 2 GIS ↔ CAD 数据桥梁稳定版 (43/43 测试通过)
- `v0.3.0-indicators`: Phase 3 规划指标自动核算引擎稳定版 (46/46 测试通过)
- `v0.4.0-validators`: Phase 4 规则与拓扑检查引擎稳定版 (49/49 测试通过)
- `v0.5.0-polish`: Phase 5 工程完善与后端重构版 (65/65 测试通过，修正重叠建筑并集与未已知 CRS 阻断)
- `v0.6.0-desktop-ui`: Phase 6 Windows 本地桌面可视化工作台 (71/71 测试通过，提供完整 PySide6 界面与打包支持)

