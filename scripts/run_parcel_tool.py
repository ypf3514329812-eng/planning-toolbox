#!/usr/bin/env python3
"""
User-facing script to run the parcel area calculation and labeling tool.
Can be executed directly by non-programmer users:
  python scripts/run_parcel_tool.py --dxf sample_data/sample_parcels.dxf
"""
import sys
from pathlib import Path

# Add src to sys.path so the package can be imported directly
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from planning_toolbox.cli import main

if __name__ == "__main__":
    # Preserve the pre-v0.6 invocation:
    #   python scripts/run_parcel_tool.py --dxf input.dxf
    # while delegating all calculation behavior to the unified CLI.
    sys.argv[1:1] = ["parcel"]
    main()
