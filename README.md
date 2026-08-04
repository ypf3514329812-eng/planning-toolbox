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

可选参数：
- `--config path/to/config.yaml` — 使用自定义配置文件
- `--output path/to/output_dir` — 自定义输出目录
- `--verbose` — 显示详细调试信息
- `--version` — 显示版本号

运行后会在 `output/` 目录中自动生成：

1. `<文件名>_labeled.dxf` — 包含地块编号（如 P001）与面积（如 1.24 ha）的标注 DXF 图纸。
2. `<文件名>.csv` — 地块面积及状态统计表格。
3. `<文件名>_report.txt` — 详细处理报告（包含有效地块数、未闭合图形及面积汇总）。

### 3. 配置说明

默认配置文件位于 `config/default.yaml`，可自定义：

- `input_layers`：指定 DXF 中哪些图层包含地块边界。默认扫描 `PARCEL` 和 `地块` 图层。
- `strict_unit_check`：默认为 `true`。当 DXF 文件未定义单位时将停止执行，避免面积误算。
- `annotation`：标注文字高度、图层名称等。

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
