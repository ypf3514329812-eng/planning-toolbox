import argparse
import sys
from pathlib import Path

# Add src/ to sys.path so non-programmer students can run without pip install -e .
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from planning_toolbox.gis.io.exporter import export_parcels_to_geojson
from planning_toolbox.gis.io.importer import import_geojson_to_dxf
from planning_toolbox.cad.parcels.calculator import process_parcels
from planning_toolbox.config import load_config

def main():
    parser = argparse.ArgumentParser(
        description="Planning Toolbox — GIS ↔ CAD Data Bridge (GeoJSON Export & Import)"
    )
    parser.add_argument("--export-geojson", help="Path to input CAD DXF file to export to GeoJSON")
    parser.add_argument("--import-geojson", help="Path to input GeoJSON file to import into CAD DXF")
    parser.add_argument("--output", default="output", help="Output directory path (default: output)")
    parser.add_argument("--config", default=None, help="Path to custom YAML configuration file")

    args = parser.parse_args()

    if not args.export_geojson and not args.import_geojson:
        parser.print_help()
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.export_geojson:
        dxf_path = Path(args.export_geojson)
        print(f"[GIS Bridge] Processing CAD file: {dxf_path}")
        cfg = load_config(args.config)
        parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, cfg, out_dir)
        geojson_file = out_dir / f"{dxf_path.stem}.geojson"
        print("\n==========================================")
        print("   GIS GeoJSON Export Completed")
        print("==========================================")
        print(f"Source DXF:     {dxf_path}")
        print(f"GeoJSON Output: {geojson_file}")
        print(f"Total Parcels:  {len(parcels)}")
        print("==========================================\n")

    if args.import_geojson:
        geojson_path = Path(args.import_geojson)
        print(f"[GIS Bridge] Importing GeoJSON file: {geojson_path}")
        out_dxf = out_dir / f"{geojson_path.stem}_from_gis.dxf"
        res_dxf, stats = import_geojson_to_dxf(geojson_path, out_dxf)
        print("\n==========================================")
        print("   GIS GeoJSON 导入至 CAD 完成")
        print("==========================================")
        print(f"源 GeoJSON 文件:     {geojson_path}")
        print(f"输出 CAD DXF:        {res_dxf}")
        print(f"导入多边形数:        {stats['imported_polygons']}")
        if stats['skipped_unsupported'] > 0 or stats['skipped_errors'] > 0:
            print(f"跳过（不支持类型）:  {stats['skipped_unsupported']}")
            print(f"跳过（解析错误）:    {stats['skipped_errors']}")
        print("==========================================\n")

if __name__ == "__main__":
    main()
