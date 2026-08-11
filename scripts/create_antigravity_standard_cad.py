"""Create a clean, metric, multi-layer CAD test scene for Antigravity MCP."""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from planning_toolbox.project.chain_manifest import CRSDefinition, new_chain_manifest
from planning_toolbox.sketchup import export_sketchup_handoff, inspect_sketchup_buildings


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "test_artifacts" / "antigravity_mcp_acceptance_v058"
DXF_PATH = OUTPUT_DIR / "standard_site_plan.dxf"
HANDOFF_PATH = OUTPUT_DIR / "standard_site_plan.ptsu.json"
SUMMARY_PATH = OUTPUT_DIR / "standard_site_plan_summary.json"


def add_rect(msp, layer: str, x0: float, y0: float, x1: float, y1: float) -> None:
    msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        close=True,
        dxfattribs={"layer": layer},
    )


def add_tree_block(doc) -> None:
    block = doc.blocks.new("PT_TREE")
    block.add_circle((0, 0), 1.5, dxfattribs={"layer": "0"})
    block.add_circle((0, 0), 0.35, dxfattribs={"layer": "0"})


def add_crosswalk_block(doc) -> None:
    block = doc.blocks.new("PT_CROSSWALK")
    for index in range(7):
        x0 = -3.6 + index * 1.2
        block.add_lwpolyline(
            [(x0, -3.0), (x0 + 0.65, -3.0), (x0 + 0.65, 3.0), (x0, 3.0)],
            close=True,
            dxfattribs={"layer": "0"},
        )


def add_simple_block(doc, name: str, width: float, depth: float) -> None:
    block = doc.blocks.new(name)
    block.add_lwpolyline(
        [
            (-width / 2, -depth / 2),
            (width / 2, -depth / 2),
            (width / 2, depth / 2),
            (-width / 2, depth / 2),
        ],
        close=True,
        dxfattribs={"layer": "0"},
    )


