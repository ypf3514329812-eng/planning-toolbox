"""CAD quality diagnostics and traceable repair-copy generation."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from math import floor, hypot
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import ezdxf
from shapely.geometry import LineString

from planning_toolbox.cad.layers.manager import (
    load_layer_config,
    standardize_document_layers,
)
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline
from planning_toolbox.core.units.unit_manager import INSUNITS_MAP, get_dxf_unit_code
from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file


Point2D = Tuple[float, float]
POLYLINE_TYPES = {"LWPOLYLINE", "POLYLINE"}
COMPLEX_ENTITY_TYPES = {
    "LINE",
    "ARC",
    "CIRCLE",
    "ELLIPSE",
    "SPLINE",
    "INSERT",
    "HATCH",
    "TEXT",
    "MTEXT",
    "DIMENSION",
    "LEADER",
    "MLEADER",
    "IMAGE",
    "WIPEOUT",
    "XLINE",
    "RAY",
    "3DFACE",
    "SOLID",
    "TRACE",
    "MESH",
    "3DSOLID",
}
PREVIEW_SUPPORTED_TYPES = POLYLINE_TYPES | {
    "LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE", "INSERT", "TEXT", "MTEXT"
}
AREA_ANALYSIS_TYPES = POLYLINE_TYPES


def _rounded_points(points: Sequence[Point2D]) -> Tuple[Point2D, ...]:
    return tuple((round(float(x), 6), round(float(y), 6)) for x, y in points)


def _signature(points: Sequence[Point2D], is_closed: bool, layer: str):
    normalized = _rounded_points(points)
    if not normalized:
        return layer, is_closed, normalized
    if is_closed:
        rotations = [normalized[i:] + normalized[:i] for i in range(len(normalized))]
        reversed_points = tuple(reversed(normalized))
        rotations.extend(
            reversed_points[i:] + reversed_points[:i]
            for i in range(len(reversed_points))
        )
        normalized = min(rotations)
    else:
        normalized = min(normalized, tuple(reversed(normalized)))
    return layer, is_closed, normalized


def _entity_points(entity) -> List[Point2D]:
    entity_type = entity.dxftype()
    if entity_type in POLYLINE_TYPES:
        return points_from_dxf_polyline(entity)[0]
    if entity_type == "LINE":
        return [
            (float(entity.dxf.start.x), float(entity.dxf.start.y)),
            (float(entity.dxf.end.x), float(entity.dxf.end.y)),
        ]
    if entity_type in {"CIRCLE", "ARC"}:
        center = entity.dxf.center
        radius = float(entity.dxf.radius)
        return [
            (center.x - radius, center.y - radius),
            (center.x + radius, center.y + radius),
        ]
    if entity_type == "ELLIPSE":
        center = entity.dxf.center
        major = entity.dxf.major_axis
        radius_x = hypot(major.x, major.y)
        radius_y = radius_x * float(entity.dxf.ratio)
        return [
            (center.x - radius_x, center.y - radius_y),
            (center.x + radius_x, center.y + radius_y),
        ]
    if entity_type == "SPLINE":
        points = list(getattr(entity, "fit_points", ())) or list(
            getattr(entity, "control_points", ())
        )
        return [
            (
                float(point.x) if hasattr(point, "x") else float(point[0]),
                float(point.y) if hasattr(point, "y") else float(point[1]),
            )
            for point in points
        ]
    return []


def _handle(entity) -> str:
    return str(getattr(entity.dxf, "handle", "") or "")


def _style_key(entity) -> Tuple[str, int, str, int]:
    return (
        str(getattr(entity.dxf, "layer", "0")).upper(),
        int(getattr(entity.dxf, "color", 256)),
        str(getattr(entity.dxf, "linetype", "BYLAYER")).upper(),
        int(getattr(entity.dxf, "lineweight", -1)),
    )


def _style_attributes(entity) -> Dict[str, Any]:
    return {
        "layer": str(getattr(entity.dxf, "layer", "0")),
        "color": int(getattr(entity.dxf, "color", 256)),
        "linetype": str(getattr(entity.dxf, "linetype", "BYLAYER")),
        "lineweight": int(getattr(entity.dxf, "lineweight", -1)),
    }


def _lwpolyline_has_bulge(entity) -> bool:
    if entity.dxftype() != "LWPOLYLINE":
        return True
    return any(abs(float(point[4])) > 1e-12 for point in entity.get_points("xyseb"))


def _vertex_count(msp) -> int:
    count = 0
    for entity in msp:
        entity_type = entity.dxftype()
        if entity_type in POLYLINE_TYPES:
            count += len(points_from_dxf_polyline(entity)[0])
        elif entity_type == "LINE":
            count += 2
    return count


def _point_distance(first: Point2D, second: Point2D) -> float:
    return hypot(first[0] - second[0], first[1] - second[1])


def _point_segment_distance(point: Point2D, start: Point2D, end: Point2D) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-24:
        return _point_distance(point, start)
    ratio = (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / length_sq
    if ratio < 0.0 or ratio > 1.0:
        return min(_point_distance(point, start), _point_distance(point, end))
    projected = (start[0] + ratio * dx, start[1] + ratio * dy)
    return _point_distance(point, projected)


def _clean_straight_vertices(
    points: Sequence[Point2D],
    is_closed: bool,
    collinear_tolerance: float,
    min_segment_length: float,
) -> Tuple[List[Point2D], int, int]:
    """Remove near-duplicate and collinear vertices without moving endpoints."""
    cleaned = [(float(x), float(y)) for x, y in points]
    removed_short = 0
    removed_collinear = 0
    minimum_vertices = 3 if is_closed else 2

    if min_segment_length > 0 and len(cleaned) > minimum_vertices:
        changed = True
        while changed and len(cleaned) > minimum_vertices:
            changed = False
            pair_count = len(cleaned) if is_closed else len(cleaned) - 1
            for index in range(pair_count):
                next_index = (index + 1) % len(cleaned)
                if _point_distance(cleaned[index], cleaned[next_index]) >= min_segment_length:
                    continue
                if not is_closed and index == 0:
                    remove_index = next_index
                elif not is_closed and next_index == len(cleaned) - 1:
                    remove_index = index
                else:
                    remove_index = next_index
                cleaned.pop(remove_index)
                removed_short += 1
                changed = True
                break

    if collinear_tolerance > 0 and len(cleaned) > minimum_vertices:
        changed = True
        while changed and len(cleaned) > minimum_vertices:
            changed = False
            indices: Iterable[int]
            indices = range(len(cleaned)) if is_closed else range(1, len(cleaned) - 1)
            for index in indices:
                previous = cleaned[index - 1]
                current = cleaned[index]
                following = cleaned[(index + 1) % len(cleaned)]
                if _point_segment_distance(current, previous, following) <= collinear_tolerance:
                    cleaned.pop(index)
                    removed_collinear += 1
                    changed = True
                    break

    return cleaned, removed_collinear, removed_short


def _endpoint_clusters(
    fragments: Sequence[Dict[str, Any]],
    tolerance: float,
) -> Tuple[List[int], Dict[int, Point2D]]:
    endpoints: List[Point2D] = []
    for fragment in fragments:
        endpoints.extend((fragment["points"][0], fragment["points"][-1]))

    parents = list(range(len(endpoints)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    if tolerance <= 0:
        exact: Dict[Point2D, int] = {}
        for index, point in enumerate(endpoints):
            key = (round(point[0], 9), round(point[1], 9))
            if key in exact:
                union(index, exact[key])
            else:
                exact[key] = index
    else:
        buckets: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for index, point in enumerate(endpoints):
            cell = (floor(point[0] / tolerance), floor(point[1] / tolerance))
            for delta_x in (-1, 0, 1):
                for delta_y in (-1, 0, 1):
                    for candidate in buckets.get((cell[0] + delta_x, cell[1] + delta_y), []):
                        if _point_distance(point, endpoints[candidate]) <= tolerance:
                            union(index, candidate)
            buckets[cell].append(index)

    members: Dict[int, List[int]] = defaultdict(list)
    for index in range(len(endpoints)):
        members[find(index)].append(index)
    root_to_node = {root: node for node, root in enumerate(sorted(members))}
    endpoint_nodes = [root_to_node[find(index)] for index in range(len(endpoints))]
    centers = {
        root_to_node[root]: (
            sum(endpoints[index][0] for index in indices) / len(indices),
            sum(endpoints[index][1] for index in indices) / len(indices),
        )
        for root, indices in members.items()
    }
    return endpoint_nodes, centers


def _collect_merge_fragments(msp) -> Dict[Tuple[str, int, str, int], List[Dict[str, Any]]]:
    groups: Dict[Tuple[str, int, str, int], List[Dict[str, Any]]] = defaultdict(list)
    for entity in list(msp):
        entity_type = entity.dxftype()
        if entity_type == "LINE":
            points = _entity_points(entity)
        elif entity_type == "LWPOLYLINE" and not entity.closed and not _lwpolyline_has_bulge(entity):
            points = _entity_points(entity)
        else:
            continue
        if len(points) < 2:
            continue
        groups[_style_key(entity)].append({"entity": entity, "points": points})
    return groups


def _merge_fragment_chains(
    msp,
    tolerance: float,
    change_log: List[Dict[str, str]],
) -> Dict[str, Any]:
    merged_groups = 0
    merged_source_entities = 0
    branching_components_skipped = 0
    max_snap_distance = 0.0

    for fragments in _collect_merge_fragments(msp).values():
        if len(fragments) < 2:
            continue
        endpoint_nodes, centers = _endpoint_clusters(fragments, tolerance)
        edges = [
            (endpoint_nodes[2 * index], endpoint_nodes[2 * index + 1])
            for index in range(len(fragments))
        ]
        adjacency: Dict[int, List[int]] = defaultdict(list)
        for edge_index, (start, end) in enumerate(edges):
            adjacency[start].append(edge_index)
            adjacency[end].append(edge_index)

        remaining = set(range(len(edges)))
        while remaining:
            seed = next(iter(remaining))
            component_edges = set()
            stack = [seed]
            component_nodes = set()
            while stack:
                edge_index = stack.pop()
                if edge_index in component_edges:
                    continue
                component_edges.add(edge_index)
                remaining.discard(edge_index)
                start, end = edges[edge_index]
                component_nodes.update((start, end))
                for node in (start, end):
                    stack.extend(
                        candidate
                        for candidate in adjacency[node]
                        if candidate not in component_edges
                    )

            if len(component_edges) < 2:
                continue
            degrees = {
                node: sum(1 for edge_index in component_edges if node in edges[edge_index])
                for node in component_nodes
            }
            if any(degree > 2 for degree in degrees.values()):
                branching_components_skipped += 1
                continue

            endpoints = [node for node, degree in degrees.items() if degree == 1]
            current_node = min(endpoints) if endpoints else min(component_nodes)
            first_node = current_node
            unvisited = set(component_edges)
            combined: List[Point2D] = []
            ordered_edges: List[int] = []
            while unvisited:
                candidates = [edge for edge in adjacency[current_node] if edge in unvisited]
                if not candidates:
                    break
                edge_index = min(candidates)
                unvisited.remove(edge_index)
                ordered_edges.append(edge_index)
                start, end = edges[edge_index]
                if start == current_node:
                    next_node = end
                    oriented = list(fragments[edge_index]["points"])
                else:
                    next_node = start
                    oriented = list(reversed(fragments[edge_index]["points"]))
                original_start, original_end = oriented[0], oriented[-1]
                oriented[0] = centers[current_node]
                oriented[-1] = centers[next_node]
                max_snap_distance = max(
                    max_snap_distance,
                    _point_distance(original_start, oriented[0]),
                    _point_distance(original_end, oriented[-1]),
                )
                if not combined:
                    combined.extend(oriented)
                else:
                    combined.extend(oriented[1:])
                current_node = next_node

            if unvisited or len(ordered_edges) != len(component_edges):
                branching_components_skipped += 1
                continue
            closed = current_node == first_node
            if closed and len(combined) >= 2 and _point_distance(combined[0], combined[-1]) <= 1e-9:
                combined.pop()
            deduplicated = [combined[0]]
            for point in combined[1:]:
                if _point_distance(point, deduplicated[-1]) > 1e-12:
                    deduplicated.append(point)
            if len(deduplicated) < (3 if closed else 2):
                continue

            first_entity = fragments[ordered_edges[0]]["entity"]
            source_entities = [fragments[index]["entity"] for index in ordered_edges]
            source_handles = [_handle(entity) for entity in source_entities]
            new_entity = msp.add_lwpolyline(
                deduplicated,
                close=closed,
                dxfattribs=_style_attributes(first_entity),
            )
            for entity in source_entities:
                msp.delete_entity(entity)
            merged_groups += 1
            merged_source_entities += len(source_entities)
            change_log.append({
                "action": "merge_fragments",
                "layer": str(new_entity.dxf.layer),
                "source_handles": ";".join(source_handles),
                "output_handle": _handle(new_entity),
                "details": (
                    f"{len(source_entities)} entities -> 1 {'closed' if closed else 'open'} "
                    f"polyline; {len(deduplicated)} vertices"
                ),
            })

    return {
        "merged_fragment_groups": merged_groups,
        "merged_source_entities": merged_source_entities,
        "fragment_entity_reduction": max(0, merged_source_entities - merged_groups),
        "branching_components_skipped": branching_components_skipped,
        "max_endpoint_snap_distance": max_snap_distance,
    }


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"无法为输出文件生成安全的新名称：{path}")


def _write_change_log(path: Path, changes: Sequence[Dict[str, str]]) -> None:
    columns = ["action", "layer", "source_handles", "output_handle", "details"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(changes)


def scan_dxf_quality(
    dxf_path: Path | str,
    near_closed_tolerance: float = 0.01,
) -> Dict[str, Any]:
    """Scan duplicate/open/invalid geometry, extents, units and entity types."""
    path = Path(dxf_path).resolve()
    source_sha256 = sha256_file(path)
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    entity_counts: Counter[str] = Counter()
    layer_counts: Counter[str] = Counter()
    polyline_signatures = set()
    line_signatures = set()
    duplicate_indices: List[int] = []
    duplicate_line_indices: List[int] = []
    open_indices: List[int] = []
    near_closed_indices: List[int] = []
    self_intersection_indices: List[int] = []
    extent_points: List[Point2D] = []
    straight_fragment_count = 0
    block_reference_counts: Counter[str] = Counter()

    for index, entity in enumerate(msp):
        entity_type = entity.dxftype()
        layer = str(getattr(entity.dxf, "layer", "0"))
        entity_counts[entity_type] += 1
        layer_counts[layer] += 1
        points = _entity_points(entity)
        extent_points.extend(points)

        if entity_type == "INSERT":
            block_reference_counts[str(getattr(entity.dxf, "name", "<unnamed>"))] += 1

        if entity_type == "LINE" and len(points) == 2:
            straight_fragment_count += 1
            signature = _signature(points, False, layer.upper())
            if signature in line_signatures:
                duplicate_line_indices.append(index)
            else:
                line_signatures.add(signature)
            continue
        if entity_type not in POLYLINE_TYPES:
            continue
        vertices, is_closed, _ = points_from_dxf_polyline(entity)
        if len(vertices) < 2:
            continue
        if not is_closed:
            open_indices.append(index)
            if entity_type == "LWPOLYLINE" and not _lwpolyline_has_bulge(entity):
                straight_fragment_count += 1
            endpoint_distance = _point_distance(vertices[0], vertices[-1])
            if endpoint_distance <= near_closed_tolerance:
                near_closed_indices.append(index)
        line = LineString(vertices + ([vertices[0]] if is_closed else []))
        if not line.is_simple:
            self_intersection_indices.append(index)
        signature = _signature(vertices, is_closed, layer.upper())
        if signature in polyline_signatures:
            duplicate_indices.append(index)
        else:
            polyline_signatures.add(signature)

    layer_names = {str(layer.dxf.name) for layer in doc.layers}
    empty_layers = sorted(layer_names - set(layer_counts))
    if extent_points:
        xs = [point[0] for point in extent_points]
        ys = [point[1] for point in extent_points]
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
        width = max_x - min_x
        height = max_y - min_y
        extent_ratio = max(width, height) / min(width, height) if min(width, height) > 0 else None
        max_coordinate = max(max(abs(value) for value in xs), max(abs(value) for value in ys))
    else:
        min_x = max_x = min_y = max_y = width = height = max_coordinate = None
        extent_ratio = None

    scale_warnings = []
    if extent_ratio is None:
        scale_warnings.append("无法建立有效二维范围")
    elif extent_ratio > 100:
        scale_warnings.append(f"图纸范围长宽比异常：{extent_ratio:.2f}")
    if max_coordinate is not None and max_coordinate > 10_000_000:
        scale_warnings.append(f"坐标绝对值较大：{max_coordinate:.2f}")

    block_names = {str(block.name) for block in doc.blocks}
    unresolved_block_references = sorted(
        name for name in block_reference_counts if name not in block_names
    )
    external_reference_names = []
    for block in doc.blocks:
        flags = int(getattr(block.block_record.dxf, "flags", 0) or 0)
        if flags & 4:
            external_reference_names.append(str(block.name))

    paper_space_entity_count = sum(
        len(layout)
        for layout in doc.layouts
        if str(layout.name).lower() != "model"
    )
    unit_code = get_dxf_unit_code(doc)
    assert_file_unchanged(path, source_sha256)
    return {
        "source_file": str(path),
        "source_sha256": source_sha256,
        "unit_code": unit_code,
        "unit_name": INSUNITS_MAP.get(unit_code, "Unspecified"),
        "entity_count": len(msp),
        "vertex_count": _vertex_count(msp),
        "entity_counts": dict(sorted(entity_counts.items())),
        "complex_entity_counts": {
            key: value for key, value in sorted(entity_counts.items()) if key in COMPLEX_ENTITY_TYPES
        },
        "preview_supported_entity_counts": {
            key: value
            for key, value in sorted(entity_counts.items())
            if key in PREVIEW_SUPPORTED_TYPES
        },
        "manual_review_entity_counts": {
            key: value
            for key, value in sorted(entity_counts.items())
            if key not in AREA_ANALYSIS_TYPES
        },
        "block_reference_counts": dict(sorted(block_reference_counts.items())),
        "unresolved_block_references": unresolved_block_references,
        "external_reference_names": sorted(external_reference_names),
        "paper_space_entity_count": paper_space_entity_count,
        "layer_counts": dict(sorted(layer_counts.items())),
        "empty_layers": empty_layers,
        "duplicate_count": len(duplicate_indices),
        "duplicate_indices": duplicate_indices,
        "duplicate_line_count": len(duplicate_line_indices),
        "duplicate_line_indices": duplicate_line_indices,
        "straight_fragment_count": straight_fragment_count,
        "open_count": len(open_indices),
        "open_indices": open_indices,
        "near_closed_count": len(near_closed_indices),
        "near_closed_indices": near_closed_indices,
        "self_intersection_count": len(self_intersection_indices),
        "self_intersection_indices": self_intersection_indices,
        "extent": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "width": width,
            "height": height,
            "ratio": extent_ratio,
        },
        "scale_warnings": scale_warnings,
    }


def repair_dxf_quality(
    dxf_path: Path | str,
    output_dir: Path | str,
    near_closed_tolerance: float = 0.01,
    remove_duplicates: bool = True,
    close_near_closed: bool = True,
    remove_duplicate_lines: bool = False,
    merge_connected_fragments: bool = False,
    join_tolerance: float = 0.05,
    simplify_collinear_vertices: bool = False,
    collinear_tolerance: float = 0.01,
    remove_short_vertices: bool = False,
    min_segment_length: float = 0.01,
    standardize_layers: bool = False,
    layer_config_path: Path | str | None = None,
    require_known_units: bool = False,
) -> Dict[str, Any]:
    """Write a traceable repaired copy while preserving the source DXF.

    Fragment merging is deliberately limited to non-branching, straight LINE
    and open LWPOLYLINE chains with matching layer/style. Curves, blocks and
    junctions remain untouched for manual review.
    """
    numeric_values = {
        "近闭合容差": near_closed_tolerance,
        "碎线连接容差": join_tolerance,
        "共线判断容差": collinear_tolerance,
        "最短线段": min_segment_length,
    }
    for label, value in numeric_values.items():
        if float(value) < 0:
            raise ValueError(f"{label}不能小于 0。")

    source = Path(dxf_path).resolve()
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    source_sha256 = sha256_file(source)
    doc = ezdxf.readfile(source)
    unit_code = get_dxf_unit_code(doc)
    if require_known_units and unit_code == 0 and (
        merge_connected_fragments
        or simplify_collinear_vertices
        or remove_short_vertices
        or close_near_closed
    ):
        raise ValueError(
            "DXF 插入单位为未知（$INSUNITS=0），无法安全解释连接、共线或短线容差。"
            "请先在 CAD 中设置图纸单位后再使用“最低人工修改”模式。"
        )

    msp = doc.modelspace()
    source_entity_count = len(msp)
    source_vertex_count = _vertex_count(msp)
    change_log: List[Dict[str, str]] = []
    standardized_layer_count = 0
    remapped_counts: Dict[str, int] = {}
    unmapped_layers: List[str] = []

    if standardize_layers:
        before_layers = {
            id(entity): (_handle(entity), str(getattr(entity.dxf, "layer", "0")))
            for entity in msp
        }
        remapped_counts, unmapped_layers = standardize_document_layers(
            doc,
            load_layer_config(layer_config_path),
        )
        for entity in msp:
            handle, old_layer = before_layers[id(entity)]
            new_layer = str(getattr(entity.dxf, "layer", "0"))
            if old_layer != new_layer:
                standardized_layer_count += 1
                change_log.append({
                    "action": "standardize_layer",
                    "layer": new_layer,
                    "source_handles": handle,
                    "output_handle": handle,
                    "details": f"{old_layer} -> {new_layer}",
                })

    polyline_signatures = set()
    line_signatures = set()
    removed_duplicates = 0
    removed_duplicate_lines = 0
    closed_polylines = 0

    for entity in list(msp):
        entity_type = entity.dxftype()
        layer = str(getattr(entity.dxf, "layer", "0")).upper()
        if entity_type == "LINE":
            points = _entity_points(entity)
            signature = _signature(points, False, layer)
            if remove_duplicate_lines and signature in line_signatures:
                change_log.append({
                    "action": "remove_duplicate_line",
                    "layer": str(entity.dxf.layer),
                    "source_handles": _handle(entity),
                    "output_handle": "",
                    "details": "Exact duplicate LINE removed",
                })
                msp.delete_entity(entity)
                removed_duplicate_lines += 1
                continue
            line_signatures.add(signature)
            continue
        if entity_type not in POLYLINE_TYPES:
            continue
        vertices, is_closed, _ = points_from_dxf_polyline(entity)
        signature = _signature(vertices, is_closed, layer)
        if remove_duplicates and signature in polyline_signatures:
            change_log.append({
                "action": "remove_duplicate_polyline",
                "layer": str(entity.dxf.layer),
                "source_handles": _handle(entity),
                "output_handle": "",
                "details": "Exact duplicate polyline removed",
            })
            msp.delete_entity(entity)
            removed_duplicates += 1
            continue
        polyline_signatures.add(signature)
        if close_near_closed and not is_closed and len(vertices) >= 3:
            endpoint_distance = _point_distance(vertices[0], vertices[-1])
            if endpoint_distance <= near_closed_tolerance:
                entity.close(True)
                closed_polylines += 1
                change_log.append({
                    "action": "close_near_polyline",
                    "layer": str(entity.dxf.layer),
                    "source_handles": _handle(entity),
                    "output_handle": _handle(entity),
                    "details": f"Endpoint gap {endpoint_distance:.6g} drawing units",
                })

    merge_result = {
        "merged_fragment_groups": 0,
        "merged_source_entities": 0,
        "fragment_entity_reduction": 0,
        "branching_components_skipped": 0,
        "max_endpoint_snap_distance": 0.0,
    }
    if merge_connected_fragments:
        merge_result = _merge_fragment_chains(msp, float(join_tolerance), change_log)

    simplified_polylines = 0
    removed_collinear_vertices = 0
    removed_short_vertex_count = 0
    if simplify_collinear_vertices or remove_short_vertices:
        for entity in list(msp):
            if entity.dxftype() != "LWPOLYLINE" or _lwpolyline_has_bulge(entity):
                continue
            points = _entity_points(entity)
            cleaned, collinear_removed, short_removed = _clean_straight_vertices(
                points,
                bool(entity.closed),
                float(collinear_tolerance) if simplify_collinear_vertices else 0.0,
                float(min_segment_length) if remove_short_vertices else 0.0,
            )
            if not collinear_removed and not short_removed:
                continue
            entity.set_points(cleaned, format="xy")
            simplified_polylines += 1
            removed_collinear_vertices += collinear_removed
            removed_short_vertex_count += short_removed
            change_log.append({
                "action": "simplify_polyline",
                "layer": str(entity.dxf.layer),
                "source_handles": _handle(entity),
                "output_handle": _handle(entity),
                "details": (
                    f"Removed {collinear_removed} collinear and {short_removed} short vertices"
                ),
            })

    output_file = _next_available_path(output_path / f"{source.stem}_quality_repaired.dxf")
    if output_file.resolve() == source:
        raise ValueError("修复输出路径不能覆盖原始 DXF。")
    change_log_file = output_file.with_name(f"{output_file.stem}_changes.csv")
    doc.saveas(output_file)
    _write_change_log(change_log_file, change_log)
    assert_file_unchanged(source, source_sha256)

    return {
        "output_file": str(output_file.resolve()),
        "change_log_file": str(change_log_file.resolve()),
        "source_sha256": source_sha256,
        "unit_code": unit_code,
        "unit_name": INSUNITS_MAP.get(unit_code, "Unspecified"),
        "source_entity_count": source_entity_count,
        "output_entity_count": len(msp),
        "source_vertex_count": source_vertex_count,
        "output_vertex_count": _vertex_count(msp),
        "removed_duplicates": removed_duplicates,
        "removed_duplicate_lines": removed_duplicate_lines,
        "closed_polylines": closed_polylines,
        "simplified_polylines": simplified_polylines,
        "removed_collinear_vertices": removed_collinear_vertices,
        "removed_short_vertices": removed_short_vertex_count,
        "standardized_layer_count": standardized_layer_count,
        "remapped_counts": remapped_counts,
        "unmapped_layers": unmapped_layers,
        "change_count": len(change_log),
        "change_log": change_log,
        **merge_result,
    }
