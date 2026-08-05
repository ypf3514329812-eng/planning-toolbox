import argparse
import sys
from pathlib import Path

# Add src/ to sys.path so non-programmer students can run without pip install -e .
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from planning_toolbox.indicators.calculator import process_dxf_indicators, calculate_parcel_indicators

def main():
    parser = argparse.ArgumentParser(
        description="Planning Toolbox — 规划指标计算工具 (FAR 容积率, 建筑密度 %, 绿地率 %)"
    )
    parser.add_argument("--dxf", help="Path to input CAD DXF file containing PARCEL, BUILDING, GREEN layers")
    parser.add_argument("--site-area", type=float, help="Manual site area in m² (for single parcel query)")
    parser.add_argument("--building-footprint", type=float, default=0.0, help="Manual building footprint area in m²")
    parser.add_argument("--total-building", type=float, default=0.0, help="Manual total building floor area in m²")
    parser.add_argument("--green-area", type=float, default=0.0, help="Manual green area in m²")
    parser.add_argument("--output", default="output", help="Output directory path (default: output)")

    parser.add_argument("--floors", type=float, default=None,
                        help="DXF 建筑总面积的楼层倍数（必须明确指定）")

    args = parser.parse_args()

    if args.site_area is not None:
        ind = calculate_parcel_indicators(
            parcel_id="P001",
            site_area_m2=args.site_area,
            building_footprint_m2=args.building_footprint,
            total_building_m2=args.total_building,
            green_area_m2=args.green_area
        )
        print("\n==========================================")
        print("   Planning Parcel Indicators Result")
        print("==========================================")
        print(f"用地面积 (Site Area):         {ind.site_area_m2:,.2f} m² ({ind.site_area_ha:.4f} ha)")
        print(f"建筑基底 (Footprint Area):    {ind.building_footprint_m2:,.2f} m²")
        print(f"总建筑面积 (Total Floor):      {ind.total_building_m2:,.2f} m²")
        print(f"绿地面积 (Green Area):        {ind.green_area_m2:,.2f} m²")
        print("------------------------------------------")
        print(f"容积率 (FAR):                 {ind.far:.2f}")
        print(f"建筑密度 (Building Density):  {ind.building_density_pct:.2f}%")
        print(f"绿地率 (Green Ratio):         {ind.green_ratio_pct:.2f}%")
        print("==========================================\n")
        return

    if args.dxf:
        dxf_path = Path(args.dxf)
        print(f"[Indicators Tool] Analyzing CAD DXF indicators: {dxf_path}")
        config = {"default_floors": args.floors} if args.floors is not None else None
        results, csv_file, report_file = process_dxf_indicators(
            dxf_path, config=config, output_dir=args.output
        )
        print("\n==========================================")
        print("   Planning Indicators DXF Analysis Done")
        print("==========================================")
        print(f"Source DXF:        {dxf_path}")
        print(f"Parcels Processed: {len(results)}")
        print(f"CSV Report Output: {csv_file}")
        print(f"Text Report Output:{report_file}")
        print("==========================================\n")
        return

    parser.print_help()

if __name__ == "__main__":
    main()
