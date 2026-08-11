"""Convert a standardized planning image into a reviewable concept DXF.

This is deliberately a local, explainable vectorization workflow.  It is not
an image-generating AI model and it does not pretend that a perspective render
contains survey-grade coordinates.  The supported first version expects a
top-down image with a small, documented planning color palette.  Every output
is marked as a concept conversion and should be visually confirmed by the
user before further analysis.
"""

from __future__ import annotations

from collections import defaultdict
from math import acos, atan2, cos, degrees, floor, radians, sin
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import ezdxf
import numpy as np
from ezdxf.colors import RGB
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.ops import nearest_points, unary_union
from skimage.measure import find_contours, label, regionprops
from skimage.morphology import (
    binary_closing,
    disk,
    medial_axis,
    remove_small_objects,
    skeletonize,
)

from planning_toolbox.cad.planning.semantic_palette import SEMANTIC_GUIDE_PALETTE
from planning_toolbox.project.quality_baseline import (
    write_image_to_cad_quality_baseline,
)
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


# Muted colors are intentionally close to the visual language used by the
# Planning Toolbox UI and easy for an AI-generated top-down image to follow.
IMAGE_PALETTE: Dict[str, Tuple[int, int, int]] = SEMANTIC_GUIDE_PALETTE
_ROAD_CENTERLINE_TRUST_THRESHOLD = 0.65
_PRESENTATION_FILL_APPID = "PT_PRESENTATION_FILL"


def _ensure_layer(doc, name: str, color: int) -> None:
    if name not in doc.layers:
        doc.layers.add(name=name, color=color)


def _style_layer(
    doc,
    name: str,
    *,
    aci_color: int,
    rgb: tuple[int, int, int],
    lineweight: int,
) -> None:
    """Apply a low-saturation ByLayer style with an ACI fallback."""
    _ensure_layer(doc, name, aci_color)
    layer = doc.layers.get(name)
    layer.dxf.color = int(aci_color)
    layer.rgb = RGB(*rgb)
    layer.dxf.lineweight = int(lineweight)


def _add_presentation_hatch(
    msp,
    polygon: Polygon,
    *,
    layer: str,
    rgb: tuple[int, int, int],
    transparency: float = 0.78,
) -> bool:
    """Add a removable translucent fill without changing boundary geometry."""
    points = [
        (float(x), float(y))
        for x, y in list(polygon.exterior.coords)[:-1]
    ]
    if len(points) < 3:
        return False
    hatch = msp.add_hatch(dxfattribs={"layer": layer})
    hatch.set_solid_fill(rgb=RGB(*rgb))
    hatch.transparency = float(transparency)
    hatch.paths.add_polyline_path(points, is_closed=True)
    hatch.set_xdata(
        _PRESENTATION_FILL_APPID,
        [(1000, "display_only_semantic_fill"), (1000, str(layer))],
    )
    return True


def _iter_polygon_parts(geometry) -> Iterable[Polygon]:
    if geometry is None or geometry.is_empty:
        return
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, MultiPolygon):
        for part in geometry.geoms:
            yield from _iter_polygon_parts(part)
    elif isinstance(geometry, GeometryCollection):
        for part in geometry.geoms:
            yield from _iter_polygon_parts(part)


def _add_polygon(msp, polygon: Polygon, layer: str) -> None:
    points = [(float(x), float(y)) for x, y in list(polygon.exterior.coords)[:-1]]
    if len(points) >= 3:
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _component_polygons(
    mask: np.ndarray,
    pixel_size_m: float,
    min_component_pixels: int,
    simplify_m: float,
    closing_radius: int = 1,
) -> List[Polygon]:
    """Trace connected raster regions into simplified CAD polygons."""
    if not np.any(mask):
        return []

    cleaned = binary_closing(mask, footprint=disk(max(1, int(closing_radius))))
    cleaned = remove_small_objects(cleaned, min_size=min_component_pixels)
    labeled = label(cleaned, connectivity=2)
    image_height = mask.shape[0]
    polygons: List[Polygon] = []

    for region in regionprops(labeled):
        if region.area < min_component_pixels:
            continue
        component = labeled == region.label
        contours = find_contours(component.astype(np.float32), 0.5)
        if not contours:
            continue
        contour = max(contours, key=len)
        coordinates = [
            (float(column) * pixel_size_m, (image_height - float(row)) * pixel_size_m)
            for row, column in contour
        ]
        polygon = Polygon(coordinates)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        polygon = polygon.simplify(simplify_m, preserve_topology=True)
        for part in _iter_polygon_parts(polygon):
            if part.area >= min_component_pixels * pixel_size_m**2 * 0.25:
                polygons.append(part)
    return polygons


def _classify_pixels(image: np.ndarray, tolerance: int):
    palette_names = list(IMAGE_PALETTE)
    palette = np.asarray([IMAGE_PALETTE[name] for name in palette_names], dtype=np.float32)
    distances = ((image[:, :, None, :] - palette[None, None, :, :]) ** 2).sum(axis=3) ** 0.5
    nearest = distances.argmin(axis=2)
    nearest_distance = distances.min(axis=2)
    masks = {
        name: (nearest == index) & (nearest_distance <= tolerance)
        for index, name in enumerate(palette_names)
    }
    preview = np.full(image.shape, 250, dtype=np.uint8)
    for index, name in enumerate(palette_names):
        preview[masks[name]] = np.asarray(IMAGE_PALETTE[name], dtype=np.uint8)
    return masks, preview


def _site_focus_bbox(masks: Dict[str, np.ndarray]) -> tuple[int, int, int, int] | None:
    """Find the combined non-road site envelope for optional noise filtering."""
    landuse_masks = [
        mask for name, mask in masks.items()
        if name != "AI_ROAD"
    ]
    if not landuse_masks:
        return None
    landuse = np.logical_or.reduce(landuse_masks)
    if not np.any(landuse):
        return None

    rows, columns = np.where(landuse)
    min_row, max_row = int(rows.min()), int(rows.max()) + 1
    min_col, max_col = int(columns.min()), int(columns.max()) + 1
    height, width = landuse.shape
    pad_y = max(4, int((max_row - min_row) * 0.04))
    pad_x = max(4, int((max_col - min_col) * 0.04))
    return (
        max(0, min_col - pad_x),
        max(0, min_row - pad_y),
        min(width, max_col + pad_x),
        min(height, max_row + pad_y),
    )


def _apply_site_focus(
    masks: Dict[str, np.ndarray],
    bbox: tuple[int, int, int, int] | None,
) -> bool:
    """Keep classified regions inside the dominant site envelope."""
    if bbox is None:
        return False
    min_col, min_row, max_col, max_row = bbox
    focus = np.zeros_like(next(iter(masks.values())), dtype=bool)
    focus[min_row:max_row, min_col:max_col] = True
    for name in masks:
        if name != "AI_ROAD":
            masks[name] &= focus

    # A surrounding city road can overlap the rectangular envelope while
    # still extending far outside it. Keep the site-side part, but trim a
    # narrow boundary band so connected entrance roads are not lost.
    if "AI_ROAD" in masks:
        road_focus = np.zeros_like(masks["AI_ROAD"], dtype=bool)
        margin = max(8, int(min(max_row - min_row, max_col - min_col) * 0.06))
        road_focus[
            min_row + margin:max_row - margin,
            min_col + margin:max_col - margin,
        ] = True
        masks["AI_ROAD"] &= road_focus
    return True


def _trace_skeleton_paths(skeleton: np.ndarray) -> List[List[Tuple[int, int]]]:
    """Trace a one-pixel skeleton into CAD-friendly centerline paths."""
    pixels = {tuple(point) for point in np.argwhere(skeleton)}
    offsets = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1), (0, 1),
        (1, -1), (1, 0), (1, 1),
    )
    adjacency: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for row, column in pixels:
        neighbours: List[Tuple[int, int]] = []
        for delta_row, delta_column in offsets:
            neighbour = (row + delta_row, column + delta_column)
            if neighbour not in pixels:
                continue
            # Avoid triangular shortcut edges around right-angle corners.
            if delta_row and delta_column and (
                (row + delta_row, column) in pixels
                or (row, column + delta_column) in pixels
            ):
                continue
            neighbours.append(neighbour)
        adjacency[(row, column)] = neighbours

    def edge_key(
        first: Tuple[int, int],
        second: Tuple[int, int],
    ) -> tuple[Tuple[int, int], Tuple[int, int]]:
        return (first, second) if first <= second else (second, first)

    visited_edges = set()
    paths: List[List[Tuple[int, int]]] = []
    nodes = [point for point, neighbours in adjacency.items() if len(neighbours) != 2]

    for start in nodes:
        for neighbour in adjacency[start]:
            edge = edge_key(start, neighbour)
            if edge in visited_edges:
                continue
            visited_edges.add(edge)
            path = [start, neighbour]
            previous, current = start, neighbour
            while len(adjacency[current]) == 2:
                next_point = (
                    adjacency[current][0]
                    if adjacency[current][1] == previous
                    else adjacency[current][1]
                )
                next_edge = edge_key(current, next_point)
                if next_edge in visited_edges:
                    break
                visited_edges.add(next_edge)
                path.append(next_point)
                previous, current = current, next_point
            if len(path) >= 2:
                paths.append(path)

    # Closed loops have no endpoint or junction and need a second pass.
    for start in pixels:
        for neighbour in adjacency[start]:
            edge = edge_key(start, neighbour)
            if edge in visited_edges:
                continue
            visited_edges.add(edge)
            path = [start, neighbour]
            previous, current = start, neighbour
            while True:
                candidates = [
                    point for point in adjacency[current]
                    if point != previous
                ]
                if not candidates:
                    break
                next_point = candidates[0]
                next_edge = edge_key(current, next_point)
                if next_edge in visited_edges:
                    break
                visited_edges.add(next_edge)
                path.append(next_point)
                previous, current = current, next_point
                if current == start:
                    break
            if len(path) >= 2:
                paths.append(path)
    return paths


def _iter_line_parts(geometry) -> Iterable[LineString]:
    """Yield non-empty line parts from Shapely overlay results."""
    if geometry is None or geometry.is_empty:
        return
    if isinstance(geometry, LineString):
        yield geometry
    elif isinstance(geometry, (MultiLineString, GeometryCollection)):
        for part in geometry.geoms:
            yield from _iter_line_parts(part)


def _point_distance(first, second) -> float:
    return float(
        ((float(first[0]) - float(second[0])) ** 2
         + (float(first[1]) - float(second[1])) ** 2) ** 0.5
    )


