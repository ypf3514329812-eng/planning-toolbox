import ezdxf
from pathlib import Path

def create_sample_dxf(output_path: Path | str):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # 6 = Meters
    
    doc.layers.add(name="PARCEL", color=3)
    msp = doc.modelspace()

    # 1. Parcel 1: 100m x 100m square (Top-Left) -> 10,000 m²
    p1 = [(0, 100), (100, 100), (100, 0), (0, 0)]
    poly1 = msp.add_lwpolyline(p1, dxfattribs={"layer": "PARCEL"})
    poly1.close(True)

    # 2. Parcel 2: 200m x 50m rectangle (Top-Right) -> 10,000 m²
    p2 = [(150, 50), (350, 50), (350, 0), (150, 0)]
    poly2 = msp.add_lwpolyline(p2, dxfattribs={"layer": "PARCEL"})
    poly2.close(True)

    # 3. Parcel 3 (Error: Open Polyline)
    p3 = [(0, -50), (50, -50), (50, -100)]  # Missing closing side back to (0, -50)
    poly3 = msp.add_lwpolyline(p3, dxfattribs={"layer": "PARCEL"})
    poly3.close(False)

    # 4. Parcel 4 (Error: Self-intersecting Figure-8)
    p4 = [(150, -50), (250, -150), (250, -50), (150, -150)]
    poly4 = msp.add_lwpolyline(p4, dxfattribs={"layer": "PARCEL"})
    poly4.close(True)

    # 5. Parcel 5: Polygon with Bulge Arc (Rounded corner parcel)
    p5 = [(0, -200), (100, -200), (100, -300), (0, -300)]
    poly5 = msp.add_lwpolyline(p5, dxfattribs={"layer": "PARCEL"})
    poly5[0] = (0, -200, 0, 0, 0.41421356237309515) # bulge = tan(pi/8) -> 90-degree arc
    poly5.close(True)

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_file)
    print(f"Sample DXF created successfully at: {out_file}")

if __name__ == "__main__":
    sample_path = Path(__file__).parent.parent / "sample_data" / "sample_parcels.dxf"
    create_sample_dxf(sample_path)
