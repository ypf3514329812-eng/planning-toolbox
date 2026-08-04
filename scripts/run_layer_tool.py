#!/usr/bin/env python3
"""
User-facing script for non-programmer users to run CAD layer tools:
- Create blank CAD template:
    python scripts/run_layer_tool.py --create-template
- Standardize layers in an existing DXF:
    python scripts/run_layer_tool.py --dxf sample_data/sample_parcels.dxf --standardize-layers
"""
import sys
from pathlib import Path

# Add src directory to sys.path
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from planning_toolbox.cli import main

if __name__ == "__main__":
    main()