def _merge_directional_centerlines(
    lines: List[LineString],
    tolerance: float,
    max_turn_degrees: float = 45.0,
) -> tuple[List[LineString], dict]:
    """Join centerline fragments only when their directions form a safe continuation.

    Skeleton tracing deliberately breaks paths at every junction.  At a T or X
    junction this routine pairs the most nearly straight-through endpoints and
    leaves the branch independent.  This protects a building outline when a
    pedestrian connection touches it, without blindly joining every nearby
    line into one uneditable network.
    """
    if len(lines) < 2:
        return lines, {
            "input_line_count": len(lines),
            "output_line_count": len(lines),
            "joined_fragment_count": 0,
            "joined_pair_count": 0,
            "max_endpoint_snap_distance": 0.0,
            "_source_line_groups": [[index] for index in range(len(lines))],
        }

    endpoint_records = []
    for line_index, line in enumerate(lines):
        coordinates = list(line.coords)
        if len(coordinates) < 2:
            continue
        start_direction = (
            coordinates[1][0] - coordinates[0][0],
            coordinates[1][1] - coordinates[0][1],
        )
        end_direction = (
            coordinates[-2][0] - coordinates[-1][0],
            coordinates[-2][1] - coordinates[-1][1],
        )
        endpoint_records.extend((
            (line_index, 0, coordinates[0], start_direction),
            (line_index, 1, coordinates[-1], end_direction),
        ))

    parents = list(range(len(endpoint_records)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    buckets: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    safe_tolerance = max(float(tolerance), 1e-9)
    for index, record in enumerate(endpoint_records):
        point = record[2]
        cell = (
            floor(float(point[0]) / safe_tolerance),
            floor(float(point[1]) / safe_tolerance),
        )
        for delta_x in (-1, 0, 1):
            for delta_y in (-1, 0, 1):
                for candidate in buckets.get(
                    (cell[0] + delta_x, cell[1] + delta_y), []
                ):
                    if _point_distance(point, endpoint_records[candidate][2]) <= safe_tolerance:
                        union(index, candidate)
        buckets[cell].append(index)

    clusters: Dict[int, List[int]] = defaultdict(list)
    for index in range(len(endpoint_records)):
        clusters[find(index)].append(index)

    pair_map: Dict[Tuple[int, int], Tuple[int, int]] = {}
    cluster_centers: Dict[Tuple[int, int], Tuple[float, float]] = {}
    max_snap_distance = 0.0
    for indices in clusters.values():
        center = (
            sum(float(endpoint_records[index][2][0]) for index in indices) / len(indices),
            sum(float(endpoint_records[index][2][1]) for index in indices) / len(indices),
        )
        for index in indices:
            record = endpoint_records[index]
            endpoint_ref = (record[0], record[1])
            cluster_centers[endpoint_ref] = center
            max_snap_distance = max(
                max_snap_distance,
                _point_distance(record[2], center),
            )

        candidates = []
        for position, first_index in enumerate(indices):
            first = endpoint_records[first_index]
            first_length = max(_point_distance((0.0, 0.0), first[3]), 1e-12)
            first_direction = (
                float(first[3][0]) / first_length,
                float(first[3][1]) / first_length,
            )
            for second_index in indices[position + 1:]:
                second = endpoint_records[second_index]
                # Do not fold one path back into itself inside a busy junction.
                if first[0] == second[0] and len(indices) > 2:
                    continue
                second_length = max(_point_distance((0.0, 0.0), second[3]), 1e-12)
                second_direction = (
                    float(second[3][0]) / second_length,
                    float(second[3][1]) / second_length,
                )
                dot = max(-1.0, min(1.0, -(
                    first_direction[0] * second_direction[0]
                    + first_direction[1] * second_direction[1]
                )))
                turn = degrees(acos(dot))
                candidates.append((turn, first_index, second_index))

        used = set()
        for turn, first_index, second_index in sorted(candidates):
            if turn > float(max_turn_degrees):
                break
            if first_index in used or second_index in used:
                continue
            first = endpoint_records[first_index]
            second = endpoint_records[second_index]
            first_ref = (first[0], first[1])
            second_ref = (second[0], second[1])
            pair_map[first_ref] = second_ref
            pair_map[second_ref] = first_ref
            used.update((first_index, second_index))

    merged: List[LineString] = []
    source_line_groups: List[List[int]] = []
    visited_lines = set()
    for seed in range(len(lines)):
        if seed in visited_lines:
            continue
        unpaired_sides = [
            side for side in (0, 1)
            if (seed, side) not in pair_map
        ]
        enter_side = unpaired_sides[0] if unpaired_sides else 0
        current = seed
        source_group: List[int] = []
        coordinates = []
        closed = False
        while True:
            current_coordinates = list(lines[current].coords)
            oriented = (
                current_coordinates
                if enter_side == 0
                else list(reversed(current_coordinates))
            )
            exit_side = 1 - enter_side
            oriented[0] = cluster_centers.get((current, enter_side), oriented[0])
            oriented[-1] = cluster_centers.get((current, exit_side), oriented[-1])
            coordinates.extend(oriented if not coordinates else oriented[1:])
            visited_lines.add(current)
            source_group.append(current)

            exit_ref = (current, exit_side)
            if exit_ref not in pair_map:
                break
            next_ref = pair_map[exit_ref]
            if next_ref[0] in visited_lines:
                closed = next_ref[0] == seed
                break
            current, enter_side = next_ref

        deduplicated = [coordinates[0]]
        for point in coordinates[1:]:
            if _point_distance(point, deduplicated[-1]) > 1e-9:
                deduplicated.append(point)
        if closed and _point_distance(deduplicated[0], deduplicated[-1]) > 1e-9:
            deduplicated.append(deduplicated[0])
        if len(deduplicated) >= 2:
            merged.append(LineString(deduplicated))
            source_line_groups.append(source_group)

    return merged, {
        "input_line_count": len(lines),
        "output_line_count": len(merged),
        "joined_fragment_count": max(0, len(lines) - len(merged)),
        "joined_pair_count": len(pair_map) // 2,
        "max_endpoint_snap_distance": max_snap_distance,
        "_source_line_groups": source_line_groups,
    }


def _trusted_centerline_component_count(
    lines: List[LineString],
    tolerance_m: float,
) -> int:
    """Count connected trusted-road parts using a very small metric tolerance."""
    if not lines:
        return 0
    parents = list(range(len(lines)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    for first_index, first in enumerate(lines):
        for second_index in range(first_index + 1, len(lines)):
            if first.distance(lines[second_index]) <= float(tolerance_m):
                union(first_index, second_index)
    return len({find(index) for index in range(len(lines))})


def _snap_trusted_road_centerline_junctions(
    lines: List[LineString],
    widths_m: List[float],
    pixel_size_m: float,
) -> tuple[List[LineString], dict]:
    """Conservatively close tiny endpoint and T-junction gaps.

    This pass runs only after confidence filtering.  A candidate endpoint must
    point towards the proposed junction, and the movement is bounded by both
    source-image resolution and the narrower detected road width.  Competing
    T-junction targets at nearly the same distance are left untouched.
    """
    if len(lines) != len(widths_m):
        raise ValueError("可信道路中心线与宽度数量不一致。")
    if len(lines) < 2:
        return lines, {
            "junction_snap_count": 0,
            "junction_endpoint_cluster_count": 0,
            "junction_t_connection_count": 0,
            "maximum_junction_snap_distance_m": 0.0,
            "trusted_network_component_count_before": len(lines),
            "trusted_network_component_count_after": len(lines),
            "ambiguous_junction_count": 0,
        }

    coordinates = [list(line.coords) for line in lines]
    connectivity_tolerance = max(float(pixel_size_m) * 0.12, 1e-6)
    component_count_before = _trusted_centerline_component_count(
        lines, connectivity_tolerance
    )

    def pair_tolerance(first_width: float, second_width: float) -> float:
        narrower = min(float(first_width), float(second_width))
        return max(
            float(pixel_size_m) * 1.25,
            min(float(pixel_size_m) * 4.0, narrower * 0.20),
        )

    def outward_vector(line_index: int, side: int) -> tuple[float, float]:
        points = coordinates[line_index]
        if side == 0:
            return (
                float(points[0][0]) - float(points[1][0]),
                float(points[0][1]) - float(points[1][1]),
            )
        return (
            float(points[-1][0]) - float(points[-2][0]),
            float(points[-1][1]) - float(points[-2][1]),
        )

    def forward_cosine(
        direction: tuple[float, float],
        movement: tuple[float, float],
    ) -> float:
        direction_length = max(_point_distance((0.0, 0.0), direction), 1e-12)
        movement_length = max(_point_distance((0.0, 0.0), movement), 1e-12)
        return (
            direction[0] * movement[0] + direction[1] * movement[1]
        ) / (direction_length * movement_length)

    endpoint_records = [
        (line_index, side)
        for line_index, points in enumerate(coordinates)
        if len(points) >= 2
        for side in (0, 1)
    ]
    parents = list(range(len(endpoint_records)))

    def find_endpoint(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union_endpoint(first: int, second: int) -> None:
        first_root, second_root = find_endpoint(first), find_endpoint(second)
        if first_root != second_root:
            parents[second_root] = first_root

    for first_index, (first_line, first_side) in enumerate(endpoint_records):
        first_point = coordinates[first_line][0 if first_side == 0 else -1]
        for second_index in range(first_index + 1, len(endpoint_records)):
            second_line, second_side = endpoint_records[second_index]
            if first_line == second_line:
                continue
            width_ratio = min(widths_m[first_line], widths_m[second_line]) / max(
                widths_m[first_line], widths_m[second_line], 1e-9
            )
            if width_ratio < 0.35:
                continue
            second_point = coordinates[second_line][0 if second_side == 0 else -1]
            distance_m = _point_distance(first_point, second_point)
            if not connectivity_tolerance < distance_m <= pair_tolerance(
                widths_m[first_line], widths_m[second_line]
            ):
                continue
            movement = (
                float(second_point[0]) - float(first_point[0]),
                float(second_point[1]) - float(first_point[1]),
            )
            if forward_cosine(outward_vector(first_line, first_side), movement) < 0.45:
                continue
            if forward_cosine(
                outward_vector(second_line, second_side),
                (-movement[0], -movement[1]),
            ) < 0.45:
                continue
            union_endpoint(first_index, second_index)

    endpoint_clusters: Dict[int, List[int]] = defaultdict(list)
    for index in range(len(endpoint_records)):
        endpoint_clusters[find_endpoint(index)].append(index)
    clustered_refs: set[tuple[int, int]] = set()
    endpoint_cluster_count = 0
    maximum_snap_distance = 0.0
    for indices in endpoint_clusters.values():
        if len(indices) < 2:
            continue
        points = []
        for index in indices:
            line_index, side = endpoint_records[index]
            points.append(coordinates[line_index][0 if side == 0 else -1])
        center = (
            sum(float(point[0]) for point in points) / len(points),
            sum(float(point[1]) for point in points) / len(points),
        )
        endpoint_cluster_count += 1
        for index, point in zip(indices, points):
            line_index, side = endpoint_records[index]
            maximum_snap_distance = max(
                maximum_snap_distance, _point_distance(point, center)
            )
            coordinates[line_index][0 if side == 0 else -1] = center
            clustered_refs.add((line_index, side))

    working_lines = [LineString(points) for points in coordinates]
    t_connection_count = 0
    ambiguous_junction_count = 0
    for line_index, points in enumerate(coordinates):
        for side in (0, 1):
            if (line_index, side) in clustered_refs:
                continue
            endpoint = points[0 if side == 0 else -1]
            endpoint_point = Point(endpoint)
            if any(
                target_index != line_index
                and endpoint_point.distance(target) <= connectivity_tolerance
                for target_index, target in enumerate(working_lines)
            ):
                continue
            direction = outward_vector(line_index, side)
            candidates = []
            for target_index, target in enumerate(working_lines):
                if target_index == line_index or target.length <= 0:
                    continue
                width_ratio = min(widths_m[line_index], widths_m[target_index]) / max(
                    widths_m[line_index], widths_m[target_index], 1e-9
                )
                if width_ratio < 0.35:
                    continue
                station = float(target.project(endpoint_point))
                endpoint_margin = max(float(pixel_size_m) * 0.5, target.length * 0.01)
                if not endpoint_margin < station < target.length - endpoint_margin:
                    continue
                projected = target.interpolate(station)
                target_point = (float(projected.x), float(projected.y))
                distance_m = _point_distance(endpoint, target_point)
                if not connectivity_tolerance < distance_m <= pair_tolerance(
                    widths_m[line_index], widths_m[target_index]
                ):
                    continue
                movement = (
                    target_point[0] - float(endpoint[0]),
                    target_point[1] - float(endpoint[1]),
                )
                if forward_cosine(direction, movement) < 0.70:
                    continue
                candidates.append((distance_m, target_index, target_point))
            candidates.sort(key=lambda value: value[0])
            if not candidates:
                continue
            if (
                len(candidates) > 1
                and candidates[1][0] - candidates[0][0]
                <= float(pixel_size_m) * 0.35
                and _point_distance(candidates[0][2], candidates[1][2])
                > connectivity_tolerance
            ):
                ambiguous_junction_count += 1
                continue
            distance_m, _target_index, target_point = candidates[0]
            coordinates[line_index][0 if side == 0 else -1] = target_point
            working_lines[line_index] = LineString(coordinates[line_index])
            maximum_snap_distance = max(maximum_snap_distance, distance_m)
            t_connection_count += 1

    snapped_lines = [LineString(points) for points in coordinates]
    return snapped_lines, {
        "junction_snap_count": endpoint_cluster_count + t_connection_count,
        "junction_endpoint_cluster_count": endpoint_cluster_count,
        "junction_t_connection_count": t_connection_count,
        "maximum_junction_snap_distance_m": round(maximum_snap_distance, 4),
        "trusted_network_component_count_before": component_count_before,
        "trusted_network_component_count_after": _trusted_centerline_component_count(
            snapped_lines, connectivity_tolerance
        ),
        "ambiguous_junction_count": ambiguous_junction_count,
    }


def _merge_road_centerline_candidates(
    lines: List[LineString],
    widths_m: List[float],
    confidences: List[float],
    pixel_size_m: float,
) -> tuple[List[LineString], List[float], List[float], dict]:
    """Conservatively join image-derived road fragments before CAD/SU handoff.

    Only trusted fragments in the same width bucket may join. Review-required
    fragments stay untouched, so joining can never promote a weak candidate
    above the modeling threshold. The maximum bridge is bounded by both image
    resolution and the detected road width.
    """
    count = len(lines)
    if len(widths_m) != count or len(confidences) != count:
        raise ValueError("道路中心线、宽度与可信度数量不一致。")
    if count < 2:
        return lines, widths_m, confidences, {
            "policy": "trusted_width_compatible_directional_with_bounded_junction_snap",
            "input_line_count": count,
            "output_line_count": count,
            "trusted_input_count": sum(
                value >= _ROAD_CENTERLINE_TRUST_THRESHOLD
                for value in confidences
            ),
            "review_input_count": sum(
                value < _ROAD_CENTERLINE_TRUST_THRESHOLD
                for value in confidences
            ),
            "joined_fragment_count": 0,
            "joined_pair_count": 0,
            "maximum_bridge_gap_m": 0.0,
            "width_compatibility_ratio": 0.25,
            "maximum_turn_degrees": 22.5,
            "junction_snap_count": 0,
            "junction_endpoint_cluster_count": 0,
            "junction_t_connection_count": 0,
            "maximum_junction_snap_distance_m": 0.0,
            "trusted_network_component_count_before": count,
            "trusted_network_component_count_after": count,
            "ambiguous_junction_count": 0,
        }

    items = [
        {
            "index": index,
            "line": line,
            "width_m": float(width),
            "confidence": float(confidence),
        }
        for index, (line, width, confidence) in enumerate(
            zip(lines, widths_m, confidences)
        )
    ]
    trusted = [
        item
        for item in items
        if item["confidence"] >= _ROAD_CENTERLINE_TRUST_THRESHOLD
    ]
    review = [
        item
        for item in items
        if item["confidence"] < _ROAD_CENTERLINE_TRUST_THRESHOLD
    ]

    width_buckets: List[List[dict]] = []
    for item in sorted(trusted, key=lambda value: (value["width_m"], value["index"])):
        target = None
        for bucket in width_buckets:
            center_width = sum(value["width_m"] for value in bucket) / len(bucket)
            relative_difference = abs(item["width_m"] - center_width) / max(
                item["width_m"], center_width, 1e-9
            )
            if relative_difference <= 0.25:
                target = bucket
                break
        if target is None:
            target = []
            width_buckets.append(target)
        target.append(item)

    output_records: List[dict] = []
    joined_fragment_count = 0
    joined_pair_count = 0
    maximum_bridge_gap_m = 0.0
    for bucket in width_buckets:
        bucket_width = sum(value["width_m"] for value in bucket) / len(bucket)
        tolerance_m = max(
            float(pixel_size_m) * 2.0,
            min(float(pixel_size_m) * 12.0, bucket_width * 0.95),
        )
        merged_lines, merge_stats = _merge_directional_centerlines(
            [value["line"] for value in bucket],
            tolerance=tolerance_m,
            max_turn_degrees=22.5,
        )
        source_groups = merge_stats.pop("_source_line_groups", [])
        joined_fragment_count += int(merge_stats["joined_fragment_count"])
        joined_pair_count += int(merge_stats["joined_pair_count"])
        maximum_bridge_gap_m = max(
            maximum_bridge_gap_m,
            float(merge_stats["max_endpoint_snap_distance"]) * 2.0,
        )
        for merged_line, local_group in zip(merged_lines, source_groups):
            source_items = [bucket[index] for index in local_group]
            weights = [max(value["line"].length, 1e-9) for value in source_items]
            total_weight = sum(weights)
            output_records.append(
                {
                    "order": min(value["index"] for value in source_items),
                    "line": merged_line,
                    "width_m": sum(
                        value["width_m"] * weight
                        for value, weight in zip(source_items, weights)
                    )
                    / total_weight,
                    "confidence": sum(
                        value["confidence"] * weight
                        for value, weight in zip(source_items, weights)
                    )
                    / total_weight,
                }
            )

    snapped_trusted_lines, junction_stats = _snap_trusted_road_centerline_junctions(
        [value["line"] for value in output_records],
        [float(value["width_m"]) for value in output_records],
        float(pixel_size_m),
    )
    for record, snapped_line in zip(output_records, snapped_trusted_lines):
        record["line"] = snapped_line

    output_records.extend(
        {
            "order": item["index"],
            "line": item["line"],
            "width_m": item["width_m"],
            "confidence": item["confidence"],
        }
        for item in review
    )
    output_records.sort(key=lambda value: value["order"])
    return (
        [value["line"] for value in output_records],
        [float(value["width_m"]) for value in output_records],
        [float(value["confidence"]) for value in output_records],
        {
            "policy": "trusted_width_compatible_directional_with_bounded_junction_snap",
            "input_line_count": count,
            "output_line_count": len(output_records),
            "trusted_input_count": len(trusted),
            "review_input_count": len(review),
            "joined_fragment_count": joined_fragment_count,
            "joined_pair_count": joined_pair_count,
            "maximum_bridge_gap_m": round(maximum_bridge_gap_m, 4),
            "width_compatibility_ratio": 0.25,
            "maximum_turn_degrees": 22.5,
            **junction_stats,
        },
    )


def _polygon_from_region(
    labeled: np.ndarray,
    region,
    image_height: int,
    pixel_size_m: float,
    simplify_m: float,
) -> Polygon | None:
    """Convert one enclosed raster region into its largest valid polygon."""
    component = labeled == region.label
    contours = find_contours(component.astype(np.float32), 0.5)
    if not contours:
        return None
    contour = max(contours, key=len)
    polygon = Polygon([
        (
            float(column) * pixel_size_m,
            (image_height - float(row)) * pixel_size_m,
        )
        for row, column in contour
    ])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    polygon = polygon.buffer(pixel_size_m * 0.75, join_style=2)
    polygon = polygon.simplify(simplify_m, preserve_topology=True)
    parts = [part for part in _iter_polygon_parts(polygon) if not part.is_empty]
    return max(parts, key=lambda part: part.area) if parts else None


def _oriented_rectangle_metrics(polygon: Polygon) -> dict | None:
    """Describe the minimum rotated rectangle around a valid polygon."""
    rectangle = polygon.minimum_rotated_rectangle
    if rectangle.is_empty or rectangle.area <= 0:
        return None
    points = list(rectangle.exterior.coords)[:4]
    if len(points) != 4:
        return None
    edges = [
        (
            points[(index + 1) % 4][0] - points[index][0],
            points[(index + 1) % 4][1] - points[index][1],
        )
        for index in range(4)
    ]
    lengths = [_point_distance((0.0, 0.0), edge) for edge in edges]
    major_index = max(range(4), key=lambda index: lengths[index])
    major_length = float(lengths[major_index])
    minor_length = float(min(lengths))
    if major_length <= 0 or minor_length <= 0:
        return None
    major_edge = edges[major_index]
    return {
        "rectangle": rectangle,
        "major_length": major_length,
        "minor_length": minor_length,
        "aspect": major_length / minor_length,
        "rotation": degrees(atan2(major_edge[1], major_edge[0])) % 180.0,
        "rectangularity": float(polygon.area / rectangle.area),
    }


def _nearest_curated_size(
    major_length: float,
    minor_length: float,
    templates: list[dict],
    maximum_relative_error: float,
) -> dict | None:
    """Return a close user-curated size; never extrapolate a distant sample."""
    best: dict | None = None
    best_score = float("inf")
    for template in templates:
        try:
            target_major = float(template["major_m"])
            target_minor = float(template["minor_m"])
        except (KeyError, TypeError, ValueError):
            continue
        if target_major <= 0 or target_minor <= 0:
            continue
        major_error = abs(major_length - target_major) / max(
            major_length, target_major, 1e-9
        )
        minor_error = abs(minor_length - target_minor) / max(
            minor_length, target_minor, 1e-9
        )
        if max(major_error, minor_error) > maximum_relative_error:
            continue
        aspect_error = abs(
            major_length / max(minor_length, 1e-9)
            - target_major / max(target_minor, 1e-9)
        )
        score = major_error + minor_error + 0.15 * aspect_error
        score -= min(0.05, int(template.get("count", 1) or 1) * 0.002)
        if score < best_score:
            best_score = score
            best = {
                "major_m": target_major,
                "minor_m": target_minor,
                "relative_error_before": max(major_error, minor_error),
            }
    return best


def _rectangle_polygon(
    center_x: float,
    center_y: float,
    major_length: float,
    minor_length: float,
    rotation_degrees: float,
) -> Polygon:
    angle = radians(rotation_degrees)
    major_x, major_y = cos(angle), sin(angle)
    minor_x, minor_y = -major_y, major_x
    half_major = major_length / 2.0
    half_minor = minor_length / 2.0
    points = []
    for major_sign, minor_sign in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        points.append(
            (
                center_x
                + major_sign * half_major * major_x
                + minor_sign * half_minor * minor_x,
                center_y
                + major_sign * half_major * major_y
                + minor_sign * half_minor * minor_y,
            )
        )
    return Polygon(points)


def _apply_knowledge_geometry_profile(
    building_candidates: List[Polygon],
    tree_candidates: List[dict],
    parking_candidates: List[dict],
    profile: dict | None,
) -> tuple[List[Polygon], List[dict], List[dict], dict]:
    """Snap only near-matching candidates to dimensions from curated DXFs."""
    enabled = bool(profile and profile.get("enabled"))
    stats = {
        "profile_found": enabled,
        "profile_id": str(profile.get("profile_id", "")) if profile else "",
        "matched_card_count": int(profile.get("matched_card_count", 0)) if profile else 0,
        "curated_cad_count": int(profile.get("curated_cad_count", 0)) if profile else 0,
        "adjusted_buildings": 0,
        "adjusted_parking_stalls": 0,
        "adjusted_trees": 0,
        "knowledge_promoted_parking_stalls": 0,
        "adjustment_count": 0,
        "maximum_relative_adjustment": 0.0,
        "geometry_policy": "near_match_snap_only",
        "disabled_reason": str(profile.get("disabled_reason", "")) if profile else "",
        "details": [],
    }
    if not enabled:
        return building_candidates, tree_candidates, parking_candidates, stats
    stats["knowledge_promoted_parking_stalls"] = sum(
        1 for candidate in parking_candidates if candidate.get("knowledge_promoted")
    )

    adjusted_buildings: List[Polygon] = []
    for polygon in building_candidates:
        oriented = _oriented_rectangle_metrics(polygon)
        match = None
        if oriented is not None and oriented["rectangularity"] >= 0.88:
            match = _nearest_curated_size(
                oriented["major_length"],
                oriented["minor_length"],
                list(profile.get("building_sizes_m", [])),
                maximum_relative_error=0.25,
            )
        if match is None or match["relative_error_before"] <= 0.002:
            adjusted_buildings.append(polygon)
            continue
        center = oriented["rectangle"].centroid
        adjusted = _rectangle_polygon(
            float(center.x),
            float(center.y),
            match["major_m"],
            match["minor_m"],
            oriented["rotation"],
        )
        adjusted_buildings.append(adjusted)
        stats["adjusted_buildings"] += 1
        stats["maximum_relative_adjustment"] = max(
            stats["maximum_relative_adjustment"], match["relative_error_before"]
        )
        stats["details"].append(
            {
                "type": "building",
                "before_m": [round(oriented["major_length"], 3), round(oriented["minor_length"], 3)],
                "after_m": [round(match["major_m"], 3), round(match["minor_m"], 3)],
            }
        )

    adjusted_parking: List[dict] = []
    for candidate in parking_candidates:
        adjusted = dict(candidate)
        match = _nearest_curated_size(
            float(candidate["length"]),
            float(candidate["width"]),
            list(profile.get("parking_sizes_m", [])),
            maximum_relative_error=0.32,
        )
        if match is not None and match["relative_error_before"] > 0.002:
            adjusted["length"] = match["major_m"]
            adjusted["width"] = match["minor_m"]
            stats["adjusted_parking_stalls"] += 1
            stats["maximum_relative_adjustment"] = max(
                stats["maximum_relative_adjustment"], match["relative_error_before"]
            )
            stats["details"].append(
                {
                    "type": "parking",
                    "before_m": [round(float(candidate["length"]), 3), round(float(candidate["width"]), 3)],
                    "after_m": [round(match["major_m"], 3), round(match["minor_m"], 3)],
                }
            )
        adjusted_parking.append(adjusted)

    radius_templates = []
    for template in profile.get("tree_radii_m", []):
        try:
            radius_templates.append(float(template["radius_m"]))
        except (KeyError, TypeError, ValueError):
            continue
    adjusted_trees: List[dict] = []
    for candidate in tree_candidates:
        adjusted = dict(candidate)
        radius = float(candidate["radius"])
        close_radii = [
            target for target in radius_templates
            if abs(radius - target) / max(radius, target, 1e-9) <= 0.30
        ]
        if close_radii:
            target = min(close_radii, key=lambda value: abs(radius - value))
            relative_error = abs(radius - target) / max(radius, target, 1e-9)
            if relative_error > 0.002:
                adjusted["radius"] = target
                stats["adjusted_trees"] += 1
                stats["maximum_relative_adjustment"] = max(
                    stats["maximum_relative_adjustment"], relative_error
                )
                stats["details"].append(
                    {
                        "type": "tree",
                        "before_m": round(radius, 3),
                        "after_m": round(target, 3),
                    }
                )
        adjusted_trees.append(adjusted)

    stats["adjustment_count"] = (
        stats["adjusted_buildings"]
        + stats["adjusted_parking_stalls"]
        + stats["adjusted_trees"]
    )
    stats["maximum_relative_adjustment"] = round(
        float(stats["maximum_relative_adjustment"]), 6
    )
    stats["details"] = stats["details"][:100]
    return adjusted_buildings, adjusted_trees, adjusted_parking, stats


def _normalize_line_polarity(
    grayscale: np.ndarray,
    requested: str,
) -> tuple[np.ndarray, str, float]:
    """Return a dark-on-light array while preserving an explainable decision."""
    border = np.concatenate((
        grayscale[0, :],
        grayscale[-1, :],
        grayscale[:, 0],
        grayscale[:, -1],
    ))
    background_luminance = float(np.median(border))
    detected = requested
    if requested == "auto":
        detected = "light_on_dark" if background_luminance < 128.0 else "dark_on_light"
    normalized = 255 - grayscale if detected == "light_on_dark" else grayscale.copy()
    return normalized.astype(np.uint8, copy=False), detected, background_luminance


def _extract_building_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
    min_component_pixels: int,
    simplify_m: float,
) -> List[Polygon]:
    """Find conservative building candidates from enclosed white interiors.

    The name is intentionally *candidate*: a black-and-white image has no
    reliable semantic labels.  The conservative area, rectangularity and
    aspect filters avoid turning small tree symbols into buildings while still
    recovering common detached residential footprints as closed CAD polygons.
    """
    background = ~cleaned
    labeled = label(background, connectivity=2)
    image_height, image_width = cleaned.shape
    image_area = float(image_width * image_height)
    minimum_area = max(float(min_component_pixels) * 8.0, image_area * 0.0015)
    maximum_area = image_area * 0.12
    minimum_span = min(image_width, image_height) * 0.035
    maximum_span = max(image_width, image_height) * 0.38
    candidates: List[Polygon] = []

    for region in regionprops(labeled):
        min_row, min_col, max_row, max_col = region.bbox
        if min_row == 0 or min_col == 0 or max_row == image_height or max_col == image_width:
            continue
        width_px = max_col - min_col
        height_px = max_row - min_row
        if not minimum_area <= float(region.area) <= maximum_area:
            continue
        if min(width_px, height_px) < minimum_span or max(width_px, height_px) > maximum_span:
            continue
        aspect = max(width_px, height_px) / max(min(width_px, height_px), 1)
        fill_ratio = float(region.area) / max(float(width_px * height_px), 1.0)
        if aspect > 4.0 or fill_ratio < 0.42:
            continue

        polygon = _polygon_from_region(
            labeled, region, image_height, pixel_size_m, simplify_m
        )
        if polygon is None or polygon.area <= 0:
            continue
        # Axis-aligned and mildly articulated footprints retain the historical
        # fill-ratio rule.  A low axis-aligned fill is accepted only when the
        # minimum rotated rectangle is a strong fit, allowing diagonal plans
        # without broadening the classifier to arbitrary organic shapes.
        if fill_ratio < 0.80:
            oriented = _oriented_rectangle_metrics(polygon)
            if (
                oriented is None
                or oriented["rectangularity"] < 0.82
                or oriented["aspect"] > 4.0
                or (
                    len(polygon.exterior.coords) > 64
                    and oriented["rectangularity"] < 0.94
                )
            ):
                continue
        candidates.append(polygon)
    return candidates


def _extract_repeated_roof_building_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
) -> tuple[List[Polygon], dict]:
    """Recover repeated residential roof symbols split by ridge linework.

    Detailed planning drawings often contain a small, nearly rectangular
    white roof core surrounded by eaves, ridges and entrance details.  The
    older enclosed-region detector sees the surrounding linework as separate
    regions and may instead promote a large blank courtyard.  This detector
    requires both a dense linework ring and at least four similarly sized roof
    cores, so an isolated room, title box or open-space rectangle is not enough
    to create a 3D building candidate.
    """
    labeled = label(~cleaned, connectivity=2)
    image_height, image_width = cleaned.shape
    minimum_dimension = float(min(image_width, image_height))
    # Do not let small circular planting symbols become roof cores on compact
    # images.  Real residential roof cores remain comfortably above 18 px at
    # the supported working resolution.
    minimum_span = max(18.0, minimum_dimension * 0.022)
    maximum_span = max(minimum_span + 2.0, minimum_dimension * 0.075)
    provisional: List[dict] = []

    for region in regionprops(labeled):
        min_row, min_col, max_row, max_col = region.bbox
        if (
            min_row == 0
            or min_col == 0
            or max_row == image_height
            or max_col == image_width
        ):
            continue
        width_px = float(max_col - min_col)
        height_px = float(max_row - min_row)
        if not (
            minimum_span <= width_px <= maximum_span
            and minimum_span <= height_px <= maximum_span
        ):
            continue
        aspect = max(width_px, height_px) / max(min(width_px, height_px), 1.0)
        fill_ratio = float(region.area) / max(width_px * height_px, 1.0)
        if aspect > 1.8 or not 0.62 <= fill_ratio <= 0.95:
            continue

        padding = int(round(max(width_px, height_px) * 0.55))
        ring_min_row = max(0, min_row - padding)
        ring_min_col = max(0, min_col - padding)
        ring_max_row = min(image_height, max_row + padding)
        ring_max_col = min(image_width, max_col + padding)
        ring = cleaned[
            ring_min_row:ring_max_row,
            ring_min_col:ring_max_col,
        ].copy()
        ring[
            min_row - ring_min_row:max_row - ring_min_row,
            min_col - ring_min_col:max_col - ring_min_col,
        ] = False
        ring_density = float(np.mean(ring)) if ring.size else 0.0
        if ring_density < 0.145:
            continue
        provisional.append({
            "center_col": (float(min_col) + float(max_col)) / 2.0,
            "center_row": (float(min_row) + float(max_row)) / 2.0,
            "width_px": width_px,
            "height_px": height_px,
            "ring_density": ring_density,
        })

    promoted: List[dict] = []
    for candidate in provisional:
        candidate_spans = sorted((candidate["width_px"], candidate["height_px"]))
        support = 0
        for other in provisional:
            other_spans = sorted((other["width_px"], other["height_px"]))
            if all(
                abs(first - second) / max(first, second, 1.0) <= 0.38
                for first, second in zip(candidate_spans, other_spans)
            ):
                support += 1
        if support >= 4:
            promoted_candidate = dict(candidate)
            promoted_candidate["repeat_support"] = support
            promoted.append(promoted_candidate)

    candidates: List[Polygon] = []
    accepted_centers: List[tuple[float, float, float]] = []
    for candidate in sorted(
        promoted,
        key=lambda item: (-item["repeat_support"], -item["ring_density"]),
    ):
        center_col = float(candidate["center_col"])
        center_row = float(candidate["center_row"])
        footprint_width_px = float(candidate["width_px"]) * 1.68
        footprint_height_px = float(candidate["height_px"]) * 1.68
        duplicate_distance = min(footprint_width_px, footprint_height_px) * 0.55
        if any(
            (center_col - other_col) ** 2 + (center_row - other_row) ** 2
            < max(duplicate_distance, other_distance) ** 2
            for other_col, other_row, other_distance in accepted_centers
        ):
            continue
        half_width = footprint_width_px / 2.0
        half_height = footprint_height_px / 2.0
        if (
            center_col - half_width <= 1.0
            or center_col + half_width >= image_width - 1.0
            or center_row - half_height <= 1.0
            or center_row + half_height >= image_height - 1.0
        ):
            continue
        min_x = (center_col - half_width) * pixel_size_m
        max_x = (center_col + half_width) * pixel_size_m
        min_y = (image_height - center_row - half_height) * pixel_size_m
        max_y = (image_height - center_row + half_height) * pixel_size_m
        candidates.append(Polygon([
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]))
        accepted_centers.append((center_col, center_row, duplicate_distance))

    stats = {
        "provisional_roof_core_count": len(provisional),
        "repeated_roof_building_count": len(candidates),
        "roof_core_minimum_repeat_support": 4,
        "minimum_ring_density": 0.145,
    }
    return candidates, stats


def _extract_repeated_hip_roof_building_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
) -> tuple[List[Polygon], dict]:
    """Recover repeated row-house footprints from hipped-roof face regions."""
    labeled = label(~cleaned, connectivity=2)
    image_height, image_width = cleaned.shape
    minimum_dimension = float(min(image_width, image_height))
    provisional: List[dict] = []

    for region in regionprops(labeled):
        min_row, min_col, max_row, max_col = region.bbox
        if (
            min_row == 0
            or min_col == 0
            or max_row == image_height
            or max_col == image_width
        ):
            continue
        width_px = float(max_col - min_col)
        height_px = float(max_row - min_row)
        short_span, long_span = sorted((width_px, height_px))
        fill_ratio = float(region.area) / max(width_px * height_px, 1.0)
        if not (
            max(16.0, minimum_dimension * 0.019) <= short_span
            <= minimum_dimension * 0.040
            and minimum_dimension * 0.038 <= long_span
            <= minimum_dimension * 0.066
        ):
            continue
        if not 1.45 <= long_span / max(short_span, 1.0) <= 2.35:
            continue
        if not 0.38 <= fill_ratio <= 0.58:
            continue
        provisional.append({
            "center_col": (float(min_col) + float(max_col)) / 2.0,
            "center_row": (float(min_row) + float(max_row)) / 2.0,
            "short_span_px": short_span,
            "long_span_px": long_span,
            "fill_ratio": fill_ratio,
        })

    promoted: List[dict] = []
    for candidate in provisional:
        support = sum(
            1
            for other in provisional
            if abs(candidate["short_span_px"] - other["short_span_px"])
            / max(candidate["short_span_px"], other["short_span_px"], 1.0)
            <= 0.24
            and abs(candidate["long_span_px"] - other["long_span_px"])
            / max(candidate["long_span_px"], other["long_span_px"], 1.0)
            <= 0.18
        )
        if support >= 6:
            item = dict(candidate)
            item["repeat_support"] = support
            promoted.append(item)

    candidates: List[Polygon] = []
    for candidate in promoted:
        center_col = float(candidate["center_col"])
        center_row = float(candidate["center_row"])
        # In the supported top-down coursework plans the narrow enclosed roof
        # face is normally perpendicular to the longer building facade.
        footprint_width_px = float(candidate["long_span_px"]) * 1.68
        footprint_height_px = float(candidate["long_span_px"]) * 1.30
        half_width = footprint_width_px / 2.0
        half_height = footprint_height_px / 2.0
        if (
            center_col - half_width <= 1.0
            or center_col + half_width >= image_width - 1.0
            or center_row - half_height <= 1.0
            or center_row + half_height >= image_height - 1.0
        ):
            continue
        min_x = (center_col - half_width) * pixel_size_m
        max_x = (center_col + half_width) * pixel_size_m
        min_y = (image_height - center_row - half_height) * pixel_size_m
        max_y = (image_height - center_row + half_height) * pixel_size_m
        candidates.append(Polygon([
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        ]))

    return candidates, {
        "provisional_hip_roof_face_count": len(provisional),
        "repeated_hip_roof_building_count": len(candidates),
        "hip_roof_minimum_repeat_support": 6,
    }


def _merge_overlapping_building_candidates(
    candidates: List[Polygon],
    overlap_threshold: float = 0.38,
) -> tuple[List[Polygon], int]:
    """Merge strongly overlapping detections of one roof into one footprint."""
    clusters: List[List[Polygon]] = []
    for candidate in sorted(candidates, key=lambda polygon: polygon.area, reverse=True):
        matched_cluster = None
        for cluster in clusters:
            combined = unary_union(cluster)
            overlap = candidate.intersection(combined).area
            if (
                overlap / max(min(candidate.area, combined.area), 1e-9)
                >= float(overlap_threshold)
            ):
                matched_cluster = cluster
                break
        if matched_cluster is None:
            clusters.append([candidate])
        else:
            matched_cluster.append(candidate)

    merged = [unary_union(cluster).envelope for cluster in clusters]
    return merged, max(0, len(candidates) - len(merged))


def _extract_repeated_enclosed_building_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
    min_component_pixels: int,
    simplify_m: float,
) -> tuple[List[Polygon], dict]:
    """Trace repeated roof interiors instead of estimating rectangular boxes.

    Clean coursework plans commonly repeat one or two roof symbols many times.
    Their enclosed white interiors are much more reliable than a fixed expansion
    around a small roof core: tracing the source boundary keeps the resulting
    SketchUp mass on the exact same pixel coordinate system as the underlay.

    Repetition is mandatory.  This deliberately rejects isolated courtyards,
    title boxes and most parking/landscape rectangles even when their dimensions
    happen to resemble one building.
    """
    labeled = label(~cleaned, connectivity=2)
    image_height, image_width = cleaned.shape
    minimum_dimension = float(min(image_width, image_height))
    minimum_span = max(24.0, minimum_dimension * 0.027)
    maximum_span = max(90.0, minimum_dimension * 0.105)
    provisional: List[dict] = []

    for region in regionprops(labeled):
        min_row, min_col, max_row, max_col = region.bbox
        if (
            min_row == 0
            or min_col == 0
            or max_row == image_height
            or max_col == image_width
        ):
            continue
        width_px = float(max_col - min_col)
        height_px = float(max_row - min_row)
        short_span, long_span = sorted((width_px, height_px))
        if not minimum_span <= short_span <= long_span <= maximum_span:
            continue
        aspect = long_span / max(short_span, 1.0)
        fill_ratio = float(region.area) / max(width_px * height_px, 1.0)
        # Very high-fill rounded rectangles are usually lawns, courts or
        # annotation boxes; repeated roof interiors in the supported plans
        # retain ridge/notch voids and stay below this conservative ceiling.
        if aspect > 2.10 or not 0.60 <= fill_ratio <= 0.82:
            continue
        polygon = _polygon_from_region(
            labeled,
            region,
            image_height,
            pixel_size_m,
            simplify_m,
        )
        if polygon is None or polygon.area <= 0:
            continue
        provisional.append({
            "center_col": (float(min_col) + float(max_col)) / 2.0,
            "center_row": (float(min_row) + float(max_row)) / 2.0,
            "short_span_px": short_span,
            "long_span_px": long_span,
            "fill_ratio": fill_ratio,
            "polygon": polygon,
        })

    promoted: List[dict] = []
    for candidate in provisional:
        support = sum(
            1
            for other in provisional
            if abs(candidate["short_span_px"] - other["short_span_px"])
            / max(candidate["short_span_px"], other["short_span_px"], 1.0)
            <= 0.16
            and abs(candidate["long_span_px"] - other["long_span_px"])
            / max(candidate["long_span_px"], other["long_span_px"], 1.0)
            <= 0.16
            and abs(candidate["fill_ratio"] - other["fill_ratio"]) <= 0.16
        )
        if support >= 4:
            item = dict(candidate)
            item["repeat_support"] = support
            promoted.append(item)

    accepted: List[dict] = []
    for candidate in sorted(
        promoted,
        key=lambda item: (-item["repeat_support"], -item["polygon"].area),
    ):
        duplicate_radius = min(
            candidate["short_span_px"], candidate["long_span_px"]
        ) * 0.35
        if any(
            (candidate["center_col"] - other["center_col"]) ** 2
            + (candidate["center_row"] - other["center_row"]) ** 2
            < duplicate_radius**2
            for other in accepted
        ):
            continue
        accepted.append(candidate)

    polygons = [item["polygon"] for item in accepted]
    return polygons, {
        "provisional_repeated_enclosure_count": len(provisional),
        "repeated_enclosure_building_count": len(polygons),
        "minimum_repeat_support": 4,
        "geometry_source": "source_boundary_trace",
        "fixed_box_expansion_used": False,
    }


def _extract_road_surface_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
    building_candidates: List[Polygon],
    simplify_m: float,
) -> tuple[List[Polygon], dict, List[LineString], List[float], List[float]]:
    """Extract conservative road surfaces from long, stable-width corridors.

    The medial axis supplies both a centerline and its distance to the paired
    dark boundaries.  Short isolated axes are common inside lawns, roofs and
    parking boxes, so only long paths or connected path networks are retained.
    The result is intentionally a review-required road candidate layer.
    """
    image_height, image_width = cleaned.shape
    minimum_dimension = float(min(image_width, image_height))
    minimum_radius_px = max(3.5, minimum_dimension * 0.0055)
    maximum_radius_px = max(minimum_radius_px + 3.0, minimum_dimension * 0.032)
    skeleton, distance = medial_axis(~cleaned, return_distance=True, rng=42)
    corridor = skeleton & (
        (distance >= minimum_radius_px) & (distance <= maximum_radius_px)
    )
    border_margin = max(8, int(round(minimum_dimension * 0.012)))
    corridor[:border_margin, :] = False
    corridor[-border_margin:, :] = False
    corridor[:, :border_margin] = False
    corridor[:, -border_margin:] = False
    corridor = remove_small_objects(corridor, min_size=4)

    minimum_path_span = max(18.0, minimum_dimension * 0.035)
    path_candidates: List[dict] = []
    for path in _trace_skeleton_paths(corridor):
        array = np.asarray(path, dtype=float)
        if array.ndim != 2 or len(array) < 12:
            continue
        span_px = max(
            float(np.ptp(array[:, 0])),
            float(np.ptp(array[:, 1])),
        )
        if span_px < minimum_path_span:
            continue
        rows = np.clip(array[:, 0].astype(int), 0, image_height - 1)
        columns = np.clip(array[:, 1].astype(int), 0, image_width - 1)
        radii = distance[rows, columns]
        mean_radius = float(np.mean(radii))
        radius_cv = float(np.std(radii) / max(mean_radius, 1e-9))
        if radius_cv > 0.28:
            continue
        world_line = LineString([
            (
                float(column) * pixel_size_m,
                (image_height - float(row)) * pixel_size_m,
            )
            for row, column in array
        ])
        if world_line.length <= 0:
            continue
        blocked_length = 0.0
        for building in building_candidates:
            blocked_length += world_line.intersection(
                building.buffer(pixel_size_m * 1.5)
            ).length
        if blocked_length / max(world_line.length, 1e-9) > 0.18:
            continue
        path_candidates.append({
            "line": world_line,
            "radius_m": float(np.median(radii)) * pixel_size_m,
            "length_px": world_line.length / pixel_size_m,
            "radius_cv": radius_cv,
            "span_px": span_px,
        })

    parent = list(range(len(path_candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parent[second_root] = first_root

    for first_index, first in enumerate(path_candidates):
        for second_index in range(first_index + 1, len(path_candidates)):
            second = path_candidates[second_index]
            bridge_distance = min(
                30.0 * pixel_size_m,
                max(
                    10.0 * pixel_size_m,
                    (first["radius_m"] + second["radius_m"]) * 0.95,
                ),
            )
            if first["line"].distance(second["line"]) <= bridge_distance:
                union(first_index, second_index)

    components: Dict[int, List[dict]] = defaultdict(list)
    for index, candidate in enumerate(path_candidates):
        components[find(index)].append(candidate)

    minimum_network_length_px = minimum_dimension * 0.09
    accepted_paths: List[dict] = []
    accepted_component_count = 0
    for items in components.values():
        total_length_px = sum(item["length_px"] for item in items)
        longest_path_px = max(item["length_px"] for item in items)
        if (
            total_length_px < minimum_network_length_px
            and longest_path_px < minimum_dimension * 0.13
        ):
            continue
        accepted_component_count += 1
        network_score = min(
            1.0,
            total_length_px / max(minimum_network_length_px * 1.8, 1.0),
        )
        for item in items:
            width_stability = max(
                0.0,
                1.0 - float(item["radius_cv"]) / 0.28,
            )
            length_score = min(
                1.0,
                float(item["length_px"])
                / max(minimum_dimension * 0.13, 1.0),
            )
            item["confidence"] = round(
                max(
                    0.05,
                    min(
                        0.99,
                        width_stability * 0.45
                        + length_score * 0.35
                        + network_score * 0.20,
                    ),
                ),
                3,
            )
        accepted_paths.extend(items)

    road_geometry = unary_union([
        item["line"].buffer(
            item["radius_m"] * 0.96,
            cap_style=2,
            join_style=1,
            quad_segs=8,
        )
        for item in accepted_paths
    ]) if accepted_paths else GeometryCollection()
    if not road_geometry.is_empty:
        closing_distance = max(pixel_size_m * 2.0, minimum_dimension * pixel_size_m * 0.0025)
        road_geometry = road_geometry.buffer(
            closing_distance,
            join_style=1,
        ).buffer(-closing_distance, join_style=1)
        if building_candidates:
            road_geometry = road_geometry.difference(
                unary_union(building_candidates).buffer(pixel_size_m * 1.2)
            )

    minimum_area_m2 = max(4.0, (minimum_dimension * pixel_size_m * 0.018) ** 2)
    road_surfaces = [
        polygon.simplify(
            max(simplify_m, pixel_size_m * 0.45),
            preserve_topology=True,
        )
        for polygon in _iter_polygon_parts(road_geometry)
        if polygon.area >= minimum_area_m2
    ]
    source_centerlines = [item["line"] for item in accepted_paths]
    source_centerline_widths_m = [
        float(item["radius_m"]) * 2.0 for item in accepted_paths
    ]
    source_centerline_confidences = [
        float(item.get("confidence", 0.0)) for item in accepted_paths
    ]
    (
        accepted_centerlines,
        accepted_centerline_widths_m,
        accepted_centerline_confidences,
        centerline_merge,
    ) = _merge_road_centerline_candidates(
        source_centerlines,
        source_centerline_widths_m,
        source_centerline_confidences,
        pixel_size_m,
    )
    centerline_widths_m = [width for width in accepted_centerline_widths_m if width > 0]
    if centerline_widths_m:
        width_median = float(np.median(centerline_widths_m))
        width_q25, width_q75 = np.percentile(centerline_widths_m, [25, 75])
        width_spread = float(width_q75 - width_q25) / max(width_median, 1e-9)
        centerline_width_profile = (
            "mixed_widths" if width_spread > 0.35 else "uniform_width"
        )
        suggested_width_m = (
            round(width_median, 3)
            if centerline_width_profile == "uniform_width"
            else None
        )
    else:
        width_q25 = width_q75 = None
        centerline_width_profile = "unavailable"
        suggested_width_m = None
    return road_surfaces, {
        "candidate_path_count": len(path_candidates),
        "accepted_path_count": len(accepted_paths),
        "accepted_network_count": accepted_component_count,
        "road_surface_count": len(road_surfaces),
        "minimum_half_width_m": round(minimum_radius_px * pixel_size_m, 4),
        "maximum_half_width_m": round(maximum_radius_px * pixel_size_m, 4),
        "total_road_area_m2": round(sum(item.area for item in road_surfaces), 3),
        "geometry_source": "paired_line_corridor_medial_axis",
        "centerline_candidate_count": len(accepted_centerlines),
        "centerline_source_fragment_count": len(source_centerlines),
        "centerline_joined_fragment_count": int(
            centerline_merge["joined_fragment_count"]
        ),
        "centerline_network_merge": centerline_merge,
        "suggested_centerline_width_m": suggested_width_m,
        "centerline_width_profile": centerline_width_profile,
        "centerline_width_q25_m": round(float(width_q25), 3) if width_q25 is not None else None,
        "centerline_width_q75_m": round(float(width_q75), 3) if width_q75 is not None else None,
        "centerline_width_min_m": (
            round(min(centerline_widths_m), 3) if centerline_widths_m else None
        ),
        "centerline_width_max_m": (
            round(max(centerline_widths_m), 3) if centerline_widths_m else None
        ),
        "centerline_confidence_threshold": _ROAD_CENTERLINE_TRUST_THRESHOLD,
        "centerline_confidence_min": (
            round(min(accepted_centerline_confidences), 3)
            if accepted_centerline_confidences
            else None
        ),
        "centerline_confidence_max": (
            round(max(accepted_centerline_confidences), 3)
            if accepted_centerline_confidences
            else None
        ),
        "centerline_confidence_mean": (
            round(float(np.mean(accepted_centerline_confidences)), 3)
            if accepted_centerline_confidences
            else None
        ),
        "centerline_review_required_count": sum(
            confidence < _ROAD_CENTERLINE_TRUST_THRESHOLD
            for confidence in accepted_centerline_confidences
        ),
    }, accepted_centerlines, accepted_centerline_widths_m, accepted_centerline_confidences


def _extract_tree_symbol_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
    min_component_pixels: int,
    simplify_m: float,
) -> List[dict]:
    """Recognize conservative small circular symbols for reusable CAD blocks."""
    labeled = label(~cleaned, connectivity=2)
    image_height, image_width = cleaned.shape
    image_area = float(image_width * image_height)
    minimum_area = max(float(min_component_pixels) * 2.0, image_area * 0.00012)
    maximum_area = image_area * 0.0015
    minimum_span = min(image_width, image_height) * 0.012
    maximum_span = min(image_width, image_height) * 0.07
    candidates: List[dict] = []

    for region in regionprops(labeled):
        min_row, min_col, max_row, max_col = region.bbox
        if min_row == 0 or min_col == 0 or max_row == image_height or max_col == image_width:
            continue
        width_px = max_col - min_col
        height_px = max_row - min_row
        area_px = float(region.area)
        if not minimum_area <= area_px <= maximum_area:
            continue
        if min(width_px, height_px) < minimum_span or max(width_px, height_px) > maximum_span:
            continue
        aspect = max(width_px, height_px) / max(min(width_px, height_px), 1)
        fill_ratio = area_px / max(float(width_px * height_px), 1.0)
        if aspect > 1.35 or not 0.52 <= fill_ratio <= 0.82:
            continue
        polygon = _polygon_from_region(
            labeled, region, image_height, pixel_size_m, simplify_m
        )
        if polygon is None:
            continue
        center = polygon.centroid
        radius = ((float(width_px) + float(height_px)) / 4.0 + 0.75) * pixel_size_m
        candidates.append({
            "center": (float(center.x), float(center.y)),
            "radius": float(radius),
            "source_polygon": polygon,
        })
    return candidates


def _extract_repeated_circle_tree_candidates(
    normalized_grayscale: np.ndarray,
    pixel_size_m: float,
    existing_candidates: List[dict],
    building_candidates: List[Polygon],
) -> tuple[List[dict], dict]:
    """Supplement split tree symbols with repeated, scale-consistent circles.

    Tree crowns with radial spokes are divided into several white regions, so
    region labeling alone misses them.  A small four-radius Hough search keeps
    memory bounded and is only accepted when a repeated symbol family exists.
    All results remain explicit candidates for user review.
    """
    from skimage.feature import canny
    from skimage.transform import hough_circle, hough_circle_peaks

    image_height, image_width = normalized_grayscale.shape
    minimum_dimension = float(min(image_width, image_height))
    minimum_radius = max(5, int(round(minimum_dimension * 0.0105)))
    maximum_radius = max(minimum_radius + 3, int(round(minimum_dimension * 0.0175)))
    radii = np.unique(
        np.linspace(minimum_radius, maximum_radius, num=4).round().astype(int)
    )
    edges = canny(
        normalized_grayscale.astype(np.float32) / 255.0,
        sigma=1.1,
        low_threshold=0.08,
        high_threshold=0.35,
    )
    hough_result = hough_circle(edges, radii)
    accumulators, center_columns, center_rows, detected_radii = hough_circle_peaks(
        hough_result,
        radii,
        min_xdistance=max(8, int(round(minimum_radius * 1.55))),
        min_ydistance=max(8, int(round(minimum_radius * 1.55))),
        threshold=0.57,
        total_num_peaks=400,
        normalize=True,
    )
    del hough_result

    provisional: List[dict] = []
    for score, center_col, center_row, radius_px in zip(
        accumulators,
        center_columns,
        center_rows,
        detected_radii,
    ):
        margin = int(radius_px) + 2
        if not (
            margin < center_col < image_width - margin
            and margin < center_row < image_height - margin
        ):
            continue
        center_x = float(center_col) * pixel_size_m
        center_y = (float(image_height) - float(center_row)) * pixel_size_m
        radius_m = float(radius_px) * pixel_size_m
        point = Point(center_x, center_y)
        if any(
            polygon.buffer(radius_m * 0.35).contains(point)
            for polygon in building_candidates
        ):
            continue
        provisional.append({
            "center": (center_x, center_y),
            "radius": radius_m,
            "source_polygon": point.buffer(radius_m, quad_segs=12),
            "detection_basis": "repeated_circle_hough",
            "confidence": float(score),
            "replace_boundary": False,
        })

    # A handful of circles can be roundabouts, labels or furniture.  Promote
    # the Hough family only when the drawing contains a repeated planting-like
    # symbol set, then merge it with the safer enclosed-region detections.
    promoted = provisional if len(provisional) >= 8 else []
    merged = [dict(candidate) for candidate in existing_candidates]
    for candidate in promoted:
        center_x, center_y = candidate["center"]
        if any(
            (center_x - other["center"][0]) ** 2
            + (center_y - other["center"][1]) ** 2
            <= max(candidate["radius"], other["radius"]) ** 2
            for other in merged
        ):
            continue
        merged.append(candidate)

    stats = {
        "searched_radii_px": [int(radius) for radius in radii],
        "hough_circle_peak_count": len(provisional),
        "repeated_circle_tree_count": max(0, len(merged) - len(existing_candidates)),
        "minimum_family_size": 8,
        "score_threshold": 0.57,
    }
    return merged, stats


def _angle_difference_degrees(first: float, second: float) -> float:
    difference = abs(float(first) - float(second)) % 180.0
    return min(difference, 180.0 - difference)


def _extract_parking_stall_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
    min_component_pixels: int,
    simplify_m: float,
    curated_sizes: list[dict] | None = None,
) -> List[dict]:
    """Recognize repeated narrow rectangles as conservative parking candidates.

    A single small rectangle is intentionally ignored.  At least three shapes
    with similar dimensions and orientation must be present, which keeps small
    rooms, labels and incidental boxes out of the parking candidate layer.
    """
    labeled = label(~cleaned, connectivity=2)
    image_height, image_width = cleaned.shape
    image_area = float(image_width * image_height)
    minimum_area = max(float(min_component_pixels) * 1.25, image_area * 0.00004)
    maximum_area = image_area * 0.003
    minimum_span = min(image_width, image_height) * 0.006
    maximum_span = max(image_width, image_height) * 0.09
    provisional: List[dict] = []

    for region in regionprops(labeled):
        min_row, min_col, max_row, max_col = region.bbox
        if min_row == 0 or min_col == 0 or max_row == image_height or max_col == image_width:
            continue
        width_px = max_col - min_col
        height_px = max_row - min_row
        area_px = float(region.area)
        if not minimum_area <= area_px <= maximum_area:
            continue
        if min(width_px, height_px) < minimum_span or max(width_px, height_px) > maximum_span:
            continue
        polygon = _polygon_from_region(
            labeled, region, image_height, pixel_size_m, simplify_m
        )
        if polygon is None:
            continue
        oriented = _oriented_rectangle_metrics(polygon)
        if oriented is None:
            continue
        if not 1.45 <= oriented["aspect"] <= 3.40:
            continue
        if oriented["rectangularity"] < 0.86:
            continue
        center = oriented["rectangle"].centroid
        provisional.append({
            "center": (float(center.x), float(center.y)),
            "length": float(oriented["major_length"]),
            "width": float(oriented["minor_length"]),
            "rotation": float(oriented["rotation"]),
            "source_polygon": polygon,
            "rectangularity": float(oriented["rectangularity"]),
            "knowledge_size_match": _nearest_curated_size(
                float(oriented["major_length"]),
                float(oriented["minor_length"]),
                list(curated_sizes or []),
                maximum_relative_error=0.32,
            ) is not None,
        })

    promoted: List[dict] = []
    for candidate in provisional:
        similar = 0
        for other in provisional:
            length_ratio = abs(candidate["length"] - other["length"]) / max(
                candidate["length"], other["length"], 1e-9
            )
            width_ratio = abs(candidate["width"] - other["width"]) / max(
                candidate["width"], other["width"], 1e-9
            )
            if (
                length_ratio <= 0.22
                and width_ratio <= 0.22
                and _angle_difference_degrees(
                    candidate["rotation"], other["rotation"]
                ) <= 12.0
            ):
                similar += 1
        if similar >= 3 or (similar >= 2 and candidate["knowledge_size_match"]):
            promoted_candidate = dict(candidate)
            promoted_candidate["knowledge_promoted"] = similar < 3
            promoted.append(promoted_candidate)
    return promoted


def _extract_landscape_ellipse_candidates(
    cleaned: np.ndarray,
    pixel_size_m: float,
    simplify_m: float,
) -> List[dict]:
    """Fit only large, smooth, ellipse-like enclosed regions as candidates."""
    labeled = label(~cleaned, connectivity=2)
    image_height, image_width = cleaned.shape
    image_area = float(image_width * image_height)
    candidates: List[dict] = []

    for region in regionprops(labeled):
        min_row, min_col, max_row, max_col = region.bbox
        if min_row == 0 or min_col == 0 or max_row == image_height or max_col == image_width:
            continue
        width_px = max_col - min_col
        height_px = max_row - min_row
        area_ratio = float(region.area) / image_area
        fill_ratio = float(region.area) / max(float(width_px * height_px), 1.0)
        aspect = max(width_px, height_px) / max(min(width_px, height_px), 1)
        if not 0.003 <= area_ratio <= 0.10:
            continue
        if not 0.50 <= fill_ratio <= 0.82 or aspect > 3.0:
            continue
        polygon = _polygon_from_region(
            labeled, region, image_height, pixel_size_m, simplify_m
        )
        if polygon is None or polygon.length <= 0:
            continue
        compactness = 4.0 * np.pi * polygon.area / (polygon.length ** 2)
        if compactness < 0.78:
            continue

        rectangle = polygon.minimum_rotated_rectangle
        rectangle_points = list(rectangle.exterior.coords)[:4]
        edges = [
            (
                rectangle_points[(index + 1) % 4][0] - rectangle_points[index][0],
                rectangle_points[(index + 1) % 4][1] - rectangle_points[index][1],
            )
            for index in range(4)
        ]
        lengths = [_point_distance((0.0, 0.0), edge) for edge in edges]
        major_index = max(range(4), key=lambda index: lengths[index])
        major_length = lengths[major_index]
        minor_length = min(lengths)
        if major_length <= 0 or minor_length <= 0:
            continue
        major_edge = edges[major_index]
        center = polygon.centroid
        candidates.append({
            "center": (float(center.x), float(center.y)),
            "major_axis": (
                float(major_edge[0]) / 2.0,
                float(major_edge[1]) / 2.0,
            ),
            "ratio": float(minor_length / major_length),
            "source_polygon": polygon,
            "compactness": float(compactness),
        })
    return candidates


def _remove_candidate_boundaries(
    lines: List[LineString],
    candidates: List[Polygon],
    tolerance: float,
    minimum_length: float,
) -> List[LineString]:
    """Remove raw skeleton pieces replaced by protected closed candidates."""
    if not candidates:
        return lines
    exclusion = unary_union([
        polygon.boundary.buffer(tolerance, cap_style=2, join_style=2)
        for polygon in candidates
    ])
    remaining: List[LineString] = []
    for line in lines:
        covered_length = line.intersection(exclusion).length
        # Skeleton tracing already splits paths at junctions.  Remove a path
        # only when most of it is the replaced outline; clipping every small
        # intersection would create new fragments in otherwise sound branches.
        if line.length > 0 and covered_length / line.length >= 0.60:
            continue
        if line.length >= minimum_length and len(line.coords) >= 2:
            remaining.append(line)
    return remaining


def _extract_linework(
    grayscale: np.ndarray,
    threshold: int,
    min_component_pixels: int,
    pixel_size_m: float,
    simplify_factor: float,
    trace_method: str,
) -> tuple[List[LineString], np.ndarray]:
    """Extract crisp dark contours for the black-and-white CAD mode."""
    dark = grayscale <= int(threshold)
    cleaned = binary_closing(dark, footprint=disk(1))
    cleaned = remove_small_objects(cleaned, min_size=int(min_component_pixels))
    image_height = grayscale.shape[0]
    simplify_m = max(pixel_size_m * float(simplify_factor), 0.005)
    lines: List[LineString] = []

    if trace_method == "centerline":
        raw_paths = _trace_skeleton_paths(skeletonize(cleaned))
    else:
        raw_paths = find_contours(cleaned.astype(np.float32), 0.5)

    for path in raw_paths:
        if len(path) < 2:
            continue
        points = [
            (
                float(column) * pixel_size_m,
                (image_height - float(row)) * pixel_size_m,
            )
            for row, column in path
        ]
        line = LineString(points)
        minimum_length = (
            max(pixel_size_m * 0.75, 0.02)
            if trace_method == "centerline"
            else max(pixel_size_m * 1.5, 0.02)
        )
        if line.length < minimum_length:
            continue
        simplified = line.simplify(simplify_m, preserve_topology=False)
        if not simplified.is_empty and len(simplified.coords) >= 2:
            lines.append(simplified)
    return lines, cleaned


def _add_linework(msp, line: LineString, layer: str):
    points = [(float(x), float(y)) for x, y in line.coords]
    if len(points) < 2:
        return None
    close = len(points) >= 3 and (
        _point_distance(points[0], points[-1]) < 0.05
    )
    if close and _point_distance(points[0], points[-1]) < 1e-9:
        points = points[:-1]
    return msp.add_lwpolyline(points, close=close, dxfattribs={"layer": layer})


def _candidate_boundary_alignment(
    polygons: List[Polygon],
    cleaned: np.ndarray,
    pixel_size_m: float,
    *,
    role: str,
) -> dict:
    """Measure how closely candidate boundaries follow dark source linework.

    This is a QA metric, not a geometry correction.  The candidate geometry is
    kept unchanged; the metric tells the user where the source image and the
    inferred boundary disagree enough to require manual CAD review.
    """
    if not polygons:
        return {
            "object_count": 0,
            "mean_boundary_distance_px": 0.0,
            "p90_boundary_distance_px": 0.0,
            "mean_boundary_distance_m": 0.0,
            "p90_boundary_distance_m": 0.0,
            "worst_object_mean_px": 0.0,
            "status": "no_candidates",
        }

    image_height, image_width = cleaned.shape
    distance_map = distance_transform_edt(~cleaned)
    all_distances: list[float] = []
    object_means: list[float] = []
    for polygon in polygons:
        boundary = polygon.exterior
        sample_count = max(2, int(np.ceil(boundary.length / max(pixel_size_m, 1e-9))))
        distances: list[float] = []
        for index in range(sample_count + 1):
            point = boundary.interpolate(boundary.length * index / sample_count)
            column = int(round(float(point.x) / pixel_size_m))
            row = int(round(image_height - float(point.y) / pixel_size_m))
            if 0 <= row < image_height and 0 <= column < image_width:
                distances.append(float(distance_map[row, column]))
        if distances:
            all_distances.extend(distances)
            object_means.append(float(np.mean(distances)))

    if not all_distances:
        return {
            "object_count": len(polygons),
            "mean_boundary_distance_px": 0.0,
            "p90_boundary_distance_px": 0.0,
            "mean_boundary_distance_m": 0.0,
            "p90_boundary_distance_m": 0.0,
            "worst_object_mean_px": 0.0,
            "status": "not_measurable",
        }

    mean_px = float(np.mean(all_distances))
    p90_px = float(np.percentile(all_distances, 90))
    worst_mean_px = max(object_means, default=0.0)
    # Roads are derived corridors and naturally have a little more raster
    # uncertainty than source-traced building footprints.
    mean_limit = 4.0 if role == "road" else 2.0
    p90_limit = 12.0 if role == "road" else 4.0
    status = "aligned" if mean_px <= mean_limit and p90_px <= p90_limit else "review_required"
    return {
        "object_count": len(polygons),
        "mean_boundary_distance_px": round(mean_px, 3),
        "p90_boundary_distance_px": round(p90_px, 3),
        "mean_boundary_distance_m": round(mean_px * pixel_size_m, 3),
        "p90_boundary_distance_m": round(p90_px * pixel_size_m, 3),
        "worst_object_mean_px": round(worst_mean_px, 3),
        "status": status,
    }


def _organized_line_layer(
    line: LineString,
    pixel_size_m: float,
    reference_width_m: float,
) -> str:
    """Group optimized linework by editing intent without claiming semantics."""
    coordinates = list(line.coords)
    if len(coordinates) >= 3 and _point_distance(coordinates[0], coordinates[-1]) <= max(
        pixel_size_m * 1.6, 0.05
    ):
        return "BW_CLOSED"
    min_x, min_y, max_x, max_y = line.bounds
    diagonal = ((max_x - min_x) ** 2 + (max_y - min_y) ** 2) ** 0.5
    if (
        line.length <= max(reference_width_m * 0.025, pixel_size_m * 24.0)
        and diagonal <= max(reference_width_m * 0.04, pixel_size_m * 32.0)
    ):
        return "BW_DETAIL"
    return "BW_LINEWORK"


def _convert_black_white_linework(
    source: Path,
    image: Image.Image,
    output_dir: Path | str,
    reference_width_m: float,
    min_component_pixels: int,
    line_threshold: int,
    simplify_factor: float,
    trace_method: str,
    optimize_linework: bool,
    line_polarity: str,
    knowledge_profile: dict | None = None,
) -> dict:
    """Convert a clean black-and-white plan into a black CAD linework DXF."""
    work_width, work_height = image.size
    pixel_size_m = float(reference_width_m) / work_width
    grayscale = np.asarray(image.convert("L"), dtype=np.uint8)
    normalized_grayscale, detected_polarity, background_luminance = _normalize_line_polarity(
        grayscale,
        line_polarity,
    )
    raw_lines, cleaned = _extract_linework(
        normalized_grayscale,
        threshold=int(line_threshold),
        min_component_pixels=int(min_component_pixels),
        pixel_size_m=pixel_size_m,
        simplify_factor=float(simplify_factor),
        trace_method=trace_method,
    )
    if not raw_lines:
        raise ValueError(
            "未识别到清晰线条。请检查线稿底色判断是否正确，"
            "或适当调整黑白线条阈值后重试。"
        )

    simplify_m = max(pixel_size_m * float(simplify_factor), 0.005)
    lines = list(raw_lines)
    building_candidates: List[Polygon] = []
    road_surface_candidates: List[Polygon] = []
    road_centerline_candidates: List[LineString] = []
    road_centerline_widths_m: List[float] = []
    road_centerline_confidences: List[float] = []
    tree_symbol_candidates: List[dict] = []
    parking_stall_candidates: List[dict] = []
    landscape_ellipse_candidates: List[dict] = []
    building_detection = {
        "mode": "enclosed_region",
        "provisional_roof_core_count": 0,
        "repeated_roof_building_count": 0,
    }
    tree_detection = {
        "hough_circle_peak_count": 0,
        "repeated_circle_tree_count": 0,
    }
    road_detection = {
        "candidate_path_count": 0,
        "accepted_path_count": 0,
        "accepted_network_count": 0,
        "road_surface_count": 0,
        "geometry_source": "paired_line_corridor_medial_axis",
    }
    merge_stats = {
        "input_line_count": len(lines),
        "output_line_count": len(lines),
        "joined_fragment_count": 0,
        "joined_pair_count": 0,
        "max_endpoint_snap_distance": 0.0,
    }
    knowledge_assist = {
        "profile_found": False,
        "adjustment_count": 0,
        "geometry_policy": "near_match_snap_only",
    }
    if optimize_linework and trace_method == "centerline":
        enclosed_building_candidates = _extract_building_candidates(
            cleaned,
            pixel_size_m=pixel_size_m,
            min_component_pixels=int(min_component_pixels),
            simplify_m=simplify_m,
        )
        repeated_enclosed_candidates, repeated_enclosed_stats = (
            _extract_repeated_enclosed_building_candidates(
                cleaned,
                pixel_size_m=pixel_size_m,
                min_component_pixels=int(min_component_pixels),
                simplify_m=simplify_m,
            )
        )
        if len(repeated_enclosed_candidates) >= 4:
            building_candidates = repeated_enclosed_candidates
            building_detection = {
                "mode": "repeated_enclosed_line_following",
                "enclosed_region_count": len(enclosed_building_candidates),
                **repeated_enclosed_stats,
                "provisional_roof_core_count": 0,
                "repeated_roof_building_count": 0,
                "provisional_hip_roof_face_count": 0,
                "repeated_hip_roof_building_count": 0,
                "merged_duplicate_detection_count": 0,
            }
        else:
            repeated_roof_candidates, repeated_roof_stats = (
                _extract_repeated_roof_building_candidates(
                    cleaned,
                    pixel_size_m=pixel_size_m,
                )
            )
            if len(repeated_roof_candidates) >= 4:
                repeated_hip_candidates, repeated_hip_stats = (
                    _extract_repeated_hip_roof_building_candidates(
                        cleaned,
                        pixel_size_m=pixel_size_m,
                    )
                )
                merged_roof_candidates, merged_roof_detection_count = (
                    _merge_overlapping_building_candidates(
                        repeated_roof_candidates,
                        overlap_threshold=0.20,
                    )
                )
                merged_hip_candidates, merged_hip_detection_count = (
                    _merge_overlapping_building_candidates(
                        repeated_hip_candidates,
                        overlap_threshold=0.52,
                    )
                )
                building_candidates = merged_roof_candidates + merged_hip_candidates
                building_detection = {
                    "mode": "repeated_roof_symbols",
                    "enclosed_region_count": len(enclosed_building_candidates),
                    **repeated_enclosed_stats,
                    **repeated_roof_stats,
                    **repeated_hip_stats,
                    "merged_roof_core_detection_count": merged_roof_detection_count,
                    "merged_hip_roof_detection_count": merged_hip_detection_count,
                    "merged_duplicate_detection_count": (
                        merged_roof_detection_count + merged_hip_detection_count
                    ),
                }
            else:
                building_candidates = enclosed_building_candidates
                building_detection = {
                    "mode": "enclosed_region",
                    "enclosed_region_count": len(enclosed_building_candidates),
                    **repeated_enclosed_stats,
                    **repeated_roof_stats,
                    "provisional_hip_roof_face_count": 0,
                    "repeated_hip_roof_building_count": 0,
                    "merged_duplicate_detection_count": 0,
                }
        tree_symbol_candidates = _extract_tree_symbol_candidates(
            cleaned,
            pixel_size_m=pixel_size_m,
            min_component_pixels=int(min_component_pixels),
            simplify_m=simplify_m,
        )
        tree_symbol_candidates, tree_detection = (
            _extract_repeated_circle_tree_candidates(
                normalized_grayscale,
                pixel_size_m=pixel_size_m,
                existing_candidates=tree_symbol_candidates,
                building_candidates=building_candidates,
            )
        )
        parking_stall_candidates = _extract_parking_stall_candidates(
            cleaned,
            pixel_size_m=pixel_size_m,
            min_component_pixels=int(min_component_pixels),
            simplify_m=simplify_m,
            curated_sizes=(knowledge_profile or {}).get("parking_sizes_m", []),
        )
        landscape_ellipse_candidates = _extract_landscape_ellipse_candidates(
            cleaned,
            pixel_size_m=pixel_size_m,
            simplify_m=simplify_m,
        )
        source_building_boundaries = list(building_candidates)
        (
            building_candidates,
            tree_symbol_candidates,
            parking_stall_candidates,
            knowledge_assist,
        ) = _apply_knowledge_geometry_profile(
            building_candidates,
            tree_symbol_candidates,
            parking_stall_candidates,
            knowledge_profile,
        )
        (
            road_surface_candidates,
            road_detection,
            road_centerline_candidates,
            road_centerline_widths_m,
            road_centerline_confidences,
        ) = _extract_road_surface_candidates(
            cleaned,
            pixel_size_m=pixel_size_m,
            building_candidates=building_candidates,
            simplify_m=simplify_m,
        )
        minimum_length = max(pixel_size_m * 0.75, 0.02)
        protected_boundaries = source_building_boundaries
        protected_boundaries.extend(
            candidate["source_polygon"]
            for candidate in tree_symbol_candidates
            if candidate.get("replace_boundary", True)
        )
        protected_boundaries.extend(
            candidate["source_polygon"] for candidate in parking_stall_candidates
        )
        protected_boundaries.extend(
            candidate["source_polygon"] for candidate in landscape_ellipse_candidates
        )
        lines = _remove_candidate_boundaries(
            lines,
            protected_boundaries,
            tolerance=max(pixel_size_m * 1.8, 0.02),
            minimum_length=minimum_length,
        )
        lines, merge_stats = _merge_directional_centerlines(
            lines,
            tolerance=max(pixel_size_m * 1.6, 0.02),
            max_turn_degrees=45.0,
        )
        merge_stats.pop("_source_line_groups", None)

    alignment_quality = {
        "building": _candidate_boundary_alignment(
            building_candidates,
            cleaned,
            pixel_size_m,
            role="building",
        ),
        "road": _candidate_boundary_alignment(
            road_surface_candidates,
            cleaned,
            pixel_size_m,
            role="road",
        ),
    }
    line_records: List[Tuple[LineString, str]] = []
    for line in lines:
        layer = (
            _organized_line_layer(line, pixel_size_m, reference_width_m)
            if optimize_linework
            else "BW_LINEWORK"
        )
        line_records.append((line, layer))
    for polygon in building_candidates:
        line_records.append((LineString(polygon.exterior.coords), "BW_BUILDING_CANDIDATE"))
    for polygon in road_surface_candidates:
        line_records.append((LineString(polygon.exterior.coords), "BW_ROAD_CANDIDATE"))
    for line in road_centerline_candidates:
        line_records.append((line, "BW_ROAD_CENTERLINE_CANDIDATE"))
    road_centerline_width_by_id = {
        id(line): float(width)
        for line, width in zip(road_centerline_candidates, road_centerline_widths_m)
        if float(width) > 0
    }
    road_centerline_confidence_by_id = {
        id(line): float(confidence)
        for line, confidence in zip(
            road_centerline_candidates,
            road_centerline_confidences,
        )
    }
    presentation_fill_count = len(building_candidates) + len(road_surface_candidates)
    geometry_object_count = (
        len(line_records)
        + len(tree_symbol_candidates)
        + len(parking_stall_candidates)
        + len(landscape_ellipse_candidates)
    )
    output_object_count = geometry_object_count + presentation_fill_count
    raw_vertex_count = sum(len(line.coords) for line in raw_lines)
    organized_vertex_count = sum(len(line.coords) for line, _ in line_records)

    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    output_dxf = output_root / f"{source.stem}_blackwhite_converted.dxf"
    output_preview = output_root / f"{source.stem}_blackwhite_preview.png"
    output_alignment = output_root / f"{source.stem}_semantic_alignment_overlay.png"
    output_road_centerline_overlay = (
        output_root / f"{source.stem}_road_centerline_overlay.png"
    )
    output_road_review_overlay = (
        output_root / f"{source.stem}_road_review_overlay_source.png"
    )
    output_cleaned = output_root / f"{source.stem}_blackwhite_cleaned_source.png"
    output_guide_template = output_root / f"{source.stem}_semantic_guide_template.png"
    output_report = output_root / f"{source.stem}_blackwhite_conversion_report.txt"

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    _style_layer(
        doc, "BW_LINEWORK", aci_color=8, rgb=(116, 118, 116), lineweight=9
    )
    _style_layer(
        doc, "BW_CLOSED", aci_color=8, rgb=(132, 132, 127), lineweight=13
    )
    _style_layer(
        doc, "BW_DETAIL", aci_color=8, rgb=(154, 153, 147), lineweight=9
    )
    _style_layer(
        doc,
        "BW_BUILDING_CANDIDATE",
        aci_color=30,
        rgb=IMAGE_PALETTE["AI_BUILDING"],
        lineweight=30,
    )
    _style_layer(
        doc,
        "BW_BUILDING_FILL",
        aci_color=30,
        rgb=IMAGE_PALETTE["AI_BUILDING"],
        lineweight=0,
    )
    _style_layer(
        doc,
        "BW_ROAD_CANDIDATE",
        aci_color=8,
        rgb=IMAGE_PALETTE["AI_ROAD"],
        lineweight=25,
    )
    _style_layer(
        doc,
        "BW_ROAD_FILL",
        aci_color=8,
        rgb=IMAGE_PALETTE["AI_ROAD"],
        lineweight=0,
    )
    _style_layer(
        doc,
        "BW_ROAD_CENTERLINE_CANDIDATE",
        aci_color=6,
        rgb=(79, 107, 142),
        lineweight=18,
    )
    _style_layer(
        doc,
        "BW_TREE_CANDIDATE",
        aci_color=3,
        rgb=IMAGE_PALETTE["AI_GREEN"],
        lineweight=18,
    )
    _style_layer(
        doc,
        "BW_PARKING_CANDIDATE",
        aci_color=2,
        rgb=IMAGE_PALETTE["AI_PARKING"],
        lineweight=18,
    )
    _style_layer(
        doc,
        "BW_LANDSCAPE_CANDIDATE",
        aci_color=3,
        rgb=(105, 145, 121),
        lineweight=20,
    )
    _style_layer(
        doc, "BW_FRAME", aci_color=8, rgb=(103, 108, 113), lineweight=25
    )
    doc.header["$LWDISPLAY"] = 1
    doc.appids.add("PT_ROAD_WIDTH_M")
    doc.appids.add("PT_ROAD_CONFIDENCE")
    doc.appids.add("PT_ROAD_CANDIDATE_ID")
    doc.appids.add(_PRESENTATION_FILL_APPID)
    msp = doc.modelspace()
    generated_fill_count = 0
    for polygon in road_surface_candidates:
        generated_fill_count += int(
            _add_presentation_hatch(
                msp,
                polygon,
                layer="BW_ROAD_FILL",
                rgb=IMAGE_PALETTE["AI_ROAD"],
                transparency=0.84,
            )
        )
    for polygon in building_candidates:
        generated_fill_count += int(
            _add_presentation_hatch(
                msp,
                polygon,
                layer="BW_BUILDING_FILL",
                rgb=IMAGE_PALETTE["AI_BUILDING"],
                transparency=0.80,
            )
        )
    if generated_fill_count != presentation_fill_count:
        raise RuntimeError("CAD 语义浅填充数量与候选边界不一致。")
    frame = [
        (0.0, 0.0),
        (reference_width_m, 0.0),
        (reference_width_m, work_height * pixel_size_m),
        (0.0, work_height * pixel_size_m),
    ]
    msp.add_lwpolyline(frame, close=True, dxfattribs={"layer": "BW_FRAME"})
    for line, layer in line_records:
        entity = _add_linework(msp, line, layer)
        if entity is not None and layer == "BW_ROAD_CENTERLINE_CANDIDATE":
            width_m = road_centerline_width_by_id.get(id(line))
            if width_m is not None:
                entity.set_xdata("PT_ROAD_WIDTH_M", [(1040, width_m)])
            confidence = road_centerline_confidence_by_id.get(id(line))
            if confidence is not None:
                entity.set_xdata("PT_ROAD_CONFIDENCE", [(1040, confidence)])
            candidate_id = next(
                (
                    index + 1
                    for index, candidate in enumerate(road_centerline_candidates)
                    if candidate is line
                ),
                None,
            )
            if candidate_id is not None:
                entity.set_xdata("PT_ROAD_CANDIDATE_ID", [(1070, candidate_id)])
    if tree_symbol_candidates:
        tree_block = doc.blocks.new(name="PT_TREE")
        tree_block.add_circle(
            center=(0.0, 0.0),
            radius=1.0,
            dxfattribs={"layer": "0"},
        )
        for candidate in tree_symbol_candidates:
            center_x, center_y = candidate["center"]
            radius = float(candidate["radius"])
            msp.add_blockref(
                "PT_TREE",
                (center_x, center_y, 0.0),
                dxfattribs={
                    "layer": "BW_TREE_CANDIDATE",
                    "xscale": radius,
                    "yscale": radius,
                    "zscale": 1.0,
                },
            )
    if parking_stall_candidates:
        parking_block = doc.blocks.new(name="PT_PARKING_STALL")
        parking_block.add_lwpolyline(
            [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)],
            close=True,
            dxfattribs={"layer": "0"},
        )
        for candidate in parking_stall_candidates:
            center_x, center_y = candidate["center"]
            msp.add_blockref(
                "PT_PARKING_STALL",
                (center_x, center_y, 0.0),
                dxfattribs={
                    "layer": "BW_PARKING_CANDIDATE",
                    "xscale": float(candidate["length"]),
                    "yscale": float(candidate["width"]),
                    "zscale": 1.0,
                    "rotation": float(candidate["rotation"]),
                },
            )
    for candidate in landscape_ellipse_candidates:
        center_x, center_y = candidate["center"]
        major_x, major_y = candidate["major_axis"]
        msp.add_ellipse(
            center=(center_x, center_y, 0.0),
            major_axis=(major_x, major_y, 0.0),
            ratio=float(candidate["ratio"]),
            dxfattribs={"layer": "BW_LANDSCAPE_CANDIDATE"},
        )

    doc.saveas(output_dxf)
    cleaned_array = np.full((*cleaned.shape, 3), 255, dtype=np.uint8)
    cleaned_array[cleaned] = np.asarray((32, 32, 32), dtype=np.uint8)
    Image.fromarray(cleaned_array, mode="RGB").save(output_cleaned)

    # Give non-technical users an exact-pixel canvas for semantic correction.
    # Reopen the immutable source instead of using the possibly downsampled work
    # image: semantic-guide mode deliberately requires identical source pixels.
    source_for_template = Image.open(source).convert("RGB")
    guide_background = Image.new("RGB", source_for_template.size, (255, 255, 255))
    guide_template = Image.blend(guide_background, source_for_template, 0.18)
    guide_draw = ImageDraw.Draw(guide_template)
    source_width, source_height = source_for_template.size
    source_pixel_size_m = float(reference_width_m) / source_width

    def guide_polygon_points(polygon: Polygon) -> List[tuple[int, int]]:
        return [
            (
                round(float(x) / source_pixel_size_m),
                round(source_height - float(y) / source_pixel_size_m),
            )
            for x, y in polygon.exterior.coords
        ]

    # Paint broad surfaces first, then small semantic objects. All fills use
    # the documented exact RGB palette so this draft can be fed straight back
    # into semantic-guide mode after optional correction in any image editor.
    for polygon in road_surface_candidates:
        points = guide_polygon_points(polygon)
        if len(points) >= 3:
            guide_draw.polygon(points, fill=IMAGE_PALETTE["AI_ROAD"])
    for candidate in landscape_ellipse_candidates:
        center_x, center_y = candidate["center"]
        major_x, major_y = candidate["major_axis"]
        ratio = float(candidate["ratio"])
        ellipse_points = []
        for parameter in np.linspace(0.0, 2.0 * np.pi, 181):
            x = center_x + major_x * np.cos(parameter) - major_y * ratio * np.sin(parameter)
            y = center_y + major_y * np.cos(parameter) + major_x * ratio * np.sin(parameter)
            ellipse_points.append((
                round(x / source_pixel_size_m),
                round(source_height - y / source_pixel_size_m),
            ))
        guide_draw.polygon(ellipse_points, fill=IMAGE_PALETTE["AI_GREEN"])
    for candidate in tree_symbol_candidates:
        center_x, center_y = candidate["center"]
        radius = float(candidate["radius"])
        center_col = center_x / source_pixel_size_m
        center_row = source_height - center_y / source_pixel_size_m
        radius_px = radius / source_pixel_size_m
        guide_draw.ellipse(
            (
                round(center_col - radius_px),
                round(center_row - radius_px),
                round(center_col + radius_px),
                round(center_row + radius_px),
            ),
            fill=IMAGE_PALETTE["AI_GREEN"],
        )
    for candidate in parking_stall_candidates:
        center_x, center_y = candidate["center"]
        half_length = float(candidate["length"]) / 2.0
        half_width = float(candidate["width"]) / 2.0
        angle = np.radians(float(candidate["rotation"]))
        cosine = np.cos(angle)
        sine = np.sin(angle)
        parking_points = []
        for local_x, local_y in (
            (-half_length, -half_width),
            (half_length, -half_width),
            (half_length, half_width),
            (-half_length, half_width),
        ):
            x = center_x + local_x * cosine - local_y * sine
            y = center_y + local_x * sine + local_y * cosine
            parking_points.append((
                round(x / source_pixel_size_m),
                round(source_height - y / source_pixel_size_m),
            ))
        guide_draw.polygon(parking_points, fill=IMAGE_PALETTE["AI_PARKING"])
    for polygon in building_candidates:
        points = guide_polygon_points(polygon)
        if len(points) >= 3:
            guide_draw.polygon(points, fill=IMAGE_PALETTE["AI_BUILDING"])
    guide_template.save(output_guide_template)

    # Create a second, exact-source-size review layer.  It is never fed back
    # into semantic-guide recognition; it only helps the beginner locate
    # candidate roads that deserve attention in the editor.
    source_review_overlay = source_for_template.convert("RGBA")
    source_review_draw = ImageDraw.Draw(source_review_overlay, "RGBA")

    def source_preview_polygon_points(polygon: Polygon) -> List[tuple[int, int]]:
        return [
            (
                round(float(x) / source_pixel_size_m),
                round(source_height - float(y) / source_pixel_size_m),
            )
            for x, y in polygon.exterior.coords
        ]

    for polygon in road_surface_candidates:
        points = source_preview_polygon_points(polygon)
        if len(points) >= 3:
            source_review_draw.polygon(
                points,
                fill=(67, 139, 176, 62),
                outline=(35, 93, 124, 210),
                width=2,
            )
    for line, confidence in zip(
        road_centerline_candidates,
        road_centerline_confidences,
    ):
        points = [
            (
                round(float(x) / source_pixel_size_m),
                round(source_height - float(y) / source_pixel_size_m),
            )
            for x, y in line.coords
        ]
        if len(points) < 2:
            continue
        line_color = (
            (232, 130, 38, 245)
            if float(confidence) >= 0.65
            else (205, 74, 64, 245)
        )
        source_review_draw.line(points, fill=line_color, width=4, joint="curve")
    source_review_overlay.convert("RGB").save(output_road_review_overlay)

    # Draw the generated vector geometry back to pixels so the preview matches
    # what the user will see in CAD, rather than showing the source stroke mask.
    vector_preview = Image.new("RGB", (work_width, work_height), (255, 255, 255))
    preview_draw = ImageDraw.Draw(vector_preview)
    for line, layer in line_records:
        preview_points = [
            (
                round(float(x) / pixel_size_m),
                round(work_height - float(y) / pixel_size_m),
            )
            for x, y in line.coords
        ]
        if len(preview_points) >= 2:
            preview_draw.line(
                preview_points,
                fill=(24, 24, 24),
                width=(
                    2
                    if layer in {
                        "BW_BUILDING_CANDIDATE",
                        "BW_ROAD_CANDIDATE",
                        "BW_ROAD_CENTERLINE_CANDIDATE",
                    }
                    else 1
                ),
                joint="curve",
            )
    for candidate in tree_symbol_candidates:
        center_x, center_y = candidate["center"]
        radius = float(candidate["radius"])
        center_col = center_x / pixel_size_m
        center_row = work_height - center_y / pixel_size_m
        radius_px = radius / pixel_size_m
        preview_draw.ellipse(
            (
                round(center_col - radius_px),
                round(center_row - radius_px),
                round(center_col + radius_px),
                round(center_row + radius_px),
            ),
            outline=(24, 24, 24),
            width=1,
        )
    for candidate in parking_stall_candidates:
        center_x, center_y = candidate["center"]
        half_length = float(candidate["length"]) / 2.0
        half_width = float(candidate["width"]) / 2.0
        angle = np.radians(float(candidate["rotation"]))
        cosine = np.cos(angle)
        sine = np.sin(angle)
        preview_points = []
        for local_x, local_y in (
            (-half_length, -half_width),
            (half_length, -half_width),
            (half_length, half_width),
            (-half_length, half_width),
            (-half_length, -half_width),
        ):
            x = center_x + local_x * cosine - local_y * sine
            y = center_y + local_x * sine + local_y * cosine
            preview_points.append((
                round(x / pixel_size_m),
                round(work_height - y / pixel_size_m),
            ))
        preview_draw.line(preview_points, fill=(24, 24, 24), width=1)
    for candidate in landscape_ellipse_candidates:
        center_x, center_y = candidate["center"]
        major_x, major_y = candidate["major_axis"]
        ratio = float(candidate["ratio"])
        ellipse_points = []
        for parameter in np.linspace(0.0, 2.0 * np.pi, 181):
            x = (
                center_x
                + major_x * np.cos(parameter)
                - major_y * ratio * np.sin(parameter)
            )
            y = (
                center_y
                + major_y * np.cos(parameter)
                + major_x * ratio * np.sin(parameter)
            )
            ellipse_points.append((
                round(x / pixel_size_m),
                round(work_height - y / pixel_size_m),
            ))
        preview_draw.line(
            ellipse_points,
            fill=(24, 24, 24),
            width=2,
            joint="curve",
        )
    vector_preview.save(output_preview)

    # Preserve the selected image itself as the visual authority and overlay
    # only the semantic candidates.  This makes a one-pixel alignment error
    # visible before the user opens CAD or SketchUp.
    alignment_preview = image.convert("RGBA")
    alignment_draw = ImageDraw.Draw(alignment_preview, "RGBA")

    def preview_polygon_points(polygon: Polygon) -> List[tuple[int, int]]:
        return [
            (
                round(float(x) / pixel_size_m),
                round(work_height - float(y) / pixel_size_m),
            )
            for x, y in polygon.exterior.coords
        ]

    for polygon in road_surface_candidates:
        points = preview_polygon_points(polygon)
        if len(points) >= 3:
            alignment_draw.polygon(
                points,
                fill=(89, 142, 171, 70),
                outline=(54, 105, 136, 220),
                width=2,
            )
    for polygon in building_candidates:
        points = preview_polygon_points(polygon)
        if len(points) >= 3:
            alignment_draw.polygon(
                points,
                fill=(190, 112, 108, 70),
                outline=(156, 72, 70, 235),
                width=2,
            )
    alignment_preview.convert("RGB").save(output_alignment)
    road_centerline_preview = image.convert("RGBA")
    road_centerline_draw = ImageDraw.Draw(road_centerline_preview, "RGBA")
    for polygon in road_surface_candidates:
        points = preview_polygon_points(polygon)
        if len(points) >= 3:
            road_centerline_draw.polygon(
                points,
                fill=(67, 139, 176, 72),
                outline=(35, 93, 124, 230),
                width=2,
            )
    for line, confidence in zip(
        road_centerline_candidates,
        road_centerline_confidences,
    ):
        points = [
            (
                round(float(x) / pixel_size_m),
                round(work_height - float(y) / pixel_size_m),
            )
            for x, y in line.coords
        ]
        if len(points) >= 2:
            line_color = (
                (232, 130, 38, 255)
                if float(confidence) >= 0.65
                else (205, 74, 64, 255)
            )
            road_centerline_draw.line(
                points,
                fill=line_color,
                width=3,
                joint="curve",
            )
            for point in (points[0], points[-1]):
                radius = 4
                road_centerline_draw.ellipse(
                    (
                        point[0] - radius,
                        point[1] - radius,
                        point[0] + radius,
                        point[1] + radius,
                    ),
                    fill=line_color,
                )
    road_centerline_preview.convert("RGB").save(output_road_centerline_overlay)
    source_hash = sha256_file(source)
    with output_report.open("w", encoding="utf-8") as report:
        report.write("=== Planning Toolbox Black-and-White Linework Report ===\n")
        report.write("This is a concept linework conversion, not a survey or approval drawing.\n")
        report.write(f"Source image: {source.name}\n")
        report.write(f"Source SHA-256: {source_hash}\n")
        report.write(f"Editable semantic-guide template: {output_guide_template.name}\n")
        report.write(
            "Semantic-guide template alignment: exact original source pixel dimensions\n"
        )
        report.write(
            "Semantic-guide template prefill: automatic building, road, green and parking "
            "candidates; review and correct before reuse\n"
        )
        report.write(f"Processed image size: {work_width} x {work_height}\n")
        report.write(f"Reference width (m): {reference_width_m:g}\n")
        report.write(f"Pixel size (m): {pixel_size_m:.6f}\n")
        report.write(f"Line threshold: {int(line_threshold)}\n")
        report.write(f"Requested line polarity: {line_polarity}\n")
        report.write(f"Detected line polarity: {detected_polarity}\n")
        report.write(f"Border background luminance: {background_luminance:.1f}\n")
        report.write(f"Minimum component pixels: {int(min_component_pixels)}\n")
        report.write(f"Line simplification factor: {float(simplify_factor):g}\n")
        report.write(f"Trace method: {trace_method}\n")
        # Keep the original report field for downstream readers.
        report.write(f"Extracted line contours: {len(line_records)}\n")
        layer_counts = {
            layer: sum(1 for _, item_layer in line_records if item_layer == layer)
            for layer in (
                "BW_LINEWORK",
                "BW_CLOSED",
                "BW_DETAIL",
                "BW_BUILDING_CANDIDATE",
                "BW_ROAD_CANDIDATE",
                "BW_ROAD_CENTERLINE_CANDIDATE",
                "BW_TREE_CANDIDATE",
                "BW_PARKING_CANDIDATE",
                "BW_LANDSCAPE_CANDIDATE",
            )
        }
        layer_counts["BW_TREE_CANDIDATE"] = len(tree_symbol_candidates)
        layer_counts["BW_PARKING_CANDIDATE"] = len(parking_stall_candidates)
        layer_counts["BW_LANDSCAPE_CANDIDATE"] = len(landscape_ellipse_candidates)
        report.write(f"Raw extracted line contours: {len(raw_lines)}\n")
        report.write(f"Output line entities: {len(line_records)}\n")
        report.write(f"Output semantic geometry objects: {geometry_object_count}\n")
        report.write(f"Output CAD objects including presentation fills: {output_object_count}\n")
        report.write(f"Raw polyline vertices: {raw_vertex_count}\n")
        report.write(f"Organized polyline vertices: {organized_vertex_count}\n")
        report.write(f"Automatic linework optimization: {'yes' if optimize_linework else 'no'}\n")
        report.write(f"Directionally joined fragments: {merge_stats['joined_fragment_count']}\n")
        report.write(f"Building candidates: {len(building_candidates)}\n")
        report.write(f"Building detection mode: {building_detection['mode']}\n")
        report.write(
            "Source-boundary building traces: "
            f"{building_detection.get('repeated_enclosure_building_count', 0)}\n"
        )
        report.write(
            "Repeated roof-core buildings: "
            f"{building_detection.get('repeated_roof_building_count', 0)}\n"
        )
        report.write(
            "Repeated hip-roof buildings: "
            f"{building_detection.get('repeated_hip_roof_building_count', 0)}\n"
        )
        report.write(
            "Merged duplicate building detections: "
            f"{building_detection.get('merged_duplicate_detection_count', 0)}\n"
        )
        report.write(f"Road surface candidates: {len(road_surface_candidates)}\n")
        report.write(
            "Removable semantic presentation fills: "
            f"{presentation_fill_count} (building + road HATCH)\n"
        )
        report.write(
            "Presentation fill layers: BW_BUILDING_FILL, BW_ROAD_FILL "
            "(toggle independently from candidate boundaries)\n"
        )
        report.write(
            "Accepted road centerline paths: "
            f"{road_detection.get('accepted_path_count', 0)}\n"
        )
        report.write(
            "Road centerline candidate entities: "
            f"{len(road_centerline_candidates)}\n"
        )
        report.write(
            "Road centerline source fragments: "
            f"{road_detection.get('centerline_source_fragment_count', len(road_centerline_candidates))}\n"
        )
        report.write(
            "Safely joined road fragments: "
            f"{road_detection.get('centerline_joined_fragment_count', 0)}; "
            f"maximum bridge gap "
            f"{road_detection.get('centerline_network_merge', {}).get('maximum_bridge_gap_m', 0):g} m\n"
        )
        report.write(
            "Safely snapped road junctions: "
            f"{road_detection.get('centerline_network_merge', {}).get('junction_snap_count', 0)}; "
            "trusted network components "
            f"{road_detection.get('centerline_network_merge', {}).get('trusted_network_component_count_before', 0)} -> "
            f"{road_detection.get('centerline_network_merge', {}).get('trusted_network_component_count_after', 0)}; "
            "maximum endpoint movement "
            f"{road_detection.get('centerline_network_merge', {}).get('maximum_junction_snap_distance_m', 0):g} m\n"
        )
        report.write(
            "Suggested centerline corridor width (m): "
            f"{road_detection.get('suggested_centerline_width_m') or 'unavailable'}\n"
        )
        report.write(
            "Centerline width profile: "
            f"{road_detection.get('centerline_width_profile', 'unavailable')}\n"
        )
        report.write(
            "Detected centerline width range (m): "
            f"{road_detection.get('centerline_width_min_m') or 'unavailable'} - "
            f"{road_detection.get('centerline_width_max_m') or 'unavailable'}\n"
        )
        report.write(
            "Centerline confidence: "
            f"mean {road_detection.get('centerline_confidence_mean') or 'unavailable'}, "
            f"min {road_detection.get('centerline_confidence_min') or 'unavailable'}, "
            f"review required {road_detection.get('centerline_review_required_count', 0)} "
            f"of {len(road_centerline_candidates)}\n"
        )
        report.write(
            "Centerline overlay legend: orange = concept-ready confidence >= 0.65; "
            "red = review required confidence < 0.65.\n"
        )
        report.write(
            "Exact-pixel road review overlay: "
            f"{output_road_review_overlay.name}; display-only, never used as semantic input.\n"
        )
        for index, (width_m, confidence) in enumerate(
            zip(road_centerline_widths_m, road_centerline_confidences),
            start=1,
        ):
            report.write(
                f"Centerline candidate {index}: width {float(width_m):.3f} m, "
                f"confidence {float(confidence):.3f}, "
                f"status {'ready_for_concept' if float(confidence) >= _ROAD_CENTERLINE_TRUST_THRESHOLD else 'review_required'}\n"
            )
        report.write(
            "Accepted road networks: "
            f"{road_detection.get('accepted_network_count', 0)}\n"
        )
        report.write(f"Tree block candidates: {len(tree_symbol_candidates)}\n")
        report.write(
            "Repeated-circle tree additions: "
            f"{tree_detection.get('repeated_circle_tree_count', 0)}\n"
        )
        report.write(f"Parking block candidates: {len(parking_stall_candidates)}\n")
        report.write(f"Landscape ellipse candidates: {len(landscape_ellipse_candidates)}\n")
        for role in ("building", "road"):
            quality = alignment_quality[role]
            report.write(
                f"{role.title()} boundary alignment: "
                f"mean {quality['mean_boundary_distance_px']:.3f} px, "
                f"P90 {quality['p90_boundary_distance_px']:.3f} px, "
                f"status {quality['status']}\n"
            )
        report.write(
            f"Knowledge quality profile: {'yes' if knowledge_assist.get('profile_found') else 'no'}\n"
        )
        report.write(
            f"Knowledge-guided geometry adjustments: {knowledge_assist.get('adjustment_count', 0)}\n"
        )
        report.write(
            "Knowledge-promoted parking stalls: "
            f"{knowledge_assist.get('knowledge_promoted_parking_stalls', 0)}\n"
        )
        report.write(
            "Knowledge policy: only near-matching dimensions from user-curated local DXFs; "
            "unreviewed candidates never alter geometry.\n"
        )
        for layer, count in layer_counts.items():
            report.write(f"{layer}: {count}\n")
        report.write(
            "Warning: text, symbols, scan noise and broken lines may also be converted. "
            "All *_CANDIDATE layers are heuristic and must be reviewed before measurements.\n"
        )

    layer_counts = {
        layer: sum(1 for _, item_layer in line_records if item_layer == layer)
        for layer in (
            "BW_LINEWORK",
            "BW_CLOSED",
            "BW_DETAIL",
            "BW_BUILDING_CANDIDATE",
            "BW_ROAD_CANDIDATE",
            "BW_ROAD_CENTERLINE_CANDIDATE",
            "BW_TREE_CANDIDATE",
            "BW_PARKING_CANDIDATE",
            "BW_LANDSCAPE_CANDIDATE",
        )
    }
    layer_counts["BW_TREE_CANDIDATE"] = len(tree_symbol_candidates)
    layer_counts["BW_PARKING_CANDIDATE"] = len(parking_stall_candidates)
    layer_counts["BW_LANDSCAPE_CANDIDATE"] = len(landscape_ellipse_candidates)

    from planning_toolbox.project.semantic_scene import build_semantic_scene_from_dxf

    semantic_scene = build_semantic_scene_from_dxf(
        output_dxf,
        source_image_path=source,
        source_image_sha256=source_hash,
        reference_width_m=reference_width_m,
        conversion_mode="black_white_linework",
    )
    return {
        "task_type": "image_to_dxf",
        "conversion_mode": "black_white_linework",
        "dxf_file": str(output_dxf),
        "source_file": str(source),
        "source_sha256": source_hash,
        "image_size": image.size,
        "processed_size": image.size,
        "reference_width_m": float(reference_width_m),
        "pixel_size_m": pixel_size_m,
        "line_threshold": int(line_threshold),
        "line_polarity_requested": line_polarity,
        "line_polarity_detected": detected_polarity,
        "background_luminance": background_luminance,
        "min_component_pixels": int(min_component_pixels),
        "line_simplify_factor": float(simplify_factor),
        "trace_method": trace_method,
        "raw_line_count": len(raw_lines),
        # Keep the historical ``line_count`` meaning stable: editable semantic
        # geometry only.  Removable presentation hatches are reported separately.
        "line_count": geometry_object_count,
        "output_line_count": len(line_records),
        "output_object_count": output_object_count,
        "geometry_object_count": geometry_object_count,
        "raw_vertex_count": raw_vertex_count,
        "organized_vertex_count": organized_vertex_count,
        "vertex_reduction": max(0, raw_vertex_count - organized_vertex_count),
        "optimization_enabled": bool(optimize_linework),
        "building_candidate_count": len(building_candidates),
        "road_candidate_count": len(road_surface_candidates),
        "road_centerline_candidate_count": len(road_centerline_candidates),
        "road_centerline_source_fragment_count": road_detection.get(
            "centerline_source_fragment_count", len(road_centerline_candidates)
        ),
        "road_centerline_joined_fragment_count": road_detection.get(
            "centerline_joined_fragment_count", 0
        ),
        "road_centerline_junction_snap_count": road_detection.get(
            "centerline_network_merge", {}
        ).get("junction_snap_count", 0),
        "road_centerline_network_component_count_before": road_detection.get(
            "centerline_network_merge", {}
        ).get("trusted_network_component_count_before", 0),
        "road_centerline_network_component_count_after": road_detection.get(
            "centerline_network_merge", {}
        ).get("trusted_network_component_count_after", 0),
        "road_centerline_maximum_junction_snap_distance_m": road_detection.get(
            "centerline_network_merge", {}
        ).get("maximum_junction_snap_distance_m", 0.0),
        "road_centerline_width_m": road_detection.get("suggested_centerline_width_m"),
        "road_centerline_widths_m": [round(float(width), 3) for width in road_centerline_widths_m],
        "road_centerline_confidences": [
            round(float(confidence), 3)
            for confidence in road_centerline_confidences
        ],
        "road_centerline_review_required_count": road_detection.get(
            "centerline_review_required_count", 0
        ),
        "road_centerline_overlay_file": str(output_road_centerline_overlay),
        "road_review_overlay_file": str(output_road_review_overlay),
        "tree_candidate_count": len(tree_symbol_candidates),
        "parking_candidate_count": len(parking_stall_candidates),
        "landscape_candidate_count": len(landscape_ellipse_candidates),
        "semantic_presentation_fill_count": presentation_fill_count,
        "line_layer_counts": layer_counts,
        "merge_stats": merge_stats,
        "building_detection": building_detection,
        "road_detection": road_detection,
        "alignment_quality": alignment_quality,
        "tree_detection": tree_detection,
        "knowledge_assist": knowledge_assist,
        "semantic_scene_file": semantic_scene["path"],
        "semantic_scene_sha256": semantic_scene["sha256"],
        "semantic_scene_summary": semantic_scene["summary"],
        "semantic_guide_template_file": str(output_guide_template),
        "semantic_guide_template_prefill_counts": {
            "AI_BUILDING": len(building_candidates),
            "AI_ROAD": len(road_surface_candidates),
            "AI_GREEN": len(tree_symbol_candidates) + len(landscape_ellipse_candidates),
            "AI_PARKING": len(parking_stall_candidates),
        },
        "region_counts": layer_counts,
        "region_areas_m2": {},
        "focus_site_only": False,
        "focus_applied": False,
        "focus_bbox_px": None,
        "output_files": [
            ("Black-white linework DXF", str(output_dxf)),
            ("CAD vector preview PNG", str(output_preview)),
            ("Black-white conversion report", str(output_report)),
            ("Cleaned source preview PNG", str(output_cleaned)),
            ("全链路语义交接 JSON", semantic_scene["path"]),
            ("Semantic alignment overlay PNG", str(output_alignment)),
            ("Editable semantic-guide template PNG", str(output_guide_template)),
            ("Road centerline overlay review PNG", str(output_road_centerline_overlay)),
            ("Exact-pixel road review overlay PNG", str(output_road_review_overlay)),
        ],
    }
    quality_baseline = write_image_to_cad_quality_baseline(result)
    result["quality_baseline_file"] = quality_baseline["path"]
    result["quality_baseline"] = quality_baseline
    result["output_files"].append(("图片转 CAD 中文质量复核清单", quality_baseline["review_path"]))
    result["output_files"].append(("图片转 CAD 质量基线 JSON", quality_baseline["path"]))
    return result


