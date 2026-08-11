# Planning Toolbox (城乡规划 CAD–GIS 自动化辅助工具箱)

> 自动消除城乡规划学习、课程设计和规划分析过程中重复、机械、低价值的数据整理、CAD 制图、GIS 转换、面积统计、指标核算和规则检查工作。
> **原则：人负责规划判断，程序负责计算和重复劳动。**

> **当前状态：开源发布准备中的 Public Beta。** 当前本地工作树尚未上传 GitHub；公开发布范围、合规要求和后续功能路线见 [开源发布与产品优化计划书](OPEN_SOURCE_RELEASE_OPTIMIZATION_PLAN.md)。

相关文档：

- [架构说明](ARCHITECTURE.md)
- [贡献指南](CONTRIBUTING.md)
- [安全政策](SECURITY.md)
- [第三方声明](THIRD_PARTY_NOTICES.md)
- [版本记录](CHANGELOG.md)
- [后续路线图](ROADMAP.md)

---

## Capabilities & System Boundaries (功能与系统边界说明)

### 1. 支持的 CAD 实体类型
- **计算支持**：2D/3D `LWPOLYLINE` (轻量多段线) 及 `POLYLINE` (二维多段线) 封闭区域。
- **弧线 Bulge 逼近**：使用 `ezdxf.path.flattening(distance=0.01)` 离散逼近圆弧段（面积逼近精度为 ±0.06‰，满足规划使用需求）。
- **预览与兼容性清点**：主界面可显示 `LINE`、`ARC`、`CIRCLE`、`ELLIPSE`、`SPLINE`、`INSERT`、`TEXT/MTEXT` 等常见复杂图元。
- **安全边界**：散乱 `LINE`、`ARC`、`CIRCLE` 或 `SPLINE` 不会被直接当作面积边界；参与面积和指标计算前仍须整理为拓扑有效的闭合 Polyline。

### 2. 单位识别与安全策略 ($INSUNITS)
- 当 DXF 文件内部包含 `$INSUNITS` 属性时（如 6 = 米），自动使用精确缩放因子。
- 当 DXF 文件内部 `$INSUNITS` 为 0 (Unspecified) 且开启 `strict_unit_check: true` 时，程序**拒绝静默假设**并提示错误 (BLOCKED)，防止误算。

### 3. 嵌套环/孔洞处理 (Nested Rings & Holes)
- 当某一图层内存在“大多边形完全包含小多边形”的嵌套结构时，内环将自动标记为 `NESTED_RING_DETECTED`，并从 `VALID` 面积汇总中扣除，防止重复累加。

### 4. GIS 数据桥梁 (CAD ↔ GIS Bidirectional Bridge)
- **轻量 GeoJSON 双向转换**：自动将地块几何与属性导出为 GeoJSON，或把投影/本地平面 GeoJSON 多边形写入 CAD DXF `LWPOLYLINE`；基础功能不需要 QGIS 或 API。
- **可选 GeoPackage / Shapefile 桥接**：优先调用电脑已有的 ArcGIS Pro 后台 Python/ArcPy；没有 ArcGIS Pro 时再检测 QGIS/GDAL `ogr2ogr`。可执行 `GPKG/SHP → 项目投影 → DXF` 和 `DXF → 米制 GeoJSON → GPKG`，两类大型 GIS 运行时都不打包进基础 EXE。
- **坐标与单位安全**：扩展格式必须先在顶部“🧭”设置经确认的米制投影 EPSG；经纬度及 EPSG:3857 被阻断。毫米、厘米、英尺 DXF 导出 GPKG 时会先精确换算为米，反向导入则按目标 DXF 单位换算。

### 5. 规划指标自动核算 (Planning Indicators Engine)
- **指标范围**：容积率 (FAR)、建筑密度 (Building Density %)、绿地率 (Green Ratio %) 及用地面积分类统计。
- **CAD 自动相交分析**：自动对 `PARCEL`、`BUILDING`、`GREEN` 图层的多边形空间求交，计算各地块内部建筑占地与绿地面积。

### 6. 拓扑与建筑退线规则检查 (Rules & Topology Validators)
- **拓扑检查**：自动扫描 CAD 图纸中的开放边界 (`OPEN`)、自交多边形 (`INVALID_GEOMETRY`) 及少于 3 顶点的退化图形。
- **退线检查**：根据输入的建筑退线要求（如 5.0m），自动校验建筑基底是否越过用地红线退线边界。

### 7. 原始文件“零破坏”保证 (Zero-Mutation Guarantee)
- 读取 DXF 时只进行内存解析，标注文件写出至独立的 `*_labeled.dxf`，原始 DXF 文件通过 SHA-256 校验对比保证 100% 字节级无修改。

### 8. 图片–CAD–SketchUp 语义接力
- 图片转 CAD 会在结果 DXF 旁生成轻量 `.ptscene.json`，只记录来源指纹、比例、候选角色、复核状态和谱系，不复制完整图形。
- 图层标准化与质量修复生成新 DXF 时会自动重建匹配的新 sidecar；过期或被手工错配的 sidecar 会被 SHA-256 校验阻断。
- SketchUp 交接沿用已识别的建筑、绿化和停车候选，并把大量普通描线合并为一个默认锁定的 `PT_UNDERLAY` 参考底图组，避免对象列表被几千条线占满。候选仍需人工确认，系统不会把机器识别冒充最终设计语义。

---

## Quickstart Guide for Planning Students (使用指南)

本工具箱无需修改任何 Python 源代码即可使用！提供**图形化桌面工作台 (GUI)** 与 **命令行工具 (CLI)** 两种使用方式。

### 1. 环境准备与安装

确保已安装 Python 3.10+。在项目根目录下运行：

```bash
pip install -e .
```

---

### 2. Windows 本地图形化桌面工作台（当前工作树）

专为无编程背景的规划专业学生打造，提供简洁直观的图形化操作界面：

