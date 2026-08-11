"""Planning Toolbox CLI — 城乡规划 CAD–GIS 自动化辅助工具箱 统一命令行入口"""
import argparse
import sys
from pathlib import Path
from planning_toolbox import __version__
from planning_toolbox.config import load_config
from planning_toolbox.core.units.unit_manager import (
    get_dxf_unit_code, get_linear_scale_to_m, resolve_unit,
)
from planning_toolbox.utils.logger import setup_logger
from planning_toolbox.utils.file_integrity import sha256_file, assert_file_unchanged
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
    from planning_toolbox.cad.layers.manager import (
        load_drafting_layer_config,
        load_layer_config,
    )

    template_path = Path(args.output) if args.output else Path("output/planning_template.dxf")
    layer_cfg = (
        load_drafting_layer_config(args.drafting_profile)
        if getattr(args, "drafting_profile", None)
        else load_layer_config(args.config)
    )
    out_file = create_planning_template(template_path, layer_cfg)

    print(format_section_header(TITLE_LAYER_TEMPLATE))
    print(f"模板文件: {out_file}")
    print(format_section_footer())


def cmd_layer_standardize(args):
    """标准化 CAD 图层 (Layer Standardizer)."""
    from planning_toolbox.cad.layers.compliance import audit_dxf_drafting_compliance
    from planning_toolbox.cad.layers.manager import (
        load_drafting_layer_config,
        load_layer_config,
        standardize_dxf_layers,
    )

    dxf_path = Path(args.dxf)
    layer_cfg = (
        load_drafting_layer_config(args.drafting_profile)
        if getattr(args, "drafting_profile", None)
        else load_layer_config(args.config)
    )
    std_dxf, report_file, remapped, unmapped = standardize_dxf_layers(
        dxf_path=dxf_path, layer_config=layer_cfg, output_dir=args.output
    )

    print(format_section_header(TITLE_LAYER_STD))
    print(f"源 DXF 文件:          {dxf_path}")
    print(f"标准化 DXF:           {std_dxf}")
    print(f"图层分析报告:         {report_file}")
    print(f"未映射图层数:         {len(unmapped)}")
    if getattr(args, "drafting_profile", None):
        compliance = audit_dxf_drafting_compliance(
            std_dxf,
            layer_cfg,
            output_dir=args.output,
            unmapped_layers=unmapped,
        )
        print(f"中国制图辅助检查:     {compliance['report_path']}")
        print(f"辅助检查结论:         {compliance['status']}")
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

    res_dxf, stats = import_geojson_to_dxf(
        geojson_path, out_dxf, target_unit=args.unit
    )

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
        if args.floors is not None:
            cfg["default_floors"] = args.floors
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
    source_sha256_before = sha256_file(dxf_path)
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # Setback values are specified in meters, so the DXF unit must be known
    # before any distance calculation is allowed.
    cfg = load_config(args.config)
    parcel_cfg = cfg.get("parcel", {})
    fallback_unit = args.fallback_unit or parcel_cfg.get("fallback_unit")
    strict_unit = parcel_cfg.get("strict_unit_check", True)
    if args.fallback_unit:
        # An explicit command-line fallback is an affirmative user choice.
        strict_unit = False
    unit_name = resolve_unit(
        get_dxf_unit_code(doc),
        fallback_unit=fallback_unit,
        strict_check=strict_unit,
    )
    geometry_unit_to_m = get_linear_scale_to_m(unit_name)

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
    if setback_m < 0:
        raise ValueError("建筑退线距离必须是非负数（米）。")

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

    setback_results = []
    if not parcel_polys:
        print(f"  未检测到 PARCEL 图层地块。")
    elif not building_polys:
        print(f"  未检测到 BUILDING 图层建筑。")
    else:
        for idx, p_poly in enumerate(parcel_polys, start=1):
            pid = f"P{idx:03d}"
            parcel_buildings = [b_poly for b_poly in building_polys if p_poly.intersects(b_poly)]
            result = check_building_setback(
                p_poly,
                parcel_buildings,
                required_setback_m=setback_m,
                parcel_id=pid,
                geometry_unit_to_m=geometry_unit_to_m,
            )
            setback_results.append({
                "parcel_id": pid,
                "status": result.status,
                "violations": result.violations_count,
                "min_distance_m": result.min_distance_m,
                "error_message": result.error_message or "",
            })
            status_cn = {
                "COMPLIANT": "[合规]", "VIOLATION": "[违规]", "NO_BUILDING": "[无建筑]"
            }.get(result.status, result.status)
            print(f"  [{pid}] {status_cn}", end="")
            if result.status == "VIOLATION":
                print(f"  违规数:{result.violations_count}  最近距离:{result.min_distance_m:.2f}m")
            elif result.status == "COMPLIANT":
                print(f"  最近距离:{result.min_distance_m:.2f}m")
            else:
                print()

    assert_file_unchanged(dxf_path, source_sha256_before)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"{dxf_path.stem}_validate_report.txt"
    with report_file.open("w", encoding="utf-8") as report:
        report.write("=== Planning Toolbox Validation Report ===\n")
        report.write(f"Source DXF: {dxf_path.name}\n")
        report.write(f"Source SHA-256: {source_sha256_before}\n")
        report.write(f"Detected Unit: {unit_name}\n")
        report.write(f"Setback Requirement (m): {setback_m:g}\n")
        report.write(f"Scanned Polylines: {len(topology_results)}\n")
        report.write(f"Valid Closed Polylines: {valid_count}\n")
        report.write(f"Open Polylines: {open_count}\n")
        report.write(f"Invalid Geometry: {invalid_count}\n")
        report.write("--- Parcel Setback Results ---\n")
        for item in setback_results:
            report.write(
                f"[{item['parcel_id']}] {item['status']} | "
                f"min_distance_m={item['min_distance_m']:.3f} | "
                f"violations={item['violations']}\n"
            )
    print(f"验证报告输出:         {report_file}")
    print(format_section_footer())


