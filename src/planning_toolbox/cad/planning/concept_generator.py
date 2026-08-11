"""Generate a conservative, parameter-driven concept plan DXF.

The generator creates a separate DXF containing setback guides, simple building
footprints and residual green-space polygons inside valid PARCEL boundaries.
It is intentionally deterministic and explicitly a concept sketch, not a
regulatory or construction drawing.
"""

from __future__ import annotations

import math
import csv
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import ezdxf
from shapely.affinity import rotate
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon, box
from shapely.ops import unary_union

from planning_toolbox.core.geometry.parser import parse_parcel_geometry, points_from_dxf_polyline
from planning_toolbox.core.units.unit_manager import (
    get_dxf_unit_code,
    get_linear_scale_to_m,
    resolve_unit,
)
from planning_toolbox.rules.standards import get_standards_profile
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


def _iter_polygons(geometry) -> Iterable[Polygon]:
    if geometry is None or geometry.is_empty:
        return
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        for part in geometry.geoms:
            yield from _iter_polygons(part)
    elif isinstance(geometry, GeometryCollection):
        for part in geometry.geoms:
            yield from _iter_polygons(part)


def _ensure_layer(doc, name: str, color: int) -> None:
    if name not in doc.layers:
        doc.layers.add(name=name, color=color)


def _add_polygon(msp, polygon: Polygon, layer: str) -> None:
    points = [(float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]]
    if len(points) >= 3:
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _rounded_rectangle(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    radius: float,
    rotation_degrees: float = 0.0,
) -> Polygon:
    """Build a CAD-friendly rounded footprint rather than a sharp rectangle.

    Shapely represents the rounded corners as a short sequence of vertices.
    When exported as an LWPOLYLINE this keeps the DXF broadly compatible while
    producing the soft, hand-composed appearance expected from a concept plan.
    """
    width = max(float(width), 0.01)
    height = max(float(height), 0.01)
    max_radius = max(0.0, min(width, height) / 2.0 - 0.001)
    radius = min(max(float(radius), 0.0), max_radius)
    footprint = box(
        center_x - width / 2,
        center_y - height / 2,
        center_x + width / 2,
        center_y + height / 2,
    )
    if radius > 0.0:
        footprint = footprint.buffer(-radius, quad_segs=1).buffer(
            radius, quad_segs=8
        )
    if rotation_degrees:
        footprint = rotate(
            footprint,
            rotation_degrees,
            origin=(center_x, center_y),
            use_radians=False,
        )
    return footprint


def _quadratic_curve(start: Tuple[float, float], end: Tuple[float, float], offset: float) -> LineString:
    """Return a smooth, deterministic quadratic Bézier-like guide line."""
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return LineString([start, end])
    normal_x = -dy / length
    normal_y = dx / length
    midpoint = ((sx + ex) / 2.0, (sy + ey) / 2.0)
    control = (
        midpoint[0] + normal_x * offset,
        midpoint[1] + normal_y * offset,
    )
    points = []
    for index in range(17):
        t = index / 16.0
        inverse = 1.0 - t
        points.append(
            (
                inverse * inverse * sx
                + 2.0 * inverse * t * control[0]
                + t * t * ex,
                inverse * inverse * sy
                + 2.0 * inverse * t * control[1]
                + t * t * ey,
            )
        )
    return LineString(points)


def _grid_centers(bounds: Tuple[float, float, float, float], count: int):
    minx, miny, maxx, maxy = bounds
    columns = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / columns))
    cell_w = (maxx - minx) / columns
    cell_h = (maxy - miny) / rows
    for row in range(rows):
        for column in range(columns):
            yield minx + (column + 0.5) * cell_w, miny + (row + 0.5) * cell_h, cell_w, cell_h