```bash
planning-toolbox-gui
```
*(或在项目根目录运行: `python scripts/run_gui.py`)*

顶部“🧩 流程”提供九阶段全链路作业向导：建立项目 → 导入资料 → 无损预检查 → 图层标准化 → 图纸质量修复 → 规划分析 → GIS 交换 → SketchUp 交接 → 成果导出。向导复用现有后台任务，不引入 API 或大型运行库；成功任务会自动记录完成证据，可选的图层标准化、GIS 和 SketchUp 阶段可以明确跳过，单位预检查和质量检查不会被误跳过。流程状态、资料来源和当前步骤随 `.ptx` 保存，下次可以继续。

#### 界面四大区域:
1. **文件与输出位置区**: 选择输入 DXF 文件与输出结果存储目录。原始 DXF 文件享有 100% 只读保护。
2. **图纸数据检查区**: 自动扫描 DXF 单位 ($INSUNITS)、`PARCEL` / `BUILDING` / `GREEN` 图层、多段线总数、未闭合线数及嵌套环前置警告。若单位未知，自动触发红色高亮拦截。
3. **分析任务与参数区**:
   - **地块面积与编号**: 自动识别图层、编号、标注导出。
   - **规划指标计算**: 输入必填楼层数，自动求交统计 FAR、建筑密度与绿地率。
   - **拓扑与退线检查**: 输入退线要求米数 (如 5.0m)，按地块归属校验建筑退线。
   - **GIS 导出/导入**: 基础 GeoJSON↔DXF；优先复用已安装的 ArcGIS Pro，缺失时回退 QGIS/GDAL，完成 GPKG/SHP↔DXF 并按项目投影自动对齐。
   - **CAD → SketchUp 低返工模型交接**: 生成轻量 `.ptsu.json` 与可安装 `.rbz` 插件；在 SketchUp 内按 PT_* 标签创建可编辑分组、明确高度建筑、楼层线、屋顶/女儿墙和共享窗组件。来自图片的 DXF 会沿用 `.ptscene.json` 语义，把普通描线汇总为一个锁定的 `PT_UNDERLAY` 底图组，同时保留建筑、绿化和停车候选。课程/汇报模式还会把闭合道路、绿地、水体、停车轮廓自动分层，并用精选 CC0 共享组件生成入口雨棚与树木。道路可选自动、完整街道、基础车行道或关闭细化；规则道路可生成双侧人行带、路缘、边线、中心虚线、双向箭头和共享街灯，`PT_PLANTER` / `PT_PARASOL` / `PT_CROSSWALK` / `PT_TRAFFIC_LIGHT` 块可显式生成花池、遮阳伞、斑马线和交通灯。普通斑马线会按可信道路方向和车行道宽度自动调整，并让标线、箭头和街灯避开过街区；固定/手动别名与歧义回退避免错误猜测。逐栋参数表可分别设置每栋建筑的参数，并支持增量更新与手工锁定保护。规则知识库与约 334 KB 的 9 个原生 SKP 组件都在本地按需使用，不保存模型权重，也不需要 API。
4. **分析结果与报告区**: 实时进度条、指标卡片与表格、一键打开输出文件夹与生成文件。

结果区的 CAD 预览采用 Qt 原生矢量画布：滚轮缩放、按住左键拖动、双击恢复全图。打开图纸时不再额外加载 Matplotlib；导出 PNG 会渲染完整图纸，不受当前屏幕尺寸和缩放位置影响。方案叠加与差异高亮仍保留原有绘图能力。

#### 独立 Windows `.exe` 单文件打包:
若需要在未安装 Python 环境的 Windows 电脑上运行，可以编译生成 Windows 桌面版：
```bash
python scripts/package_exe.py
```
打包成功后，可通过 `dist/PlanningToolbox/PlanningToolbox.exe` 启动。日常桌面快捷方式直接指向目录版 EXE，避免每次双击解压数百 MB 的科学计算依赖；程序还会阻止重复启动多个工作台实例。

---

#### 面向初学者的运行流程

1. 点击“示例图纸”或选择自己的 DXF 文件。
2. 等待“运行前检查”完成，先确认 DXF 单位和图层数量。
3. 可以选择“教学示例”快速填入 6 层 / 5 米退线参数；这只是演示参数，不代表法定规划条件。
4. 运行任务后，在结果区打开报告或输出文件夹。报告会记录源文件 SHA-256、单位、楼层倍数和检查结果，便于复核。

#### 批量分析文件夹中的 DXF

桌面版的“5. 批量分析”页签可以一次处理一个文件夹中的多张 DXF；每张图纸会保存独立结果，另外生成 `batch_summary.csv` 汇总成功和失败原因。

命令行也可以使用同一模块：

```bash
planning-toolbox batch --input sample_data/ --task parcel --output output/batch
planning-toolbox batch --input sample_data/ --task indicator --floors 6 --output output/batch-indicator
```

桌面版的“7. CAD 图层标准化”页签默认开启“中国标准制图辅助”，可以选择“中国规划课程总平面”“中国居住区总平面”或“国土空间规划图件”模板。系统按所选模板建立18–25个相关图层，统一已有标准图层的颜色、线宽和线型，识别常见中文/英文别名，并保留无法识别的自定义图层；原始 DXF 不会被覆盖。输出除标准化 DXF 和图层报告外，还包含中文辅助检查报告及 JSON，明确区分单位阻断项、空的必备图层、自定义图层、坐标系人工复核项和已通过项。

中国制图辅助库共维护40类规划/总图/国土空间图层和5个可编辑矢量图块（指北针、100米图示比例尺、出入口、树木、5.0×2.5米停车位），按模板按需装入，不会让居住区图纸混入无关的国土空间控制线。来源索引记录 `GB/T 50001-2017`、`GB/T 50103-2010`、`GB/T 20257.1-2017`、`GB 50180-2018`、自然资源部2021年市级国土空间总体规划制图试行规范、2023年用地用海分类指南和 `GB/T 39972-2021`。内置颜色、线宽和线型属于学习辅助默认值；检查通过不等于法定审查或审批通过，正式项目仍须核对最新版标准、地方规划条件和设计单位要求。

