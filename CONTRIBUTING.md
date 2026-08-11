# Contributing to Planning Toolbox

感谢你关注 Planning Toolbox。项目目前处于 Public Beta，欢迎提交文档改进、可复现的 CAD/GIS 缺陷报告、测试样例和小型功能修复。

## 提交前检查

- 不要提交真实用户图纸、个人信息、学校项目资料或来源不明的图片/模型；
- 使用合成或已获许可的 DXF、GeoJSON、图片和 SketchUp 资产；
- 说明操作系统、Python 版本、Planning Toolbox 版本和可选软件版本；
- 对几何问题提供最小可复现样例，不要上传完整课程作业；
- 运行 `python -m pytest -q`，并在 Pull Request 中说明结果；
- 任何涉及规范模板的修改必须附标准编号、版本、适用地区和非审批声明。

## Pull Request 原则

每个 PR 尽量只解决一个问题，并说明：

1. 用户遇到什么问题；
2. 修改后的行为是什么；
3. 新增或更新了哪些测试；
4. 是否影响 DXF 零修改、单位/CRS 阻断、MCP 安全边界或输出格式；
5. 是否增加依赖、安装包体积或内存占用。

功能代码、GUI、SketchUp Ruby 插件、文档和测试应尽量保持清晰分层。不要为了提高测试数字而降低几何安全门或隐藏待复核结果。

## 设计边界

Planning Toolbox 是规划学习与研究辅助工具，不是法定审批、施工图审查或专业责任替代品。涉及面积、规范、坐标、道路和建筑语义的自动结果必须保留来源、参数和人工复核状态。

## 开发环境

```text
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

ArcGIS Pro、SketchUp 和 ODA/AutoCAD 属于可选的本机验收环境，不要求贡献者安装全部软件。
