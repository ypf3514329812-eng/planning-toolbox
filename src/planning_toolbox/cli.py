"""Planning Toolbox CLI — 城乡规划 CAD–GIS 自动化辅助工具箱 统一命令行入口"""
import argparse
import sys
from pathlib import Path
from planning_toolbox import __version__
from planning_toolbox.config import load_config
from planning_toolbox.utils.logger import setup_logger
from planning_toolbox.utils.i18n import (
    format_section_header, format_section_footer,
    TITLE_MAIN, TITLE_PARCEL, TITLE_LAYER_TEMPLATE, TITLE_LAYER_STD,
    TITLE_GIS_EXPORT, TITLE_GIS_IMPORT, TITLE_INDICATOR, TITLE_VALIDATE,
    MSG_TASK_DONE, ERR_UNIT_UNKNOWN,
)

logger = setup_logger()


# ──────────────────────────────────────────────
#  Subcommand implementations
# ──────────────────────────────────────────────

def cmd_parcel(args):
    """地块面积计算与编号工具 (Parcel Area Calculator)."""
    from planning_toolbox.cad.parcels.calculator import process_parcels

    cfg = load_config(args.config)
    dxf_path = Path(args.dxf)
    out_dir = args.output

    logger.info(f"正在处理 DXF 文件: {dxf_path}")
    parcels, labeled_dxf, csv_file, report_file = process_parcels(
        dxf_path=dxf_path, config=cfg, output_dir=out_dir
    )

    valid_count = sum(1 for p in parcels if p.status == "VALID")
    total_ha = sum(p.area_ha for p in parcels if p.status == "VALID")
    error_count = sum(1 for p in parcels if p.status != "VALID")

    geojson_file = (Path(out_dir) if out_dir else Path("output")) / f"{dxf_path.stem}.geojson"

    print(format_section_header(TITLE_PARCEL))
    print(f"源 DXF 文件:           {dxf_path}")
    print(f"候选实体总数:         {len(parcels)}")
    print(f"有效闭合地块:         {valid_count}")
    if error_count > 0:
        print(f"错误/警告:            {error_count}")
    print(f"有效面积合计:         {total_ha:.4f} ha")
    print("------------------------------------------")
    print(f"标注 DXF 输出:        {labeled_dxf}")
    print(f"CSV 汇总输出:         {csv_file}")
    print(f"GeoJSON GIS 输出:     {geojson_file}")
    print(f"详细报告输出:         {report_file}")
    print(format_section_footer())


def cmd_layer_template(args):
    """生成城乡规划标准空白 CAD 模板 (Layer Template Generator)."""
    from planning_toolbox.cad.layers.template import create_planning_template
    from planning_toolbox.cad.layers.manager import load_layer_config

    template_path = Path(args.output) if args.output else Path("output/planning_template.dxf")
    layer_cfg = load_layer_config(args.config)
    out_file = create_planning_template(template_path, layer_cfg)

    print(format_section_header(TITLE_LAYER_TEMPLATE))
    print(f"模板文件: {out_file}")
    print(format_section_footer())


def cmd_layer_standardize(args):
    """标准化 CAD 图层 (Layer Standardizer)."""
    from planning_toolbox.cad.layers.manager import load_layer_config, standardize_dxf_layers

    dxf_path = Path(args.dxf)
    layer_cfg = load_layer_config(args.config)
    std_dxf, report_file, remapped, unmapped = standardize_dxf_layers(
        dxf_path=dxf_path, layer_config=layer_cfg, output_dir=args.output
    )

    print(format_section_header(TITLE_LAYER_STD))
    print(f"源 DXF 文件:          {dxf_path}")
    print(f"标准化 DXF:           {std_dxf}")
    print(f"图层分析报告:         {report_file}")
    print(f"未映射图层数:         {len(unmapped)}")
    print(format_section_footer())


def cmd_gis_export(args):
    """导出 CAD 地块至 GeoJSON (GIS Export)."""
    from planning_toolbox.cad.parcels.calculator import process_parcels

    cfg = load_config(args.config)
    dxf_path = Path(args.dxf)
    out_dir = Path(args.output) if args.output else Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, cfg, out_dir)
    geojson_file = out_dir / f"{dxf_path.stem}.geojson"

    print(format_section_header(TITLE_GIS_EXPORT))
    print(f"源 DXF 文件:          {dxf_path}")
    print(f"GeoJSON 输出:         {geojson_file}")
    print(f"地块总数:             {len(parcels)}")
    print(format_section_footer())