def cmd_rules_list(args):
    """List built-in planning-condition templates."""
    from planning_toolbox.rules.presets import list_rule_presets

    print("可用规划条件模板:")
    for preset in list_rule_presets():
        floors = str(preset.floors) if preset.floors is not None else "未指定"
        print(
            f"- {preset.preset_id}: {preset.name} | "
            f"楼层倍数={floors} | 退线={preset.setback_m:g}m"
        )
        print(f"  {preset.description}")


def cmd_batch(args):
    """Analyze all DXF files in a folder and write a summary CSV."""
    from planning_toolbox.batch.analyzer import analyze_dxf_batch

    result = analyze_dxf_batch(
        input_dir=args.input,
        output_dir=args.output,
        task_type=args.task,
        floors=args.floors,
        config_path=args.config,
    )
    print("批量 DXF 分析完成")
    print(f"处理文件数: {result['processed_count']}")
    print(f"成功文件数: {result['success_count']}")
    print(f"失败文件数: {result['failed_count']}")
    print(f"汇总报告: {result['summary_file']}")


# ──────────────────────────────────────────────
#  Main CLI entry point
# ──────────────────────────────────────────────

def cmd_concept_plan(args):
    """Generate a local, parameterized concept-plan DXF."""
    from planning_toolbox.cad.planning.concept_generator import generate_concept_plan

    result = generate_concept_plan(
        dxf_path=args.dxf,
        output_dir=args.output,
        building_count=args.buildings,
        coverage_ratio=args.coverage / 100.0,
        setback_m=args.setback,
        parcel_layer=args.parcel_layer,
        fallback_unit=args.fallback_unit,
        floors=args.floors,
        parking_ratio=args.parking_ratio,
        building_gap_m=args.building_gap,
        access_width_m=args.access_width,
        standards_profile_id=args.standards_profile,
        layout_style=args.layout_style,
    )
    print("概念方案草图已生成（仅供方案研究，不是审批成果）")
    print(f"有效地块: {result['parcels_count']}")
    print(f"建筑轮廓: {result['building_footprints']}")
    print(f"建筑基底面积: {result['building_footprint_m2']:.2f} m2")
    if result["estimated_gfa_m2"] is not None:
        print(f"估算总建筑面积: {result['estimated_gfa_m2']:.2f} m2")
    if result["parking_ratio"] is not None:
        print(
            f"概念停车位: {result['parking_generated']}/{result['parking_required']} "
            f"（未放置 {result['parking_unplaced']}）"
        )
    print(f"实际建筑覆盖率: {result['actual_coverage_ratio'] * 100:.2f}%")
    if result["minimum_setback_m"] is not None:
        print(f"生成建筑最小退线: {result['minimum_setback_m']:.2f} m")
    if result["minimum_building_gap_m"] is not None:
        print(f"生成建筑最小间距: {result['minimum_building_gap_m']:.2f} m")
    if result["access_width_m"] > 0:
        print(f"概念道路/消防通道: {result['access_width_m']:.2f} m，面积 {result['access_corridor_m2']:.2f} m2")
    print(f"规范依据框架: {result['standards_profile_name']}")
    print(f"绿地轮廓: {result['green_polygons']}")
    for label, path in result["output_files"]:
        print(f"{label}: {path}")