def convert_image_to_dxf(
    image_path: Path | str,
    output_dir: Path | str = "output",
    reference_width_m: float | None = None,
    color_tolerance: int = 55,
    min_component_pixels: int = 80,
    max_dimension: int = 1200,
    focus_site_only: bool = False,
    conversion_mode: str = "color_regions",
    line_threshold: int = 220,
    line_simplify_factor: float = 0.35,
    line_trace_method: str = "outline",
    optimize_linework: bool = False,
    line_polarity: str = "auto",
    knowledge_profile: dict | None = None,
    semantic_guide_path: Path | str | None = None,
) -> dict:
    """Convert a standardized top-down planning image into a concept DXF.

    ``reference_width_m`` is deliberately required.  The converter never
    guesses a real-world scale from an image, because that would make area and
    setback calculations misleading.
    """
    source = Path(image_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"图片文件不存在: {source}")
    if reference_width_m is None or reference_width_m <= 0:
        raise ValueError("必须填写图片对应的实际宽度（米），系统不会猜测比例")
    if not 5 <= int(color_tolerance) <= 150:
        raise ValueError("颜色识别容差必须在 5 到 150 之间")
    if not 4 <= int(min_component_pixels) <= 1_000_000:
        raise ValueError("最小识别区域像素数必须在 4 到 1000000 之间")
    if not 200 <= int(max_dimension) <= 4000:
        raise ValueError("图片处理最长边必须在 200 到 4000 像素之间")

    if conversion_mode not in {
        "color_regions",
        "black_white_linework",
        "semantic_guide",
    }:
        raise ValueError("不支持的图片转 CAD 模式")
    if not 20 <= int(line_threshold) <= 250:
        raise ValueError("黑白线条阈值必须在 20 到 250 之间")
    if not 0.01 <= float(line_simplify_factor) <= 1.0:
        raise ValueError("黑白线条精细度参数必须在 0.01 到 1.0 之间")
    if line_trace_method not in {"outline", "centerline"}:
        raise ValueError("黑白线条追踪方式必须是 outline 或 centerline")
    if line_polarity not in {"auto", "dark_on_light", "light_on_dark"}:
        raise ValueError("线稿底色判断必须是 auto、dark_on_light 或 light_on_dark")

    try:
        image = Image.open(source).convert("RGB")
    except Exception as exc:
        raise ValueError(f"无法读取图片，请使用 PNG/JPG 格式: {exc}") from exc

    guide_source: Path | None = None
    guide_image: Image.Image | None = None
    guide_hash = ""
    if conversion_mode == "semantic_guide":
        if not semantic_guide_path:
            raise ValueError("语义引导模式必须选择一张标准颜色引导图")
        guide_source = Path(semantic_guide_path).resolve()
        if not guide_source.is_file():
            raise FileNotFoundError(f"语义引导图不存在: {guide_source}")
        guide_hash = sha256_file(guide_source)
        try:
            guide_image = Image.open(guide_source).convert("RGB")
        except Exception as exc:
            raise ValueError(f"无法读取语义引导图，请使用 PNG/JPG 格式: {exc}") from exc
        if guide_image.size != image.size:
            raise ValueError(
                "语义引导图必须与原始底图像素尺寸完全一致，"
                f"当前底图为 {image.size[0]}×{image.size[1]}，"
                f"引导图为 {guide_image.size[0]}×{guide_image.size[1]}。"
            )

    original_width, original_height = image.size
    resize_ratio = min(1.0, max_dimension / max(original_width, original_height))
    work_size = (
        max(1, round(original_width * resize_ratio)),
        max(1, round(original_height * resize_ratio)),
    )
    if work_size != image.size:
        image = image.resize(work_size, Image.Resampling.LANCZOS)
        if guide_image is not None:
            guide_image = guide_image.resize(work_size, Image.Resampling.NEAREST)
    if conversion_mode == "black_white_linework":
        return _convert_black_white_linework(
            source=source,
            image=image,
            output_dir=output_dir,
            reference_width_m=float(reference_width_m),
            min_component_pixels=int(min_component_pixels),
            line_threshold=int(line_threshold),
            simplify_factor=float(line_simplify_factor),
            trace_method=line_trace_method,
            optimize_linework=bool(optimize_linework),
            line_polarity=line_polarity,
            knowledge_profile=knowledge_profile,
        )
    classification_image = guide_image if guide_image is not None else image
    image_array = np.asarray(classification_image, dtype=np.float32)
    work_width, work_height = image.size
    pixel_size_m = float(reference_width_m) / work_width
    masks, preview_array = _classify_pixels(image_array, int(color_tolerance))
    focus_bbox = _site_focus_bbox(masks) if focus_site_only else None
    focus_applied = _apply_site_focus(masks, focus_bbox)
    if focus_site_only:
        preview_array = np.full(image_array.shape, 250, dtype=np.uint8)
        for name, mask in masks.items():
            preview_array[mask] = np.asarray(IMAGE_PALETTE[name], dtype=np.uint8)

    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    output_stem = "guided" if conversion_mode == "semantic_guide" else "ai"
    output_dxf = output_root / f"{source.stem}_{output_stem}_converted.dxf"
    output_preview = output_root / f"{source.stem}_{output_stem}_vector_preview.png"
    output_report = output_root / f"{source.stem}_{output_stem}_conversion_report.txt"
    output_alignment = (
        output_root / f"{source.stem}_guided_alignment_overlay.png"
        if conversion_mode == "semantic_guide"
        else None
    )

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # meters
    layer_colors = {
        "AI_BUILDING": 1,
        "AI_ROAD": 8,
        "AI_GREEN": 3,
        "AI_WATER": 5,
        "AI_PARKING": 2,
        "AI_LABEL": 7,
        "AI_FRAME": 9,
    }
    for layer, color in layer_colors.items():
        _ensure_layer(doc, layer, color)

    msp = doc.modelspace()
    frame = [(0.0, 0.0), (reference_width_m, 0.0),
             (reference_width_m, work_height * pixel_size_m),
             (0.0, work_height * pixel_size_m)]
    msp.add_lwpolyline(frame, close=True, dxfattribs={"layer": "AI_FRAME"})

    counts: Dict[str, int] = {}
    areas: Dict[str, float] = {}
    semantic_road_detection = {
        "region_count_before_gap_heal": 0,
        "region_count_after_gap_heal": 0,
        "network_component_count": 0,
        "healed_region_count": 0,
        "gap_closing_radius_px": 2,
        "status": "no_road_region",
    }
    simplify_m = max(pixel_size_m * 1.25, 0.02)
    label_height = max(min(reference_width_m / 80.0, 5.0), 0.8)
    for layer_name, mask in masks.items():
        before_gap_heal = None
        if layer_name == "AI_ROAD":
            before_gap_heal = _component_polygons(
                mask,
                pixel_size_m=pixel_size_m,
                min_component_pixels=int(min_component_pixels),
                simplify_m=simplify_m,
                closing_radius=1,
            )
        polygons = _component_polygons(
            mask,
            pixel_size_m=pixel_size_m,
            min_component_pixels=int(min_component_pixels),
            simplify_m=simplify_m,
            # A road path may have a tiny anti-aliased or click-spacing gap at
            # a junction.  Heal only a bounded 2-pixel road gap; other semantic
            # regions retain the stricter one-pixel behavior.
            closing_radius=2 if layer_name == "AI_ROAD" else 1,
        )
        counts[layer_name] = len(polygons)
        areas[layer_name] = sum(part.area for part in polygons)
        if layer_name == "AI_ROAD":
            road_union = unary_union(polygons) if polygons else GeometryCollection()
            network_parts = list(_iter_polygon_parts(road_union))
            network_count = len(network_parts)
            before_count = len(before_gap_heal or [])
            nearby_gap_threshold_px = 8.0
            nearby_gap_distances_m = []
            for first_index, first_polygon in enumerate(polygons):
                for second_polygon in polygons[first_index + 1:]:
                    gap_m = float(first_polygon.distance(second_polygon))
                    if 1e-9 < gap_m <= pixel_size_m * nearby_gap_threshold_px:
                        nearby_gap_distances_m.append(gap_m)
            nearby_gap_distances_m.sort()
            nearby_gap_count = len(nearby_gap_distances_m)
            semantic_road_detection = {
                "region_count_before_gap_heal": before_count,
                "region_count_after_gap_heal": len(polygons),
                "network_component_count": network_count,
                "healed_region_count": max(0, before_count - len(polygons)),
                "gap_closing_radius_px": 2,
                "nearby_gap_threshold_px": nearby_gap_threshold_px,
                "nearby_gap_suggestion_count": nearby_gap_count,
                "nearby_gap_distances_m": [
                    round(value, 3) for value in nearby_gap_distances_m[:12]
                ],
                "status": (
                    "single_network"
                    if network_count == 1
                    else "nearby_gaps_review"
                    if nearby_gap_count > 0
                    else "multiple_networks_review"
                    if network_count > 1
                    else "no_road_region"
                ),
            }
        for index, polygon in enumerate(polygons, start=1):
            _add_polygon(msp, polygon, layer_name)
            if polygon.area >= reference_width_m**2 * 0.002:
                point = polygon.representative_point()
                label = msp.add_mtext(
                    f"{layer_name.replace('AI_', '')} {polygon.area:.1f}m2",
                    dxfattribs={
                        "layer": "AI_LABEL",
                        "char_height": label_height,
                        "attachment_point": 5,
                    },
                )
                label.set_location(insert=(point.x, point.y, 0.0))

    total_regions = sum(counts.values())
    if total_regions == 0:
        raise ValueError(
            "没有识别到标准规划颜色。请使用标准化俯视图，或提高颜色识别容差后重试"
        )

    doc.saveas(output_dxf)
    Image.fromarray(preview_array, mode="RGB").save(output_preview)
    if output_alignment is not None:
        guide_overlay = np.zeros((work_height, work_width, 4), dtype=np.uint8)
        for name, mask in masks.items():
            guide_overlay[mask, :3] = np.asarray(IMAGE_PALETTE[name], dtype=np.uint8)
            guide_overlay[mask, 3] = 112
        alignment = Image.alpha_composite(
            image.convert("RGBA"),
            Image.fromarray(guide_overlay, mode="RGBA"),
        )
        alignment.convert("RGB").save(output_alignment)
    source_hash = sha256_file(source)
    with output_report.open("w", encoding="utf-8") as report:
        report.write("=== Planning Toolbox AI Image to CAD Report ===\n")
        report.write("This is a concept vectorization, not a survey or approval drawing.\n")
        report.write(f"Source image: {source.name}\n")
        report.write(f"Source SHA-256: {source_hash}\n")
        if guide_source is not None:
            report.write(f"Semantic guide image: {guide_source.name}\n")
            report.write(f"Semantic guide SHA-256: {guide_hash}\n")
            report.write("Semantic guide alignment: exact source pixel dimensions\n")
        report.write(f"Original image size: {original_width} x {original_height}\n")
        report.write(f"Processed image size: {work_width} x {work_height}\n")
        report.write(f"Reference width (m): {reference_width_m:g}\n")
        report.write(f"Pixel size (m): {pixel_size_m:.6f}\n")
        report.write(f"Color tolerance: {int(color_tolerance)}\n")
        report.write(f"Minimum component pixels: {int(min_component_pixels)}\n")
        report.write(f"Focus site only: {'yes' if focus_site_only else 'no'}\n")
        report.write(f"Focus applied: {'yes' if focus_applied else 'no'}\n")
        if focus_bbox:
            report.write(f"Focus bbox (px): {focus_bbox}\n")
        for layer_name in IMAGE_PALETTE:
            report.write(
                f"{layer_name}: {counts.get(layer_name, 0)} regions, "
                f"{areas.get(layer_name, 0.0):.2f} m2\n"
            )
        if conversion_mode == "semantic_guide":
            report.write(
                "Semantic road network: "
                f"{semantic_road_detection['region_count_after_gap_heal']} regions, "
                f"{semantic_road_detection['network_component_count']} network components, "
                f"healed {semantic_road_detection['healed_region_count']} small gaps, "
                f"nearby gap suggestions {semantic_road_detection['nearby_gap_suggestion_count']}, "
                f"status {semantic_road_detection['status']}\n"
            )
        report.write(
            "Warning: perspective renders, shadows, text, trees and decorative textures "
            "can be misclassified. Confirm the DXF overlay before using any measurements.\n"
        )

    from planning_toolbox.project.semantic_scene import build_semantic_scene_from_dxf

    semantic_scene = build_semantic_scene_from_dxf(
        output_dxf,
        source_image_path=source,
        source_image_sha256=source_hash,
        semantic_guide_path=guide_source,
        semantic_guide_sha256=guide_hash,
        reference_width_m=reference_width_m,
        conversion_mode=conversion_mode,
    )
    output_files = [
        (
            "语义引导图转换 DXF"
            if conversion_mode == "semantic_guide"
            else "AI 效果图转换 DXF",
            str(output_dxf),
        ),
        ("识别结果预览 PNG", str(output_preview)),
        ("识别说明报告", str(output_report)),
        ("全链路语义交接 JSON", semantic_scene["path"]),
    ]
    if output_alignment is not None:
        output_files.append(("原图与语义引导叠加检查 PNG", str(output_alignment)))
    if guide_source is not None:
        assert_file_unchanged(guide_source, guide_hash)
    result = {
        "task_type": "image_to_dxf",
        "dxf_file": str(output_dxf),
        "source_file": str(source),
        "source_sha256": source_hash,
        "image_size": (original_width, original_height),
        "processed_size": (work_width, work_height),
        "reference_width_m": float(reference_width_m),
        "pixel_size_m": pixel_size_m,
        "color_tolerance": int(color_tolerance),
        "min_component_pixels": int(min_component_pixels),
        "focus_site_only": bool(focus_site_only),
        "focus_applied": bool(focus_applied),
        "focus_bbox_px": focus_bbox,
        "conversion_mode": conversion_mode,
        "semantic_guide_file": str(guide_source) if guide_source else "",
        "semantic_guide_sha256": guide_hash,
        "region_counts": counts,
        "region_areas_m2": areas,
        "semantic_road_detection": semantic_road_detection,
        "semantic_scene_file": semantic_scene["path"],
        "semantic_scene_sha256": semantic_scene["sha256"],
        "semantic_scene_summary": semantic_scene["summary"],
        "output_files": output_files,
    }
    quality_baseline = write_image_to_cad_quality_baseline(result)
    result["quality_baseline_file"] = quality_baseline["path"]
    result["quality_baseline"] = quality_baseline
    result["output_files"].append(("图片转 CAD 中文质量复核清单", quality_baseline["review_path"]))
    result["output_files"].append(("图片转 CAD 质量基线 JSON", quality_baseline["path"]))
    return result
