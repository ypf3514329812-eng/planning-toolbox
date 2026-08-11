"""Beginner-friendly coursework workflow guide."""

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout


_GUIDES = {
    "area": {
        "title": "地块面积与编号作业",
        "goal": "把 CAD 中的闭合地块整理成有编号、有面积、有统计表的基础数据。",
        "steps": [
            "选择 DXF，等待左侧运行前检查完成。",
            "打开“1. 地块面积与编号”，确认地块图层名称，通常是 PARCEL。",
            "运行后查看有效地块数量、总面积和异常线数量。",
            "打开作业包中的 CAD、CSV 和报告，补充老师要求的分析说明。",
        ],
        "outputs": "带编号 DXF、面积 CSV、GeoJSON、文字报告。",
        "issues": "有效地块为 0 时，优先检查图层名、闭合状态和 DXF 单位。",
    },
    "indicator": {
        "title": "规划指标计算作业",
        "goal": "根据地块、建筑和绿地图层，计算面积、建筑密度、绿地率和 FAR。",
        "steps": [
            "打开“2. 规划指标计算”。",
            "填写老师或规划条件明确给出的楼层倍数，不能让程序猜。",
            "确认 PARCEL、BUILDING、GREEN 图层名称。",
            "运行后查看每个地块的指标，并在报告中写出你的判断。",
        ],
        "outputs": "指标 CSV、指标报告和运行日志。",
        "issues": "楼层数、图层名或单位不完整时，系统会阻止计算。",
    },
    "validate": {
        "title": "拓扑与退线检查作业",
        "goal": "检查边界是否闭合、建筑是否越过退线，并整理问题清单。",
        "steps": [
            "打开“3. 拓扑与建筑退线检查”。",
            "填写作业题目给出的退线距离。",
            "确认 PARCEL 和 BUILDING 图层名称。",
            "运行后按合规、违规、无建筑分类整理问题。",
        ],
        "outputs": "拓扑/退线报告和问题明细。",
        "issues": "单位未知时不要凭感觉计算，优先在 CAD 中设置单位或明确选择回退单位。",
    },
    "concept": {
        "title": "概念方案 CAD 作业",
        "goal": "根据已有地块快速形成可继续修改的建筑、通道、停车和绿地初稿。",
        "steps": [
            "打开“6. 方案草图生成”，先选择规范依据框架或自定义/地方条件。",
            "填写建筑数量、覆盖率、退线、建筑间距和概念通道宽度。",
            "需要指标估算时填写楼层和停车配比。",
            "运行后在 CAD 中继续调整建筑、道路、停车和标注。",
        ],
        "outputs": "概念方案 DXF、尺寸/面积标注、CSV 明细表、规范依据报告。",
        "issues": "这是概念初稿，不代表道路连通、消防、日照或审批合规。",
    },
    "gis": {
        "title": "CAD-GIS 转换作业",
        "goal": "在 CAD、GeoJSON、GeoPackage 和 Shapefile 之间安全转换规划多边形。",
        "steps": [
            "打开“4. GIS 导出与导入”。",
            "基础 GeoJSON 转换可直接使用；GPKG/SHP 模式先点击顶部“🧭”填写经确认的项目投影 EPSG。",
            "导出时确认 CAD 单位和图层；导入时选择目标 DXF 单位。",
            "GPKG/SHP 会优先使用电脑已有的 ArcGIS Pro；没有 ArcGIS Pro 时再检测 QGIS/GDAL。",
            "完成后在 QGIS 中抽查位置与属性，在 CAD 中抽查边界尺寸，再整理作业截图。",
        ],
        "outputs": "GeoJSON、GeoPackage、导入 DXF 或转换记录。",
        "issues": "经纬度“度”和 EPSG:3857 不能作为精确规划量算坐标；目前只把面要素写入 DXF，多面图层 GPKG 需先明确目标图层。",
    },
    "sketchup": {
        "title": "CAD 转 SketchUp 低返工模型",
        "goal": "把已整理的 CAD 图层交接为分组、分层、带程序化细节且可增量更新的 SketchUp 场地与建筑模型。",
        "steps": [
            "先点击顶部“🧭”确认项目坐标；投影坐标项目必须启用场地附近的建模原点。",
            "打开“10. CAD → SketchUp 模型交接”，确认建筑图层名称；通常保持图块和三维面开启，确有标注交接需求时再开启文字。",
            "如果来自图片转 CAD，保持“仅高可信候选生成实体（推荐）”；系统会保留低可信中心线供复核，不把它们直接扩大为道路面。",
            "图片道路同时有面候选和可信中心线时，推荐策略会把重复面降级为复核轮廓，只由中心线生成道路实体，避免双层道路、重复标线和过量街灯。",
            "密集道路中心线会沿起点到终点均匀取样并完整建模，每条最多 64 个断面；简单两点中心线也可生成道路带。",
            "只要二维线面时把楼层设为 0；需要体量时明确填写楼层数和标准层高。",
            "建筑高度或用途不同时，点击“逐栋设置高度与模型样式”，在列表中多选建筑并批量填写楼层、层高、类型、屋顶和精度；未设置建筑继续使用全局参数。",
            "如果 CAD 图层已明确写成住宅_6F_层高3.0_平屋顶或 BUILDING_OFFICE_F8_H32，系统会自动接力；逐栋设置仍然优先。",
            "普通作业选“课程作业（推荐）”，再选择建筑类型与屋顶；系统会补充楼层线、轻量屋顶和共享窗组件。",
            "保持增量更新开启。需要手工精修某栋建筑前，先在 SketchUp 扩展程序菜单锁定该对象，避免下次导入覆盖。",
            "运行后先在 SketchUp 扩展程序管理器安装 RBZ，再从扩展程序菜单导入 .ptsu.json。",
            "在 SketchUp 中按 PT_BUILDING、PT_DETAIL、PT_FACADE、PT_GREEN、PT_ROAD 等标签检查并继续建模。",
        ],
        "outputs": "轻量 .ptsu.json 模型交接文件、可安装 .rbz SketchUp 插件。",
        "issues": "逐栋参数按稳定建筑编号保存；若 CAD 删除或重画了轮廓，结果区会提示未匹配，需要重新选择。建筑参数优先级是逐栋设置、明确图层参数、全局参数；普通编号不会被猜成高度。结果区课程模型检查只报告资料完整度，不代表课程评分或规范符合。四边形建筑可自动生成平/双坡/四坡屋顶，复杂轮廓会安全退回平屋顶；大型场地会均匀控制窗组件数量以保持流畅。图像道路中心线只会保守拼接高可信、同宽级和方向连续的短段；方向明确、距离受限的端点或 T 形路口可安全吸附，歧义路口保持原样。密集中心线会在完整路径上限量取样而不是截掉尾段，但道路宽度与交通组织仍需人工核对。重复道路面转为复核轮廓，红色低可信候选仍需人工复核。图片转 CAD 的低饱和浅色填充仅用于 CAD 显示，进入 SketchUp 时会忽略；外部参照、复杂材质和网格仍不会自动重建，建筑高度、坐标原点与复杂曲线必须人工复核。",
    },
}


