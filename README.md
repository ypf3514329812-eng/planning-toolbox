# Planning Toolbox (城乡规划 CAD–GIS 自动化辅助工具箱)

> 自动消除城乡规划学习、课程设计和规划分析过程中重复、机械、低价值的数据整理、CAD 制图、GIS 转换、面积统计、指标核算和规则检查工作。
> **原则：人负责规划判断，程序负责计算和重复劳动。**

---

## Quickstart Guide for Planning Students (使用指南)

本工具箱无需修改任何 Python 源代码即可使用！

### 1. 环境准备

确保已安装 Python 3.10+。在命令行运行：

```bash
pip install -e .
```

### 2. MVP-1 地块面积与编号工具

将 CAD 图纸（.dxf 格式）放入 `sample_data` 目录或任意路径，运行以下简单命令：

```bash
python scripts/run_parcel_tool.py --dxf sample_data/sample_parcels.dxf
```

运行后会在 `output/` 目录中自动生成：

1. `sample_parcels_labeled.dxf` — 包含地块编号（如 P001）与面积（如 1.24 ha）的标注 DXF 图纸。
2. `sample_parcels.csv` — 地块面积及状态统计表格。
3. `parcel_report.txt` — 详细处理报告（包含有效地块数、未闭合图形及面积汇总）。

---

## 项目架构与自动化测试

运行核心测试集：

```bash
pytest
```

---

## Git 版本记录

各稳定版本使用 Git tag 标记：
- `v0.1.0-mvp1`: MVP-1 地块面积与编号工具稳定版。