def main():
    parser = argparse.ArgumentParser(
        prog="planning-toolbox",
        description=f"城乡规划 CAD-GIS 自动化辅助工具箱 v{__version__}\n"
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
    sp_lt.add_argument(
        "--drafting-profile",
        default=None,
        choices=(
            "china_coursework_general",
            "china_residential_site",
            "china_territorial_spatial_review",
        ),
        help="使用内置中国规划制图辅助模板",
    )
    sp_lt.set_defaults(func=cmd_layer_template)

    sp_ls = layer_sub.add_parser("standardize", help="标准化 CAD 图层名称")
    sp_ls.add_argument("--dxf", required=True, help="输入 DXF 文件路径")
    sp_ls.add_argument("--config", default=None, help="图层配置文件路径")
    sp_ls.add_argument("--output", default=None, help="输出目录路径")
    sp_ls.add_argument(
        "--drafting-profile",
        default=None,
        choices=(
            "china_coursework_general",
            "china_residential_site",
            "china_territorial_spatial_review",
        ),
        help="使用内置中国规划制图辅助模板并生成一致性检查报告",
    )
    sp_ls.set_defaults(func=cmd_layer_standardize)

    # ─── gis ───
    sp_gis = subparsers.add_parser("gis", help="GIS-CAD 数据桥梁")
    gis_sub = sp_gis.add_subparsers(dest="gis_action", title="GIS 操作", metavar="<操作>")

    sp_ge = gis_sub.add_parser("export", help="导出 CAD 地块至 GeoJSON")
    sp_ge.add_argument("--dxf", required=True, help="输入 DXF 文件路径")
    sp_ge.add_argument("--config", default=None, help="YAML 配置文件路径")
    sp_ge.add_argument("--output", default="output", help="输出目录路径")
    sp_ge.set_defaults(func=cmd_gis_export)

    sp_gi = gis_sub.add_parser("import", help="导入 GeoJSON 至 CAD DXF")
    sp_gi.add_argument("--geojson", required=True, help="输入 GeoJSON 文件路径")
    sp_gi.add_argument("--output", default="output", help="输出目录路径")
    sp_gi.add_argument("--unit", default=None, help="输出 DXF 的单位（例如 m、cm、mm）；未指定则保留为未知单位")
    sp_gi.set_defaults(func=cmd_gis_import)

    # ─── batch ───
    sp_batch = subparsers.add_parser("batch", help="批量分析文件夹中的 DXF 图纸")
    sp_batch.add_argument("--input", required=True, help="包含 DXF 文件的输入文件夹")
    sp_batch.add_argument(
        "--task",
        choices=["parcel", "indicator"],
        default="parcel",
        help="批量任务类型：parcel 或 indicator",
    )
    sp_batch.add_argument("--floors", type=float, default=None, help="指标任务必须填写楼层倍数")
    sp_batch.add_argument("--config", default=None, help="YAML 配置文件路径")
    sp_batch.add_argument("--output", default="output/batch", help="汇总输出文件夹")
    sp_batch.set_defaults(func=cmd_batch)

    # ─── concept ───
    sp_concept = subparsers.add_parser("concept", help="生成参数化的概念方案 CAD 草图")
    sp_concept.add_argument("--dxf", required=True, help="包含 PARCEL 地块的输入 DXF")
    sp_concept.add_argument("--output", default="output/concept", help="输出目录")
    sp_concept.add_argument("--buildings", type=int, default=1, help="每个地块的概念建筑数量")
    sp_concept.add_argument("--coverage", type=float, default=25.0, help="概念建筑覆盖率百分比")
    sp_concept.add_argument("--setback", type=float, default=5.0, help="建筑退线距离（米）")
    sp_concept.add_argument("--building-gap", type=float, default=0.0, help="概念建筑最小间距（米）")
    sp_concept.add_argument("--access-width", type=float, default=0.0, help="概念道路/消防通道宽度（米）")
    sp_concept.add_argument(
        "--layout-style",
        choices=("organic", "rectilinear"),
        default="organic",
        help="布局风格：organic=圆角曲线（推荐），rectilinear=简洁矩形",
    )
    sp_concept.add_argument(
        "--standards-profile",
        choices=["custom_local", "residential_national_framework", "civil_building_national_framework"],
        default="custom_local",
        help="规范依据框架；仅作为核对索引，不替代地方条件和正式标准文本",
    )
    sp_concept.add_argument("--floors", type=int, default=None, help="概念建筑楼层数；用于估算总建筑面积")
    sp_concept.add_argument("--parking-ratio", type=float, default=None, help="概念停车配比（个/1000m²），需同时指定 --floors")
    sp_concept.add_argument("--parcel-layer", default="PARCEL", help="地块图层名称")
    sp_concept.add_argument("--fallback-unit", default=None, help="DXF 单位未知时的明确回退单位，例如 m")
    sp_concept.set_defaults(func=cmd_concept_plan)

    # ─── rules ───
    sp_rules = subparsers.add_parser("rules", help="规划条件模板")
    rules_sub = sp_rules.add_subparsers(dest="rules_action", title="模板操作", metavar="<操作>")

    sp_rules_list = rules_sub.add_parser("list", help="列出内置规划条件模板")
    sp_rules_list.set_defaults(func=cmd_rules_list)

    # ─── indicator ───
    sp_ind = subparsers.add_parser("indicator", help="规划指标自动核算 (FAR, 密度, 绿地率)")
    sp_ind.add_argument("--dxf", default=None, help="输入 DXF 文件路径")
    sp_ind.add_argument("--config", default=None, help="YAML 配置文件路径")
    sp_ind.add_argument("--site-area", type=float, default=None, help="手动输入用地面积 (m²)")
    sp_ind.add_argument("--building-footprint", type=float, default=0.0, help="建筑基底面积 (m²)")
    sp_ind.add_argument("--total-building", type=float, default=0.0, help="总建筑面积 (m²)")
    sp_ind.add_argument("--green-area", type=float, default=0.0, help="绿地面积 (m²)")
    sp_ind.add_argument("--output", default="output", help="输出目录路径")
    sp_ind.add_argument("--floors", type=float, default=None, help="DXF 建筑总面积的楼层倍数（必须明确指定）")
    sp_ind.set_defaults(func=cmd_indicator)

    # ─── validate ───
    sp_val = subparsers.add_parser("validate", help="拓扑与退线规则检查")
    sp_val.add_argument("--dxf", required=True, help="输入 DXF 文件路径")
    sp_val.add_argument("--setback", type=float, default=5.0, help="建筑退线距离 (米, 默认: 5.0)")
    sp_val.add_argument("--parcel-layer", default="PARCEL", help="地块图层名称 (默认: PARCEL)")
    sp_val.add_argument("--building-layer", default="BUILDING", help="建筑图层名称 (默认: BUILDING)")
    sp_val.add_argument("--output", default="output", help="输出目录路径")
    sp_val.add_argument("--config", default=None, help="YAML 配置（可提供 fallback_unit）")
    sp_val.add_argument("--fallback-unit", default=None, help="DXF 未声明单位时采用的单位，例如 m、cm、mm")
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