桌面版的“8. 图纸质量增强检查”提供“最低人工修改（推荐）”“安全修复”“只检查”三种模式。推荐模式除扫描精确重复图元、未闭合线、自交候选、空图层和异常范围外，还会删除同图层重复 `LINE`，把同图层、同线型且无分叉的 `LINE`/开放 `LWPOLYLINE` 碎片吸附并合并成可编辑多段线，清理共线冗余点和极短段，同时按内置别名整理规划图层。分叉路口、弧线、样条、自交和块参照不会被强行修改。结果始终另存为新 DXF，并生成质量报告和逐项修改 CSV；原始 DXF 由 SHA-256 校验保持不变。距离型整理要求 `$INSUNITS` 已明确，单位未知时会阻断推荐模式。

#### 保存作业项目

桌面版顶部的“保存项目”会将当前 DXF 路径、结果输出目录、任务参数和最近一次结果记录保存为 `.ptx` 项目文件；下次点击“打开项目”可以恢复这些内容并继续工作。项目文件只保存轻量元数据、路径和参数，不复制或修改原始 DXF；如果图纸被移动，需要重新选择有效路径。

#### GIS–CAD–SU 全链路项目骨架

`v0.12.0` 在不增加大型依赖的前提下，将 `.ptx` 升级为兼容旧项目的第二版格式。点击桌面版顶部“🧭”可以保存项目名称、类型、项目 CRS、CAD 单位和 SketchUp 近原点变换；每个项目拥有稳定 UUID，后续 GIS 要素、CAD 图元和 SketchUp 对象可以通过确定性的 `PT-*` 编号保持关联。近原点变换同时保存 X/Y/Z 偏移与旋转角，可以无损转换回项目投影坐标。旧版 `.ptx` 打开时会根据项目路径生成稳定的兼容身份，不会修改原文件。

`v0.13.0` 将这个坐标契约接入可选 GIS 矢量桥：基础桌面版仍不捆绑 QGIS、GDAL 或 SketchUp；如果电脑已有 QGIS/GDAL，则自动调用其转换程序，支持 GeoPackage/Shapefile 与现有 DXF 流程连接。源 GIS/CAD 文件都做 SHA-256 前后校验，转换只写入新文件。经纬度和 `EPSG:3857` 不会被当作精确量算坐标；正式量算应使用项目所在地适用的 CGCS2000 投影坐标。

使用扩展 GIS 格式时：先点击“🧭”设置项目投影 EPSG，再进入“4. GIS 导出与导入”选择 GPKG/SHP 模式。软件会优先显示并调用 ArcGIS Pro；只有电脑没有 ArcGIS Pro 时才检测 QGIS/GDAL。现有 GeoJSON 功能始终不受影响。只导入多边形和多多边形，点、线、文字等会安全跳过并在结果中计数；GeoPackage 包含多个面图层时会要求先在 ArcGIS Pro 中只导出需要的图层，避免猜错。

`v0.15.0` 补齐 CAD → SketchUp 的实际交接。桌面版第 10 个任务把 `LWPOLYLINE`、`POLYLINE`、`LINE`、`ARC`、`CIRCLE`、`ELLIPSE` 和 `SPLINE` 归一为米制坐标，投影项目必须先应用可逆近原点变换；每个对象保留稳定 `PT-*` ID、DXF handle、来源图层和角色。楼层为 0 时明确生成二维线面，楼层大于 0 时必须同时填写标准层高，软件不会猜建筑高度。输出的 RBZ 通过 SketchUp 扩展程序管理器安装，在 SketchUp 的“扩展程序”菜单导入 `.ptsu.json` 后生成原生可编辑分组、面和推拉体。

`v0.16.0` 继续增强复杂 CAD 兼容性：`INSERT` 块参照和嵌套块会按原层级生成 SketchUp 分组，块内 0 图层对象继承插入层；`3DFACE`、`SOLID`、`TRACE` 作为可编辑面交接；`TEXT`、`MTEXT`、`ATTRIB`、`ATTDEF` 可按需作为 SketchUp 文字导入。界面默认保留图块和三维面、默认关闭文字，以兼顾信息完整性和模型流畅度。该流程仍不捆绑 SketchUp、不联网、不需要 API；填充、外部参照、代理对象、材质和复杂网格仍需人工复核。

`v0.17.0` 面向“尽量少人工返工”继续增强 CAD → SketchUp：课程作业/快速体量/汇报模型三档预设，按项目或用户选择的居住、办公、商业、校园、通用类型设置立面模数；按明确层高生成楼层辅助线，四边形建筑可生成双坡/四坡屋顶，平屋顶生成女儿墙，窗使用共享组件。schema 3 为每个对象保存确定性几何指纹；同一项目重复导入时只替换变化对象，SketchUp 菜单可锁定已精修对象防止覆盖。大型场地对窗组件均匀设置课程 8,000 / 汇报 16,000 的全局细节预算，保留所有建筑、楼层线和屋顶，同时避免模型无上限膨胀。实现仅参考开源项目的程序化建模与对象版本化思想，未复制其业务代码，也未增加大型依赖。

