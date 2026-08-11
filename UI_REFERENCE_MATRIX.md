# Planning Toolbox 前端 UI 参考矩阵分析 (UI Reference Matrix)

> **当前补充版本**: `v0.26.0-road-local-tangent`（保留 v0.6.0 原始 UI 审计内容）
> **项目根目录**: `C:\AutoOS\OS1`
> **目的**: 总结并对比开源 GIS / Web 地图项目的功能组织、界面交互与设计理念，指导 Planning Toolbox 本地图形化桌面工作台及未来 Web 版的演进方向。

> **v0.13.0 补充**：全链路实现直接使用 MIT 许可证的 `ezdxf`；GPKG/SHP 扩展只通过独立进程调用用户电脑已有的 GDAL `ogr2ogr`，不复制或链接 QGIS 源码；`pyproj` 仅为源码环境可选 CRS 复核组件。SketchUp 官方 Ruby API 教程与 stubs 仅作为下一阶段插件结构参考，当前尚未复制其代码。

> **v0.14.0 补充**：检测到 ArcGIS Pro 时优先调用其独立 Python/ArcPy 进程，未复制 Esri 代码、未把 ArcPy 打包或重新分发；仅在用户已有有效 ArcGIS Pro 安装与许可的电脑上使用。QGIS/GDAL 保留为第二适配器。

> **v0.15.0 补充**：已按 SketchUp 官方 Ruby API 扩展结构独立实现本地 RBZ 导入器，参考的是公开接口与教程结构，没有复制 QGIS/SketchUp 经典项目的业务代码。插件只读取 Planning Toolbox 自有 `.ptsu.json`，在 SketchUp 主线程事务中创建原生分组、标签、面和推拉体。

> **v0.16.0 补充**：根据 ezdxf 官方虚拟图元/递归分解接口和 SketchUp 官方 `Entities` 接口扩展复杂 CAD 交接，独立实现嵌套块分组、三维面和可选文字；没有复制外部项目业务代码，也没有引入新的大型运行时。

