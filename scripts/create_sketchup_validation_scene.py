"""Create a deterministic local scene for real SketchUp extension validation."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from planning_toolbox.project.chain_manifest import CRSDefinition, new_chain_manifest
from planning_toolbox.sketchup import (
    build_sketchup_extension,
    export_sketchup_handoff,
    inspect_sketchup_buildings,
)


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output" / "sketchup_validation_v026"
DXF_PATH = OUTPUT_DIR / "planning_toolbox_su_validation.dxf"
HANDOFF_PATH = OUTPUT_DIR / "planning_toolbox_su_validation.ptsu.json"
PLUGIN_PATH = OUTPUT_DIR / "PlanningToolbox_SketchUp_Importer.rbz"


def create_scene() -> dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    layer_colors = {
        "PARCEL": 1,
        "BUILDING": 7,
        "ROAD": 8,
        "GREEN": 3,
        "PARKING": 4,
        "WATER": 5,
        "LABEL": 2,
    }
    for name, color in layer_colors.items():
        doc.layers.add(name, color=color)
    modelspace = doc.modelspace()
    tree = doc.blocks.new("PT_TREE")
    tree.add_circle((0, 0), 1.5, dxfattribs={"layer": "0"})
    planter = doc.blocks.new("PT_PLANTER")
    planter.add_circle((0, 0), 0.55, dxfattribs={"layer": "0"})
    parasol = doc.blocks.new("PT_PARASOL")
    parasol.add_circle((0, 0), 1.2, dxfattribs={"layer": "0"})
    crossing = doc.blocks.new("PT_CROSSWALK")
    crossing.add_lwpolyline(
        [(-1, -1), (1, -1), (1, 1), (-1, 1)],
        close=True,
        dxfattribs={"layer": "0"},
    )
    traffic_light = doc.blocks.new("PT_TRAFFIC_LIGHT")
    traffic_light.add_circle((0, 0), 0.25, dxfattribs={"layer": "0"})
    modelspace.add_lwpolyline(
        [(0, 0), (100, 0), (100, 90), (0, 90)],
        close=True,
        dxfattribs={"layer": "PARCEL"},
    )
    for points in (
        [(10, 10), (30, 10), (30, 25), (10, 25)],
        [(40, 10), (70, 10), (70, 25), (40, 25)],
        [(10, 40), (35, 40), (35, 55), (10, 55)],
        [(48, 38), (75, 38), (75, 58), (48, 58)],
    ):
        modelspace.add_lwpolyline(
            points, close=True, dxfattribs={"layer": "BUILDING"}
        )
    modelspace.add_lwpolyline(
        [(4, 29), (84, 29), (84, 35), (4, 35)],
        close=True,
        dxfattribs={"layer": "ROAD"},
    )
    modelspace.add_lwpolyline(
        [(37, 5), (37, 64)], dxfattribs={"layer": "ROAD"}
    )
    modelspace.add_lwpolyline(
        [(4, 70), (94, 70), (94, 82), (4, 82)],
        close=True,
        dxfattribs={"layer": "ROAD"},
    )
    modelspace.add_circle((20, 32), 4.5, dxfattribs={"layer": "GREEN"})
    modelspace.add_circle((67, 32), 4.5, dxfattribs={"layer": "GREEN"})
    modelspace.add_lwpolyline(
        [(4, 66), (94, 66), (94, 68), (4, 68)],
        close=True,
        dxfattribs={"layer": "WATER"},
    )
    for x, y in ((6, 6), (34, 8), (78, 8), (8, 58), (42, 61), (80, 59)):
        modelspace.add_blockref("PT_TREE", (x, y), dxfattribs={"layer": "GREEN"})
    modelspace.add_blockref("PT_PLANTER", (43, 32), dxfattribs={"layer": "GREEN"})
    modelspace.add_blockref("PT_PARASOL", (73, 32), dxfattribs={"layer": "GREEN"})
    modelspace.add_blockref("PT_CROSSWALK", (50, 76), dxfattribs={"layer": "ROAD"})
    modelspace.add_blockref("PT_TRAFFIC_LIGHT", (45, 70.9), dxfattribs={"layer": "ROAD"})
    modelspace.add_blockref(
        "PT_TRAFFIC_LIGHT", (55, 81.1), dxfattribs={"layer": "ROAD", "rotation": 180}
    )
    for index in range(6):
        x0 = 6 + index * 5.5
        modelspace.add_lwpolyline(
            [(x0, 62), (x0 + 5, 62), (x0 + 5, 64.5), (x0, 64.5)],
            close=True,
            dxfattribs={"layer": "PARKING"},
        )
    modelspace.add_text(
        "Planning Toolbox v0.26 SketchUp Road Validation",
        dxfattribs={"layer": "LABEL", "height": 1.5},
    ).set_placement((3, 87))
    doc.saveas(DXF_PATH)

    manifest = new_chain_manifest(
        "Planning Toolbox SketchUp 真实验收", "residential"
    ).with_updates(
        crs=CRSDefinition(
            name="Local metric validation scene",
            kind="local",
            linear_unit="m",
        ).to_dict(),
        cad_unit="m",
    )
    catalog = inspect_sketchup_buildings(DXF_PATH, manifest, "BUILDING")
    buildings = catalog["buildings"]
    if len(buildings) != 4:
        raise RuntimeError(f"验收场景应包含 4 栋建筑，实际为 {len(buildings)} 栋。")
    overrides = {
        buildings[0]["object_id"]: {
            **buildings[0],
            "floors": 4,
            "floor_height_m": 3.0,
            "building_type": "residential",
            "roof_type": "flat",
            "model_detail_level": "presentation",
        },
        buildings[1]["object_id"]: {
            **buildings[1],
            "floors": 10,
            "floor_height_m": 3.6,
            "building_type": "office",
            "roof_type": "gable",
            "model_detail_level": "presentation",
        },
        buildings[2]["object_id"]: {
            **buildings[2],
            "floors": 2,
            "floor_height_m": 4.5,
            "building_type": "commercial",
            "roof_type": "flat",
            "model_detail_level": "course",
        },
        buildings[3]["object_id"]: {
            **buildings[3],
            "floors": 6,
            "floor_height_m": 3.6,
            "building_type": "campus",
            "roof_type": "hip",
            "model_detail_level": "presentation",
        },
    }
    result = export_sketchup_handoff(
        DXF_PATH,
        HANDOFF_PATH,
        manifest,
        floors=4,
        floor_height_m=3.0,
        building_layers="BUILDING",
        include_open_linework=True,
        include_blocks=True,
        include_faces=True,
        include_text=True,
        model_detail_level="presentation",
        road_design_preset="complete",
        building_type="residential",
        roof_type="flat",
        incremental_update=True,
        building_overrides=overrides,
    )
    plugin = build_sketchup_extension(PLUGIN_PATH)
    return {
        **result,
        "plugin_file": plugin["path"],
        "plugin_sha256": plugin["sha256"],
    }


if __name__ == "__main__":
    scene = create_scene()
    print(f"DXF={DXF_PATH}")
    print(f"HANDOFF={scene['handoff_file']}")
    print(f"PLUGIN={scene['plugin_file']}")
    print(
        "BUILDINGS="
        f"{scene['building_count']}; EXTRUDED={scene['extruded_building_count']}; "
        f"OVERRIDES={scene['matched_building_override_count']}"
    )