class AssignmentGuideDialog(QDialog):
    """A small local guide for common planning-course assignments."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HelpDialog")
        self.setWindowTitle("Planning Toolbox 作业助手")
        self.setMinimumSize(760, 560)
        self.resize(900, 680)

        layout = QVBoxLayout(self)
        self.combo = QComboBox()
        for guide_id, guide in _GUIDES.items():
            self.combo.addItem(guide["title"], guide_id)
        self.combo.currentIndexChanged.connect(self._render)
        layout.addWidget(self.combo)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        layout.addWidget(self.browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self._render(0)

    def _render(self, index: int):
        guide = _GUIDES.get(self.combo.itemData(index))
        if not guide:
            return
        steps = "".join(f"<li>{step}</li>" for step in guide["steps"])
        self.browser.setHtml(
            f"<h2>{guide['title']}</h2>"
            f"<p><b>这类作业要完成什么：</b>{guide['goal']}</p>"
            f"<h3>建议步骤</h3><ol>{steps}</ol>"
            f"<h3>作业包会包含</h3><p>{guide['outputs']}</p>"
            f"<div style='background:#F4E9D3;padding:10px;'><b>常见问题：</b>{guide['issues']}</div>"
            "<p><b>提交前：</b>请把自动计算结果转化为你自己的设计说明和判断，保留人工修改痕迹。</p>"
        )
