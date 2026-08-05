"""生成城乡规划示例 DXF 文件 (含 PARCEL、BUILDING、GREEN 图层)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ezdxf

def generate_sample_dxf(output_path: str = "sample_data/sample_parcels.dxf"):
    """Generate a sample DXF file with PARCEL, BUILDING, and GREEN layers."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # Meters

    # Create standard layers
    doc.layers.add(name="PARCEL", color=2)        # Yellow
    doc.layers.add(name="BUILDING", color=4)       # Cyan
    doc.layers.add(name="GREEN", color=3)          # Green

    msp = doc.modelspace()

    # === Parcel 1: 100x100m square (10,000 m²) ===
    p1_pts = [(0, 0), (100, 0), (100, 100), (0, 100)]
    lw1 = msp.add_lwpolyline(p1_pts, dxfattribs={"layer": "PARCEL"})
    lw1.close(True)

    # Building inside Parcel 1: 20x30m (600 m²), offset from boundary
    b1_pts = [(10, 10), (40, 10), (40, 40), (10, 40)]
    bw1 = msp.add_lwpolyline(b1_pts, dxfattribs={"layer": "BUILDING"})
    bw1.close(True)

    # Second building inside Parcel 1: 15x20m (300 m²)
    b1b_pts = [(55, 50), (75, 50), (75, 70), (55, 70)]
    bw1b = msp.add_lwpolyline(b1b_pts, dxfattribs={"layer": "BUILDING"})
    bw1b.close(True)

    # Green area inside Parcel 1: 30x20m (600 m²)
    g1_pts = [(60, 10), (90, 10), (90, 30), (60, 30)]
    gw1 = msp.add_lwpolyline(g1_pts, dxfattribs={"layer": "GREEN"})
    gw1.close(True)

    # === Parcel 2: 80x60m rectangle (4,800 m²), offset to the right ===
    p2_pts = [(120, 0), (200, 0), (200, 60), (120, 60)]
    lw2 = msp.add_lwpolyline(p2_pts, dxfattribs={"layer": "PARCEL"})
    lw2.close(True)

    # Building inside Parcel 2: 25x25m (625 m²)
    b2_pts = [(135, 15), (160, 15), (160, 40), (135, 40)]
    bw2 = msp.add_lwpolyline(b2_pts, dxfattribs={"layer": "BUILDING"})
    bw2.close(True)

    # Green area inside Parcel 2: 20x15m (300 m²)
    g2_pts = [(170, 10), (190, 10), (190, 25), (170, 25)]
    gw2 = msp.add_lwpolyline(g2_pts, dxfattribs={"layer": "GREEN"})
    gw2.close(True)

    # === Parcel 3: L-shaped parcel (7,500 m²) ===
    p3_pts = [(0, 120), (100, 120), (100, 170), (50, 170), (50, 220), (0, 220)]
    lw3 = msp.add_lwpolyline(p3_pts, dxfattribs={"layer": "PARCEL"})
    lw3.close(True)

    # Building inside Parcel 3: 30x20m (600 m²)
    b3_pts = [(10, 130), (40, 130), (40, 150), (10, 150)]
    bw3 = msp.add_lwpolyline(b3_pts, dxfattribs={"layer": "BUILDING"})
    bw3.close(True)

    # Green area inside Parcel 3: 25x20m (500 m²)
    g3_pts = [(10, 180), (35, 180), (35, 200), (10, 200)]
    gw3 = msp.add_lwpolyline(g3_pts, dxfattribs={"layer": "GREEN"})
    gw3.close(True)

    # === Additional test case: open polyline (should be flagged) ===
    open_pts = [(250, 0), (300, 0), (300, 50)]
    msp.add_lwpolyline(open_pts, dxfattribs={"layer": "PARCEL"})
    # Intentionally NOT closed

    doc.saveas(out)
    print(f"[生成完成] 示例 DXF 文件已保存: {out}")
    print(f"  - PARCEL 图层: 3 个闭合地块 + 1 个未闭合测试")
    print(f"  - BUILDING 图层: 4 个建筑基底")
    print(f"  - GREEN 图层: 3 个绿地区域")
    return out


def generate_sample_geojson(output_path: str = "sample_data/sample_parcels.geojson"):
    """Generate a sample GeoJSON file for GIS import testing."""
    import json

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    geojson = {
        "type": "FeatureCollection",
        "name": "sample_parcels",
        "planning_toolbox_metadata": {
            "coordinate_reference_system": "UNKNOWN",
            "coordinate_units": "Meters",
            "coordinate_transform_applied": False,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "parcel_id": "GIS_P001",
                    "source_layer": "PARCEL",
                    "area_m2": 10000.0,
                    "area_ha": 1.0,
                    "geometry_status": "VALID"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0], [0.0, 0.0]
                    ]]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "parcel_id": "GIS_P002",
                    "source_layer": "PARCEL",
                    "area_m2": 4800.0,
                    "area_ha": 0.48,
                    "geometry_status": "VALID"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [120.0, 0.0], [200.0, 0.0], [200.0, 60.0], [120.0, 60.0], [120.0, 0.0]
                    ]]
                }
            }
        ]
    }

    with open(out, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"[生成完成] 示例 GeoJSON 文件已保存: {out}")
    print(f"  - 2 个矢量地块边界")
    return out


if __name__ == "__main__":
    generate_sample_dxf()
    generate_sample_geojson()
