"""Create a small, deterministic curved-road scene for real SketchUp validation."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from planning_toolbox.project.chain_manifest import (
    CRSDefinition,
    LocalOrigin,
    new_chain_manifest,
)
from planning_toolbox.sketchup import build_sketchup_extension, export_sketchup_handoff


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "sketchup_validation_v028_curved_lights"
DXF_PATH = OUTPUT_DIR / "curved_road_validation.dxf"
HANDOFF_PATH = OUTPUT_DIR / "curved_road_validation.ptsu.json"
PLUGIN_PATH = OUTPUT_DIR / "PlanningToolbox_SketchUp_Importer.rbz"
ORIGIN = (500000.0, 3400000.0)


def curved_road_strip(width: float = 12.0) -> list[tuple[float, float]]:
    centerline = [(0.0, 0.0), (20.0, 0.0), (38.0, 8.0), (52.0, 24.0)]
    half_width = width / 2.0
    left: list[tuple[float, float]] = []
    right: list[tuple[float, float]] = []
    for index, (x, y) in enumerate(centerline):
        if index == 0:
            dx, dy = centerline[1][0] - x, centerline[1][1] - y
        elif index == len(centerline) - 1:
            dx, dy = x - centerline[index - 1][0], y - centerline[index - 1][1]
        else:
            dx = centerline[index + 1][0] - centerline[index - 1][0]
            dy = centerline[index + 1][1] - centerline[index - 1][1]
        length = math.hypot(dx, dy)
        normal = (-dy / length, dx / length)
        left.append(
            (ORIGIN[0] + x + normal[0] * half_width, ORIGIN[1] + y + normal[1] * half_width)
        )
        right.append(
            (ORIGIN[0] + x - normal[0] * half_width, ORIGIN[1] + y - normal[1] * half_width)
        )
    return left + list(reversed(right))


def create_scene() -> dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    for name in ("PARCEL", "BUILDING", "ROAD", "GREEN"):
        doc.layers.add(name)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [
            (ORIGIN[0] - 8, ORIGIN[1] - 10),
            (ORIGIN[0] + 78, ORIGIN[1] - 10),
            (ORIGIN[0] + 78, ORIGIN[1] + 68),
            (ORIGIN[0] - 8, ORIGIN[1] + 68),
        ],
        close=True,
        dxfattribs={"layer": "PARCEL"},
    )
    msp.add_lwpolyline(curved_road_strip(), close=True, dxfattribs={"layer": "ROAD"})
    msp.add_lwpolyline(
        [
            (ORIGIN[0] + 58, ORIGIN[1] + 42),
            (ORIGIN[0] + 72, ORIGIN[1] + 42),
            (ORIGIN[0] + 72, ORIGIN[1] + 56),
            (ORIGIN[0] + 58, ORIGIN[1] + 56),
        ],
        close=True,
        dxfattribs={"layer": "BUILDING"},
    )
    msp.add_circle((ORIGIN[0] + 64, ORIGIN[1] + 28), 4.0, dxfattribs={"layer": "GREEN"})

    crossing = doc.blocks.new("PT_CROSSWALK")
    crossing.add_lwpolyline(
        [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
        close=True,
    )
    msp.add_blockref(
        "PT_CROSSWALK",
        (ORIGIN[0] + 20.0, ORIGIN[1]),
        dxfattribs={"layer": "ROAD", "rotation": 11.0},
    )
    doc.saveas(DXF_PATH)

    manifest = new_chain_manifest("弯道道路 SketchUp 真机验收", "residential").with_updates(
        crs=CRSDefinition(name="Local metric curved-road validation", kind="local").to_dict(),
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
    )
    plugin = build_sketchup_extension(PLUGIN_PATH)
    return {**result, "plugin_file": plugin["path"], "plugin_sha256": plugin["sha256"]}


if __name__ == "__main__":
    result = create_scene()
    print(f"DXF={DXF_PATH}")
    print(f"HANDOFF={HANDOFF_PATH}")
    print(f"PLUGIN={PLUGIN_PATH}")
    print(f"CURVED_HINTS={result['road_curved_hint_count']}")
    print(f"CROSSWALK_LOCAL_TANGENTS={result['road_crossing_local_tangent_count']}")
