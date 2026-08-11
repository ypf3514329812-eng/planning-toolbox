"""Tests for the lightweight external GIS adapter and CRS contract."""

import json
from pathlib import Path

import pytest
import shapely.geometry

from planning_toolbox.gis.crs import (
    CRSValidationError,
    normalize_crs_identifier,
    require_projected_metric_crs,
)
from planning_toolbox.gis.ogr_bridge import (
    GISAdapterUnavailableError,
    build_geojson_to_gpkg_command,
    build_vector_to_geojson_command,
    convert_geojson_to_gpkg,
    convert_vector_to_geojson,
    find_ogr2ogr,
    require_ogr2ogr,
)
from planning_toolbox.project.chain_manifest import CRSDefinition, new_chain_manifest
from planning_toolbox.core.models.parcel import Parcel
from planning_toolbox.gis.io.exporter import export_parcels_to_geojson
from planning_toolbox.gis.io.importer import import_geojson_to_dxf


def _project_manifest(code=4547, kind="projected"):
    return new_chain_manifest("GIS 桥接测试").with_updates(
        crs=CRSDefinition(code=code, kind=kind, linear_unit="m").to_dict()
    )


def test_crs_contract_accepts_projected_metric_and_blocks_unsafe_values(monkeypatch):
    real_import = __import__

    def no_pyproj(name, *args, **kwargs):
        if name == "pyproj":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("planning_toolbox.gis.crs.importlib.import_module", no_pyproj)
    assert normalize_crs_identifier("4547") == "EPSG:4547"
    assert require_projected_metric_crs(_project_manifest()) == "EPSG:4547"
    with pytest.raises(CRSValidationError, match="网络地图"):
        require_projected_metric_crs(_project_manifest(3857))
    with pytest.raises(CRSValidationError, match="经纬度"):
        require_projected_metric_crs(_project_manifest(4490))
    with pytest.raises(CRSValidationError, match="投影坐标"):
        require_projected_metric_crs(_project_manifest(4547, kind="local"))


def test_find_ogr2ogr_respects_an_explicit_file(tmp_path):
    executable = tmp_path / "ogr2ogr.exe"
    executable.write_bytes(b"test adapter")
    assert find_ogr2ogr(executable) == executable.resolve()
    assert find_ogr2ogr(tmp_path / "missing.exe") is None


def test_require_ogr2ogr_has_beginner_friendly_missing_message(monkeypatch):
    monkeypatch.setattr("planning_toolbox.gis.ogr_bridge.find_ogr2ogr", lambda *_: None)
    with pytest.raises(GISAdapterUnavailableError, match="安装 QGIS"):
        require_ogr2ogr()


def test_command_builders_use_argument_lists_and_explicit_crs(tmp_path):
    executable = tmp_path / "ogr2ogr.exe"
    source = tmp_path / "source data.gpkg"
    geojson = tmp_path / "normalized.geojson"
    command = build_vector_to_geojson_command(
        executable,
        source,
        geojson,
        target_crs="EPSG:4547",
        layer_name="parcel layer",
    )
    assert command[0] == str(executable)
    assert "-t_srs" in command
    assert command[command.index("-t_srs") + 1] == "EPSG:4547"
    assert str(source) in command
    assert command[-1] == "parcel layer"

    gpkg_command = build_geojson_to_gpkg_command(
        executable,
        geojson,
        tmp_path / "result.gpkg",
        source_crs="4547",
        layer_name="规划 地块",
    )
    assert gpkg_command[gpkg_command.index("-a_srs") + 1] == "EPSG:4547"
    assert gpkg_command[gpkg_command.index("-nln") + 1] == "planning_features"


def test_vector_bridge_generates_projected_intermediate_without_mutating_source(
    tmp_path, monkeypatch
):
    source = tmp_path / "source.gpkg"
    source.write_bytes(b"immutable-gpkg")
    executable = tmp_path / "ogr2ogr.exe"
    executable.write_bytes(b"adapter")
    output = tmp_path / "normalized.geojson"

    def fake_run(command, timeout_seconds=300):
        output.write_text(
            json.dumps({"type": "FeatureCollection", "features": []}),
            encoding="utf-8",
        )

    monkeypatch.setattr("planning_toolbox.gis.ogr_bridge._run_command", fake_run)
    result = convert_vector_to_geojson(
        source,
        output,
        target_crs="EPSG:4547",
        ogr2ogr_path=executable,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert source.read_bytes() == b"immutable-gpkg"
    assert result.output_path == output.resolve()
    assert data["planning_toolbox_metadata"]["coordinate_reference_system"] == "EPSG:4547"
    assert data["planning_toolbox_metadata"]["coordinate_transform_applied"] is True


def test_gpkg_bridge_preserves_source_and_creates_output(tmp_path, monkeypatch):
    source = tmp_path / "parcels.geojson"
    source.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    original = source.read_bytes()
    executable = tmp_path / "ogr2ogr.exe"
    executable.write_bytes(b"adapter")
    output = tmp_path / "parcels.gpkg"

    def fake_run(command, timeout_seconds=300):
        output.write_bytes(b"gpkg-result")

    monkeypatch.setattr("planning_toolbox.gis.ogr_bridge._run_command", fake_run)
    result = convert_geojson_to_gpkg(
        source,
        output,
        source_crs="EPSG:4547",
        ogr2ogr_path=executable,
    )
    assert source.read_bytes() == original
    assert result.output_path == output.resolve()
    assert output.read_bytes() == b"gpkg-result"


def test_geojson_coordinate_scaling_and_dxf_unit_conversion_are_reversible(tmp_path):
    parcel = Parcel(
        parcel_id="P001",
        source_layer="PARCEL",
        status="VALID",
        raw_area=1_000_000.0,
        area_m2=1.0,
        area_ha=0.0001,
        geometry=shapely.geometry.Polygon(
            [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0)]
        ),
    )
    geojson = export_parcels_to_geojson(
        [parcel],
        tmp_path / "scaled.geojson",
        crs_name="EPSG:4547",
        coordinate_units="Meters",
        coordinate_scale=0.001,
    )
    coordinates = json.loads(geojson.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"][0]
    assert max(point[0] for point in coordinates) == pytest.approx(1.0)

    dxf_path, stats = import_geojson_to_dxf(
        geojson,
        tmp_path / "restored_mm.dxf",
        target_unit="mm",
        source_unit="m",
    )
    import ezdxf

    doc = ezdxf.readfile(dxf_path)
    entity = next(iter(doc.modelspace().query("LWPOLYLINE")))
    assert doc.header["$INSUNITS"] == 4
    assert max(point[0] for point in entity.get_points("xy")) == pytest.approx(1000.0)
    assert stats["coordinate_scale"] == pytest.approx(1000.0)