def cmd_gis_import(args):
    """导入 GeoJSON 至 CAD DXF (GIS Import)."""
    from planning_toolbox.gis.io.importer import import_geojson_to_dxf

    geojson_path = Path(args.geojson)
    out_dir = Path(args.output) if args.output else Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dxf = out_dir / f"{geojson_path.stem}_from_gis.dxf"

    res_dxf, stats = import_geojson_to_dxf(geojson_path, out_dxf)

    print(format_section_header(TITLE_GIS_IMPORT))
    print(f"源 GeoJSON 文件:      {geojson_path}")
    print(f"输出 CAD DXF:         {res_dxf}")
    print(f"导入多边形数:         {stats['imported_polygons']}")
    if stats['skipped_unsupported'] > 0 or stats['skipped_errors'] > 0:
        print(f"跳过（不支持类型）:   {stats['skipped_unsupported']}")
        print(f"跳过（解析错误）:     {stats['skipped_errors']}")
    print(format_section_footer())


def cmd_indicator(args):
    """规划指标自动核算 (Planning Indicators)."""
    from planning_toolbox.indicators.calculator import (
        calculate_parcel_indicators, process_dxf_indicators
    )

    if args.site_area is not None:
        ind = calculate_parcel_indicators(
            parcel_id="P001",
            site_area_m2=args.site_area,
            building_footprint_m2=args.building_footprint,
            total_building_m2=args.total_building,
            green_area_m2=args.green_area
        )
        print(format_section_header(TITLE_INDICATOR))
        print(f"用地面积:             {ind.site_area_m2:,.2f} m² ({ind.site_area_ha:.4f} ha)")
        print(f"建筑基底面积:         {ind.building_footprint_m2:,.2f} m²")
        print(f"总建筑面积:           {ind.total_building_m2:,.2f} m²")
        print(f"绿地面积:             {ind.green_area_m2:,.2f} m²")
        print("------------------------------------------")
        print(f"容积率 (FAR):         {ind.far:.2f}")
        print(f"建筑密度:             {ind.building_density_pct:.2f}%")
        print(f"绿地率:               {ind.green_ratio_pct:.2f}%")
        print(format_section_footer())
        return

    if args.dxf:
        dxf_path = Path(args.dxf)
        cfg = {}
        if args.config:
            cfg = load_config(args.config)
        results, csv_file, report_file = process_dxf_indicators(
            dxf_path, config=cfg, output_dir=args.output
        )
        print(format_section_header(TITLE_INDICATOR))
        print(f"源 DXF 文件:          {dxf_path}")
        print(f"分析地块数:           {len(results)}")
        print(f"CSV 报告输出:         {csv_file}")
        print(f"文本报告输出:         {report_file}")
        print(format_section_footer())
        return

    print("错误: 请指定 --dxf 或 --site-area 参数。")
    sys.exit(1)


def cmd_validate(args):
    """拓扑与退线规则检查 (Topology & Setback Validator)."""
    import ezdxf
    from planning_toolbox.validators.topology import validate_polyline_topology
    from planning_toolbox.validators.setback import check_building_setback
    from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry

    dxf_path = Path(args.dxf)
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # 1. Topology Audit
    topology_results = []
    for idx, entity in enumerate(msp):
        if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            res = validate_polyline_topology(entity, idx)
            topology_results.append(res)

    valid_count = sum(1 for r in topology_results if r.status == "VALID")
    open_count = sum(1 for r in topology_results if r.status == "OPEN")
    invalid_count = sum(1 for r in topology_results if r.status == "INVALID_GEOMETRY")

    print(format_section_header(TITLE_VALIDATE))
    print(f"扫描多段线总数:       {len(topology_results)}")
    print(f"有效闭合边界:         {valid_count}")
    print(f"未闭合边界:           {open_count}")
    print(f"自交/无效几何:        {invalid_count}")

    # 2. Building Setback Check
    parcel_layer = getattr(args, 'parcel_layer', 'PARCEL').upper()
    building_layer = getattr(args, 'building_layer', 'BUILDING').upper()
    setback_m = args.setback

    parcel_polys = []
    building_polys = []
    for entity in msp:
        if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
            continue
        layer_upper = str(entity.dxf.layer).upper()
        pts, is_closed, _ = points_from_dxf_polyline(entity)
        status, poly, _ = parse_parcel_geometry(pts, is_closed)
        if status == "VALID" and poly:
            if layer_upper == parcel_layer:
                parcel_polys.append(poly)
            elif layer_upper == building_layer:
                building_polys.append(poly)

    print(f"------------------------------------------")
    print(f"建筑退线合规检查 (退线要求: {setback_m}m)")

    if not parcel_polys:
        print(f"  未检测到 PARCEL 图层地块。")
    elif not building_polys:
        print(f"  未检测到 BUILDING 图层建筑。")
    else:
        for idx, p_poly in enumerate(parcel_polys, start=1):
            pid = f"P{idx:03d}"
            result = check_building_setback(p_poly, building_polys, setback_m, pid)
            status_cn = {
                "COMPLIANT": "✓ 合规", "VIOLATION": "✗ 违规", "NO_BUILDING": "— 无建筑"
            }.get(result.status, result.status)
            print(f"  [{pid}] {status_cn}", end="")
            if result.status == "VIOLATION":
                print(f"  违规数:{result.violations_count}  最近距离:{result.min_distance_m:.2f}m")
            elif result.status == "COMPLIANT":
                print(f"  最近距离:{result.min_distance_m:.2f}m")
            else:
                print()

    print(format_section_footer())