`v0.18.0` 新增逐栋建筑参数表。用户无需接触对象编号：系统从当前建筑图层只读列出顶层闭合轮廓，可多选建筑并批量设置各自楼层、标准层高、居住/办公/商业/校园/通用类型、平/双坡/四坡屋顶和模型精度。设置按项目 UUID 与 DXF handle 形成稳定建筑身份并随 `.ptx` 保存；未设置建筑继续使用全局默认，CAD 删除或重画轮廓造成的失配会在结果区明确提示。逐栋扫描只读取闭合状态和实体身份，不展开曲线点集；750 栋压力测试仍执行立面实例预算，并使用自动清理的临时目录。该升级未增加第三方运行依赖，也不需要 API。SketchUp 2026 `26.2.243` 真实验收已完成：修复 `Sketchup::Entities` 集合兼容问题后，真实生成并保存 4 栋程序化建筑、468 个共享窗组件、屋顶/女儿墙和 72 条楼层辅助线，同时导出可编辑 SKP 与 1600×1000 原生预览图。

`v0.20.0` 将场地语义接入 SketchUp 原生建模。schema 4 对闭合道路、绿地、停车和水体写入克制的厘米级视觉高差/薄层，避免共面闪烁；快速体量模式不生成这些细节。`PT_TREE`、`TREE_SYMBOL` 等叶级树木块会按 CAD 符号尺度生成分层圆冠的低多边形三维树，尺寸量化后复用 SketchUp 组件定义，树列不会逐棵复制整套几何。插件继续接受 schema 1–3。SketchUp 2026 真机测试生成 6 个树实例但只有 1 个树定义、10 个场地分层面和 9 个薄层，同时保留 4 栋建筑、468 个共享窗、72 条楼层线；所有建筑高度已按 Z 向包围盒复核。该升级不新增 Python 依赖、不需要 API，也不打包 SketchUp。

`v0.21.0` 在 schema 5 中补充建筑与场地表达：课程/汇报模式生成基座、入口和雨棚，汇报模式为住宅增加有界数量的共享阳台、为平屋顶增加轻量设备；入口会避让首层窗。道路、停车、水体和绿地可生成路缘、标线、水岸或收边，规则四边形道路生成有上限的中心虚线；建筑用途使用不同低饱和材质，树木增加确定性旋转和小范围缩放变化。SketchUp 2026 真机验收保存 4 栋程序化建筑、463 个共享窗、4 组入口/雨棚、3 个阳台、1 个屋顶设备、6 棵共享树和 10 个道路中心虚线，仍只有 1 个树定义。

`v0.22.0` 新增真正参与 CAD→SU 生成的轻量城乡规划建模知识库。规则文件记录 3 档精度、5 类建筑、4 类场地和植被细节预算，并为 OGC CityGML、CityJSON、OSM2World、SketchUp 官方资料和 3D City Database 保存来源、许可证、采纳范围与可信度。加载器会校验知识库结构，禁止嵌入图片、模型和模型权重；用户逐栋参数始终优先，规则不冒充规划审批或规范结论。完整说明见 [SKETCHUP_MODELING_KNOWLEDGE.md](SKETCHUP_MODELING_KNOWLEDGE.md)。本版本不增加 Python 依赖、不需要 API，完整回归 200/200 通过，并完成 SketchUp 2026 原生 SKP/PNG 真机验收。

`v0.23.0` 把“规则知识”升级为“规则 + 精选组件”的混合建模。组件目录记录 6 个许可清晰的来源，内置 7 个逐件转换和 SHA-256 校验的 CC0 SketchUp 组件，总计 193,334 bytes；运行时按需加载并共享定义。树木和建筑入口自动调用组件，汇报道路可生成共享街灯，`PT_PLANTER` / `PT_PARASOL` 块显式调用花池与遮阳伞；损坏或缺失时保留程序化生成或原块线稿。SketchUp 2026 `26.2.243` 真机验收创建 20 个组件实例但只加载 6 个定义，并保存原生 SKP 与 1600×1000 PNG。当前组件用于提高课程模型完成度，不替代重点建筑、景观和竖向设计。

