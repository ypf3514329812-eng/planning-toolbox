"""Create a deterministic centerline-to-road-corridor scene for SketchUp validation."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from planning_toolbox.project.chain_manifest import (
    CRSDefinition,
    LocalOrigin,
    new_chain_manifest,
)
from planning_toolbox.sketchup import build_sketchup_extension, export_sketchup_handoff


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "sketchup_validation_v030_centerline_corridor"
DXF_PATH = OUTPUT_DIR / "centerline_corridor_validation.dxf"
HANDOFF_PATH = OUTPUT_DIR / "centerline_corridor_validation.ptsu.json"
PLUGIN_PATH = OUTPUT_DIR / "PlanningToolbox_SketchUp_Importer.rbz"
ORIGIN = (500000.0, 3400000.0)


def create_scene() -> dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    for name in ("ROAD_CENTERLINE", "GREEN"):
        doc.layers.add(name)
    msp = doc.modelspace()
    # This is intentionally an axis-only ARC.  The opt-in exporter must build
    # the editable conceptual carriageway from local tangent frames rather
    # than treating the ARC as a flat source face.
    msp.add_arc(
        (ORIGIN[0] + 30.0, ORIGIN[1] + 30.0),
        24.0,
        20.0,
        160.0,
        dxfattribs={"layer": "ROAD_CENTERLINE"},
    )

    crossing = doc.blocks.new("PT_CROSSWALK")
    crossing.add_lwpolyline(
        [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
        close=True,
    )
    # The crossing sits on the north side of the arc so the importer must use
    # the centerline's local tangent when orienting the reusable component.
    msp.add_blockref(
        "PT_CROSSWALK",
        (ORIGIN[0] + 30.0, ORIGIN[1] + 54.0),
        dxfattribs={"layer": "GREEN"},
    )
    doc.saveas(DXF_PATH)

    manifest = new_chain_manifest(
        "中心线概念道路带 SketchUp 真机验收",
        "residential",
    ).with_updates(
        crs=CRSDefinition(name="Local metric centerline validation", kind="local").to_dict(),
        cad_unit="m",
        local_origin=LocalOrigin(
            enabled=True,
            easting=ORIGIN[0],
            northing=ORIGIN[1],
        ).to_dict(),
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
        road_design_preset="complete",
        incremental_update=True,
        centerline_corridor=True,
        centerline_width_m=12.0,
    )
    plugin = build_sketchup_extension(PLUGIN_PATH)
    return {**result, "plugin_file": plugin["path"], "plugin_sha256": plugin["sha256"]}


if __name__ == "__main__":
    result = create_scene()
    print(f"DXF={DXF_PATH}")
    print(f"HANDOFF={HANDOFF_PATH}")
    print(f"PLUGIN={PLUGIN_PATH}")
    print(f"CENTERLINE_CORRIDOR_HINTS={result['road_centerline_corridor_hint_count']}")
    print(f"CROSSWALK_LOCAL_TANGENTS={result['road_crossing_local_tangent_count']}")
