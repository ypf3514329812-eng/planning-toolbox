"""Create a small real-SketchUp scene containing the new planning components."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from planning_toolbox.project.chain_manifest import CRSDefinition, LocalOrigin, new_chain_manifest
from planning_toolbox.sketchup import build_sketchup_extension, export_sketchup_handoff


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "test_artifacts" / "native_component_runtime_v058"
DXF_PATH = OUTPUT_DIR / "native_component_validation.dxf"
HANDOFF_PATH = OUTPUT_DIR / "native_component_validation.ptsu.json"
PLUGIN_PATH = OUTPUT_DIR / "PlanningToolbox_SketchUp_Importer.rbz"
ORIGIN = (500000.0, 3400000.0)


def create_scene() -> dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    for name in ("PARCEL", "BUILDING", "ROAD", "GREEN", "PARKING"):
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(ORIGIN[0] - 8, ORIGIN[1] - 8), (ORIGIN[0] + 82, ORIGIN[1] - 8),
         (ORIGIN[0] + 82, ORIGIN[1] + 62), (ORIGIN[0] - 8, ORIGIN[1] + 62)],
        close=True, dxfattribs={"layer": "PARCEL"}
    )
    msp.add_lwpolyline(
        [(ORIGIN[0], ORIGIN[1] + 8), (ORIGIN[0] + 74, ORIGIN[1] + 8),
         (ORIGIN[0] + 74, ORIGIN[1] + 14), (ORIGIN[0], ORIGIN[1] + 14)],
        close=True, dxfattribs={"layer": "ROAD"}
    )
    msp.add_lwpolyline(
        [(ORIGIN[0] + 12, ORIGIN[1] + 26), (ORIGIN[0] + 30, ORIGIN[1] + 26),
         (ORIGIN[0] + 30, ORIGIN[1] + 42), (ORIGIN[0] + 12, ORIGIN[1] + 42)],
        close=True, dxfattribs={"layer": "BUILDING"}
    )

    symbols = {
        "PT_PARKED_CAR": ("PARKING", 8),
        "PT_BENCH": ("GREEN", 12),
        "PT_SHRUB_CLUSTER": ("GREEN", 16),
        "PT_BOLLARD": ("ROAD", 20),
        "PT_BUS_SHELTER": ("ROAD", 24),
    }
    for name, (layer, radius) in symbols.items():
        block = doc.blocks.new(name)
        block.add_circle((0, 0), radius=max(0.2, radius / 10))
        msp.add_blockref(
            name,
            (ORIGIN[0] + radius, ORIGIN[1] + 18),
            dxfattribs={"layer": layer},
        )
    doc.saveas(DXF_PATH)

    manifest = new_chain_manifest("原生规划组件 SketchUp 真机验收", "residential").with_updates(
        crs=CRSDefinition(name="Local metric component validation", kind="local").to_dict(),
        cad_unit="m",
        local_origin=LocalOrigin(enabled=True, easting=ORIGIN[0], northing=ORIGIN[1]).to_dict(),
    )
    result = export_sketchup_handoff(
        DXF_PATH,
        HANDOFF_PATH,
        manifest,
        floors=0,
        floor_height_m=0.0,
        building_layers="BUILDING",
        include_open_linework=True,
        include_blocks=True,
        include_faces=True,
        model_detail_level="presentation",
        road_design_preset="basic",
        incremental_update=True,
    )
    plugin = build_sketchup_extension(PLUGIN_PATH)
    return {**result, "plugin_file": plugin["path"], "plugin_sha256": plugin["sha256"]}


if __name__ == "__main__":
    result = create_scene()
    print(f"HANDOFF={HANDOFF_PATH}")
    print(f"PLUGIN={result['plugin_file']}")
    print(f"EXPLICIT_COMPONENTS={result['explicit_library_symbol_count']}")