`v0.24.0` 强化道路横断面与显式路口设施。接近矩形的闭合 ROAD 面可按用户选择生成完整街道或基础车行道：双侧人行带、端部开放的路缘、两条边线、中心虚线、双向箭头和有实例上限的共享街灯；不规则道路仍保留 CAD 原轮廓。组件库增加 KayKit CC0 斑马线道路块和交通灯，9 个原生 SKP 总计 342,348 bytes，CAD 块旋转角会保留。规则思想参考 [Godot Road Generator](https://github.com/TheDuckCow/godot-road-generator) 的横断面与分段预算、[Streetmix](https://github.com/streetmix/streetmix) 的街道组成交互，但没有复制其代码；只复用 [KayKit City Builder Bits](https://github.com/KayKit-Game-Assets/KayKit-City-Builder-Bits-1.0) 的两件 CC0 资产。SketchUp 2026 真机验证还发现并修复了原组件 X/Y/Z 包围盒缩放轴错误，树木、街灯、斑马线和信号灯现均按目标尺寸生成。

`v0.25.0` 修正斑马线方向并扩充轻量道路设施知识。普通 `PT_CROSSWALK` 会匹配最近的可信近矩形道路，使斑马线长条与车辆行驶方向平行，并按车行道宽度调整横跨距离；匹配成功时，中心虚线、方向箭头和自动街灯会避让过街区。七条白色标线改由插件生成独立薄实体，原 CC0 道路块只保留来源与尺寸审计，避免隐藏网格或道路底板影响显示。`PT_CROSSWALK_FIXED` / `PT_CROSSWALK_MANUAL` 可明确保留 CAD 角度。交叉口歧义、异形道路、距离过远或可信度不足时不会强行旋转，而是保留 CAD 角度并在结果页列入待复核。条纹数量、宽度、间距、表面偏移和实例上限由 `2026.08.4` 规则库统一控制，组件库仍只有 9 个 SKP、342,348 bytes，不新增常驻模型或 API。方向语义参考现行 [GB 5768.3-2025](https://std.samr.gov.cn/gb/search/gbDetailed?id=40C4523A3FB81115E06397BE0A0AE2D3) 元数据与 [FHWA MUTCD 第11版 Part 3](https://mutcd.fhwa.dot.gov/pdfs/11th_Edition/part3.pdf) 的公开方法说明，但系统仍是教学建模辅助，不给出规范合规结论。

`v0.26.0` 增加道路局部切线感知。满足两侧边界近似平行、宽度稳定条件的多段弯道会为斑马线提供局部方向；明确命名的 `ROAD_CENTERLINE`、`ROAD_AXIS` 或 `CENTERLINE` 开放线也可用于方向辅助。中心线的道路宽度会明确标记为概念估计，不会冒充测量值；弯道只输出局部方向提示，不强行生成超出 CAD 边界的矩形横断面。结果区新增弯道识别、中心线辅助、局部帧和局部切线计数，仍不需要 API 或大型知识库。

`v0.28.0` 修正图片→CAD→SketchUp 的底图贴合与道路缺失问题。重复屋顶不再按固定倍数扩成矩形，而是直接追踪原图闭合黑线；道路由长、宽度稳定且成网的双边线空白走廊生成 `BW_ROAD_CANDIDATE` 闭合面。SketchUp schema 7 同时导入 SHA-256 校验的原始 PNG 锁定底图和矢量参考底图，便于俯视核对。1076×1462 实图验收得到 30 个建筑、12 个道路面、189 棵树和 3 个停车候选；建筑边界采样平均/P90 偏差均为 0 px，道路平均约 3.49 px。图宽 360 m 仍是用户提供的暂定比例，所有道路和图片语义都必须复核，不能直接用于报批、施工或精确指标。

`v0.27.0` 强化复杂住宅总平图的图片→CAD→SketchUp 接力。黑白线稿会把重复屋顶核心及坡屋顶面作为两类独立证据，聚合同一建筑的重叠检测，并用限定半径的圆检测补齐被辐射线切碎的树冠符号。真实 1010×920 课程图验收从旧版 8 栋建筑、14 棵树提升到 26 栋建筑、91 棵树；SketchUp 使用 1 个锁定底图组、共享树组件和图片候选自适应窗户预算，保留屋顶、入口和立面表达。所有图片语义仍是待复核候选，不能替代楼层、建筑边界或审批判断；推荐使用原生清晰线稿，最长边 2000–4000 像素，模糊图单纯放大不会增加有效信息。

#### 多方案结果对比

桌面版顶部的“📊 方案对比”可以读取多个已保存的 `.ptx` 项目，提取每个项目最近一次结果中的有效地块/处理数、总用地面积、FAR、建筑密度、绿地率、停车位、退线或图层标准化结果，生成并排对比表，并可导出 CSV 或 Excel。切换到“🎨 图形叠加”后，不同方案会使用不同颜色绘制，重叠处混色，斜线标出方案独有的差异区域，并可导出叠加 PNG。对比模块只读取项目记录，不重新计算、不修改 DXF；修改参数后请重新运行并保存项目，再进行对比。

#### 参数化概念方案草图

桌面版的“6. 方案草图生成”页签可以先选择规范依据框架，再根据已有 `PARCEL` 地块，按建筑数量、概念覆盖率、退线距离、建筑间距和概念道路/消防通道宽度生成沿地块主方向布置的独立概念方案 DXF，并增加建筑尺寸/面积标注。默认的“自然曲线”布局会生成圆角建筑轮廓和弧形通行引导；需要规整表达时也可以切换为“简洁矩形”。填写楼层数后可以估算总建筑面积，填写停车配比后可以生成概念停车位。输出包含 `CONCEPT_SETBACK`、`CONCEPT_BUILDING`、`CONCEPT_PARKING`、`CONCEPT_GREEN`、`CONCEPT_ROAD`、`CONCEPT_LABEL` 和 `CONCEPT_DIMENSION` 图层，并生成 `*_concept_plan_schedule.csv` 明细表；仅用于方案研究，不能替代正式规划或施工图。

#### AI 效果图转 CAD 概念草图

桌面版的“9. AI 效果图转 CAD”支持两种本地转换流程。彩色分区模式把 AI 生成的**俯视、正交、低饱和度分区效果图**转换为 `AI_BUILDING`、`AI_ROAD`、`AI_GREEN`、`AI_WATER`、`AI_PARKING`、`AI_LABEL` 和 `AI_FRAME` 图层；黑白线稿模式支持白底黑线和黑底白线，并可自动判断主要底色。黑白模式默认开启“自动整理线条”：按方向安全连接中心线短段，保护正放或旋转矩形建筑的闭合候选，把重复小圆形符号归并为 `PT_TREE` 块引用，把至少三个尺寸与方向相近的窄矩形归并为 `PT_PARKING_STALL` 停车位块，并将规则圆形/椭圆拟合为真正的 DXF `ELLIPSE`。结果分为 `BW_LINEWORK`、`BW_CLOSED`、`BW_DETAIL`、`BW_BUILDING_CANDIDATE`、`BW_TREE_CANDIDATE`、`BW_PARKING_CANDIDATE`、`BW_LANDSCAPE_CANDIDATE` 和 `BW_FRAME`。所有名称含 `CANDIDATE` 的图层都只是几何候选，不代表系统已经理解真实用途，面积计算前必须人工确认。用户需要明确填写图片中整个场地的实际宽度；系统不会猜测比例。两种流程都生成预览 PNG 与说明报告，完全本地运行，不需要 API，也不会修改原图；透视、阴影、文字、树木纹理和复杂材质可能造成误识别，输出不能直接作为审批、测绘或施工成果。

黑白线稿建议优先使用“精细”或“极精细”：输入应为俯视正交、白底黑线、无阴影、无透视且线宽稳定的原生图，最长边 2000–4000 像素较合适。系统会按所选级别在 2400 或 4000 像素上限内处理；低分辨率会使相邻屋顶、连廊和树冠粘连，高分辨率但本身模糊的图片不会因放大而恢复真实细节。

#### 轻量图纸知识库与精选 CAD

`v0.10.0` 默认在图转 CAD 完成后生成一份 Markdown 图纸知识卡。知识卡只记录原图路径与 SHA-256、用户明确填写的比例依据、转换参数、候选对象数量、成果路径、可信度边界和人工复核状态；不会嵌入原图、缩略图、像素矩阵或模型权重。相同原图和相同参数会更新同一张卡，不会反复生成重复记录；本地检索知识卡时也不会加载原图。

系统采用“轻量索引 + 少量精选 CAD”的混合方式。自动转换页中的“收藏本次 DXF 为候选 CAD 样本”默认关闭，只有用户主动选择才复制 DXF；候选样本不会被冒充为标准答案。完成 CAD 人工精修后，可以在结果区点击“⭐ 收藏精修 CAD”，把经过检查的 DXF 作为 `user_curated` 个人参考样本保存。系统按需读取该 DXF，并记录单位、图层、图元数量、来源路径与 SHA-256。Markdown 用于查找和理解，精确几何仍以人工确认后的 DXF 为准。

知识库现在会真实参与黑白图转 CAD：系统从同一输出知识库中、同一图纸类型的 `user_curated` DXF 提取建筑长宽、停车位长宽和树木符号半径。新识别对象只有在形态与尺寸已经接近精选样本时才吸附到精修尺寸，差异较大的对象保持原样。普通模式仍要求至少 3 个相似封闭停车位；有人工确认尺寸时可以识别 2 个相似停车位，但单个矩形仍不会被提升。机器候选、单位未知 CAD 和“待确认”图纸类型不会参与几何校正。该过程是本地确定性规则，不是大型模型训练，也不需要 API。

规范依据框架目前包含：居住区国家标准框架（GB 50180-2018、GB 50137-2011、GB 55031-2022、GB 55037-2022）、民用建筑国家标准框架（GB 55031-2022、GB 55037-2022、GB 50352-2019）和自定义/地方条件。框架用于记录核对依据，不会自动生成全国统一的退线、停车或消防数值；正式项目必须填写项目所在地最新规划条件并核对正式标准文本。

中国制图辅助也可以从命令行使用：

```bash
planning-toolbox layer template --drafting-profile china_coursework_general --output output/china_coursework_template.dxf
planning-toolbox layer standardize --dxf input.dxf --drafting-profile china_residential_site --output output/
```

#### 作业助手与作业包

桌面版顶部的“📝 作业助手”会按地块面积、规划指标、退线检查、概念方案和 CAD-GIS 转换等作业类型，给出目标、具体步骤、输出文件和常见问题。任务完成后，结果区的“📤 导出 Excel/PDF/图片”可以生成 `.xlsx` 结果表、`.pdf` 结果报告和 `.png` 预览图；“🧰 整理为作业包”会把本次生成文件自动分为 `01_CAD`、`02_数据表`、`03_报告`、`04_预览图` 和 `05_其他`，并生成 `00_作业包说明.txt`、`00_结果摘要.txt` 与 ZIP 压缩包。该流程完全本地运行，不需要 API；作业包只是整理工具，仍需补充个人设计说明、截图和人工判断。

命令行也可以使用：

```bash
planning-toolbox concept --dxf sample_data/sample_parcels.dxf --standards-profile residential_national_framework --buildings 2 --coverage 25 --setback 5 --building-gap 6 --access-width 6 --floors 6 --parking-ratio 1.0 --output output/concept

# 自然曲线布局为默认值；如需规整矩形示意，可追加：--layout-style rectilinear
```

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

运行全部 148 项回归测试：

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
- `v0.6.0-desktop-ui`: Phase 6 Windows 本地桌面可视化工作台 (111/111 测试通过，提供完整 PySide6 界面、滚动适配、自然曲线概念方案草图、国标依据框架、AI 效果图转 CAD 概念草图、CAD 图层标准化、图纸质量增强检查、作业项目保存、多方案指标与图形叠加对比、作业助手、Excel/PDF/PNG 导出与作业包整理)
- `v0.7.0-minimum-manual-editing`: 人工修改最小化工作版本 (118/118 测试通过；新增无分叉碎线合并、重复 LINE 删除、共线/极短顶点清理、图层别名一体化整理、未知单位阻断和逐项修改 CSV；正式 Git 标签待工作树收口后创建)
- `v0.8.0-memory-cad-compatibility`: 内存与 CAD 兼容增强工作版本 (126/126 测试通过；空闲 GUI 按需加载、复杂图元预览/清点、块参照/XREF/布局审计、修复前后差异高亮及本机 DWG→DXF 助手)
- `v0.8.1-native-preview`: 原生低内存预览工作版本 (128/128 测试通过；主 CAD 预览改用 Qt 原生矢量画布，保留复杂图元、缩放拖动、完整场景高清 PNG 与旧预览接口兼容)
- `v0.8.2-image-to-cad`: 图转 CAD 整理增强工作版本 (130/130 测试通过；黑白中心线支持安全方向合并、闭合建筑候选保护、编辑用途分层和界面默认自动整理)
- `v0.8.3-cad-object-optimization`: 图转 CAD 图元轻量化工作版本 (132/132 测试通过；重复树木轮廓归并为 PT_TREE 块引用，大型规则椭圆拟合为 DXF ELLIPSE，主预览可展开树木块)
- `v0.8.4-cad-scenario-expansion`: 图转 CAD 场景扩展工作版本（136/136 测试通过；支持黑底白线自动判断、旋转矩形建筑、重复停车位 PT_PARKING_STALL 块和中等尺度规则圆/椭圆候选）
- `v0.9.0-lightweight-knowledge-base`: 轻量规划图纸知识库工作版本（144/144 测试通过；Markdown 卡片不嵌入图片，相同配置不重复建卡，可按需收藏少量候选/人工精修 DXF，并记录来源、单位、图层、图元数、SHA-256 与复核状态）
- `v0.10.0-knowledge-guided-cad`: 知识引导 CAD 质量增强工作版本（148/148 测试通过；只使用同类型 `user_curated` 米制 DXF，学习建筑/停车位/树木尺寸，对近似对象做保守几何校正，并支持两个已知尺寸停车位的知识辅助识别）
- `v0.11.0-china-drafting-assist`: 中国规划制图辅助工作版本（新增3套可选择模板、40类轻量图层、5个矢量图块、7项可追溯依据索引、单位/图层/样式/坐标人工复核检查和GUI/CLI输出报告；不冒充法定审批结论）
- `v0.12.0-chain-project-core`: GIS–CAD–SU 全链路项目骨架（`.ptx` v2 向后兼容、稳定项目身份、项目 CRS/CAD 单位、可逆近原点变换和跨软件稳定对象编号；保持轻量且不新增大型依赖）
- `v0.13.0-lightweight-gis-vector-bridge`: 轻量 GIS 矢量桥（基础 GeoJSON 保持兼容；可选调用本机 QGIS/GDAL 完成 GPKG/SHP↔DXF；强制米制投影 CRS、单位精确换算、临时文件自动清理和源文件 SHA-256 只读校验）
- `v0.14.0-arcgis-pro-adapter`: ArcGIS Pro 零增肥适配（优先调用现有 ArcGIS Pro 3.7 后台 ArcPy，不打开 ArcGIS 界面；没有时回退 QGIS/GDAL；真实 GPKG→投影 GeoJSON→DXF 往返保持坐标、单位与源哈希）
- `v0.15.0-sketchup-handoff`: CAD→SketchUp 轻量交接（第 10 个 GUI 任务、米制/近原点坐标契约、稳定对象 ID、二维/明确层高体量、可安装 RBZ 插件和本地中文教程；不打包 SketchUp、不使用 API）
- `v0.16.0-complex-cad-handoff`: 复杂 CAD→SketchUp 交接（嵌套块分组、3DFACE/SOLID/TRACE、可选文字、schema 1 向后兼容、182/182 测试通过；目录包和常驻内存基本不变）
- `v0.17.0-minimum-manual-sketchup`: SketchUp 低返工建模（程序化楼层线、屋顶/女儿墙、共享窗组件、三档细节预设、对象指纹、增量更新和手工锁定保护；183/183 测试通过）
- `v0.18.0-per-building-sketchup`: 逐栋 SketchUp 参数（每栋独立楼层/层高/类型/屋顶/精度、稳定 DXF 身份、项目保存恢复、失配提示和 750 栋有界内存压力流；187/187 测试通过）
- `v0.19.0-full-chain-workflow`: 九阶段全链路作业向导（资料来源选择、完成证据自动记录、可选阶段明确跳过、`.ptx` 进度恢复、任务/导出回调和窄屏图标布局；不增加大型依赖，191/191 测试通过）
- `v0.20.0-site-aware-sketchup`: 场地感知 CAD→SU（道路/绿地/水体/停车轻量分层、共享低多边形三维树、schema 1–4 兼容、工作图谱系续接和 SketchUp 2026 真机验收；196/196 测试通过）
- `v0.21.0-architectural-detail-sketchup`: 建筑与场地精细表达（入口/雨棚/基座、住宅阳台、屋顶设备、用途材质、路缘/标线/道路虚线和树木稳定变化；schema 1–5 兼容，197/197 测试通过）
- `v0.22.0-lightweight-su-knowledge`: 轻量城乡规划建模知识库（6 项可追溯来源、3 档精度、5 类建筑、4 类场地和植被规则；规则真实驱动 CAD→SU，不含图片/SKP/权重，200/200 测试与 SketchUp 2026 真机验收通过）
- `v0.23.0-reusable-su-components`: 轻量可复用 SketchUp 组件库（7 个 CC0 原生组件、193,334 bytes、逐件来源/许可证/尺寸/SHA-256/预算校验，入口、树木、街灯、花池和遮阳伞真实参与生成）
- `v0.24.0-road-cross-section`: 道路横断面与路口设施（可选完整/基础/关闭道路细化，双侧人行带、开放端部路缘、边线、中心虚线、双向箭头、共享街灯，以及保留 CAD 旋转的 CC0 斑马线和交通灯；SketchUp 2026 真机尺寸复核）
- `v0.25.0-crosswalk-road-alignment`: 斑马线道路感知（可信规则道路自动对齐、车行道宽度适配、手动角度块、歧义/异形安全回退、结果页复核计数与轻量规则库扩充）
- `v0.26.0-road-local-tangent`: 弯道/多段道路局部切线与显式道路中心线方向辅助，宽度可信度标记、弯道候选预算和结果区复核计数
- `v0.28.0-source-aligned-underlay`: 原线追踪建筑、双边线道路候选、语义叠加预览、SHA-256 锁定 PNG 底图与 SketchUp schema 7；真实 SketchUp 2026 生成 30 栋建筑、12 个道路面和 189 棵共享树
- `v0.30.0-in-app-semantic-guide-editor`: 原图 + 同像素语义引导图现在可直接在工作台内编辑。使用道路、建筑、绿化、水体、停车和橡皮工具在半透明叠加层上补画；复杂道路可切换“道路路径”逐点对齐，双击/完成路径一次提交整条道路，并支持撤销/重做。鼠标滚轮缩放、中键平移、双击适配。原图始终锁定，保存时强制 PNG、像素尺寸一致并在前后执行 SHA-256 零修改校验；用户可直接接续生成 AI_* 闭合 CAD 面和 SketchUp 模型。
- `v0.45-alignment-quality-review`: 黑白图转 CAD 为建筑/道路候选增加原图边界平均偏差与 P90 质量指标，并在结果区提示先查看叠加图再进入 CAD/SU。
- `v0.46-road-centerline-candidates`: 黑白图转 CAD 额外输出 `BW_ROAD_CENTERLINE_CANDIDATE` 道路中心线候选层，结果区显示可接力 SketchUp 的中心线数量；中心线仍明确标记为候选，需先查看叠加图确认道路范围。
- `v0.47-road-diagnostics-width-handoff`: 输出道路专用中心线叠加复核图，检测多种道路宽度并将每条中心线的宽度写入 DXF XDATA；SketchUp 开启中心线道路带且不手填统一宽度时，会自动按各中心线宽度接力，减少逐条调整。
- `v0.48-road-confidence-review`: 为每条道路中心线写入可信度、候选编号和复核状态；叠加图用橙色/红色区分可用于概念建模与需优先复核的路段，SketchUp 交接文件同步保留该标记。
- `v0.49-one-click-road-repair`: 图片转 CAD 结果区新增“修正道路”入口，自动带入原图与语义引导草稿并打开道路路径编辑器；保持原图/DXF 只读，窄屏布局无横向溢出。
- `v0.50-pixel-aligned-road-review-overlay`: 一键道路修正编辑器增加同像素道路复核叠加层；橙/红提示只作为显示层，不会污染语义引导 PNG，保存后仍可直接回流图片转 CAD。
- `v0.51-direct-image-to-sketchup-handoff`: 图转 CAD 结果区新增“继续生成 SketchUp”直达入口；自动带入生成 DXF，并在检测到道路中心线候选时打开中心线道路带接力，减少重新选文件和漏开道路选项造成的返工。
- `v0.52-trusted-road-corridor-gate`: SketchUp 道路带新增“仅高可信候选生成实体（推荐）/全部候选生成实体”策略；低可信图像识别道路保留为待复核中心线，不再自动放大为错误道路面。
- `v0.53-road-centerline-network-merge`: 黑白图道路中心线会保守拼接高可信、宽度相近且方向连续的短段；低可信、异宽和明显转弯候选保持独立，减少 SketchUp 中同一路段被拆成多个道路组的返工。
- `v0.54-image-road-surface-dedup`: 图片道路同时存在面候选和可信中心线时，推荐策略只让中心线生成道路实体；重复面候选保留为可见复核轮廓，不再重复生成厚度、标线和街灯。真实 SketchUp 2026 模型直接面数减少约 27%，建筑和源图位置保持不变。
- `v0.55-cad-semantic-visual-hierarchy`: 黑白图转 CAD 不再把所有对象都显示为同一种黑线。已识别建筑使用低饱和暖红、道路浅灰、树木/绿化柔绿、停车米黄、道路中心线蓝灰虚线；未确认线条降为浅灰参考线。建筑与道路半透明 HATCH 分别放在可独立关闭的 `BW_BUILDING_FILL` / `BW_ROAD_FILL` 图层，边界多段线仍是唯一可编辑几何依据。显示填充带有 `PT_PRESENTATION_FILL` 标记，进入 SketchUp 时有记录地忽略，不会生成重复面或增加待复核错误。道路中心线网络还会在可信、同宽级、方向明确且距离受限时尝试端点路口和 T 形路口安全连接；歧义路口保持原样。
- `v0.56-sketchup-full-road-path`: CAD→SketchUp 道路中心线改为按全路径弧长均匀取样，从真实起点覆盖到真实终点，每条最多 64 个断面；密集折线不再只生成前 64 个源线段，两点中心线也能完整建模。斑马线会投影到连续道路段，并沿最近局部道路轴向校正，兼顾稀疏长路和弯道。结果区新增“道路全长覆盖”，帮助页说明精度上限与人工复核边界。真实用户图 13/13 条道路端点误差不超过 0.000001 m，SketchUp 2026 真机与 254 项测试通过。
- `v0.57-course-building-semantics`: CAD 建筑图层可明确携带楼层、层高、总高、用途和屋顶，例如 `BUILDING_RES_6F_FH3.0_FLAT`、`住宅_6层_层高3.1_平屋顶`；逐栋设置优先、明确图层参数其次、全局参数最后，普通数字不会被猜成高度。结果区新增九项“课程基础模型检查”，客观提示建筑层次、道路、绿化、停车、底图和候选复核缺口，但不冒充课程评分或规范结论。多高度实例在 SketchUp 2026 真机生成4类建筑、3档高度和平/双坡/四坡屋顶；真实用户图被诚实评为7/9，256项测试通过。
- `v0.58-lightweight-planning-component-pack`: 组件资源包硬上限提升为 100 MB，但首批实际只增加到约 1.22 MB；新增停车车辆、公共座椅、灌木组、道路隔离柱和公交候车亭 5 个可复用组件。组件使用共享定义、按需加载和项目原生过程式生成，兼容 SKP 快照只作备用，不需要 API。新增 22 类规划建模参考模式索引，保存来源页面、参考图检索词、几何要点和复核清单，不嵌入图片、纹理或模型权重。
- `v0.29.0-semantic-guide-draft`: 原图 + 同像素语义引导图工作流；黑白转换自动输出预填建筑/道路/绿化/停车的可编辑草稿，用户只需补漏或擦除误判即可重新生成 AI_* 闭合 CAD 面；原图与引导图双 SHA-256 只读校验，230/230 测试和 SketchUp 2026 真机验收通过
- `v0.27.0-image-semantic-recall`: 重复屋顶核心与坡屋顶面聚合、辐射树冠圆检测、图片来源 SU 立面自适应预算；真实 SketchUp 2026 生成 26 栋坡屋顶建筑和 91 棵共享树
- `semantic-full-chain-working-batch`: 图片转 CAD 轻量语义 sidecar、修复/图层标准化谱系接力、schema 6 `PT_UNDERLAY` 锁定底图聚合、向导状态提示与真实 SketchUp 2026 总平面验收（222/222 测试通过；正式版本号与 Git 标签待工作树收口后决定）
