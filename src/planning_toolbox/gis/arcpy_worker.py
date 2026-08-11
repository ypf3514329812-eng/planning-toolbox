"""ArcGIS Pro subprocess worker.

This file is intentionally executed by ArcGIS Pro's own Python interpreter.
Planning Toolbox never imports ArcPy into its desktop process.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def _emit(payload):
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _workspace_feature(source, scratch_gdb, requested_layer=None):
    import arcpy

    suffix = Path(source).suffix.lower()
    if suffix in {".geojson", ".json"}:
        output = os.path.join(scratch_gdb, "json_input")
        arcpy.conversion.JSONToFeatures(source, output, "POLYGON")
        return output, ""
    if suffix == ".shp":
        return source, Path(source).stem
    if suffix != ".gpkg":
        raise RuntimeError("ArcGIS Pro 适配器仅接受 GeoJSON、GeoPackage 或 Shapefile。")

    old_workspace = arcpy.env.workspace
    try:
        arcpy.env.workspace = source
        feature_classes = list(arcpy.ListFeatureClasses() or [])
    finally:
        arcpy.env.workspace = old_workspace
    polygon_layers = []
    for name in feature_classes:
        dataset = os.path.join(source, name)
        try:
            if str(arcpy.Describe(dataset).shapeType).lower() == "polygon":
                polygon_layers.append(name)
        except Exception:
            continue
    if requested_layer:
        if requested_layer not in polygon_layers:
            raise RuntimeError(
                "指定的 GeoPackage 面图层不存在。可用面图层：" + "、".join(polygon_layers)
            )
        layer = requested_layer
    elif len(polygon_layers) == 1:
        layer = polygon_layers[0]
    elif not polygon_layers:
        raise RuntimeError("GeoPackage 中没有可转换的 Polygon 面图层。")
    else:
        raise RuntimeError(
            "GeoPackage 包含多个面图层，请先在 ArcGIS Pro 中只导出需要的图层："
            + "、".join(polygon_layers)
        )
    return os.path.join(source, layer), layer


def _project_feature(input_feature, scratch_gdb, epsg):
    import arcpy

    target_sr = arcpy.SpatialReference(int(epsg))
    source_sr = arcpy.Describe(input_feature).spatialReference
    if not source_sr or str(getattr(source_sr, "name", "")).lower() in {"", "unknown"}:
        raise RuntimeError("源 GIS 图层没有可识别的坐标系，系统不会猜测投影。")
    transformations = list(arcpy.ListTransformations(source_sr, target_sr) or [])
    transformation = transformations[0] if transformations else ""
    output = os.path.join(scratch_gdb, "projected_polygon")
    arcpy.management.Project(input_feature, output, target_sr, transformation)
    return output, transformation


def vector_to_geojson(args):
    import arcpy

    scratch_gdb = os.path.join(args.scratch, "arcgis_bridge.gdb")
    arcpy.management.CreateFileGDB(args.scratch, "arcgis_bridge.gdb")
    input_feature, selected_layer = _workspace_feature(
        args.source, scratch_gdb, args.layer or None
    )
    projected, transformation = _project_feature(input_feature, scratch_gdb, args.epsg)
    arcpy.conversion.FeaturesToJSON(
        projected,
        args.output,
        "FORMATTED",
        "NO_Z_VALUES",
        "NO_M_VALUES",
        "GEOJSON",
        "KEEP_INPUT_SR",
        "USE_FIELD_NAME",
    )
    return {
        "selected_layer": selected_layer,
        "geographic_transformation": transformation,
        "feature_count": int(arcpy.management.GetCount(projected)[0]),
    }


def geojson_to_gpkg(args):
    import arcpy

    scratch_gdb = os.path.join(args.scratch, "arcgis_bridge.gdb")
    arcpy.management.CreateFileGDB(args.scratch, "arcgis_bridge.gdb")
    input_feature = os.path.join(scratch_gdb, "json_input")
    arcpy.conversion.JSONToFeatures(args.source, input_feature, "POLYGON")
    spatial_ref = arcpy.SpatialReference(int(args.epsg))
    arcpy.management.DefineProjection(input_feature, spatial_ref)
    if arcpy.Exists(args.output):
        arcpy.management.Delete(args.output)
    arcpy.management.CreateSQLiteDatabase(args.output, "GEOPACKAGE")
    output_feature = os.path.join(args.output, args.layer)
    arcpy.conversion.ExportFeatures(input_feature, output_feature)
    return {
        "selected_layer": args.layer,
        "geographic_transformation": "",
        "feature_count": int(arcpy.management.GetCount(output_feature)[0]),
    }


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("mode", choices=("vector-to-geojson", "geojson-to-gpkg"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--epsg", required=True, type=int)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--layer", default="")
    args = parser.parse_args()

    try:
        import arcpy

        arcpy.env.overwriteOutput = True
        arcpy.env.addOutputsToMap = False
        arcpy.env.parallelProcessingFactor = "0"
        if args.mode == "vector-to-geojson":
            detail = vector_to_geojson(args)
        else:
            detail = geojson_to_gpkg(args)
        _emit(
            {
                "status": "ok",
                "arcgis_version": arcpy.GetInstallInfo().get("Version", ""),
                **detail,
            }
        )
        return 0
    except Exception as exc:
        try:
            import arcpy

            messages = str(arcpy.GetMessages(2) or "").strip()
        except Exception:
            messages = ""
        _emit({"status": "error", "message": str(exc), "details": messages})
        return 1


if __name__ == "__main__":
    sys.exit(main())
