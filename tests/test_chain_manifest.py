"""Tests for the lightweight GIS-CAD-SU project coordinate contract."""

import pytest

from planning_toolbox.project.chain_manifest import (
    CRSDefinition,
    ChainManifest,
    LocalOrigin,
    make_stable_object_id,
    new_chain_manifest,
)


def test_chain_manifest_round_trip_is_json_ready():
    manifest = new_chain_manifest("居住区课程设计", "residential")
    configured = manifest.with_updates(
        crs=CRSDefinition(
            code=4547,
            name="CGCS2000 / 3-degree Gauss-Kruger CM 114E",
            kind="projected",
        ).to_dict(),
        cad_unit="m",
        local_origin=LocalOrigin(
            enabled=True,
            easting=385000.0,
            northing=3456000.0,
            elevation=18.5,
            rotation_deg=12.0,
        ).to_dict(),
    )

    loaded = ChainManifest.from_dict(configured.to_dict())

    assert loaded.project_id == manifest.project_id
    assert loaded.name == "居住区课程设计"
    assert loaded.crs.identifier == "EPSG:4547"
    assert loaded.crs.metric_ready is True
    assert loaded.local_origin.enabled is True


def test_local_origin_transform_is_reversible():
    origin = LocalOrigin(
        enabled=True,
        easting=500000.0,
        northing=3400000.0,
        elevation=25.0,
        rotation_deg=31.5,
    )
    project_point = (500123.456, 3400789.012, 42.0)

    local_point = origin.to_local(*project_point)
    restored = origin.to_project(*local_point)

    assert restored == pytest.approx(project_point, abs=1e-9)


def test_stable_object_id_is_repeatable_and_project_scoped():
    first_project = new_chain_manifest("A")
    second_project = new_chain_manifest("B")

    first = make_stable_object_id(first_project.project_id, "building", "GIS:128")
    repeated = make_stable_object_id(first_project.project_id, "building", "GIS:128")
    other_project = make_stable_object_id(second_project.project_id, "building", "GIS:128")

    assert first == repeated
    assert first.startswith("PT-BUILDING-")
    assert first != other_project


def test_geographic_crs_is_not_metric_ready():
    geographic = CRSDefinition(code=4490, name="CGCS2000", kind="geographic")
    assert geographic.identifier == "EPSG:4490"
    assert geographic.metric_ready is False

    web_map = CRSDefinition(code=3857, name="Web Mercator", kind="projected")
    assert web_map.metric_ready is False
