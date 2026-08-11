"""Tests for ArcGIS Pro detection and preferred GIS adapter routing."""

from pathlib import Path

import pytest

from planning_toolbox.gis.arcgis_bridge import (
    ArcGISAdapterUnavailableError,
    build_arcgis_worker_command,
    find_arcgis_python,
    require_arcgis_python,
)
from planning_toolbox.gis.vector_bridge import (
    VectorAdapterInfo,
    adapter_status_text,
    find_preferred_adapter,
)


def test_arcgis_python_detection_accepts_explicit_executable_and_home(tmp_path):
    home = tmp_path / "ArcGIS" / "Pro"
    python_path = home / "bin" / "Python" / "envs" / "arcgispro-py3" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b"test-python")
    assert find_arcgis_python(python_path) == python_path.resolve()
    assert find_arcgis_python(home) == python_path.resolve()


def test_arcgis_missing_message_is_beginner_friendly(monkeypatch):
    monkeypatch.setattr("planning_toolbox.gis.arcgis_bridge.find_arcgis_python", lambda *_: None)
    with pytest.raises(ArcGISAdapterUnavailableError, match="ArcGIS Pro"):
        require_arcgis_python()


def test_arcgis_worker_command_is_shell_free_argument_list(tmp_path):
    command = build_arcgis_worker_command(
        tmp_path / "python.exe",
        tmp_path / "worker.py",
        "vector-to-geojson",
        source=tmp_path / "source data.gpkg",
        output=tmp_path / "output data.geojson",
        epsg=4547,
        scratch=tmp_path / "scratch",
        layer_name="parcel layer",
    )
    assert command[0].endswith("python.exe")
    assert command[2] == "vector-to-geojson"
    assert command[command.index("--epsg") + 1] == "4547"
    assert command[command.index("--layer") + 1] == "parcel layer"


def test_preferred_adapter_uses_arcgis_before_ogr(monkeypatch, tmp_path):
    arcgis = tmp_path / "arcgis-python.exe"
    ogr = tmp_path / "ogr2ogr.exe"
    monkeypatch.setattr("planning_toolbox.gis.arcgis_bridge.find_arcgis_python", lambda: arcgis)
    monkeypatch.setattr("planning_toolbox.gis.ogr_bridge.find_ogr2ogr", lambda: ogr)
    adapter = find_preferred_adapter()
    assert adapter == VectorAdapterInfo("arcgis", "ArcGIS Pro", arcgis)
    assert "ArcGIS Pro" in adapter_status_text()


def test_preferred_adapter_falls_back_to_ogr(monkeypatch, tmp_path):
    ogr = tmp_path / "ogr2ogr.exe"
    monkeypatch.setattr("planning_toolbox.gis.arcgis_bridge.find_arcgis_python", lambda: None)
    monkeypatch.setattr("planning_toolbox.gis.ogr_bridge.find_ogr2ogr", lambda: ogr)
    adapter = find_preferred_adapter()
    assert adapter == VectorAdapterInfo("ogr", "QGIS / GDAL", ogr)
