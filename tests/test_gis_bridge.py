import json
import pytest
import ezdxf
from shapely.geometry import Polygon
from planning_toolbox.core.models.parcel import Parcel
from planning_toolbox.gis.io.exporter import export_parcels_to_geojson
from planning_toolbox.gis.io.importer import import_geojson_to_dxf, GISImportError

def test_geojson_export_valid_parcels(tmp_path):
    """Test exporting valid Parcel objects into a standard GeoJSON FeatureCollection."""
    poly = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    parcel1 = Parcel(
        parcel_id="P001",
        source_layer="PARCEL",
        status="VALID",
        raw_area=10000.0,
        area_m2=10000.0,
        area_ha=1.0,
        geometry=poly,
        label_point=(50.0, 50.0)
    )

    out_geojson = tmp_path / "test_out.geojson"
    res_path = export_parcels_to_geojson([parcel1], out_geojson)

    assert res_path.exists()
    with open(res_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1

    feat = data["features"][0]
    assert feat["type"] == "Feature"
    assert feat["properties"]["parcel_id"] == "P001"
    assert feat["properties"]["area_m2"] == 10000.0
    assert feat["properties"]["area_ha"] == 1.0
    assert feat["properties"]["geometry_status"] == "VALID"
    assert feat["geometry"]["type"] == "Polygon"


def test_geojson_export_empty_geometry(tmp_path):
    """Test exporting a parcel with no geometry (e.g. invalid parcel)."""
    parcel_err = Parcel(
        parcel_id="P_ERR_01",
        source_layer="PARCEL",
        status="OPEN",
        raw_area=0.0,
        area_m2=0.0,
        area_ha=0.0,
        geometry=None,
        label_point=None,
        error_message="Polyline boundary is not closed."
    )

    out_geojson = tmp_path / "err_out.geojson"
    res_path = export_parcels_to_geojson([parcel_err], out_geojson)

    with open(res_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    feat = data["features"][0]
    assert feat["properties"]["parcel_id"] == "P_ERR_01"
    assert feat["geometry"] is None


def test_geojson_import_to_dxf(tmp_path):
    """Test importing GeoJSON features into CAD DXF polylines."""
    geojson_path = tmp_path / "input.geojson"
    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"parcel_id": "P001"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[(0, 0), (100, 0), (100, 100), (0, 100), (0, 0)]]
                }
            }
        ]
    }
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f)

    out_dxf = tmp_path / "imported.dxf"
    res_dxf, stats = import_geojson_to_dxf(geojson_path, out_dxf, target_layer="GIS_PARCEL")

    assert res_dxf.exists()
    assert stats["imported_polygons"] == 1
    doc = ezdxf.readfile(res_dxf)
    entities = [e for e in doc.modelspace() if e.dxf.layer == "GIS_PARCEL"]
    assert len(entities) == 1
    assert entities[0].dxftype() == "LWPOLYLINE"
    assert entities[0].is_closed is True


def test_geojson_import_path_collision(tmp_path):
    """Test import_geojson_to_dxf raises ValueError if output path is identical to source path."""
    same_path = tmp_path / "file.json"
    same_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        import_geojson_to_dxf(same_path, same_path)
    assert "Direct overwrite is forbidden" in str(exc.value)


def test_cad_gis_cad_roundtrip(tmp_path):
    """Test CAD DXF -> GeoJSON export -> DXF import roundtrip fidelity."""
    from planning_toolbox.cad.parcels.calculator import process_parcels

    # Create CAD DXF with 1 square parcel
    dxf_src = tmp_path / "square.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add(name="PARCEL", color=1)
    poly = doc.modelspace().add_lwpolyline([(0, 0), (200, 0), (200, 200), (0, 200)], dxfattribs={"layer": "PARCEL"})
    poly.close(True)
    doc.saveas(dxf_src)

    # 1. CAD -> Process -> GeoJSON
    config = {"parcel": {"input_layers": ["PARCEL"], "fallback_unit": "m", "strict_unit_check": False}}
    parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_src, config, tmp_path / "out")
    geojson_file = tmp_path / "out" / "square.geojson"
    assert geojson_file.exists()

    # 2. GeoJSON -> Import CAD DXF
    reimported_dxf = tmp_path / "out" / "square_reimported.dxf"
    res_dxf, stats = import_geojson_to_dxf(geojson_file, reimported_dxf, target_layer="GIS_PARCEL")

    assert res_dxf.exists()
    assert stats["imported_polygons"] >= 1
    re_doc = ezdxf.readfile(res_dxf)
    ents = [e for e in re_doc.modelspace() if e.dxf.layer == "GIS_PARCEL"]
    assert len(ents) == 1
    pts = list(ents[0].get_points(format="xy"))
    assert len(pts) == 4
    # Roundtrip bounding box check
    min_x = min(p[0] for p in pts)
    max_x = max(p[0] for p in pts)
    assert min_x == 0.0
    assert max_x == 200.0
