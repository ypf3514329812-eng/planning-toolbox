# Planning Toolbox 前端 UI 参考矩阵分析 (UI Reference Matrix)

> **版本**: `v0.6.0-desktop-ui`  
> **项目根目录**: `C:\AutoOS\OS1`  
> **目的**: 总结并对比开源 GIS / Web 地图项目的功能组织、界面交互与设计理念，指导 Planning Toolbox 本地图形化桌面工作台及未来 Web 版的演进方向。

---

## 一、开源参考项目核心对照矩阵 (Reference Matrix)

| 参考项目 | 参考内容 | Planning Toolbox 采用方式 | 是否当前实现 (v0.6.0) | 许可证 (License) |
|---|---|---|:---:|---|
| **QGIS**<br>([QGIS/QGIS](https://github.com/qgis/QGIS)) | 图层管理面板、处理工具箱、CRS/单位警告、状态反馈 | 左侧数据检查区 (图层/单位/实体统计)，处理任务区 (参数表单与任务队列)，结果区安全警告 | **是** (桌面版) | GPL-2.0-or-later |
| **OpenJUMP**<br>([openjump-gis/openjump](https://github.com/openjump-gis/openjump)) | 本地桌面 GIS 布局、拓扑检查与几何分析入口、小而专注结构 | 主窗口四大区域布局 (文件/检查/任务/结果)，专注地块/指标/退线/GIS 四大计算任务 | **是** (桌面版) | GPL-2.0 |
| **QField**<br>([opengisch/QField](https://github.com/opengisch/QField)) | 低认知负担、极简交互、分步骤引导、清晰状态反馈 | 减少不必要选项，提供必填项提示 (如楼层数)，不向非程序用户展示 Traceback | **是** (桌面版) | GPL-3.0-or-later |
| **MapStore2**<br>([geosolutions-it/MapStore2](https://github.com/geosolutions-it/MapStore2)) | 顶部工具栏、仪表盘式结果展示、地图与表格联动 | 结果区指标卡片与表格化总结；未来自研 Web 版参考顶栏与属性面板布局 | **否** (未来 Web 版) | BSD-2-Clause |
| **Leaflet-Geoman**<br>([geoman-io/leaflet-geoman](https://github.com/geoman-io/leaflet-geoman)) | 边界绘制、顶点吸附、裁切分割、多边形编辑工具栏 | 预留未来 2D Canvas / Web 地图边界交互接口；当前版保持静止只读预览与结果显示 | **否** (未来 2D/3D 版) | MIT |
| **GeoNode**<br>([GeoNode/geonode](https://github.com/GeoNode/geonode)) | 数据集管理、元数据编辑、非专业用户资源管理 | 未来多人协作平台参考；当前版不引入数据库、用户登录或云端存储 | **否** (未来云端版) | GPL-3.0-or-later |
| **GeoServer**<br>([geoserver/geoserver](https://github.com/geoserver/geoserver)) | 空间数据服务 (WMS/WFS)、图层发布、CRS 坐标转换引擎 | 未来后端空间服务参考；当前版不运行 Web 服务器或后台守护进程 | **否** (未来云端版) | GPL-2.0-or-later |

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

1. **零代码复制与开源合规**: 本项目未复制上述 7 个开源项目的任何源代码、资产图片或商标。所有 GUI 界面使用 PySide6 (LGPLv3) 自研构建。
2. **零核心引擎侵入**: 界面完全构建于现有的 `planning_toolbox` 核心模块之上，未修改任何已通过测试的 CAD/GIS 计算逻辑。
3. **CLI 完全保留**: 统一命令行 `planning-toolbox [parcel|layer|gis|indicator|validate]` 继续 100% 可用。
4. **安全提示不可隐藏**:
   - DXF 单位未知 ($INSUNITS=0) 时强制拦截面积与距离计算。
   - 规划指标计算强制要求用户填写楼层数，拒绝隐式默认。
   - GIS 导出与导入明确提示 CRS 未进行经纬度投影转换，并拦截 WGS84 经纬度 GeoJSON 输入。
5. **回归测试通过**: 全量 71 项自动化测试 100% 保持绿色通过。
