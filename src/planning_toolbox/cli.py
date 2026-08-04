import argparse
import sys
from pathlib import Path
from planning_toolbox import __version__
from planning_toolbox.config import load_config
from planning_toolbox.cad.parcels.calculator import process_parcels
from planning_toolbox.utils.logger import setup_logger

logger = setup_logger()

def main():
    parser = argparse.ArgumentParser(
        description="Planning Toolbox - 城乡规划 CAD–GIS 自动化辅助工具箱"
    )
    parser.add_argument("--version", action="version", version=f"Planning Toolbox v{__version__}")
    parser.add_argument("--dxf", required=True, help="Path to input DXF file")
    parser.add_argument("--config", default=None, help="Path to YAML configuration file")
    parser.add_argument("--output", default=None, help="Output directory path")
    parser.add_argument("--verbose", action="store_true", help="Show detailed debug output")

    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.getLogger("planning_toolbox").setLevel(logging.DEBUG)

    try:
        cfg = load_config(args.config)
        dxf_path = Path(args.dxf)

        logger.info(f"Processing DXF file: {dxf_path}")
        parcels, labeled_dxf, csv_file, report_file = process_parcels(
            dxf_path=dxf_path,
            config=cfg,
            output_dir=args.output
        )

        valid_count = sum(1 for p in parcels if p.status == "VALID")
        total_ha = sum(p.area_ha for p in parcels if p.status == "VALID")
        error_count = sum(1 for p in parcels if p.status != "VALID")

        logger.info(f"Successfully processed parcels.")
        print("\n==========================================")
        print("    Planning Toolbox Task Completed")
        print("==========================================")
        print(f"Total Candidate Entities: {len(parcels)}")
        print(f"Valid Closed Parcels:     {valid_count}")
        if error_count > 0:
            print(f"Errors/Warnings:          {error_count}")
        print(f"Total Valid Area:         {total_ha:.4f} ha")
        print("------------------------------------------")
        print(f"Labeled DXF Output:       {labeled_dxf}")
        print(f"CSV Summary Output:       {csv_file}")
        print(f"Detailed Report Output:   {report_file}")
        print("==========================================\n")

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
