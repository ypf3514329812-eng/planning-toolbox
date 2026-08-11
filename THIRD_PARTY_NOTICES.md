# Third-Party Notices

Planning Toolbox 的公开源码和随项目发布的组件必须保留各自许可证。此文件是发布清单，不替代第三方原始许可证文本。发布前应根据实际打包内容重新生成并复核。

## Python 依赖

| 依赖 | 用途 | 许可证/说明 |
|---|---|---|
| ezdxf | DXF 读写、图元审计和单位标记 | MIT；保留其许可证和版权声明 |
| Shapely | 平面几何与空间分析 | BSD 3-Clause |
| PyYAML | 配置和规则读取 | MIT |
| PySide6 / Qt for Python | Windows 桌面 GUI | LGPLv3/GPLv3 或商业许可；目录版/EXE 发布必须附相应 Qt 通知与许可材料 |
| Matplotlib | 可选图表和报告渲染 | Matplotlib License |
| openpyxl | Excel 导出 | MIT |
| ReportLab | PDF 导出 | BSD-style / ReportLab license |
| scikit-image | 可选图像处理 | BSD 系列及其依赖的各自声明 |
| pyproj | 可选 CRS 能力 | MIT；不属于基础依赖 |

## 随项目提供的素材

- Kenney City Kit 精选素材：CC0-1.0，原始许可证位于 `assets/sketchup_component_sources/kenney_cc0/`；
- KayKit City Builder Bits 精选素材：CC0-1.0，原始许可证位于 `assets/sketchup_component_sources/kaykit_cc0/`；
- Planning Toolbox 原生过程式组件：由本项目代码生成，仍需遵守本项目许可证。

## 仅作参考而未复制代码的项目

QGIS、OpenJUMP、QField、MapStore2、Leaflet-Geoman、GeoNode、GeoServer、Building Tools、Speckle Connectors、Godot Road Generator、Streetmix、OSM2World 和 3D City Database 等项目仅用于交互、数据组织或建模思想参考，未作为运行时依赖，也不应在发布包中暗示其背书关系。具体边界见 `UI_REFERENCE_MATRIX.md` 和 `SKETCHUP_MODELING_KNOWLEDGE.md`。

## 发布前必做

1. 选择并添加本项目根许可证；
2. 将实际分发的 Qt、Python 和二进制依赖清单固定到 Release；
3. 附上依赖许可证全文或明确的获取方式；
4. 对 PySide6/Qt 动态库分发执行 LGPLv3 合规检查；
5. 不把未经审计的图片、纹理、模型、字体或标准全文放入 Release。