def _dominant_angle(polygon: Polygon) -> float:
    """Return the angle of the longest edge of a polygon's minimum rectangle."""
    rectangle = polygon.minimum_rotated_rectangle
    coordinates = list(rectangle.exterior.coords)
    longest = 0.0
    angle = 0.0
    for start, end in zip(coordinates, coordinates[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        if length > longest:
            longest = length
            angle = math.degrees(math.atan2(dy, dx))
    return angle


def _polygon_dimensions_m(polygon: Polygon, linear_scale: float) -> Tuple[float, float]:
    """Return long and short dimensions of a polygon in metres."""
    rectangle = polygon.minimum_rotated_rectangle
    coordinates = list(rectangle.exterior.coords)
    lengths = []
    for start, end in zip(coordinates, coordinates[1:]):
        lengths.append(math.hypot(end[0] - start[0], end[1] - start[1]))
    lengths.sort(reverse=True)
    if len(lengths) < 2:
        return 0.0, 0.0
    return lengths[0] * linear_scale, lengths[1] * linear_scale


def _make_buildings(
    parcel: Polygon,
    usable: Polygon,
    count: int,
    coverage_ratio: float,
    orientation_degrees: float = 0.0,
    minimum_gap_source_units: float = 0.0,
    organic: bool = False,
) -> List[Polygon]:
    """Place non-overlapping concept buildings aligned to the parcel direction.

    ``organic=True`` rounds the building corners and gives the footprints a
    softer campus/neighbourhood-plan character.  The conservative rectangular
    mode remains available for users who prefer a deliberately simple study
    diagram.
    """
    if usable.is_empty or usable.area <= 0 or count <= 0:
        return []

    target_total = min(usable.area * 0.70, parcel.area * coverage_ratio)
    desired_area = max(target_total / count, usable.area * 0.01)
    buildings: List[Polygon] = []

    for shrink in (1.0, 0.88, 0.76, 0.64, 0.52, 0.40):
        if len(buildings) >= count:
            break
        buildings = []
        for cx, cy, cell_w, cell_h in _grid_centers(usable.bounds, count):
            aspect = 1.55
            width = min(math.sqrt(desired_area * aspect), cell_w * 0.68) * shrink
            height = min(math.sqrt(desired_area / aspect), cell_h * 0.68) * shrink
            if width <= 0 or height <= 0:
                continue
            if organic:
                candidate = _rounded_rectangle(
                    cx,
                    cy,
                    width,
                    height,
                    radius=min(width, height) * 0.18,
                    rotation_degrees=orientation_degrees,
                )
            else:
                candidate = box(
                    cx - width / 2,
                    cy - height / 2,
                    cx + width / 2,
                    cy + height / 2,
                )
                candidate = rotate(
                    candidate,
                    orientation_degrees,
                    origin=(cx, cy),
                    use_radians=False,
                )
            safety_candidate = (
                candidate.buffer(minimum_gap_source_units / 2)
                if minimum_gap_source_units > 0
                else candidate
            )
            if not usable.contains(safety_candidate):
                continue
            if any(
                safety_candidate.intersects(
                    existing.buffer(minimum_gap_source_units / 2)
                    if minimum_gap_source_units > 0
                    else existing
                )
                for existing in buildings
            ):
                continue
            buildings.append(candidate)
            if len(buildings) >= count:
                break

    return buildings


def _make_parking_slots(
    usable: Polygon,
    buildings: List[Polygon],
    count: int,
    linear_scale: float,
) -> List[Polygon]:
    """Place simple conceptual parking bays in remaining usable space.

    Parking bays are deliberately conservative 5.0 m x 2.5 m rectangles.
    This is a visual quantity estimate, not a road-access or parking-code
    compliance check.
    """
    if count <= 0 or usable.is_empty or usable.area <= 0:
        return []

    slot_length = 5.0 / linear_scale
    slot_width = 2.5 / linear_scale
    clearance = max(0.5 / linear_scale, 0.01)
    minx, miny, maxx, maxy = usable.bounds
    obstacles = list(buildings)
    slots: List[Polygon] = []

    for width, height in ((slot_length, slot_width), (slot_width, slot_length)):
        if len(slots) >= count:
            break
        span_x = maxx - minx
        span_y = maxy - miny
        if width >= span_x or height >= span_y:
            continue
        columns = max(1, min(40, math.floor(span_x / (width + clearance))))
        rows = max(1, min(40, math.floor(span_y / (height + clearance))))

        for row in range(rows):
            for column in range(columns):
                cx = minx + (column + 0.5) * span_x / columns
                cy = miny + (row + 0.5) * span_y / rows
                candidate = box(
                    cx - width / 2,
                    cy - height / 2,
                    cx + width / 2,
                    cy + height / 2,
                )
                safety_candidate = candidate.buffer(clearance / 2)
                if not usable.contains(safety_candidate):
                    continue
                if any(
                    safety_candidate.intersects(obstacle.buffer(clearance / 2))
                    for obstacle in obstacles + slots
                ):
                    continue
                slots.append(candidate)
                if len(slots) >= count:
                    break
            if len(slots) >= count:
                break

    return slots


def _make_access_corridor(
    parcel: Polygon,
    usable: Polygon,
    width_source_units: float,
    organic: bool = False,
):
    """Create a conceptual access/fire corridor from the longest parcel edge.

    The corridor is a study guide only. It is clipped to the setback-usable
    area so subsequent building and parking placement avoids it.
    """
    if width_source_units <= 0 or usable.is_empty:
        return None

    coordinates = list(parcel.exterior.coords)
    longest_length = 0.0
    edge_midpoint = None
    for start, end in zip(coordinates, coordinates[1:]):
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        if length > longest_length:
            longest_length = length
            edge_midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    if edge_midpoint is None:
        return None

    target = parcel.representative_point()
    if organic:
        bounds_width = parcel.bounds[2] - parcel.bounds[0]
        bounds_height = parcel.bounds[3] - parcel.bounds[1]
        curve_offset = min(bounds_width, bounds_height) * 0.16
        guide = _quadratic_curve(
            edge_midpoint,
            (target.x, target.y),
            offset=curve_offset,
        )
        corridor = guide.buffer(
            width_source_units / 2,
            quad_segs=8,
            cap_style=1,
            join_style=1,
        )
        # Add a soft perimeter loop where the parcel is large enough.  This
        # produces the familiar human-planned neighbourhood pattern: an
        # access bend feeding a slower internal loop around the buildings.
        loop_centerline = usable.buffer(-width_source_units * 1.6)
        if not loop_centerline.is_empty and loop_centerline.area > width_source_units**2 * 4:
            loop = loop_centerline.boundary.buffer(
                width_source_units / 2,
                quad_segs=8,
                cap_style=1,
                join_style=1,
            )
            corridor = unary_union([corridor, loop])
    else:
        guide = LineString([edge_midpoint, (target.x, target.y)])
        corridor = guide.buffer(width_source_units / 2, cap_style=2, join_style=2)
    return corridor.intersection(usable)


def generate_concept_plan(
    dxf_path: Path | str,
    output_dir: Path | str = "output",
    building_count: int = 1,
    coverage_ratio: float = 0.25,
    setback_m: float = 5.0,
    parcel_layer: str = "PARCEL",
    fallback_unit: Optional[str] = None,
    floors: Optional[int] = None,
    parking_ratio: Optional[float] = None,
    building_gap_m: float = 0.0,
    access_width_m: float = 0.0,
    standards_profile_id: str = "custom_local",
    layout_style: str = "organic",
) -> dict:
    """Generate a deterministic concept-plan DXF from valid parcel polygons.

    ``building_count`` is the requested number of footprints per parcel and
    ``coverage_ratio`` is the requested building coverage ratio as a fraction.
    ``floors`` and ``parking_ratio`` are optional planning-study inputs. When
    both are supplied, the report includes estimated gross floor area and a
    conceptual parking-bay count. The function never overwrites the source
    DXF and blocks unknown units unless the caller explicitly supplies
    ``fallback_unit``. ``layout_style`` can be ``organic`` for rounded
    footprints and curved access guides, or ``rectilinear`` for simple
    rectangular study geometry.
    """
    source = Path(dxf_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"DXF 文件不存在：{source}")
    if building_count < 1 or building_count > 50:
        raise ValueError("每个地块的建筑数量必须在 1 到 50 之间。")
    if not math.isfinite(coverage_ratio) or coverage_ratio <= 0 or coverage_ratio > 0.80:
        raise ValueError("建筑覆盖率必须大于 0 且不超过 80%。")
    if not math.isfinite(setback_m) or setback_m < 0:
        raise ValueError("建筑退线距离必须是非负数。")
    if not math.isfinite(building_gap_m) or building_gap_m < 0 or building_gap_m > 100:
        raise ValueError("建筑间距约束必须在 0 到 100 米之间。")
    if not math.isfinite(access_width_m) or access_width_m < 0 or access_width_m > 100:
        raise ValueError("概念道路/消防通道宽度必须在 0 到 100 米之间。")
    if floors is not None and (floors < 1 or floors > 200):
        raise ValueError("楼层数必须在 1 到 200 之间；不估算时可以留空。")
    if parking_ratio is not None and (
        not math.isfinite(parking_ratio) or parking_ratio < 0 or parking_ratio > 100
    ):
        raise ValueError("停车配比必须在 0 到 100 个/1000m² 之间。")
    if parking_ratio and floors is None:
        raise ValueError("要估算概念停车位，必须同时明确填写建筑楼层数。")
    if layout_style not in {"organic", "rectilinear"}:
        raise ValueError("layout_style must be organic or rectilinear")
    standards_profile = get_standards_profile(standards_profile_id)

    source_hash = sha256_file(source)
    doc = ezdxf.readfile(source)
    unit_name = resolve_unit(
        get_dxf_unit_code(doc),
        fallback_unit=fallback_unit,
        strict_check=fallback_unit is None,
    )
    linear_scale = get_linear_scale_to_m(unit_name)
    setback_source_units = setback_m / linear_scale
    building_gap_source_units = building_gap_m / linear_scale
    access_width_source_units = access_width_m / linear_scale
    organic_layout = layout_style == "organic"

    parcels: List[Polygon] = []
    for entity in doc.modelspace():
        if entity.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
            continue
        if str(entity.dxf.layer).upper() != parcel_layer.upper():
            continue
        points, is_closed, _ = points_from_dxf_polyline(entity)
        status, polygon, _ = parse_parcel_geometry(points, is_closed)
        if status == "VALID" and polygon and polygon.area > 0:
            parcels.append(polygon)

    parcels.sort(key=lambda polygon: (-polygon.centroid.y, polygon.centroid.x))
    if not parcels:
        raise ValueError(f"没有在 {parcel_layer} 图层中找到有效闭合地块。")

    output_path = (Path(output_dir) / f"{source.stem}_concept_plan.dxf").resolve()
    report_path = (Path(output_dir) / f"{source.stem}_concept_plan_report.txt").resolve()
    if output_path == source:
        raise ValueError("概念方案输出路径不能覆盖原始 DXF。")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    msp = doc.modelspace()
    _ensure_layer(doc, "CONCEPT_SETBACK", 5)
    _ensure_layer(doc, "CONCEPT_BUILDING", 1)
    _ensure_layer(doc, "CONCEPT_GREEN", 3)
    _ensure_layer(doc, "CONCEPT_LABEL", 7)
    _ensure_layer(doc, "CONCEPT_PARKING", 2)
    _ensure_layer(doc, "CONCEPT_DIMENSION", 6)
    _ensure_layer(doc, "CONCEPT_ROAD", 4)

    building_total = 0
    building_footprint_m2 = 0.0
    estimated_gfa_m2 = 0.0 if floors is not None else None
    parcel_area_m2 = sum(parcel.area for parcel in parcels) * (linear_scale ** 2)
    building_records = []
    minimum_setback_m = math.inf
    minimum_building_gap_m = math.inf
    access_corridor_m2 = 0.0
    green_total = 0
    green_area_m2 = 0.0
    parking_required_total = 0
    parking_generated_total = 0
    parking_unplaced_total = 0
    skipped_parcels = 0
    label_height = max(1.5 / linear_scale, 0.01)

    for index, parcel in enumerate(parcels, start=1):
        usable = parcel.buffer(-setback_source_units)
        if usable.is_empty or usable.area <= 0:
            skipped_parcels += 1
            continue

        for usable_part in _iter_polygons(usable):
            _add_polygon(msp, usable_part, "CONCEPT_SETBACK")

        access_corridor = _make_access_corridor(
            parcel,
            usable,
            access_width_source_units,
            organic=organic_layout,
        )
        access_parts = (
            list(_iter_polygons(access_corridor))
            if access_corridor is not None and not access_corridor.is_empty
            else []
        )
        for access_part in access_parts:
            _add_polygon(msp, access_part, "CONCEPT_ROAD")
            access_corridor_m2 += access_part.area * (linear_scale ** 2)
        if access_parts:
            access_label = msp.add_mtext(
                f"ACCESS / FIRE GUIDE {access_width_m:.1f}m",
                dxfattribs={
                    "layer": "CONCEPT_LABEL",
                    "char_height": label_height * 0.8,
                    "attachment_point": 5,
                },
            )
            access_point = access_parts[0].representative_point()
            access_label.set_location(insert=(access_point.x, access_point.y, 0.0))

        building_area = (
            usable.difference(access_corridor)
            if access_corridor is not None and not access_corridor.is_empty
            else usable
        )

        parcel_angle = _dominant_angle(parcel)
        parcel_buildings = _make_buildings(
            parcel,
            building_area,
            building_count,
            coverage_ratio,
            orientation_degrees=parcel_angle,
            minimum_gap_source_units=building_gap_source_units,
            organic=organic_layout,
        )
        for building_index, building in enumerate(parcel_buildings, start=1):
            _add_polygon(msp, building, "CONCEPT_BUILDING")
            building_id = f"B{index:03d}-{building_index:02d}"
            label = msp.add_mtext(
                building_id,
                dxfattribs={
                    "layer": "CONCEPT_LABEL",
                    "char_height": label_height,
                    "attachment_point": 5,
                },
            )
            point = building.centroid
            label.set_location(insert=(point.x, point.y, 0.0))
            width_m, depth_m = _polygon_dimensions_m(building, linear_scale)
            building_area_m2 = building.area * (linear_scale ** 2)
            building_setback_m = building.distance(parcel.boundary) * linear_scale
            minimum_setback_m = min(minimum_setback_m, building_setback_m)
            dimension_label = msp.add_mtext(
                f"{width_m:.1f} x {depth_m:.1f}m\n{building_area_m2:.1f}m2",
                dxfattribs={
                    "layer": "CONCEPT_DIMENSION",
                    "char_height": label_height * 0.8,
                    "attachment_point": 5,
                },
            )
            dimension_label.set_location(insert=(point.x, point.y - label_height * 2, 0.0))
            building_records.append({
                "type": "Building",
                "parcel_id": f"P{index:03d}",
                "feature_id": building_id,
                "area_m2": building_area_m2,
                "width_m": width_m,
                "depth_m": depth_m,
                "floors": floors if floors is not None else "",
                "estimated_gfa_m2": (
                    building_area_m2 * floors if floors is not None else ""
                ),
                "min_setback_m": building_setback_m,
                "requested_building_gap_m": building_gap_m,
            })
        building_total += len(parcel_buildings)
        parcel_footprint_m2 = sum(building.area for building in parcel_buildings) * (linear_scale ** 2)
        building_footprint_m2 += parcel_footprint_m2
        if estimated_gfa_m2 is not None:
            estimated_gfa_m2 += parcel_footprint_m2 * floors

        parcel_parking_required = 0
        if floors is not None and parking_ratio:
            parcel_gfa_m2 = parcel_footprint_m2 * floors
            parcel_parking_required = math.ceil(parcel_gfa_m2 / 1000.0 * parking_ratio)
        parking_required_total += parcel_parking_required
        parking_slots = _make_parking_slots(
            building_area,
            parcel_buildings,
            parcel_parking_required,
            linear_scale,
        )
        for parking_index, parking in enumerate(parking_slots, start=1):
            _add_polygon(msp, parking, "CONCEPT_PARKING")
            parking_label = msp.add_mtext(
                f"P{index:03d}-{parking_index:02d}",
                dxfattribs={
                    "layer": "CONCEPT_LABEL",
                    "char_height": label_height * 0.8,
                    "attachment_point": 5,
                },
            )
            point = parking.centroid
            parking_label.set_location(insert=(point.x, point.y, 0.0))
        parking_generated_total += len(parking_slots)
        parking_unplaced_total += max(0, parcel_parking_required - len(parking_slots))
        if len(parcel_buildings) > 1:
            for first_index, first in enumerate(parcel_buildings):
                for second in parcel_buildings[first_index + 1:]:
                    minimum_building_gap_m = min(
                        minimum_building_gap_m,
                        first.distance(second) * linear_scale,
                    )

        occupied = parcel_buildings + parking_slots
        remaining = building_area.difference(unary_union(occupied)) if occupied else building_area
        for green_part in _iter_polygons(remaining):
            if green_part.area > 1e-9:
                _add_polygon(msp, green_part, "CONCEPT_GREEN")
                green_total += 1
                green_area_m2 += green_part.area * (linear_scale ** 2)

    note = msp.add_mtext(
        "CONCEPT PLAN - CONCEPTUAL ONLY - NOT FOR APPROVAL",
        dxfattribs={"layer": "CONCEPT_LABEL", "char_height": label_height},
    )
    minx = min(parcel.bounds[0] for parcel in parcels)
    miny = min(parcel.bounds[1] for parcel in parcels)
    note.set_location(insert=(minx, miny - label_height * 3, 0.0))

    doc.saveas(output_path)
    assert_file_unchanged(source, source_hash)

    schedule_path = (Path(output_dir) / f"{source.stem}_concept_plan_schedule.csv").resolve()
    if math.isinf(minimum_setback_m):
        minimum_setback_m = None
    if math.isinf(minimum_building_gap_m):
        minimum_building_gap_m = None
    actual_coverage_ratio = (
        building_footprint_m2 / parcel_area_m2 if parcel_area_m2 > 0 else 0.0
    )
    estimated_far = (
        estimated_gfa_m2 / parcel_area_m2
        if estimated_gfa_m2 is not None and parcel_area_m2 > 0
        else None
    )

    with schedule_path.open("w", encoding="utf-8-sig", newline="") as schedule:
        fieldnames = [
            "type", "parcel_id", "feature_id", "area_m2", "width_m", "depth_m",
            "floors", "estimated_gfa_m2", "min_setback_m", "requested_building_gap_m",
        ]
        writer = csv.DictWriter(schedule, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(building_records)

    estimated_gfa_text = (
        f"{estimated_gfa_m2:.2f}" if estimated_gfa_m2 is not None else "not specified"
    )
    with report_path.open("w", encoding="utf-8") as report:
        report.write("=== Planning Toolbox Concept Plan Report ===\n")
        report.write("This output is a conceptual sketch and is not a regulatory or construction drawing.\n")
        report.write(f"Source DXF: {source.name}\n")
        report.write(f"Source SHA-256: {source_hash}\n")
        report.write(f"Detected Unit: {unit_name}\n")
        report.write(f"Parcel Layer: {parcel_layer}\n")
        report.write(f"Valid Parcels: {len(parcels)}\n")
        report.write(f"Requested Buildings Per Parcel: {building_count}\n")
        report.write(f"Coverage Ratio: {coverage_ratio:.4f}\n")
        report.write(f"Setback (m): {setback_m:g}\n")
        report.write(f"Requested Building Gap (m): {building_gap_m:g}\n")
        report.write(f"Concept Access / Fire Corridor Width (m): {access_width_m:g}\n")
        report.write(f"Layout Style: {layout_style}\n")
        report.write(f"Standards Profile: {standards_profile.name}\n")
        report.write(f"Standards References: {standards_profile.reference_summary()}\n")
        report.write(
            "Standards Note: This is a guided study reference, not a compliance conclusion. "
            "Verify the latest local and project-specific requirements.\n"
        )
        report.write(f"Floors: {floors if floors is not None else 'not specified'}\n")
        report.write(
            f"Parking Ratio (spaces per 1000m2): "
            f"{parking_ratio if parking_ratio is not None else 'not specified'}\n"
        )
        report.write(f"Parcel Area (m2): {parcel_area_m2:.2f}\n")
        report.write(f"Building Footprint Area (m2): {building_footprint_m2:.2f}\n")
        report.write(f"Estimated Gross Floor Area (m2): {estimated_gfa_text}\n")
        report.write(f"Actual Coverage Ratio: {actual_coverage_ratio:.4f}\n")
        report.write(
            f"Estimated FAR: {estimated_far:.4f}\n"
            if estimated_far is not None
            else "Estimated FAR: not specified\n"
        )
        report.write(
            f"Minimum Generated Building Setback (m): {minimum_setback_m:.3f}\n"
            if minimum_setback_m is not None
            else "Minimum Generated Building Setback (m): not available\n"
        )
        report.write(
            f"Minimum Generated Building Gap (m): {minimum_building_gap_m:.3f}\n"
            if minimum_building_gap_m is not None
            else "Minimum Generated Building Gap (m): not available\n"
        )
        report.write(f"Generated Building Footprints: {building_total}\n")
        report.write(f"Generated Green-space Polygons: {green_total}\n")
        report.write(f"Green-space Area (m2): {green_area_m2:.2f}\n")
        report.write(f"Concept Access / Fire Corridor Area (m2): {access_corridor_m2:.2f}\n")
        report.write(f"Required Concept Parking Bays: {parking_required_total}\n")
        report.write(f"Generated Concept Parking Bays: {parking_generated_total}\n")
        report.write(f"Unplaced Concept Parking Bays: {parking_unplaced_total}\n")
        report.write(f"Parcels Without Usable Area: {skipped_parcels}\n")
        report.write(
            "Layers: CONCEPT_SETBACK, CONCEPT_BUILDING, CONCEPT_PARKING, "
            "CONCEPT_GREEN, CONCEPT_ROAD, CONCEPT_LABEL, CONCEPT_DIMENSION\n"
        )

    return {
        "task_type": "concept_plan",
        "source_file": str(source),
        "source_sha256": source_hash,
        "unit_name": unit_name,
        "parcels_count": len(parcels),
        "parcel_area_m2": parcel_area_m2,
        "building_count_requested": building_count,
        "building_footprints": building_total,
        "building_footprint_m2": building_footprint_m2,
        "actual_coverage_ratio": actual_coverage_ratio,
        "building_gap_m": building_gap_m,
        "access_width_m": access_width_m,
        "layout_style": layout_style,
        "access_corridor_m2": access_corridor_m2,
        "standards_profile_id": standards_profile.profile_id,
        "standards_profile_name": standards_profile.name,
        "standards_references": standards_profile.reference_codes,
        "minimum_setback_m": minimum_setback_m,
        "minimum_building_gap_m": minimum_building_gap_m,
        "floors": floors,
        "estimated_gfa_m2": estimated_gfa_m2,
        "estimated_far": estimated_far,
        "parking_ratio": parking_ratio,
        "parking_required": parking_required_total,
        "parking_generated": parking_generated_total,
        "parking_unplaced": parking_unplaced_total,
        "green_polygons": green_total,
        "green_area_m2": green_area_m2,
        "skipped_parcels": skipped_parcels,
        "output_files": [
            ("概念方案 DXF", str(output_path)),
            ("概念方案报告", str(report_path)),
            ("概念方案明细表", str(schedule_path)),
        ],
    }
