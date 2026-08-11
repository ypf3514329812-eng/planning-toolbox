"""Beginner-friendly in-app guide for the Planning Toolbox workbench."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)


class HelpDialog(QDialog):
    """A non-technical guide shown from the main workbench."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HelpDialog")
        self.setWindowTitle("Planning Toolbox 使用帮助")
        self.setMinimumSize(820, 620)
        self.resize(980, 720)
        self.setModal(False)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("如何使用 Planning Toolbox")
        title.setObjectName("HelpTitle")
        header.addWidget(title)
        header.addStretch()
        tip = QLabel("面向没有 CAD / GIS 编程经验的规划学习者")
        tip.setObjectName("HelpSubtitle")
        header.addWidget(tip)
        layout.addLayout(header)

        intro = QLabel(
            "你不需要编写代码。第一次使用可点击顶部“🧩 流程”，按向导完成资料导入、检查、分析、建模和导出。"
        )
        intro.setObjectName("HelpIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._browser(self._quick_start_html()), "快速开始")
        self.tabs.addTab(self._browser(self._tasks_html()), "我可以帮你做什么")
        self.tabs.addTab(self._browser(self._workflows_html()), "具体操作流程")
        self.tabs.addTab(self._browser(self._faq_html()), "常见问题")
        self.tabs.addTab(self._browser(self._safety_html()), "安全提醒")
        layout.addWidget(self.tabs, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def _browser(self, html: str) -> QTextBrowser:
        browser = QTextBrowser()
        browser.setObjectName("HelpContent")
        browser.setReadOnly(True)
        browser.setOpenExternalLinks(False)
        browser.setOpenLinks(False)
        browser.setHtml(
            """
            <html><head><style>
            body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; color: #3C3D39; font-size: 14px; line-height: 1.55; }
            h2 { color: #566D8E; font-size: 19px; margin: 4px 0 10px 0; }
            h3 { color: #607A6A; font-size: 15px; margin: 16px 0 5px 0; }
            p { margin: 6px 0; }
            ul, ol { margin-top: 4px; margin-bottom: 8px; }
            li { margin: 4px 0; }
            .card { background: #F6F3EC; border: 1px solid #D8D3C8; border-radius: 8px; padding: 9px 12px; margin: 8px 0; }
            .blue { background: #E1EAF0; border-left: 4px solid #7189AA; padding: 8px 10px; margin: 8px 0; }
            .green { background: #E3EEE8; border-left: 4px solid #829A8B; padding: 8px 10px; margin: 8px 0; }
            .yellow { background: #F4E9D3; border-left: 4px solid #A6814D; padding: 8px 10px; margin: 8px 0; }
            .red { background: #F4DDDA; border-left: 4px solid #A96761; padding: 8px 10px; margin: 8px 0; }
            .muted { color: #74766F; }
            strong { color: #4B5F78; }
            table { border-collapse: collapse; width: 100%; }
            td, th { border: 1px solid #D8D3C8; padding: 7px 9px; vertical-align: top; }
            th { background: #E8E4DA; color: #566D8E; text-align: left; }
            </style></head><body>"""
            + html
            + "</body></html>"
        )
        return browser

    @staticmethod
    def _quick_start_html() -> str:
        return """
        <h2>第一次使用：优先打开“🧩 流程”向导</h2>
        <div class="green"><strong>推荐入门方式：</strong>先点击主界面的“⭑ 一键示例图纸”，用内置样例完整体验一次，再换成自己的 DXF 文件。</div>
        <div class="blue"><strong>最省事的入口：</strong>点击顶部“🧩 流程”，选择资料来自 DXF、AI 参考图还是 GIS。向导会记录每一步的完成状态，并把你带到已有功能页面；点击“保存项目进度”后，下次打开 `.ptx` 可以继续。</div>
        <h3>也可以按下面 8 步手动操作</h3>
        <ol>
          <li><strong>打开或新建项目：</strong>如果之前保存过 `.ptx` 文件，可以先点击顶部“📂 打开项目”；新建 GIS–CAD–SU 项目时，点击顶部“🧭”设置项目名称、坐标系、CAD 单位和 SketchUp 本地原点。</li>
          <li><strong>选择图纸：</strong>在顶部“文件与工作区”选择 DXF，或者直接把 .dxf 文件拖进输入框。</li>
          <li><strong>选择保存位置：</strong>指定“结果输出目录”。生成的 DXF、CSV、GeoJSON、Excel、PDF 和报告都会放在这里。</li>
          <li><strong>等待自动检查：</strong>中间左侧会显示 DXF 单位、PARCEL / BUILDING / GREEN 图层数量、闭合情况和嵌套情况。</li>
          <li><strong>确认检查结果：</strong>看到“单位可识别”后再做面积、指标或退线计算；如果单位未知，请先处理单位提示。</li>
          <li><strong>选择任务：</strong>在中间右侧选择对应页签，填写必要参数。指标任务必须填写楼层倍数；希望尽量减少 CAD 手工清理时，选择“8. 图纸质量增强检查”的“最低人工修改（推荐）”。</li>
          <li><strong>运行并查看结果：</strong>点击底部“运行所选分析任务”，等待进度完成，在下方结果表、日志和图形预览中查看结果。</li>
          <li><strong>导出和保存：</strong>点击“📤 导出 Excel/PDF/图片”生成汇报材料，再点击“🧰 整理为作业包”；最后点击“💾 保存项目”方便下次继续。</li>
        </ol>
        <div class="blue"><strong>界面怎么读：</strong>顶部是项目和输入文件；中左是数据体检；中右是任务设置；底部是结果、日志和 CAD 预览。预览区可用鼠标滚轮缩放、按住左键拖动，双击或点击“适应窗口”恢复全图。你可以把它理解为“先体检，再计算，最后导出和保存”。</div>
        <h3>第一次建议怎么练习？</h3>
        <p>用示例图纸依次试：① 地块面积与编号 → ② 规划指标（楼层填 6）→ ③ 退线检查（退线填 5 米）→ ④ CAD 图层标准化。每次运行后先看结果表，再导出 Excel/PDF/PNG，最后整理作业包。</p>
        <div class="yellow"><strong>不用 API：</strong>图纸检查、计算、图层标准化、项目保存和成果导出都在本地完成；只有以后增加聊天式 AI 助手时才需要额外配置 API。</div>
        """

    @staticmethod
    def _tasks_html() -> str:
        return """
        <h2>它可以帮你完成哪些工作？</h2>
        <div class="card"><h3>1. 地块面积与编号</h3><p>识别 PARCEL 图层的闭合地块，计算面积，自动编号，识别未闭合线和嵌套环。</p><p class="muted">常见输出：地块统计 CSV、带编号 DXF、GeoJSON 和文字报告。</p></div>
        <div class="card"><h3>2. 规划指标估算</h3><p>结合 PARCEL、BUILDING、GREEN 图层，估算用地面积、建筑基底面积、总建筑面积、容积率、建筑密度和绿地率。</p><p class="muted">需要你明确填写建筑楼层倍数；系统不会替你猜楼层。</p></div>
        <div class="card"><h3>3. 拓扑与建筑退线检查</h3><p>检查多段线是否闭合、几何是否异常，并判断建筑基底是否越过地块边界的退线距离。</p><p class="muted">例如输入 5 米，表示检查建筑距离用地边界是否至少为 5 米。</p></div>
        <div class="card"><h3>4. CAD 与 GIS 数据转换</h3><p>基础版可直接完成 GeoJSON↔DXF；扩展格式优先复用电脑已有的 ArcGIS Pro，没有时再使用 QGIS/GDAL，把 GeoPackage/Shapefile 按项目投影对齐后导入 DXF，或把 CAD 地块导出为 GeoPackage。</p><p class="muted">转换只启动后台 GIS 进程，不打开完整 ArcGIS 界面，也不会把 ArcPy 打包进本软件。</p></div>
        <div class="card"><h3>5. 中国标准制图辅助与 CAD 图层标准化</h3><p>可选择“中国规划课程总平面”“中国居住区总平面”或“国土空间规划图件”模板，识别常见中英文别名，统一图层颜色、线宽和线型，并生成中文辅助检查报告。</p><p class="muted">报告会区分阻断项、待人工确认项和已通过项，并列出标准来源与版本；它检查的是图层和制图一致性，不等于法定审查或审批通过。</p></div>
        <div class="card"><h3>6. 最低人工修改与图纸质量增强</h3><p>除检查重复线、未闭合线、自交和异常范围外，推荐模式还能删除重复 LINE、连接同图层同线型且无分叉的碎线链、清理共线/极短冗余点，并同时整理常见中英文图层别名。</p><p class="muted">输出包含修复 DXF、质量报告和逐项修改 CSV。原始 DXF 不会被覆盖；分叉路口、曲线、块参照和自交仍留给人工判断。</p></div>
        <div class="card"><h3>7. 批量分析</h3><p>选择一个包含多张 DXF 的文件夹，批量执行地块分析或指标分析，并生成汇总表。</p><p class="muted">某一张图纸失败时会记录原因，不会让其他图纸全部停止。</p></div>
        <div class="card"><h3>8. 参数化概念方案草图</h3><p>根据已有 PARCEL 地块，按规范依据框架、建筑数量、覆盖率、退线、建筑间距和概念道路/消防通道宽度生成沿地块主方向布置的建筑轮廓，并输出尺寸/面积标注；填写楼层和停车配比后，还可以生成概念停车位并估算总建筑面积。</p><p class="muted">规范框架用于记录核对依据，不会替你猜测地方规划条件，也不是自动完成的正式总平面设计。</p></div>
        <div class="card"><h3>9. 作业助手与成果导出</h3><p>顶部“作业助手”会按作业类型给出操作步骤、输出文件和常见问题。任务完成后，结果区可以一键导出 Excel 结果表、PDF 结果报告和高分辨率 PNG 全图；继续点击“整理为作业包”，还会自动分类 CAD、数据表、报告和预览图，并生成说明文件、结果摘要和 ZIP 压缩包。</p><p class="muted">PNG 从完整矢量场景生成，不受当前缩放和屏幕窗口大小影响。这些文件用于整理和检查，不会替你完成设计说明、规范判断或最终提交成果。</p></div>
        <div class="card"><h3>10. 保存作业项目</h3><p>顶部“保存项目”会保存当前 DXF 路径、输出目录、任务参数和最近一次结果记录；下次点击“打开项目”即可恢复工作状态。</p><p class="muted">项目文件只保存路径和参数，不会复制或修改原始 DXF；如果文件被移动，需要重新选择有效路径。</p></div>
        <div class="card"><h3>11. 多方案结果对比</h3><p>先分别保存多个 `.ptx` 作业项目，再点击顶部“📊 方案对比”，选择这些项目并生成对比表。</p><p class="muted">系统可以并列查看用地面积、FAR、建筑密度、绿地率、停车位、退线和图层标准化结果；切换“🎨 图形叠加”可以用不同颜色查看方案轮廓，重叠处混色，斜线标出方案独有差异，还可以导出 PNG。</p></div>
        <div class="card"><h3>12. GIS–CAD–SU 全链路项目</h3><p>点击顶部“🧭”，设置全流程共用的项目名称、投影坐标、CAD 单位和近原点模型坐标。`.ptx` 携带稳定项目 ID；项目投影已用于 GPKG/SHP 与 DXF 的自动对齐。</p><p class="muted">适配顺序为 ArcGIS Pro → QGIS/GDAL → 内置 GeoJSON。外部 GIS 只在任务运行时启动，基础工作台保持轻量。</p></div>
        <div class="card"><h3>13. CAD → SketchUp 可编辑模型交接</h3><p>把已整理的 DXF 线、多段线、常见曲线、图块和三维面转成轻量交接文件，并提供一个可安装的 SketchUp RBZ 插件。插件会按建筑、地块、绿地、道路、水体、停车和其他对象生成独立分组与 PT_* 标签。</p><p class="muted">“课程作业”模式可按明确楼层与层高自动补充入口、复用雨棚、建筑基座、楼层线、屋顶和共享窗；树木优先使用可追溯 CC0 共享组件，道路、绿地、水体和停车闭合面自动分层。道路细化可选择自动、完整街道、基础车行道或关闭；完整街道为规则道路生成双侧人行带、路缘、边线、中心虚线、双向箭头和共享街灯。CAD 使用 PT_PLANTER / PT_PARASOL / PT_CROSSWALK / PT_TRAFFIC_LIGHT 块名时可调用花池、遮阳伞、斑马线和交通灯。9 个组件总计约 334 KB、按需加载，全程本地运行且不需要 API；用户逐栋参数永远优先，道路参数是教学表达默认值，不代替规范审查。</p></div>
        <div class="yellow"><strong>重要：</strong>这些结果是学习、方案比较和数据整理的辅助结果，不等于规划审批结论，也不能替代当地规范和人工复核。</div>
        """

    @staticmethod
    def _workflows_html() -> str:
        return """
        <h2>按任务操作：照着做即可</h2>
        <h3>任务 0：建立 GIS–CAD–SU 全链路项目</h3>
        <ol><li>点击顶部的“🧭”按钮。</li><li>填写项目名称和作业类型。</li><li>已经知道项目投影坐标时，填写 EPSG 编号并选择“投影坐标”；不确定时先选择“暂未确认”，不要猜测。</li><li>确认 CAD 图纸使用米、毫米或其他单位。</li><li>准备进入 SketchUp 时，启用“近原点坐标”，把场地附近的投影坐标填写为原点 X、Y；后续三维模型会保留返回真实坐标所需的变换。</li><li>点击保存项目设置，再使用顶部“💾 保存”写入 `.ptx`。</li></ol>
        <div class="yellow">经纬度不能直接用于面积、退线和三维尺寸。EPSG:3857 只适合网络地图显示，不应用作精确规划量算。坐标不确定时可以先保存项目，后续通过 GIS 步骤确认。</div>

        <h3>任务 A：计算地块面积</h3>
        <ol><li>选择 DXF，并等待左侧检查完成。</li><li>打开“1. 地块面积与编号”。默认图层名通常是 PARCEL。</li><li>如果你的图层名称不同，把“目标地块图层名称”改成实际名称。</li><li>确认单位可识别，点击运行。</li><li>在结果区查看有效地块数量和总面积，并到输出目录查看 CSV / DXF / GeoJSON。</li></ol>

        <h3>任务 B：计算规划指标</h3>
        <ol><li>打开“2. 规划指标计算”。</li><li>在“建筑楼层倍数”填写明确数值，例如 6；这不是默认值，需要根据你的方案输入。</li><li>确认 BUILDING 和 GREEN 图层名称正确。</li><li>点击运行，查看每个地块的 FAR、建筑密度和绿地率。</li></ol>
        <div class="yellow">楼层倍数只是估算参数：如果不同建筑楼层不一样，建议分组处理或把结果作为初步估算，不要直接当作最终报审数据。</div>

        <h3>任务 C：检查建筑退线</h3>
        <ol><li>打开“3. 拓扑与建筑退线检查”。</li><li>填写退线要求距离，例如 5.0 米。</li><li>确认 PARCEL 和 BUILDING 图层名称正确。</li><li>如果 DXF 单位未知，先选择明确的单位回退值，或回到 CAD 中设置图纸单位后重新导入。</li><li>点击运行，结果会区分“合规、违规、无建筑”等状态。</li></ol>

        <h3>任务 D：转换 GIS 文件</h3>
        <ol><li>打开“4. GIS 导出与导入”。</li><li>只使用 GeoJSON 时可直接选择前两项；要使用 GPKG/SHP，先点击顶部“🧭”，填写经确认的米制项目投影 EPSG。</li><li>选择转换方向。导入时选择目标 DXF 单位；软件会正确处理米、毫米、厘米和英尺换算。</li><li>界面显示“已检测到 ArcGIS Pro”即可直接运行，不需要安装 QGIS，也不需要打开 ArcGIS Pro 界面。</li><li>完成后在 ArcGIS Pro 中抽查图层位置与属性，在 CAD 中用 DIST/AREA 抽查尺寸和面积。</li></ol>
        <div class="red">声明为 WGS84/CGCS2000 经纬度的 GeoJSON 会被拦截；EPSG:3857 也不会用于精确量算。GPKG/SHP 导入目前只转换 Polygon/MultiPolygon，点、线和文字会安全跳过。</div>

        <h3>任务 E：标准化 CAD 图层</h3>
        <ol><li>选择 DXF 并等待运行前检查完成。</li><li>打开“7. CAD 图层标准化”，保持“使用中国标准制图辅助”开启。</li><li>普通课程作业选择“中国规划课程总平面”；居住区课程设计选择“中国居住区总平面”；只有国土空间规划图件才选择相应试行规范模板。</li><li>点击运行，系统会生成新的标准化 DXF、图层报告、中国制图辅助检查和机器可读 JSON。</li><li>先处理“阻断项”，再查看空的必备图层、自定义图层、坐标系和地方要求等“待确认项”。</li></ol>
        <div class="blue">标准化不会覆盖原始 DXF。模板中的颜色、线宽和线型是学习辅助默认值；学校、设计单位或地方有明确要求时，以其最新版要求为准。</div>

        <h3>任务 F：增强图纸质量检查与修复</h3>
        <ol><li>选择 DXF，确认左侧显示明确图纸单位。</li><li>打开“8. 图纸质量增强检查”，保持“最低人工修改（推荐）”。</li><li>通常先保留默认容差：近闭合 0.01、碎线连接 0.05、共线判断 0.01 图纸单位；图纸使用毫米时应根据实际精度调整。</li><li>点击运行。系统会删除重复图元、闭合明确小缺口、连接无分叉碎线、清理冗余顶点并整理图层别名。</li><li>先看结果中的“分叉碎线组”“自交候选”“块参照与外部参照”，这些是系统主动保留给你的人工判断项。</li><li>点击结果区“修复对比”：灰色是未变化，红色是删除/替换，绿色是新增/替换；再打开“逐项修改记录 CSV”逐项确认。</li><li>确认后使用“安全修复 DXF”继续画图。如果只想审查，把模式改为“只检查，不修改”；图纸复杂且担心误改时选择“安全修复”。</li></ol>
        <div class="yellow">推荐模式不会强行跨越分叉节点，也不会把 ARC、SPLINE 或块参照拆散。单位未知时会阻断距离容差修复，避免把毫米和米混用。</div>

        <h3>任务 G：批量处理多张图纸</h3>
        <ol><li>打开“5. 批量分析”，选择包含多张 .dxf 的文件夹。</li><li>选择“地块面积与编号”或“规划指标计算”。</li><li>如果选择指标计算，必须填写批量指标楼层倍数。</li><li>顶部仍需选择一个结果输出目录。</li><li>运行后，每张图纸会有独立结果文件夹，同时生成 batch_summary.csv。</li></ol>

        <h3>任务 H：生成概念方案 CAD 草图</h3>
        <ol><li>先选择一张包含有效闭合 PARCEL 地块的 DXF，并等待检查完成。</li><li>打开“6. 方案草图生成”。</li><li>先选择“规范依据框架”：居住区项目可选择居住区国家标准框架，公共/民用建筑可选择民用建筑国家标准框架；正式项目仍应优先选择自定义/地方条件。</li><li>在“布局风格”中选择“自然曲线（推荐）”，系统会生成圆角建筑轮廓和弧形通行引导；需要规整示意时可切换为“简洁矩形”。</li><li>填写每个地块的建筑数量、概念建筑覆盖率、建筑退线距离；如需控制建筑之间的距离，再填写“概念建筑间距”。</li><li>如需生成弧形道路/消防引导，填写“概念道路/消防通道宽度”；建筑和停车位会尽量避开该通道。</li><li>如果希望估算总建筑面积，填写明确的楼层数；如果希望估算停车位，再填写“停车配比（个/1000m²）”。</li><li>确认单位可识别，再点击运行。</li><li>在输出目录打开 *_concept_plan.dxf。它会保留原始图纸，并增加 CONCEPT_SETBACK、CONCEPT_BUILDING、CONCEPT_PARKING、CONCEPT_GREEN、CONCEPT_ROAD、CONCEPT_LABEL 和 CONCEPT_DIMENSION 图层；同时生成可用 Excel 打开的 *_concept_plan_schedule.csv。</li></ol>
        <div class="yellow">生成的只是规则化初稿：国家标准框架用于记录核对依据，不能自动替代项目所在地的规划条件；尺寸和面积是几何计算结果，概念通道不等于真实道路或消防审查结论，停车位不等于停车配建合规。</div>

        <h3>任务 I：导出与整理作业成果</h3>
        <ol><li>先在顶部点击“📝 作业助手”，选择与你的题目最接近的任务类型，按步骤完成分析。</li><li>任务完成后，先点击“📤 导出 Excel/PDF/图片”，得到可编辑表格、打印报告和预览截图。</li><li>再点击“🧰 整理为作业包”，按 <strong>01_CAD</strong>、<strong>02_数据表</strong>、<strong>03_报告</strong>、<strong>04_预览图</strong> 检查输出；同时阅读“作业包说明”和“结果摘要”。</li><li>确认没有问题后保存 ZIP；再补充你自己的设计说明、截图和人工判断。</li></ol>
        <div class="blue">作业包不需要联网，也不需要 API。它只是把本次结果整理得更清楚，方便你学习、备份和提交前检查。</div>

        <h3>任务 J：保存并继续作业项目</h3>
        <ol><li>在填写参数或任务运行完成后，点击顶部“💾 保存项目”。</li><li>选择一个容易找到的位置，保存为 `.ptx` 文件。</li><li>下次打开程序后点击“📂 打开项目”，选择这个 `.ptx` 文件。</li><li>系统会恢复 DXF 路径、输出目录、任务参数和最近一次结果记录；确认图纸仍存在后即可继续。</li></ol>
        <div class="yellow">项目文件保存工作记录、全链路坐标清单和文件路径，不是 DXF 备份。请保留原始 DXF，并在文件移动后重新选择路径。</div>

        <h3>任务 K：比较多个方案</h3>
        <ol><li>先为不同参数或不同布局分别保存项目，例如“方案 A.ptx”和“方案 B.ptx”。</li><li>点击顶部“📊 方案对比”，再点击“添加项目”选择两个或多个 `.ptx` 文件。</li><li>点击“开始对比”，查看用地面积、FAR、建筑密度、绿地率、停车位和退线结果。</li><li>切换到“🎨 图形叠加”：颜色代表不同方案，重叠位置会混色，带斜线的轮廓表示该方案独有的差异区域。</li><li>需要交作业或汇报时，点击“导出对比 CSV”“导出对比 Excel”或“导出叠加 PNG”。</li></ol>
        <div class="blue">对比的是每个项目最近一次保存的结果记录。如果修改参数或重新运行，请重新保存对应项目后再对比。叠加图只读取项目记录中的 DXF，不会修改原始图纸。</div>
        <h3>任务 L：AI 效果图转 CAD 概念草图</h3>
        <div class="blue"><strong>新增的全链路语义交接：</strong>每次转换会在 DXF 旁生成一个很小的 `.ptscene.json` 文件。它不复制图形，只记录“哪些是建筑候选、绿化候选、停车候选、哪些只是参考底图”以及原图和 DXF 的校验指纹。继续运行图纸质量修复或图层标准化时，该文件会自动跟随；不要单独改名或手工编辑。</div>
        <div class="blue"><strong>道路复杂时推荐“原图 + 彩色语义引导图”：</strong>先用“黑白线稿 CAD”运行一次，结果目录会自动生成一张与原图像素尺寸完全相同的“可编辑语义引导草稿”。系统已预填高置信建筑、道路、绿化和停车候选；请在画图软件中只补涂遗漏范围、擦除明显误判，不需要从零描整张图。标准颜色为：低饱和红 `RGB(198,119,119)` 填建筑、灰 `RGB(151,151,145)` 填道路、绿 `RGB(126,165,142)` 填绿地、蓝 `RGB(118,157,184)` 填水体、米黄 `RGB(204,169,113)` 填停车。不得裁剪、缩放或移动画布；不要加入阴影、文字、纹理或透视。然后选择“原图 + 彩色语义引导图”重新运行，先检查叠加 PNG，再进入 CAD / SketchUp。原图与引导图均执行 SHA-256 零修改验证，全程不需要 API。</div>
        <div class="green"><strong>不会使用画图软件也没关系：</strong>在“语义引导图”一行点击“新建/编辑引导图”。窗口会显示原图作为只读参考；自由画笔适合小范围补涂，复杂道路可切换“道路路径”，按道路走向逐点点击，双击或点击“完成路径”一次提交整条道路；误操作可用“撤销/重做”。也可以切换建筑、绿地、水体、停车、擦除。滚轮缩放，中键拖动，双击自由画笔时适应窗口。点击“保存引导图并使用”后，系统会自动填入路径；编辑器不会裁剪、缩放或覆盖原图。</div>
        <div class="blue"><strong>看懂道路网络检查：</strong>结果区会显示道路面数量、最终连成的网络块数量、自动修复的小断口数量和“近距离断口建议”。近距离断口建议表示两块道路相距不远，适合回到“道路路径”工具补画连接；它不是系统强行连接的结果。网络块大于 1 时，不一定是错误（可能是场地内外两组道路），但应在叠加检查图和 CAD 中确认是否有道路断开；系统只做小范围几何修复，不会替你猜测道路红线、路口组织或消防结论。</div>
        <div class="blue"><strong>道路中心线自动整理：</strong>黑白线稿识别后，系统会尝试把被树木、文字或细小空隙切开的道路中心线接成较长对象，但只拼接高可信、宽度相近、方向近似直行且间隙不超过约一个道路宽度的短段。低可信线、不同道路等级和明显转弯不会强行合并。结果表中的“安全拼接碎段”表示减少了多少个重复道路组；仍应先查看橙/红道路复核叠加图。</div>
        <div class="green"><strong>为什么 CAD 不再只有黑色轮廓：</strong>系统会把已识别建筑显示为低饱和暖红、道路显示为浅灰、树木和绿化显示为柔绿、停车显示为米黄、道路中心线显示为蓝灰虚线；尚未确认的普通线条保留为浅灰参考线。建筑和道路的浅色区域分别放在 `BW_BUILDING_FILL`、`BW_ROAD_FILL` 显示图层，真实边界仍在候选多段线图层。关闭两个 FILL 图层不会删除边界，进入 SketchUp 时这些显示填充也不会重复建模。</div>
        <ol><li>先准备一张俯视、正交、尽量没有透视和阴影的平面效果图。彩色分区图使用低饱和度红/灰/绿/蓝/米色；线稿既可以白底黑线，也可以黑底白线。</li><li>打开“9. AI 效果图转 CAD”，选择 PNG/JPG 图片，再选择“彩色分区 CAD”或“黑白线稿 CAD”。黑白模式默认自动判断底色，判断不正确时可手动指定。</li><li>填写图片中整个场地的实际宽度，例如图片场地宽 100 米；系统不会替你猜测比例。</li><li>黑白线稿建议选择“精细”，并保持“自动整理线条”开启。系统会连接方向一致的短段，保护正放或旋转建筑候选，把重复小圆形符号归并为 PT_TREE 块，把至少三个尺寸与方向相近的窄矩形归并为 PT_PARKING_STALL 停车位块，并把规则圆形/椭圆拟合为可编辑 ELLIPSE 候选。</li><li>先看彩色 CAD 预览：暖红建筑、浅灰道路、绿色树木、米黄停车位是否与底图基本重合；仍为浅灰线的对象表示系统尚未可靠确认用途。</li><li>查看“道路中心线候选”中的安全拼接数量、路口安全吸附和橙/红复核叠加图；橙色高可信短段可保守连接，红色低可信线不会自动生成 SU 道路实体。</li><li>保持“使用已确认的精修 CAD 知识辅助校正”开启，并明确选择图纸类型。系统不会把“待确认”类型和不同类型项目混在一起。</li><li>保持“生成轻量 Markdown 图纸知识卡”开启并填写少量检索标签。知识卡只保存原图指纹、比例依据、识别摘要、复核状态和成果路径，不保存图片像素。</li><li>通常不要勾选“收藏本次 DXF 为候选 CAD 样本”。候选样本只供查看，不会用于校正，以免错误结果污染知识库。</li><li>点击运行并先查看预览。结果中的“知识库辅助”会显示匹配了多少份精修 CAD、实际校正了多少个规则图元。</li><li>打开 DXF 后，依次隔离 BW_BUILDING_CANDIDATE、BW_ROAD_CENTERLINE_CANDIDATE、BW_TREE_CANDIDATE、BW_PARKING_CANDIDATE 和 BW_LANDSCAPE_CANDIDATE。确认无误的候选才可改入正式图层；错误候选应删除或重新描绘。若只想看线稿，直接关闭 `BW_BUILDING_FILL` 和 `BW_ROAD_FILL`，边界线不会被删除。</li><li>需要进一步清理时，再运行“8. 图纸质量增强检查 → 最低人工修改”，最后在 CAD 中复核比例、闭合、道路连接和复杂曲线。</li><li>完成真正的人工精修后，回到结果区点击“⭐ 收藏精修 CAD”，选择精修 DXF 并确认。系统提取建筑、停车位和树木的米制尺寸；下次使用相同输出知识库、选择相同图纸类型时才会参与校正。</li></ol>
        <div class="yellow">这项功能不需要 API，适合把 AI 生成的“构思图”快速变成可编辑的 CAD 草图。Markdown 是检索索引，不能代替 CAD 几何；未校准的机器候选不会显示虚假的可信百分比。透视、阴影、文字和复杂材质仍可能产生误识别，不能直接作为审批、测绘或施工成果。</div>
        <h3>任务 M：导入 DWG 图纸</h3>
        <ol><li>在顶部文件区点击“DWG 导入”。</li><li>选择原始 .dwg 文件和输出目录。</li><li>系统调用电脑本机的 ODA File Converter，生成一个新的 DXF；文件不会上传，也不会覆盖 DWG。</li><li>转换完成后 DXF 会自动载入。先运行“图纸质量增强检查”，重点核对字体、块参照、外部参照、代理对象和布局空间。</li></ol>
        <div class="blue">DWG 转换不需要 API，但电脑需安装 ODA File Converter。若未安装，系统会给出中文提示；你也可以在 AutoCAD 中手动“另存为 DXF”后再导入。</div>
        <h3>任务 N：把 CAD 交接为 SketchUp 模型</h3>
        <div class="blue"><strong>图片 → CAD → SketchUp 的推荐方式：</strong>如果 DXF 旁有有效的 `.ptscene.json`，系统会直接沿用已识别的对象用途，不再重复猜测。大量普通线条会合并到一个默认锁定的 `PT_UNDERLAY` 参考底图组，建筑、绿化、停车等候选仍保持为可单独选择的对象。请先核对候选再建模，不要把锁定底图当作已确认设计对象。</div>
        <div class="green"><strong>让建筑不再全部一样高：</strong>如果 CAD 图层名称已经明确写出信息，系统会自动接力，例如 `BUILDING_RES_6F_FH3.0_FLAT`、`BUILDING_OFFICE_F8_H32_FLAT`、`住宅_6层_层高3.1_平屋顶`、`建筑_商业_3层_层高4.5_双坡`。可使用 `F6/6F/6层` 表示楼层，`FH3.0/层高3.0` 表示标准层高，`H18/高度18` 表示总高；用途支持住宅、办公、商业、学校，屋顶支持平屋顶、双坡和四坡。系统只读取带明确前缀的参数，不会把普通图层编号猜成高度；“逐栋设置高度与模型样式”始终优先于图层名称。</div>
        <div class="blue"><strong>避免道路重复：</strong>图片转 CAD 可能同时保留道路面候选和道路中心线。开启“中心线生成概念道路带”并保持“仅高可信候选生成实体（推荐）”时，系统只让可信中心线生成道路实体，把重复道路面保留为可见复核轮廓，不再重复铺面、画标线或布置街灯；结果区会显示降级数量。</div>
        <div class="blue">曲线道路提示：明确命名为 ROAD_CENTERLINE、ROAD_AXIS 或 CENTERLINE 的 ARC/SPLINE 开放线默认只辅助斑马线定向；勾选“中心线生成概念道路带”后，才会按局部切线生成可编辑道路带，但宽度仍是概念估计，必须人工复核。密集折线会从起点到终点按全长均匀取样，最多保留 64 个断面，不再因为原线段很多而只生成道路前半段；只有两个端点的简单中心线也能生成完整道路带。圆形道路只有放在 ROUNDABOUT 或“环岛”图层时才生成环带，并保留中央空腔，不会填成实心圆。</div>
        <div class="muted">如果勾选中心线道路带，可在下方输入道路总宽度（4–60 m）；填 0 使用知识库默认值 6 m。宽度包含两侧人行道，系统会按轻量规则推导车行道与人行道，生成后仍需检查道路红线、横断面和地方要求。</div>
        <ol><li>先整理 CAD 图层和单位；建议先运行“7. CAD 图层标准化”和“8. 图纸质量增强检查”。</li><li>点击顶部“🧭”确认项目坐标。使用 CGCS2000 等投影坐标时，必须启用场地附近的近原点，避免 SketchUp 大坐标抖动。</li><li>打开“10. CAD → SketchUp 模型交接”，确认建筑图层名称。</li><li>通常保持“保留图块层级”和“导入三维面”开启；只有确实需要 CAD 标注时才开启“导入文字”，以免模型中过多标签影响浏览。</li><li>只需要二维底图时把楼层设为 0；需要建筑体量时明确填写楼层数和标准层高。建筑图层已有 F/FH/H 明确参数时会自动接力，没有写明的部分继续使用这里的全局值。</li><li>如果各栋建筑高度、用途或屋顶不同，点击“逐栋设置高度与模型样式”；在表格中选择一栋或多栋，填写参数后点击应用，最后保存逐栋参数。优先级为：逐栋设置 → 明确图层参数 → 全局参数；任何层级都不会替你猜测审批高度。</li><li>普通作业选择“课程作业（推荐）”；只看体量时选“快速体量”，需要更完整建筑表达时选“汇报模型”。</li><li>在“道路建模”中可选：跟随模型精度、完整街道、基础车行道或关闭细化。完整街道主要处理闭合且接近矩形的 ROAD 道路面；满足两侧边界稳定条件的弯道会提供局部方向辅助，但不会强行矩形化。明确命名为 ROAD_CENTERLINE、ROAD_AXIS 或 CENTERLINE 的开放线也可帮助斑马线定向，宽度会标记为概念估计。这里是教学表达预设，不是道路规范符合性证明。</li><li>希望加入花池、遮阳伞、斑马线或交通灯时，在 CAD 中放置简单块并分别命名为 PT_PLANTER、PT_PARASOL、PT_CROSSWALK 或 PT_TRAFFIC_LIGHT；块内圆或方框只用于定位，进入 SketchUp 后会替换为共享组件。普通 PT_CROSSWALK 会匹配最近的可信规则道路，使斑马线长条与车辆行驶方向平行，并按车行道宽度调整跨度；系统还会让中心虚线、方向箭头和自动街灯避开过街区。要完全保留 CAD 指定角度时，把块命名为 PT_CROSSWALK_FIXED 或 PT_CROSSWALK_MANUAL。交叉口歧义、宽度不可信、异形道路或无法匹配时，系统保留 CAD 角度并在结果区计为待复核。交通灯始终保留 CAD 块角度，系统不会自动猜测信号控制。</li><li>系统会在入口位置自动少放首层窗，避免门窗重叠；不同建筑类型采用低饱和用途材质。自动入口默认放在最长立面中部，若它不是实际主入口，请在 SketchUp 中移动后锁定建筑。</li><li>保持“重复导入时只更新变化对象”开启，运行后得到 `.ptsu.json` 和 `PlanningToolbox_SketchUp_Importer.rbz`。结果区会显示建筑图层参数接力和“课程基础模型检查”：建筑高度、建筑层次、道路、绿化、停车、底图、待复核候选和未交接图元中哪些仍需补充。它只检查资料完整度，不是课程评分。</li><li>在 SketchUp 中打开“扩展程序管理器”，安装 RBZ；如果提示可更新，请安装本次输出的新 RBZ。</li><li>从“扩展程序 → 导入 Planning Toolbox 模型交接”选择 `.ptsu.json`，等待模型生成。</li><li>按 PT_BUILDING、PT_DETAIL、PT_FACADE、PT_GREEN 和 PT_ROAD 等标签检查对象。需要手工精修某栋建筑时，先选中其顶层分组，再执行“扩展程序 → 锁定选中的 Planning Toolbox 对象”。</li><li>修改 CAD 后重新导出并导入同一项目：未变化对象原样保留，变化对象自动替换，锁定对象不覆盖；如果需要系统重新生成某栋建筑，先解除该对象锁定。</li></ol>
        <div class="yellow">入口、阳台、屋顶设备和道路标线是按明确几何规则生成的作业辅助，不代表系统理解了真实建筑功能或交通组织；入口默认位于最长立面。窗、门、雨棚、街灯、阳台、设备和树优先复用组件定义，并设置数量上限。需要替换成自己的精致 SKP 时，可在 SketchUp“扩展程序”菜单打开 Planning Toolbox 自定义组件文件夹，按说明使用固定文件名；删除自定义文件即可恢复内置组件。场地高差只有几厘米，用于视觉分层而不代表真实竖向设计。填充、外部参照、复杂材质、代理对象和复杂网格仍不会自动重建，最终设计质量必须人工复核。</div>
        """

    @staticmethod
    def _faq_html() -> str:
        return """
        <h2>遇到问题时，先看这里</h2>
        <table>
          <tr><th>看到的情况</th><th>可能原因</th><th>怎么处理</th></tr>
          <tr><td>提示“请选择 DXF 文件”</td><td>还没有选择图纸，或路径已经失效。</td><td>重新浏览选择 .dxf 文件，或使用“一键示例图纸”。</td></tr>
          <tr><td>提示“DXF 单位未知”</td><td>图纸没有写入 INSUNITS 单位。</td><td>优先在 AutoCAD 中用 UNITS 设置单位后重新保存；学习测试时也可以在任务参数中明确选择回退单位。</td></tr>
          <tr><td>最低人工修改模式被阻断</td><td>DXF 单位未知，系统无法安全解释 0.05 等连接容差。</td><td>先在 CAD 中设置真实单位并另存 DXF；不要为了运行而随意猜测米或毫米。</td></tr>
          <tr><td>报告显示“分叉碎线组已跳过”</td><td>多条线在同一点形成路口或支路，自动合并可能改变连接含义。</td><td>这是安全保护。根据逐项修改 CSV 在 CAD 中人工确认该路口，其余无分叉碎线已自动处理。</td></tr>
          <tr><td>指标任务无法运行</td><td>没有填写楼层倍数，或填写为 0。</td><td>在指标页填写真实的楼层倍数，例如 6；不要让程序替你猜。</td></tr>
          <tr><td>有效地块数量为 0</td><td>图层名称不匹配、线没有闭合，或几何存在异常。</td><td>检查左侧图层数量和未闭合线数量；确认任务页的图层名与 DXF 一致。</td></tr>
          <tr><td>结果数量不符合预期</td><td>地块与建筑可能跨界、重叠、嵌套，或图纸存在重复线。</td><td>先看检查区的总线数、闭合数、嵌套数，再回 CAD 清理图层和重复轮廓。</td></tr>
          <tr><td>GeoJSON 导入被阻断</td><td>文件是 WGS84 经纬度，或没有经过适当的投影转换。</td><td>先在 QGIS / ArcGIS 中转换为适合当地平面距离计算的投影坐标，再导入。</td></tr>
          <tr><td>提示“需要安装本机 GIS 转换组件”</td><td>选择了 GPKG/SHP 模式，但电脑没有检测到 ArcGIS Pro 或 QGIS/GDAL。</td><td>如果已经安装 ArcGIS Pro，请确认安装完整并重启软件；否则仍可使用基础 GeoJSON↔DXF。</td></tr>
          <tr><td>GeoPackage 提示包含多个面图层</td><td>系统无法判断应该把哪一个面图层写入 CAD。</td><td>在 ArcGIS Pro 中只导出本次需要的面图层为单独 GPKG/SHP，再导入；系统不会擅自选择第一个图层。</td></tr>
          <tr><td>GPKG/SHP 导入后数量较少</td><td>数据中包含点、线、文字或其他非面要素。</td><td>当前只写入 Polygon/MultiPolygon；查看结果中的跳过数量，并在 QGIS 中先筛选面图层。</td></tr>
          <tr><td>窗口看起来没有反应</td><td>正在后台处理大图纸；程序设计为计算时保持界面可响应。</td><td>先观察底部进度和日志，不要连续点击运行；必要时等待任务结束。</td></tr>
          <tr><td>输出目录里文件很多</td><td>每次任务都会保留报告和中间结果，便于追溯。</td><td>按文件名中的 DXF 名称和任务类型查找；批量任务看 batch_summary.csv。</td></tr>
          <tr><td>不知道哪些文件要交</td><td>输出文件按用途分散在目录中。</td><td>任务完成后点击“整理为作业包”，按 CAD、数据表、报告三个文件夹逐项检查；最终以老师要求为准。</td></tr>
          <tr><td>作业包能不能代替作业说明</td><td>作业包只负责整理自动结果。</td><td>不能。请补充自己的方案思路、规范判断、截图和人工修改说明。</td></tr>
          <tr><td>打开项目后找不到图纸</td><td>原始 DXF 被移动、改名或移动了电脑位置。</td><td>重新浏览选择有效 DXF；项目中的参数仍然可以继续使用。</td></tr>
          <tr><td>导出的 Excel、PDF、PNG 在哪里</td><td>它们会写入当前“结果输出目录”。</td><td>先点击结果区“导出 Excel/PDF/图片”，再用“整理为作业包”统一分类保存。</td></tr>
          <tr><td>图层标准化后还有未识别图层</td><td>原图使用了内置规范之外的自定义名称。</td><td>打开图层检查报告，确认这些图层用途；系统会保留它们，不会擅自删除。</td></tr>
          <tr><td>中国制图检查显示“需要人工确认”</td><td>必备图层为空、存在自定义图层，或DXF无法可靠声明地理坐标系。</td><td>这通常不是程序故障。打开检查报告逐项确认；国土空间规划图件还必须核对CGCS2000、高斯-克吕格投影和高程基准。</td></tr>
          <tr><td>已经显示“辅助检查通过”，能否直接报审</td><td>机器只能核对单位、图层和辅助样式，不能理解全部条文、地方条件和设计合理性。</td><td>不能直接报审。继续核对最新版正式标准、地方规划条件、课程任务书并进行专业复核。</td></tr>
          <tr><td>方案对比里没有项目</td><td>还没有保存 `.ptx` 项目，或项目没有最近一次结果。</td><td>先分别运行并保存每个方案，再打开“方案对比”添加项目。</td></tr>
          <tr><td>方案叠加图为空或少了轮廓</td><td>项目没有可用的 DXF 结果，或图纸主要由暂不绘制的散乱图元组成。</td><td>确认项目仍能找到 DXF；必要时先导出/保存新的 DXF。叠加图用于方案位置比较，详细图元请回 CAD 复核。</td></tr>
          <tr><td>质量修复后图纸仍需检查</td><td>自动修复只针对精确重复线和近闭合线。</td><td>阅读质量报告，在 CAD 中核对建筑、道路、块参照和复杂曲线；不要把修复副本直接当成最终成果。</td></tr>
          <tr><td>提示语义场景与当前 DXF 不匹配</td><td>DXF 在外部软件中被改过，但旁边的 `.ptscene.json` 仍对应旧文件。</td><td>这是安全阻断。回到图片转 CAD 重新生成，或把已人工确认的对象整理到正式 CAD 图层后再导出；不要复制旧语义文件冒充新结果。</td></tr>
          <tr><td>SketchUp 中参考线很多但对象列表很短</td><td>系统把大量图片描线合并成一个锁定的 `PT_UNDERLAY` 底图组。</td><td>这是正常的轻量化结果。需要查看时解除隐藏，不要逐线编辑；真正需要修改的建筑、绿化和停车候选仍是独立对象。</td></tr>
          <tr><td>SketchUp 道路出现双层、灰块或重复街灯</td><td>旧交接文件把图片道路面候选和中心线道路带同时建成了实体，或者仍在使用旧版插件。</td><td>安装本次输出的新 RBZ，重新生成交接文件，并保持“仅高可信候选生成实体（推荐）”；结果区应显示“重复道路面转复核轮廓”。</td></tr>
          <tr><td>SketchUp 交接提示必须启用近原点</td><td>DXF 使用数十万或数百万的投影坐标，直接进入 SketchUp 容易出现显示和精度问题。</td><td>点击顶部“🧭”，启用近原点并填写场地附近的东坐标、北坐标；系统会保存可逆转换关系，不会修改原 DXF。</td></tr>
          <tr><td>SketchUp 中没有导入菜单</td><td>RBZ 还没有安装，或扩展程序被禁用。</td><td>在 SketchUp“扩展程序管理器”安装输出目录中的 RBZ，并确认“Planning Toolbox 模型交接”已启用。</td></tr>
          <tr><td>SketchUp 建筑只有平面没有高度</td><td>导出时楼层数为 0，或轮廓不是闭合建筑图层。</td><td>确认建筑轮廓闭合、图层名已列入建筑图层，并明确填写楼层数和标准层高后重新导出。</td></tr>
          <tr><td>SketchUp 中图块或文字太多</td><td>原 CAD 含大量重复图块或标注，并开启了相应兼容开关。</td><td>不需要时关闭“保留图块层级”或“导入文字”；文字默认关闭，常规体量建模通常无需导入全部标注。</td></tr>
          <tr><td>重复导入后手工调整被替换</td><td>该对象没有先锁定，且 CAD 几何或建模参数已经变化。</td><td>精修重点建筑前，选中顶层 PT_* 分组，点击“扩展程序 → 锁定选中的 Planning Toolbox 对象”；需要自动更新时再解除锁定。</td></tr>
          <tr><td>复杂建筑没有生成坡屋顶</td><td>当前自动坡屋顶只处理四边形闭合建筑，复杂凹多边形会安全退回平屋顶。</td><td>保留自动平屋顶作为体量底稿，再在 SketchUp 中手工处理重点建筑屋顶并锁定该对象。</td></tr>
        </table>
        <h3>仍然不确定时</h3>
        <p>不要直接把结果当作最终结论。保留原始 DXF、输出报告和问题截图，先确认图层、单位、楼层和坐标系这四项基础信息。</p>
        """

    @staticmethod
    def _safety_html() -> str:
        return """
        <h2>五条必须记住的安全规则</h2>
        <div class="green"><strong>1. 原始 DXF 只读保护</strong><br>系统读取原始图纸并计算 SHA-256 校验值，结果写入新文件，不会覆盖原始 DXF。</div>
        <div class="red"><strong>2. 单位未知时不要硬算</strong><br>如果 DXF 没有明确单位，面积和退线距离可能相差很大。系统会阻断相关计算，除非你明确选择单位回退值。</div>
        <div class="yellow"><strong>3. 楼层必须由你确认</strong><br>建筑总面积依赖楼层倍数。程序不会默认为 1 层或其他楼层，示例预设只用于学习，不代表法定标准。</div>
        <div class="blue"><strong>4. 经纬度不是米制平面坐标</strong><br>WGS84 经纬度的数值单位是“度”，不能直接用于 CAD 距离和面积。导入前请完成投影转换。</div>
        <div class="blue"><strong>5. 项目文件不是图纸备份</strong><br>`.ptx` 保存 DXF 路径、参数、结果记录和轻量全链路坐标清单，但不会复制原始 DXF。请单独保留原始图纸，并在移动文件后重新选择路径。</div>
        <div class="yellow"><strong>6. “中国标准辅助”不是审批承诺</strong><br>模板只核对可机器检查的图层、单位和样式。标准版本、地方条件、坐标基准和专业条文仍须人工确认。</div>
        <div class="blue"><strong>7. SketchUp 交接不是自动完成设计</strong><br>系统可交接已识别的几何、常见嵌套图块、三维面、可选文字、图层、坐标和明确高度。填充、外部参照、材质、代理对象、复杂网格以及空间设计判断仍须在 CAD / SketchUp 中人工完成。</div>
        <h3>结果应该如何使用？</h3>
        <ul>
          <li>适合：课程练习、方案比选、图纸体检、初步面积统计、批量整理和生成可追溯报告。</li>
          <li>不适合：替代当地规划条件、施工图审查、测绘成果、审批意见或专业人员最终签字。</li>
          <li>提交成果前：核对图层、单位、坐标系、楼层、退线规则，并由专业人员复核。</li>
        </ul>
        """
