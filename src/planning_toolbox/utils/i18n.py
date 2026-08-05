"""轻量中文消息映射 (Lightweight Chinese message mapping for non-programmer users)."""

# CLI 标题
TITLE_MAIN = "城乡规划 CAD–GIS 自动化辅助工具箱"
TITLE_PARCEL = "地块面积计算与编号工具"
TITLE_LAYER_TEMPLATE = "CAD 图层标准模板生成"
TITLE_LAYER_STD = "CAD 图层标准化"
TITLE_GIS_EXPORT = "CAD → GeoJSON 导出"
TITLE_GIS_IMPORT = "GeoJSON → CAD 导入"
TITLE_INDICATOR = "规划指标自动核算"
TITLE_VALIDATE = "拓扑与退线规则检查"

# 状态信息
MSG_TASK_DONE = "任务完成"
MSG_PROCESSING = "正在处理"
MSG_SOURCE_FILE = "源文件"
MSG_OUTPUT_FILE = "输出文件"
MSG_TOTAL_PARCELS = "地块总数"
MSG_VALID_PARCELS = "有效闭合地块"
MSG_OPEN_BOUNDARIES = "未闭合边界"
MSG_INVALID_GEOM = "无效几何"
MSG_TOTAL_AREA = "有效面积合计"
MSG_ERRORS_WARNINGS = "错误/警告"

# 指标标签
LBL_SITE_AREA = "用地面积"
LBL_BUILDING_FOOTPRINT = "建筑基底面积"
LBL_TOTAL_FLOOR = "总建筑面积"
LBL_GREEN_AREA = "绿地面积"
LBL_FAR = "容积率 (FAR)"
LBL_DENSITY = "建筑密度"
LBL_GREEN_RATIO = "绿地率"

# 验证标签
LBL_TOPOLOGY_VALID = "有效闭合边界"
LBL_TOPOLOGY_OPEN = "未闭合边界"
LBL_TOPOLOGY_INVALID = "自交/无效几何"
LBL_SETBACK_COMPLIANT = "退线合规"
LBL_SETBACK_VIOLATION = "退线违规"
LBL_SETBACK_NO_BUILDING = "未检测到建筑"

# 错误信息（用户友好型）
ERR_UNIT_UNKNOWN = (
    "DXF 文件单位 ($INSUNITS) 未设置。\n"
    "  解决方法：\n"
    "  1. 在 AutoCAD 中输入 UNITS 命令，将单位设为【米】(Meters)\n"
    "  2. 或在配置文件 config/default.yaml 中设置 fallback_unit: 'm'\n"
    "  3. 设置后重新保存 DXF 文件再运行本工具"
)
ERR_FILE_NOT_FOUND = "文件未找到: {path}\n请检查文件路径是否正确。"
ERR_DXF_PARSE_FAILED = "DXF 文件解析失败: {path}\n可能原因: 文件损坏或版本不兼容。"
ERR_GEOJSON_PARSE_FAILED = "GeoJSON 文件解析失败: {path}\n请确认文件格式是否为标准 RFC 7946 GeoJSON。"
ERR_PATH_COLLISION = "输出路径与源文件相同，禁止直接覆盖原始文件。\n请指定不同的输出路径。"
ERR_SELF_INTERSECTION = "多段线自交错误。请在 AutoCAD 中检查并修复该边界。"
ERR_OPEN_BOUNDARY = "多段线未闭合。请在 AutoCAD 中使用 PEDIT > Close 闭合该边界。"


def format_section_header(title: str) -> str:
    """格式化节标题，用于 CLI 输出。"""
    bar = "=" * 44
    return f"\n{bar}\n   {title}\n{bar}"


def format_section_footer() -> str:
    return "=" * 44 + "\n"
