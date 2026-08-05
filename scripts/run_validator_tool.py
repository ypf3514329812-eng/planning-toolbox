"""Planning Toolbox — 规则与拓扑检查工具 (拓扑审计 + 建筑退线合规检查)"""
import argparse
import sys
from pathlib import Path

# Add src/ to sys.path so non-programmer students can run without pip install -e .
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ezdxf
from shapely.geometry import Polygon
from planning_toolbox.validators.topology import validate_polyline_topology
from planning_toolbox.validators.setback import check_building_setback
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry

def main():
    parser = argparse.ArgumentParser(
        description="Planning Toolbox — 规则与拓扑检查工具 (自交、未闭合、退线规范检查)"
    )
    parser.add_argument("--dxf", help="待检查的 CAD DXF 文件路径")
    parser.add_argument("--setback", type=float, default=5.0,
                        help="建筑退线要求距离（米），默认: 5.0m")
    parser.add_argument("--parcel-layer", default="PARCEL",
                        help="地块图层名称 (默认: PARCEL)")
    parser.add_argument("--building-layer", default="BUILDING",
                        help="建筑图层名称 (默认: BUILDING)")
    parser.add_argument("--output", default="output",
                        help="输出目录路径 (默认: output)")

    args = parser.parse_args()

    if not args.dxf:
        parser.print_help()
        sys.exit(1)

    dxf_path = Path(args.dxf)
    print(f"[拓扑检查工具] 正在检查 CAD 文件: {dxf_path}")

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # === 1. Topology Audit ===
    topology_results = []
    for idx, entity in enumerate(msp):
        if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
            res = validate_polyline_topology(entity, idx)
            topology_results.append(res)

    valid_count = sum(1 for r in topology_results if r.status == "VALID")
    open_count = sum(1 for r in topology_results if r.status == "OPEN")
    invalid_count = sum(1 for r in topology_results if r.status == "INVALID_GEOMETRY")

    print("\n==========================================")
    print("   CAD 拓扑检查结果")
    print("==========================================")
    print(f"扫描多段线总数:     {len(topology_results)}")
    print(f"有效闭合边界:       {valid_count}")
    print(f"未闭合边界:         {open_count}")
    print(f"自交/无效几何:      {invalid_count}")
    print("==========================================")

    # === 2. Building Setback Compliance Check ===
    parcel_layer_upper = args.parcel_layer.upper()
    building_layer_upper = args.building_layer.upper()

    parcel_polygons = []
    building_polygons = []

    for entity in msp:
        if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
            continue
        layer_upper = str(entity.dxf.layer).upper()
        pts, is_closed, _ = points_from_dxf_polyline(entity)
        status, poly, _ = parse_parcel_geometry(pts, is_closed)
        if status == "VALID" and poly:
            if layer_upper == parcel_layer_upper:
                parcel_polygons.append(poly)
            elif layer_upper == building_layer_upper:
                building_polygons.append(poly)

    print(f"\n==========================================")
    print(f"   建筑退线合规检查 (退线要求: {args.setback}m)")
    print(f"==========================================")

    if not parcel_polygons:
        print(f"  未检测到 '{args.parcel_layer}' 图层地块。")
        print("==========================================\n")
        return

    if not building_polygons:
        print(f"  未检测到 '{args.building_layer}' 图层建筑。")
        print(f"  状态: NO_BUILDING — 无建筑基底可检查。")
        print("==========================================\n")
        return

    for idx, parcel_poly in enumerate(parcel_polygons, start=1):
        pid = f"P{idx:03d}"
        result = check_building_setback(
            parcel_polygon=parcel_poly,
            building_polygons=building_polygons,
            required_setback_m=args.setback,
            parcel_id=pid
        )
        status_cn = {
            "COMPLIANT": "✓ 合规",
            "VIOLATION": "✗ 违规",
            "NO_BUILDING": "— 无建筑"
        }.get(result.status, result.status)

        print(f"  [{pid}] {status_cn}")
        if result.status == "VIOLATION":
            print(f"         违规建筑数: {result.violations_count}")
            print(f"         最近距离: {result.min_distance_m:.2f}m (要求 ≥ {args.setback}m)")
        elif result.status == "COMPLIANT":
            print(f"         最近距离: {result.min_distance_m:.2f}m")

    print("==========================================\n")


if __name__ == "__main__":
    main()
