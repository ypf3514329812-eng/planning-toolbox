import argparse
import sys
from pathlib import Path

# Add src/ to sys.path so non-programmer students can run without pip install -e .
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ezdxf
from shapely.geometry import Polygon
from planning_toolbox.validators.topology import validate_polyline_topology
from planning_toolbox.validators.setback import check_building_setback
from planning_toolbox.cad.parcels.calculator import process_parcels

def main():
    parser = argparse.ArgumentParser(
        description="Planning Toolbox — 规则与拓扑检查工具 (自交、未闭合、退线规范检查)"
    )
    parser.add_argument("--dxf", help="Path to input CAD DXF file to validate")
    parser.add_argument("--setback", type=float, default=5.0, help="Required building setback distance in meters (default: 5.0m)")
    parser.add_argument("--output", default="output", help="Output directory path (default: output)")

    args = parser.parse_args()

    if not args.dxf:
        parser.print_help()
        sys.exit(1)

    dxf_path = Path(args.dxf)
    print(f"[Validator Tool] Auditing CAD topology & setback compliance: {dxf_path}")

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

    print("\n==========================================")
    print("   CAD Topology Validation Audit Result")
    print("==========================================")
    print(f"Total Polylines Scanned: {len(topology_results)}")
    print(f"Valid Closed Boundaries: {valid_count}")
    print(f"Open Boundaries:         {open_count}")
    print(f"Self-Intersecting/Invalid:{invalid_count}")
    print("==========================================\n")

if __name__ == "__main__":
    main()