def create_scene() -> dict[str, object]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # meters
    doc.header["$MEASUREMENT"] = 1

    layer_colors = {
        "PARCEL": 1,
        "ROAD": 8,
        "CENTERLINE": 9,
        "BUILDING": 7,
        "GREEN": 3,
        "PARKING": 4,
        "WATER": 5,
        "ENTRANCE": 2,
        "LABEL": 2,
    }
    for name, color in layer_colors.items():
        doc.layers.add(name, color=color)
    if "CENTER" not in doc.linetypes:
        doc.linetypes.add("CENTER", pattern=[1.25, -0.25, 0.25, -0.25])
    if "DASHED" not in doc.linetypes:
        doc.linetypes.add("DASHED", pattern=[0.8, -0.4])

    msp = doc.modelspace()

    # 160 m x 110 m rectangular site with a clear metric frame.
    add_rect(msp, "PARCEL", 0, 0, 160, 110)

    # Outer roads, a main east-west spine and a north-south connector.
    add_rect(msp, "ROAD", 0, 94, 160, 110)
    add_rect(msp, "ROAD", 0, 0, 12, 94)
    add_rect(msp, "ROAD", 148, 0, 160, 94)
    add_rect(msp, "ROAD", 12, 48, 148, 56)
    add_rect(msp, "ROAD", 76, 56, 84, 94)
    add_rect(msp, "ROAD", 76, 16, 84, 48)

    # Road centerlines are intentionally separate from road surfaces.
    for points in (
        [(0, 102), (160, 102)],
        [(6, 0), (6, 94)],
        [(154, 0), (154, 94)],
        [(12, 52), (148, 52)],
        [(80, 56), (80, 94)],
        [(80, 16), (80, 48)],
    ):
        msp.add_lwpolyline(
            points,
            dxfattribs={"layer": "CENTERLINE", "linetype": "CENTER"},
        )

    # Eight simple buildings with varied footprints for massing tests.
    building_rects = [
        (20, 65, 45, 84),
        (53, 65, 73, 84),
        (87, 65, 112, 84),
        (120, 65, 141, 84),
        (18, 19, 43, 38),
        (51, 19, 73, 38),
        (88, 19, 114, 38),
        (121, 19, 143, 38),
    ]
    for rect in building_rects:
        add_rect(msp, "BUILDING", *rect)

    # Central green courtyard, two pocket parks and a small water feature.
    add_rect(msp, "GREEN", 45, 58, 73, 88)
    add_rect(msp, "GREEN", 87, 58, 115, 88)
    add_rect(msp, "GREEN", 45, 8, 73, 45)
    add_rect(msp, "GREEN", 87, 8, 115, 45)
    add_rect(msp, "WATER", 57, 60, 103, 66)

    # Parking bays and individual slots.
    add_rect(msp, "PARKING", 17, 42, 45, 47)
    add_rect(msp, "PARKING", 87, 42, 115, 47)
    add_rect(msp, "PARKING", 17, 57, 45, 62)
    add_rect(msp, "PARKING", 115, 57, 143, 62)
    for base_x in (19, 29, 39, 89, 99, 109, 117, 127, 137):
        add_rect(msp, "PARKING", base_x, 42.8, base_x + 7, 46.2)
    for base_x in (19, 29, 39, 117, 127, 137):
        add_rect(msp, "PARKING", base_x, 57.8, base_x + 7, 61.2)

    # Street trees form a readable planting rhythm along roads and parks.
    add_tree_block(doc)
    tree_points = [
        (18, 60), (27, 60), (36, 60), (45, 60), (115, 60), (124, 60),
        (133, 60), (142, 60), (18, 48), (27, 48), (36, 48), (45, 48),
        (115, 48), (124, 48), (133, 48), (142, 48), (49, 72), (69, 72),
        (91, 72), (110, 72), (49, 30), (69, 30), (91, 30), (110, 30),
    ]
    for point in tree_points:
        msp.add_blockref("PT_TREE", point, dxfattribs={"layer": "GREEN"})

    # Standard transport and public-space symbols for the MCP component test.
    add_crosswalk_block(doc)
    add_simple_block(doc, "PT_TRAFFIC_LIGHT", 0.8, 0.8)
    add_simple_block(doc, "PT_BENCH", 1.8, 0.65)
    add_simple_block(doc, "PT_PARKED_CAR", 4.8, 2.0)
    add_simple_block(doc, "PT_BOLLARD", 0.32, 0.32)
    add_simple_block(doc, "PT_BUS_SHELTER", 4.0, 1.6)
    msp.add_blockref("PT_CROSSWALK", (80, 52), dxfattribs={"layer": "ROAD"})
    msp.add_blockref("PT_TRAFFIC_LIGHT", (75, 52), dxfattribs={"layer": "ENTRANCE"})
    msp.add_blockref("PT_TRAFFIC_LIGHT", (85, 52), dxfattribs={"layer": "ENTRANCE", "rotation": 180})
    msp.add_blockref("PT_BUS_SHELTER", (119, 53), dxfattribs={"layer": "ROAD"})
    msp.add_blockref("PT_BENCH", (80, 72), dxfattribs={"layer": "GREEN"})
    msp.add_blockref("PT_PARKED_CAR", (22, 44.5), dxfattribs={"layer": "PARKING"})
    msp.add_blockref("PT_BOLLARD", (14, 52), dxfattribs={"layer": "ENTRANCE"})

    # Simple plan annotation and orientation aids.
    msp.add_text("STANDARD SITE PLAN - METRIC TEST BASE", dxfattribs={"layer": "LABEL", "height": 2.2}).set_placement((4, 106))
    msp.add_text("N", dxfattribs={"layer": "LABEL", "height": 2.5}).set_placement((151, 104))
    msp.add_line((152, 100), (152, 107), dxfattribs={"layer": "LABEL"})
    msp.add_line((150.5, 105), (152, 107), dxfattribs={"layer": "LABEL"})
    msp.add_line((153.5, 105), (152, 107), dxfattribs={"layer": "LABEL"})
    msp.add_text("0     20     40     80 m", dxfattribs={"layer": "LABEL", "height": 1.2}).set_placement((4, 2))
    msp.add_text("ROAD", dxfattribs={"layer": "LABEL", "height": 1.4}).set_placement((68, 53.5))
    msp.add_text("CENTRAL GREEN", dxfattribs={"layer": "LABEL", "height": 1.2}).set_placement((64, 87))

    doc.saveas(DXF_PATH)

    manifest = new_chain_manifest("Antigravity MCP Standard Site Plan", "residential").with_updates(
        crs=CRSDefinition(name="Local metric test coordinate system", kind="local", linear_unit="m").to_dict(),
        cad_unit="m",
    )
    catalog = inspect_sketchup_buildings(DXF_PATH, manifest, "BUILDING")
    buildings = catalog["buildings"]
    floors_by_index = [4, 6, 5, 8, 3, 5, 4, 6]
    types_by_index = ["residential", "residential", "office", "commercial", "residential", "campus", "commercial", "residential"]
    overrides = {
        building["object_id"]: {
            **building,
            "floors": floors_by_index[index],
            "floor_height_m": 3.0,
            "building_type": types_by_index[index],
            "roof_type": "flat" if index % 2 == 0 else "gable",
            "model_detail_level": "presentation",
        }
        for index, building in enumerate(buildings)
    }
    handoff = export_sketchup_handoff(
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
    summary = {
        "dxf_path": str(DXF_PATH.resolve()),
        "handoff_path": str(HANDOFF_PATH.resolve()),
        "site_bounds_m": [160, 110],
        "dxf_units": "m",
        "layers": list(layer_colors),
        "building_count": len(buildings),
        "tree_symbol_count": len(tree_points),
        "handoff_summary": handoff,
        "purpose": "Stable vector base for Antigravity MCP SketchUp acceptance testing",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = create_scene()
    print(f"DXF={result['dxf_path']}")
    print(f"HANDOFF={result['handoff_path']}")
    print(f"SUMMARY={SUMMARY_PATH.resolve()}")
    print(f"BUILDINGS={result['building_count']}")
