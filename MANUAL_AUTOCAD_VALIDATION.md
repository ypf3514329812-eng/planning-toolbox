# Planning Toolbox — AutoCAD & ArcGIS Pro 人工抽验指南 (Student Validation Manual)

> **致城乡规划专业同学**：
> 本指南为无编程背景的规划专业学生提供一份简单、清晰的 AutoCAD 和 ArcGIS Pro 手工核验步骤。
> 请按以下 4 个步骤在 AutoCAD 中打开生成的标注图纸进行抽验，确认软件计算结果与 CAD 原生结果完全一致。

---

## 一、AutoCAD 面积与标注抽验步骤

### 步骤 1：打开生成的标注图纸
在 AutoCAD 中打开程序输出的 `*_labeled.dxf` 图纸（位于 `sample_data/output/sample_parcels_labeled.dxf` 或 `output/` 目录）。

### 步骤 2：检查地块标注图层
1. 观察图纸上是否增加了黄色的 MTEXT 文字标注（例如：`P001 \n 1.00 ha`）。
2. 在图层管理器 (`LAYER`) 中确认：
   - 原始地块线仍保留在 `PARCEL` 或 `地块` 图层，颜色与线型未被篡改。
   - 标注文字位于独立的 `PARCEL_LABEL` 图层，可独立关闭或隐藏。

### 步骤 3：AutoCAD 原生 `AREA` 命令核验
1. 在命令行输入 `AREA` 并按回车。
2. 输入 `O`（对象/Object），点击 `P001` 地块的多段线边界。
3. 查看 AutoCAD 命令行弹出的面积数值（如 `10000.0000 平方毫米` 或 `10000.0000 平方米`）。
4. 将该数值换算为公顷（除以 10,000），对比 MTEXT 标注值 `1.00 ha`。
5. **判定标准**：二者差距应小于 0.001 ha。

### 步骤 4：AutoCAD 原生 `LIST` 命令特性检查
1. 选中地块多段线，在命令行输入 `LIST` 并回车。
2. 确认属性列表中：
   - `闭合` (Closed) 属性为 `是` (Yes)。
   - `图层` (Layer) 属性与配置一致。

---

## 二、ArcGIS Pro 属性表与空间位置抽验步骤

### 步骤 1：导入 CSV 属性表
1. 在 ArcGIS Pro 中打开项目，点击 `Add Data` -> `Standalone Table`。
2. 选择程序生成的 `.csv` 报表文件（例如 `sample_parcels.csv`）。

### 步骤 2：核验属性字段
1. 右键表格点击 `Open` 打开属性表。
2. 检查字段 `parcel_id`（地块编号）、`area_m2`（平方米面积）、`area_ha`（公顷面积）、`geometry_status`（几何状态）。
3. 确认 `VALID` 状态地块的 `area_ha` 与 `area_m2` 具备精确比例关系（1 ha = 10,000 m²）。

---

## 三、异常情况反馈
如果在手工抽验中发现任何标号遗漏、面积不符或图形篡改，请保存当前 DXF 图纸并记录截图，在项目中提交 Bug 报告。