# ──────────────────────────────────────────────
#  Main CLI entry point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="planning-toolbox",
        description=f"城乡规划 CAD–GIS 自动化辅助工具箱 v{__version__}\n"
                    "原则：人负责规划判断，程序负责计算和重复劳动。",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", action="version", version=f"Planning Toolbox v{__version__}")
    parser.add_argument("--verbose", action="store_true", help="显示详细调试输出")

    subparsers = parser.add_subparsers(dest="command", title="可用子命令", metavar="<命令>")

    # ─── parcel ───
    sp_parcel = subparsers.add_parser("parcel", help="地块面积计算与编号")
    sp_parcel.add_argument("--dxf", required=True, help="输入 DXF 文件路径")
    sp_parcel.add_argument("--config", default=None, help="YAML 配置文件路径")
    sp_parcel.add_argument("--output", default=None, help="输出目录路径")
    sp_parcel.set_defaults(func=cmd_parcel)

    # ─── layer ───
    sp_layer = subparsers.add_parser("layer", help="CAD 图层管理")
    layer_sub = sp_layer.add_subparsers(dest="layer_action", title="图层操作", metavar="<操作>")

    sp_lt = layer_sub.add_parser("template", help="生成标准空白 CAD 模板")
    sp_lt.add_argument("--output", default=None, help="模板输出路径")
    sp_lt.add_argument("--config", default=None, help="图层配置文件路径")
    sp_lt.set_defaults(func=cmd_layer_template)

    sp_ls = layer_sub.add_parser("standardize", help="标准化 CAD 图层名称")
    sp_ls.add_argument("--dxf", required=True, help="输入 DXF 文件路径")
    sp_ls.add_argument("--config", default=None, help="图层配置文件路径")
    sp_ls.add_argument("--output", default=None, help="输出目录路径")
    sp_ls.set_defaults(func=cmd_layer_standardize)

    # ─── gis ───
    sp_gis = subparsers.add_parser("gis", help="GIS ↔ CAD 数据桥梁")
    gis_sub = sp_gis.add_subparsers(dest="gis_action", title="GIS 操作", metavar="<操作>")

    sp_ge = gis_sub.add_parser("export", help="导出 CAD 地块至 GeoJSON")
    sp_ge.add_argument("--dxf", required=True, help="输入 DXF 文件路径")
    sp_ge.add_argument("--config", default=None, help="YAML 配置文件路径")
    sp_ge.add_argument("--output", default="output", help="输出目录路径")
    sp_ge.set_defaults(func=cmd_gis_export)

    sp_gi = gis_sub.add_parser("import", help="导入 GeoJSON 至 CAD DXF")
    sp_gi.add_argument("--geojson", required=True, help="输入 GeoJSON 文件路径")
    sp_gi.add_argument("--output", default="output", help="输出目录路径")
    sp_gi.set_defaults(func=cmd_gis_import)

    # ─── indicator ───
    sp_ind = subparsers.add_parser("indicator", help="规划指标自动核算 (FAR, 密度, 绿地率)")
    sp_ind.add_argument("--dxf", default=None, help="输入 DXF 文件路径")
    sp_ind.add_argument("--config", default=None, help="YAML 配置文件路径")
    sp_ind.add_argument("--site-area", type=float, default=None, help="手动输入用地面积 (m²)")
    sp_ind.add_argument("--building-footprint", type=float, default=0.0, help="建筑基底面积 (m²)")
    sp_ind.add_argument("--total-building", type=float, default=0.0, help="总建筑面积 (m²)")
    sp_ind.add_argument("--green-area", type=float, default=0.0, help="绿地面积 (m²)")
    sp_ind.add_argument("--output", default="output", help="输出目录路径")
    sp_ind.set_defaults(func=cmd_indicator)

    # ─── validate ───
    sp_val = subparsers.add_parser("validate", help="拓扑与退线规则检查")
    sp_val.add_argument("--dxf", required=True, help="输入 DXF 文件路径")
    sp_val.add_argument("--setback", type=float, default=5.0, help="建筑退线距离 (米, 默认: 5.0)")
    sp_val.add_argument("--parcel-layer", default="PARCEL", help="地块图层名称 (默认: PARCEL)")
    sp_val.add_argument("--building-layer", default="BUILDING", help="建筑图层名称 (默认: BUILDING)")
    sp_val.add_argument("--output", default="output", help="输出目录路径")
    sp_val.set_defaults(func=cmd_validate)

    # ─── Parse and dispatch ───
    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.getLogger("planning_toolbox").setLevel(logging.DEBUG)

    if not args.command:
        parser.print_help()
        return

    try:
        args.func(args)
    except Exception as e:
        from planning_toolbox.core.units.unit_manager import UnitError
        if isinstance(e, UnitError):
            logger.error(ERR_UNIT_UNKNOWN)
        else:
            logger.error(f"执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