> **v0.17.0 补充**：参考 [Building Tools](https://github.com/ranjian0/building_tools) 的程序化楼层/窗/屋顶拆分思路，以及 [Speckle Connectors](https://github.com/specklesystems/speckle-sharp-connectors) 的对象化与版本更新思想，独立实现 SketchUp 建模预设、共享窗组件、确定性几何指纹、增量更新与手工锁定保护。Building Tools 为 MIT，Speckle Connectors 为 Apache-2.0；本项目没有复制二者代码，也没有引入 Blender、Speckle 服务端或其运行时。

> **v0.24.0 补充**：道路增强参考 [Godot Road Generator](https://github.com/TheDuckCow/godot-road-generator)（MIT）的横断面、分段生成与几何预算，以及 [Streetmix](https://github.com/streetmix/streetmix)（AGPL-3.0-or-later）的街道组成交互。两者均只参考思想、不复制代码、不引入运行时。实际复用仅限 [KayKit City Builder Bits](https://github.com/KayKit-Game-Assets/KayKit-City-Builder-Bits-1.0) 的斑马线道路块和交通灯两件 CC0 资产，并保留来源、许可证、哈希、尺寸和实例预算。

> **v0.25.0 补充**：斑马线方向规则参考国家标准信息公共服务平台发布的 `GB 5768.3-2025` 标准元数据和 FHWA `MUTCD 11th Edition Part 3` 的公开方向语义，独立实现道路有向矩形匹配、车行道宽度适配、手动角度覆盖与歧义安全回退。未复制标准正文、示意图或第三方算法代码；这些来源只用于可解释的建模语义和复核边界，不把课程模型声明为规范合规成果。

> **v0.26.0 补充**：沿用 Godot Road Generator 的“道路段/横断面分离”思想，独立实现多段道路边界配对、局部切线帧和显式道路中心线辅助；没有复制第三方代码，也没有增加运行时。结果页将弯道识别、中心线辅助、局部帧和局部切线数量展示给非专业用户，并把中心线宽度标记为概念估计；交叉口竞争或边界不稳定时保留 CAD 角度并要求复核。

---

## 一、开源参考项目核心对照矩阵 (Reference Matrix)

| 参考项目 | 参考内容 | Planning Toolbox 采用方式 | 是否当前实现 (v0.6.0) | 许可证 (License) |
|---|---|---|:---:|---|
| **QGIS**<br>([QGIS/QGIS](https://github.com/qgis/QGIS)) | 图层管理面板、处理工具箱、CRS/单位警告、状态反馈 | 左侧数据检查区 (图层/单位/实体统计)，处理任务区 (参数表单与任务队列)，结果区安全警告 | **是** (桌面版) | GPL-2.0-or-later |
| **OpenJUMP**<br>([openjump-gis/openjump](https://github.com/openjump-gis/openjump)) | 本地桌面 GIS 布局、拓扑检查与几何分析入口、小而专注结构 | 主窗口四大区域布局 (文件/检查/任务/结果)，专注地块/指标/退线/GIS 四大计算任务 | **是** (桌面版) | GPL-2.0 |
| **QField**<br>([opengisch/QField](https://github.com/opengisch/QField)) | 低认知负担、极简交互、分步骤引导、清晰状态反馈 | 减少不必要选项，提供必填项提示 (如楼层数)，不向非程序用户展示 Traceback | **是** (桌面版) | GPL-2.0 |
| **MapStore2**<br>([geosolutions-it/MapStore2](https://github.com/geosolutions-it/MapStore2)) | 顶部工具栏、仪表盘式结果展示、地图与表格联动 | 结果区指标卡片与表格化总结；未来自研 Web 版参考顶栏与属性面板布局 | **否** (未来 Web 版) | BSD-2-Clause |
| **Leaflet-Geoman**<br>([geoman-io/leaflet-geoman](https://github.com/geoman-io/leaflet-geoman)) | 边界绘制、顶点吸附、裁切分割、多边形编辑工具栏 | 预留未来 2D Canvas / Web 地图边界交互接口；当前版保持静止只读预览与结果显示 | **否** (未来 2D/3D 版) | MIT |
| **GeoNode**<br>([GeoNode/geonode](https://github.com/GeoNode/geonode)) | 数据集管理、元数据编辑、非专业用户资源管理 | 未来多人协作平台参考；当前版不引入数据库、用户登录或云端存储 | **否** (未来云端版) | GPL-3.0-or-later |
| **GeoServer**<br>([geoserver/geoserver](https://github.com/geoserver/geoserver)) | 空间数据服务 (WMS/WFS)、图层发布、CRS 坐标转换引擎 | 未来后端空间服务参考；当前版不运行 Web 服务器或后台守护进程 | **否** (未来云端版) | GPL-2.0-or-later |
| **Building Tools**<br>([ranjian0/building_tools](https://github.com/ranjian0/building_tools)) | 程序化楼层、窗、门和屋顶的可组合生成 | 只采纳“按预设生成轻量细节”的思想；在 SketchUp Ruby API 中独立实现楼层线、屋顶/女儿墙和共享窗组件 | **是** (v0.17 独立实现) | MIT |
| **Speckle Connectors**<br>([specklesystems/speckle-sharp-connectors](https://github.com/specklesystems/speckle-sharp-connectors)) | AEC 对象化、稳定身份与增量同步 | 只采纳对象版本化思想；使用自有 PT-* ID、SHA-256 几何指纹与本地 JSON 实现增量更新，不接入 Speckle 服务 | **是** (v0.17 独立实现) | Apache-2.0 |
| **Godot Road Generator**<br>([TheDuckCow/godot-road-generator](https://github.com/TheDuckCow/godot-road-generator)) | 横断面、车道/路肩分离、道路段按需生成、几何预算 | 独立实现规则道路的人行带、车行带、路缘、标线、箭头和街灯预算；未复制 GDScript | **是** (v0.24 独立实现) | MIT |
| **Streetmix**<br>([streetmix/streetmix](https://github.com/streetmix/streetmix)) | 面向普通用户的街道横断面组合与预设 | 参考“完整/基础/关闭”低认知负担预设；不复制 Web 代码或素材 | **是** (仅交互参考) | AGPL-3.0-or-later |
| **KayKit City Builder Bits**<br>([KayKit-Game-Assets/KayKit-City-Builder-Bits-1.0](https://github.com/KayKit-Game-Assets/KayKit-City-Builder-Bits-1.0)) | 轻量城市道路与交通设施组件 | 仅复用斑马线道路块和交通灯两件 CC0 资产，经 SketchUp 2026 转换为原生 SKP 并逐件校验 | **是** (v0.24) | CC0-1.0 |
| **OSMnx / OSM2World** | OSM 道路网络获取、二维语义转三维 | 保留为未来 OSM 导入参考；当前不引入网络下载、Java 或完整 Python 图分析栈 | **否** (候选) | MIT |
| **Lanelet2**<br>([fzi-forschungszentrum-informatik/Lanelet2](https://github.com/fzi-forschungszentrum-informatik/Lanelet2)) | 高精地图车道与交通规则语义 | 当前个人作业场景过重，不引入 C++/ROS 栈 | **否** | BSD-3-Clause |

---

## 二、逐项参考深度分析 (Detailed Analytical Breakdown)

### 1. QGIS (桌面 GIS 处理工具箱与状态提示范式)
- **选择原因**: QGIS 是全球最成熟的开源 GIS 软件，其 Processing Toolbox（处理工具箱）与消息栏（Message Bar）是空间分析交互的行业标准。
- **采纳的交互**: 
  - 采纳了 QGIS 的“参数配置 → 后台 Thread 运行 → 结果摘要”流水线。
  - 采纳了 QGIS 的强安全提示机制（单位未知或 GeoJSON 未投影时弹出高亮红色警告）。
- **明确不采纳的功能及理由**: 
  - **不采纳** QGIS 极其复杂的 C++ CGL/GDAL 插件渲染架构与数百个通用 GIS 工具，避免引起非程序员规划学生的学习焦虑。
- **许可证与安全分析**: QGIS 采用 GPL-2.0-or-later。Planning Toolbox 为独立 PySide6 GUI，仅通过 Python 标准库与 `ezdxf`/`shapely` 库调用自身计算引擎，**不包含或链接 QGIS 任何 C++ 代码**，无 GPL 污染或许可证风险。
- **工程复杂度**: 零额外 C 库依赖，工程复杂度增量极小。

### 2. OpenJUMP (小而专注的 Windows 本地几何拓扑分析桌面形态)
- **选择原因**: OpenJUMP 以极其轻量、专注几何拓扑分析（Topology & Vector Analysis）著称，是桌面向量分析软件的典型代表。
- **采纳的交互**: 
  - 采纳了 OpenJUMP 的“四大区域分区”桌面布局（文件区、数据检查区、任务区、结果与日志区）。
  - 采纳了“按任务选择并提供直观参数”的轻量桌面前端形态。
- **明确不采纳的功能及理由**: 
  - **不采纳** OpenJUMP 的 Java Swing 界面框架与复杂图层树多重嵌套。
- **许可证分析**: OpenJUMP 为 GPL-2.0。Planning Toolbox 采用自研 PySide6 界面与自研几何算法，无代码复制。

### 3. QField (面向非专业用户的低认知负担与极简交互)
- **选择原因**: QField 专门针对外业调查与非专业人员设计，主打“少按钮、少术语、分步骤”。
- **采纳的交互**: 
  - 采纳了“降低认知负荷”的设计哲学：所有输入框带有中文 Placeholder 与直观提示。
  - 彻底屏蔽 Python 控制台 Traceback，向规划学生展示包含具体 AutoCAD 操作建议的中文帮助说明。
- **明确不采纳的功能及理由**: 
  - **不采纳** QField 针对触控屏的大图标手势交互。

### 4. MapStore2 (未来 Web 版地图与仪表盘分析参考)
- **选择原因**: MapStore2 具备优秀的 Web 空间仪表盘（Dashboard）与地图表格联动能力。
- **当前处理方式**: **明确不采纳在 v0.6.0 桌面版中引入**。MapStore2 依赖 React/Redux/GeoServer，若引入会导致架构过度膨胀。将其作为未来 Web SaaS 版本的参考模型。

### 5. Leaflet-Geoman (未来矢量边界几何编辑工具栏参考)
- **选择原因**: Leaflet-Geoman 是前端最优秀的多边形绘制与边界裁切/编辑插件。
- **当前处理方式**: **当前版本不实现矢量在线编辑**。界面布局上为未来增加几何画板预留区域，当前专注于“导入 DXF ➔ 自动计算 ➔ 输出结果”。

### 6. GeoNode 与 7. GeoServer (未来云端数据管理与空间服务参考)
- **选择原因**: 企业级空间数据管理与 WMS/WFS 地图服务。
- **当前处理方式**: **明确禁止在当前 MVP 中引入**。当前 `v0.6.0-desktop-ui` 不包含任何数据库 (PostGIS)、Web 服务器、用户注册或云端存储，保持零网络依赖的纯本地桌面工具属性。

---

## 三、合规性与边界承诺 (Compliance & Boundary Commitments)

1. **代码与资产合规**: 本项目没有复制上述参考项目的业务代码、界面图片或商标；GUI 使用 PySide6 (LGPLv3) 自研构建。唯一新增复用内容是逐件审核并注明来源的 CC0 SketchUp 组件资产。
2. **零核心引擎侵入**: 界面完全构建于现有的 `planning_toolbox` 核心模块之上，未修改任何已通过测试的 CAD/GIS 计算逻辑。
3. **CLI 完全保留**: 统一命令行 `planning-toolbox [parcel|layer|gis|indicator|validate]` 继续 100% 可用。
4. **安全提示不可隐藏**:
   - DXF 单位未知 ($INSUNITS=0) 时强制拦截面积与距离计算。
   - 规划指标计算强制要求用户填写楼层数，拒绝隐式默认。
   - GIS 导出与导入明确提示 CRS 未进行经纬度投影转换，并拦截 WGS84 经纬度 GeoJSON 输入。
5. **回归测试通过**: 当前工作树全量 210 项自动化测试 100% 通过，并完成 ArcGIS Pro 3.7 真实互操作、复杂 CAD 交接、SketchUp 2026 程序化建模/增量更新、斑马线道路感知与 RBZ 结构验证。

## 四、全链路工程参考与实际采用状态（v0.13.0）

| GitHub 项目 | 许可证 | 当前状态 | 实际用途与边界 |
|---|---|---|---|
| `mozman/ezdxf` | MIT | 已直接依赖 | DXF 读取、写入、图元审计与单位标记；保留第三方许可证。 |
| `OSGeo/gdal` | MIT-style | 可选外部调用 | 检测用户已安装的 `ogr2ogr`，完成 GPKG/SHP/GeoJSON 格式转换与投影；不打包 GDAL。 |
| `pyproj4/pyproj` | MIT | 可选 | 源码环境安装后增加 EPSG 类型与米制轴复核；基础 EXE 排除该依赖。 |
| `QGIS/QGIS` | GPL-2.0-or-later | 交互参考 / 外部安装来源 | 参考 CRS 提示与处理工具箱流程；不复制、不链接 QGIS 代码。 |
| `SketchUp/sketchup-ruby-api-tutorials` / `ruby-api-stubs` | MIT | 已参考接口结构 | 独立实现 RBZ 根加载器、扩展菜单、事务、嵌套分组、原生面、文字与属性字典；未复制示例业务代码，已通过 SketchUp 2026 `26.2.243` 真机导入、SKP 保存和 PNG 视觉验证。 |

本阶段没有把 GPL 项目代码复制进 Planning Toolbox，也没有引入 QGIS、Blender、GeoServer、PostGIS 等大型运行时，因此扩展 GIS 能力不会使基础桌面包明显膨胀。
