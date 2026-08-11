"""QThread 异步任务执行器 (处理耗时 CAD/GIS 计算，防止 UI 界面卡死)."""
from pathlib import Path
from typing import Dict, Any
import math
from PySide6.QtCore import QThread, Signal

class TaskWorker(QThread):
    """
    后台计算线程 Worker，支持分析、GIS、批量、概念方案和图层标准化任务。
    """
    progress_signal = Signal(int, str)       # (进度百分比, 状态描述)
    finished_signal = Signal(dict)          # (任务结果摘要字典)
    error_signal = Signal(str, str)         # (错误标题, 用户友好的中文错误说明)

    def __init__(self, task_type: str, params: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.task_type = task_type
        self.params = params
        self._is_cancelled = False

    def cancel(self):
        """请求取消任务。"""
        self._is_cancelled = True
        self.requestInterruption()

    def _cancel_requested(self) -> bool:
        """Return whether the task has received a cooperative cancellation request."""
        return self._is_cancelled or self.isInterruptionRequested()

    def run(self):
        try:
            if self._cancel_requested():
                return
            self.progress_signal.emit(10, "正在准备任务...")

            if self.task_type == "parcel":
                self._run_parcel_task()
            elif self.task_type == "indicator":
                self._run_indicator_task()
            elif self.task_type == "validate":
                self._run_validate_task()
            elif self.task_type == "gis_export":
                self._run_gis_export_task()
            elif self.task_type == "gis_import":
                self._run_gis_import_task()
            elif self.task_type == "batch":
                self._run_batch_task()
            elif self.task_type == "concept_plan":
                self._run_concept_plan_task()
            elif self.task_type == "layer_standardize":
                self._run_layer_standardize_task()
            elif self.task_type == "quality_check":
                self._run_quality_check_task()
            elif self.task_type == "image_to_dxf":
                self._run_image_to_dxf_task()
            elif self.task_type == "dwg_convert":
                self._run_dwg_convert_task()
            elif self.task_type == "sketchup_export":
                self._run_sketchup_export_task()
            else:
                self.error_signal.emit("未知的任务类型", f"暂不支持任务类型 '{self.task_type}'")

        except ValueError as e:
            msg = str(e)
            if type(e).__name__ == "UnitError":
                self.error_signal.emit(
                    "单位核验失败",
                    "无法确认 DXF 单位 ($INSUNITS)。\n\n建议步骤：\n"
                    "1. 在 AutoCAD 中打开 DXF 文件，输入 UNITS 命令将单位设为【米】。\n"
                    "2. 或在配置文件中指定 fallback_unit。",
                )
            elif "Direct overwrite is forbidden" in msg:
                from planning_toolbox.utils.i18n import ERR_PATH_COLLISION

                self.error_signal.emit("输出路径错误", ERR_PATH_COLLISION)
            else:
                self.error_signal.emit("参数校验错误", msg)
        except FileNotFoundError as e:
            self.error_signal.emit("文件未找到", str(e))
        except Exception as e:
            if type(e).__name__ == "UnitError":
                self.error_signal.emit(
                    "单位核验失败",
                    "无法确认 DXF 单位 ($INSUNITS)。\n\n建议步骤：\n"
                    "1. 在 AutoCAD 中打开 DXF 文件，输入 UNITS 命令将单位设为【米】。\n"
                    "2. 或在配置文件中指定 fallback_unit。",
                )
            elif type(e).__name__ == "GISImportError":
                self.error_signal.emit("GIS 数据导入失败", f"无法导入 GeoJSON：{e}")
            elif type(e).__name__ == "GISAdapterUnavailableError":
                self.error_signal.emit("需要安装本机 GIS 转换组件", str(e))
            elif type(e).__name__ in {
                "GISConversionError",
                "CRSValidationError",
                "ArcGISConversionError",
                "VectorAdapterUnavailableError",
            }:
                self.error_signal.emit("GIS 转换未完成", str(e))
            elif type(e).__name__ == "DwgConverterUnavailable":
                self.error_signal.emit("需要安装本机 DWG 转换组件", str(e))
            else:
                self.error_signal.emit("计算过程异常", f"处理过程中发生错误:\n{str(e)}")

    def _run_parcel_task(self):
        from planning_toolbox.cad.parcels.calculator import process_parcels
        from planning_toolbox.config import load_config
        from planning_toolbox.utils.file_integrity import sha256_file

        dxf_path = Path(self.params["dxf_path"])
        source_sha256_before = sha256_file(dxf_path)
        out_dir = Path(self.params.get("output_dir", "output"))
        cfg_path = self.params.get("config_path")
        cfg = load_config(cfg_path)

        if "target_layer" in self.params and self.params["target_layer"]:
            cfg.setdefault("parcel", {})["input_layers"] = [self.params["target_layer"]]

        self.progress_signal.emit(30, f"正在解析 CAD 地块多边形: {dxf_path.name}...")
        parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, cfg, out_dir)

        if self._cancel_requested():
            return

        self.progress_signal.emit(90, "正在生成标注与分析报告...")

        valid_count = sum(1 for p in parcels if p.status == "VALID")
        total_ha = sum(p.area_ha for p in parcels if p.status == "VALID")
        total_m2 = sum(p.area_m2 for p in parcels if p.status == "VALID")
        open_count = sum(1 for p in parcels if p.status == "OPEN")
        invalid_count = sum(1 for p in parcels if p.status in ("INVALID_GEOMETRY", "ZERO_AREA"))
        nested_count = sum(1 for p in parcels if p.status == "NESTED_RING_DETECTED")

        geojson_file = out_dir / f"{dxf_path.stem}.geojson"

        self.progress_signal.emit(100, "地块计算完成！")
        self.finished_signal.emit({
            "task_type": "parcel",
            "source_file": str(dxf_path),
            "total_candidates": len(parcels),
            "valid_count": valid_count,
            "open_count": open_count,
            "invalid_count": invalid_count,
            "nested_count": nested_count,
            "source_sha256": source_sha256_before,
            "total_ha": total_ha,
            "total_m2": total_m2,
            "output_files": [
                ("标注 DXF", str(labeled_dxf)),
                ("CSV 统计表", str(csv_file)),
                ("GeoJSON 矢量", str(geojson_file)),
                ("详细分析报告", str(report_file))
            ]
        })

    def _run_indicator_task(self):
        from planning_toolbox.config import load_config
        from planning_toolbox.indicators.calculator import process_dxf_indicators
        from planning_toolbox.utils.file_integrity import sha256_file

        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        raw_floors = self.params.get("floors")
        if raw_floors is None:
            raise ValueError("规划指标计算必须明确填写楼层倍数，系统不会自动假设楼层数。")
        try:
            floors = float(raw_floors)
        except (TypeError, ValueError) as exc:
            raise ValueError("建筑楼层倍数必须是正数。") from exc
        if not math.isfinite(floors) or floors <= 0:
            raise ValueError("建筑楼层倍数必须是正数。")
        if floors.is_integer():
            floors = int(floors)

        source_sha256_before = sha256_file(dxf_path)
        
        cfg_path = self.params.get("config_path")
        cfg = load_config(cfg_path)
        cfg["default_floors"] = floors

        if "building_layer" in self.params and self.params["building_layer"]:
            cfg["building_layer"] = self.params["building_layer"]
        if "green_layer" in self.params and self.params["green_layer"]:
            cfg["green_layer"] = self.params["green_layer"]

        self.progress_signal.emit(40, f"正在计算地块内部建筑与绿地空间求交 (楼层倍数: {floors})...")
        results, csv_file, report_file = process_dxf_indicators(dxf_path, config=cfg, output_dir=out_dir)

        if self._cancel_requested():
            return

        self.progress_signal.emit(100, "指标计算完成！")
        self.finished_signal.emit({
            "task_type": "indicator",
            "source_file": str(dxf_path),
            "parcels_count": len(results),
            "floors": floors,
            "source_sha256": source_sha256_before,
            "indicators": [r.to_dict() for r in results],
            "output_files": [
                ("指标 CSV 统计表", str(csv_file)),
                ("指标文本报告", str(report_file))
            ]
        })

    def _run_validate_task(self):
        import ezdxf

        from planning_toolbox.core.geometry.parser import (
            parse_parcel_geometry,
            points_from_dxf_polyline,
        )
        from planning_toolbox.core.units.unit_manager import (
            get_dxf_unit_code,
            get_linear_scale_to_m,
            resolve_unit,
        )
        from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file
        from planning_toolbox.validators.setback import check_building_setback
        from planning_toolbox.validators.topology import validate_polyline_topology

        dxf_path = Path(self.params["dxf_path"])
        source_sha256_before = sha256_file(dxf_path)
        out_dir = Path(self.params.get("output_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        setback_m = float(self.params["setback_m"])
        if setback_m < 0:
            raise ValueError("建筑退线距离必须是非负数（米）。")
        parcel_layer = self.params.get("parcel_layer", "PARCEL").upper()
        building_layer = self.params.get("building_layer", "BUILDING").upper()
        fallback_unit = self.params.get("fallback_unit")

        self.progress_signal.emit(30, "正在检查 CAD 拓扑有效性...")
        doc = ezdxf.readfile(dxf_path)
        
        # 显式校验单位安全
        unit_code = get_dxf_unit_code(doc)
        unit_name = resolve_unit(unit_code, fallback_unit=fallback_unit, strict_check=(fallback_unit is None))
        geometry_unit_to_m = get_linear_scale_to_m(unit_name)
        
        msp = doc.modelspace()

        # 1. Topology Audit
        topology_results = []
        for idx, entity in enumerate(msp):
            if entity.dxftype() in ('LWPOLYLINE', 'POLYLINE'):
                res = validate_polyline_topology(entity, idx)
                topology_results.append(res)

        valid_count = sum(1 for r in topology_results if r.status == "VALID")
        open_count = sum(1 for r in topology_results if r.status == "OPEN")
        invalid_count = sum(1 for r in topology_results if r.status == "INVALID_GEOMETRY")

        # 2. Building Setback Check
        self.progress_signal.emit(60, f"正在进行建筑退线规则检查 (要求 ≥ {setback_m}m)...")
        parcel_polys = []
        building_polys = []

        for entity in msp:
            if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
                continue
            layer_upper = str(entity.dxf.layer).upper()
            pts, is_closed, _ = points_from_dxf_polyline(entity)
            status, poly, _ = parse_parcel_geometry(pts, is_closed)
            if status == "VALID" and poly:
                if layer_upper == parcel_layer:
                    parcel_polys.append(poly)
                elif layer_upper == building_layer:
                    building_polys.append(poly)

        setback_results = []
        if parcel_polys:
            for idx, p_poly in enumerate(parcel_polys, start=1):
                pid = f"P{idx:03d}"
                parcel_buildings = [b_poly for b_poly in building_polys if p_poly.intersects(b_poly)]
                res = check_building_setback(
                    p_poly,
                    parcel_buildings,
                    setback_m,
                    parcel_id=pid,
                    geometry_unit_to_m=geometry_unit_to_m,
                )
                setback_results.append({
                    "parcel_id": pid,
                    "status": res.status,
                    "violations": res.violations_count,
                    "min_distance_m": res.min_distance_m,
                    "error_message": res.error_message or ""
                })

        self.progress_signal.emit(100, "规则与拓扑检查完成！")
        if self._cancel_requested():
            return
        assert_file_unchanged(dxf_path, source_sha256_before)
        report_file = out_dir / f"{dxf_path.stem}_validate_report.txt"
        with report_file.open("w", encoding="utf-8") as report:
            report.write("=== Planning Toolbox Validation Report ===\n")
            report.write(f"Source DXF: {dxf_path.name}\n")
            report.write(f"Source SHA-256: {source_sha256_before}\n")
            report.write(f"Detected Unit: {unit_name}\n")
            report.write(f"Setback Requirement (m): {setback_m:g}\n")
            report.write(f"Scanned Polylines: {len(topology_results)}\n")
            report.write(f"Valid Closed Polylines: {valid_count}\n")
            report.write(f"Open Polylines: {open_count}\n")
            report.write(f"Invalid Geometry: {invalid_count}\n")
            report.write("--- Parcel Setback Results ---\n")
            for item in setback_results:
                report.write(
                    f"[{item['parcel_id']}] {item['status']} | "
                    f"min_distance_m={item['min_distance_m']:.3f} | "
                    f"violations={item['violations']}\n"
                )
        self.finished_signal.emit({
            "task_type": "validate",
            "source_file": str(dxf_path),
            "unit_name": unit_name,
            "scanned_polylines": len(topology_results),
            "valid_count": valid_count,
            "open_count": open_count,
            "invalid_count": invalid_count,
            "setback_m": setback_m,
            "setback_results": setback_results,
            "source_sha256": source_sha256_before,
            "output_files": [("退线检查报告", str(report_file))]
        })

    def _run_gis_export_task(self):
        from planning_toolbox.cad.parcels.calculator import process_parcels
        from planning_toolbox.config import load_config
        from planning_toolbox.gis.crs import require_projected_metric_crs
        from planning_toolbox.project.chain_manifest import ChainManifest
        from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file

        dxf_path = Path(self.params["dxf_path"])
        source_sha256_before = sha256_file(dxf_path)
        out_dir = Path(self.params.get("output_dir", "output"))
        cfg = load_config(self.params.get("config_path"))
        output_format = str(self.params.get("output_format", "geojson")).lower()
        manifest_value = self.params.get("chain_manifest")
        manifest = ChainManifest.from_dict(manifest_value) if isinstance(manifest_value, dict) else None
        project_crs = None
        adapter_info = None
        adapter_details = {}
        if output_format == "gpkg":
            from planning_toolbox.gis.vector_bridge import require_vector_adapter

            if manifest is None:
                raise ValueError("缺少全链路项目坐标设置，无法生成 GeoPackage。")
            project_crs = require_projected_metric_crs(manifest)
            adapter_info = require_vector_adapter()
        elif manifest is not None and manifest.crs.metric_ready and manifest.crs.code is not None:
            project_crs = require_projected_metric_crs(manifest)
        if project_crs:
            cfg.setdefault("gis", {})["crs"] = project_crs
        if output_format == "gpkg":
            cfg.setdefault("gis", {})["normalize_to_meters"] = True

        self.progress_signal.emit(35, "正在读取 CAD 地块并生成轻量 GeoJSON 中间数据...")
        parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, cfg, out_dir)

        if self._cancel_requested():
            return
        geojson_file = out_dir / f"{dxf_path.stem}.geojson"
        output_files = [("GeoJSON 矢量文件", str(geojson_file))]
        if output_format == "gpkg":
            from planning_toolbox.gis.vector_bridge import convert_geojson_to_gpkg

            self.progress_signal.emit(75, "正在写入带坐标和空间索引的 GeoPackage...")
            gpkg_file = out_dir / f"{dxf_path.stem}.gpkg"
            result = convert_geojson_to_gpkg(
                geojson_file,
                gpkg_file,
                source_crs=project_crs,
                layer_name=f"{dxf_path.stem}_parcels",
            )
            adapter_details = getattr(result, "details", {}) or {}
            output_files.insert(0, ("GeoPackage 空间数据", str(result.output_path)))
        assert_file_unchanged(dxf_path, source_sha256_before)

        self.progress_signal.emit(100, "GIS 导出完成！")
        self.finished_signal.emit({
            "task_type": "gis_export",
            "output_format": output_format,
            "source_file": str(dxf_path),
            "parcels_count": len(parcels),
            "source_sha256": source_sha256_before,
            "project_crs": project_crs or "未设置",
            "conversion_adapter": adapter_info.display_name if adapter_info else "内置 GeoJSON",
            "geographic_transformation": adapter_details.get("geographic_transformation", ""),
            "crs_warning": (
                f"已按项目坐标 {project_crs} 写入；请在 QGIS 中抽查位置。"
                if project_crs
                else "当前未声明项目 CRS，请不要把本地 CAD 坐标直接当作真实经纬度使用。"
            ),
            "output_files": output_files,
        })

    def _run_gis_import_task(self):
        from planning_toolbox.gis.io.importer import import_geojson_to_dxf
        from planning_toolbox.project.chain_manifest import ChainManifest
        from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file

        geojson_path = Path(self.params["geojson_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        unit_str = self.params.get("unit", "m")
        source_sha256 = sha256_file(geojson_path)
        use_vector_bridge = bool(self.params.get("use_vector_bridge", False))
        manifest_value = self.params.get("chain_manifest")
        manifest = ChainManifest.from_dict(manifest_value) if isinstance(manifest_value, dict) else None

        out_dxf = out_dir / f"{geojson_path.stem}_from_gis.dxf"
        project_crs = None
        adapter_info = None
        adapter_details = {}
        if use_vector_bridge:
            from tempfile import TemporaryDirectory

            from planning_toolbox.gis.crs import require_projected_metric_crs
            from planning_toolbox.gis.vector_bridge import (
                convert_vector_to_geojson,
                require_vector_adapter,
            )

            if manifest is None:
                raise ValueError("缺少全链路项目坐标设置，无法对齐 GIS 数据。")
            project_crs = require_projected_metric_crs(manifest)
            adapter_info = require_vector_adapter()
            self.progress_signal.emit(
                35,
                f"正在通过 {adapter_info.display_name} 对齐到项目坐标 {project_crs}...",
            )
            with TemporaryDirectory(prefix="planning-toolbox-gis-") as temp_dir:
                normalized = Path(temp_dir) / "projected.geojson"
                conversion_result = convert_vector_to_geojson(
                    geojson_path,
                    normalized,
                    target_crs=project_crs,
                )
                adapter_details = getattr(conversion_result, "details", {}) or {}
                self.progress_signal.emit(70, f"正在写入 DXF 多边形（单位: {unit_str}）...")
                res_dxf, stats = import_geojson_to_dxf(
                    normalized,
                    out_dxf,
                    target_unit=unit_str,
                    source_unit="m",
                )
        else:
            self.progress_signal.emit(60, f"正在将 GeoJSON 多边形写入 DXF（单位: {unit_str}）...")
            res_dxf, stats = import_geojson_to_dxf(
                geojson_path,
                out_dxf,
                target_unit=unit_str,
            )
        assert_file_unchanged(geojson_path, source_sha256)

        if self._cancel_requested():
            return

        self.progress_signal.emit(100, "GIS 导入完成！")
        self.finished_signal.emit({
            "task_type": "gis_import",
            "source_file": str(geojson_path),
            "source_format": geojson_path.suffix.lower().lstrip("."),
            "project_crs": project_crs or "源 GeoJSON 平面坐标",
            "conversion_adapter": adapter_info.display_name if adapter_info else "内置 GeoJSON",
            "geographic_transformation": adapter_details.get("geographic_transformation", ""),
            "imported_polygons": stats["imported_polygons"],
            "skipped_unsupported": stats["skipped_unsupported"],
            "output_files": [
                ("导入生成 DXF", str(res_dxf))
            ]
        })

    def _run_batch_task(self):
        from planning_toolbox.batch.analyzer import analyze_dxf_batch

        input_dir = Path(self.params["input_dir"])
        out_dir = Path(self.params.get("output_dir", "output"))
        batch_task = self.params.get("batch_task", "parcel")
        floors = self.params.get("floors")

        self.progress_signal.emit(15, "正在检查批量 DXF 文件夹...")
        result = analyze_dxf_batch(
            input_dir=input_dir,
            output_dir=out_dir,
            task_type=batch_task,
            floors=floors,
            config_path=self.params.get("config_path"),
        )
        if self._cancel_requested():
            return

        self.progress_signal.emit(100, "批量分析完成！")
        self.finished_signal.emit({
            "task_type": "batch",
            "batch_task": batch_task,
            "processed_count": result["processed_count"],
            "success_count": result["success_count"],
            "failed_count": result["failed_count"],
            "items": result["items"],
            "floors": floors,
            "output_files": [("批量汇总 CSV", result["summary_file"])],
        })

    def _run_layer_standardize_task(self):
        from planning_toolbox.cad.layers.compliance import audit_dxf_drafting_compliance
        from planning_toolbox.cad.layers.manager import (
            load_drafting_layer_config,
            load_layer_config,
            standardize_dxf_layers,
        )
        from planning_toolbox.project.semantic_scene import (
            propagate_semantic_scene_to_derived_dxf,
        )
        from planning_toolbox.utils.file_integrity import assert_file_unchanged, sha256_file

        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        source_sha256_before = sha256_file(dxf_path)
        use_china_standard = bool(self.params.get("use_china_standard", False))
        drafting_profile_id = str(
            self.params.get("drafting_profile_id", "china_coursework_general")
        )
        self.progress_signal.emit(30, "正在读取 CAD 图层规范并扫描图元...")
        layer_config = (
            load_drafting_layer_config(drafting_profile_id)
            if use_china_standard
            else load_layer_config(self.params.get("config_path"))
        )
        standardized_dxf, report_file, remapped_counts, unmapped_layers = standardize_dxf_layers(
            dxf_path=dxf_path,
            layer_config=layer_config,
            output_dir=out_dir,
        )
        if self._cancel_requested():
            return
        semantic_scene = propagate_semantic_scene_to_derived_dxf(
            dxf_path,
            standardized_dxf,
        )
        compliance = None
        if use_china_standard:
            self.progress_signal.emit(80, "正在检查单位、必备图层和中国制图辅助样式...")
            compliance = audit_dxf_drafting_compliance(
                standardized_dxf,
                layer_config,
                output_dir=out_dir,
                unmapped_layers=unmapped_layers,
            )
        assert_file_unchanged(dxf_path, source_sha256_before)
        remapped_total = sum(remapped_counts.values())
        self.progress_signal.emit(100, "CAD 图层标准化完成！")
        output_files = [
            ("标准化 DXF", str(standardized_dxf)),
            ("图层检查报告", str(report_file)),
        ]
        if semantic_scene:
            output_files.append(("全链路语义场景 JSON", semantic_scene["path"]))
        if compliance:
            output_files.extend([
                ("中国制图辅助检查", compliance["report_path"]),
                ("机器可读检查 JSON", compliance["json_path"]),
            ])
        profile = layer_config.get("profile", {})
        self.finished_signal.emit({
            "task_type": "layer_standardize",
            "source_file": str(dxf_path),
            "source_sha256": source_sha256_before,
            "remapped_total": remapped_total,
            "remapped_counts": remapped_counts,
            "unmapped_layers": unmapped_layers,
            "use_china_standard": use_china_standard,
            "drafting_profile_id": profile.get("profile_id", "legacy_basic"),
            "drafting_profile_name": profile.get("name", "基础图层配置"),
            "drafting_references": profile.get("references", []),
            "drafting_compliance": compliance or {},
            "semantic_scene_file": semantic_scene["path"] if semantic_scene else None,
            "semantic_scene_summary": semantic_scene.get("summary", {})
            if semantic_scene
            else {},
            "output_files": output_files,
        })

    def _run_quality_check_task(self):
        from planning_toolbox.cad.quality import repair_dxf_quality, scan_dxf_quality
        from planning_toolbox.project.semantic_scene import (
            propagate_semantic_scene_to_derived_dxf,
        )

        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        tolerance = float(self.params.get("near_closed_tolerance", 0.01))
        if tolerance < 0:
            raise ValueError("近闭合修复容差不能小于 0。")
        repair_profile = self.params.get("repair_profile", "safe")
        self.progress_signal.emit(20, "正在扫描重复线、断线、碎线链、自交和 CAD 图元类型...")
        quality = scan_dxf_quality(dxf_path, near_closed_tolerance=tolerance)
        if self._cancel_requested():
            return

        self.progress_signal.emit(55, "正在生成可追溯修复副本，并保留原始 DXF...")
        repair_result = repair_dxf_quality(
            dxf_path=dxf_path,
            output_dir=out_dir,
            near_closed_tolerance=tolerance,
            remove_duplicates=bool(self.params.get("remove_duplicates", True)),
            close_near_closed=bool(self.params.get("close_near_closed", True)),
            remove_duplicate_lines=bool(self.params.get("remove_duplicate_lines", False)),
            merge_connected_fragments=bool(self.params.get("merge_connected_fragments", False)),
            join_tolerance=float(self.params.get("join_tolerance", 0.05)),
            simplify_collinear_vertices=bool(
                self.params.get("simplify_collinear_vertices", False)
            ),
            collinear_tolerance=float(self.params.get("collinear_tolerance", 0.01)),
            remove_short_vertices=bool(self.params.get("remove_short_vertices", False)),
            min_segment_length=float(self.params.get("min_segment_length", 0.01)),
            standardize_layers=bool(self.params.get("standardize_layers", False)),
            require_known_units=bool(self.params.get("require_known_units", False)),
        )
        repaired_path = Path(repair_result["output_file"])
        semantic_scene = propagate_semantic_scene_to_derived_dxf(
            dxf_path,
            repaired_path,
        )
        report_file = repaired_path.with_name(f"{repaired_path.stem}_report.txt")
        report_file.write_text(
            "=== Planning Toolbox CAD Quality Report ===\n"
            f"Source DXF: {dxf_path.name}\n"
            f"Source SHA-256: {quality['source_sha256']}\n"
            f"Repair profile: {repair_profile}\n"
            f"DXF unit: {quality['unit_name']} ($INSUNITS={quality['unit_code']})\n"
            f"Source entities / vertices: {repair_result['source_entity_count']} / {repair_result['source_vertex_count']}\n"
            f"Output entities / vertices: {repair_result['output_entity_count']} / {repair_result['output_vertex_count']}\n"
            f"Duplicate polylines: {quality['duplicate_count']}\n"
            f"Duplicate LINE entities: {quality.get('duplicate_line_count', 0)}\n"
            f"Open polylines: {quality['open_count']}\n"
            f"Near-closed polylines: {quality['near_closed_count']}\n"
            f"Straight fragments available: {quality.get('straight_fragment_count', 0)}\n"
            f"Self-intersection candidates: {quality['self_intersection_count']}\n"
            f"Empty layers: {', '.join(quality['empty_layers']) or 'None'}\n"
            f"Entity counts: {quality['entity_counts']}\n"
            f"Preview-supported entities: {quality.get('preview_supported_entity_counts', {})}\n"
            f"Manual-review entities: {quality.get('manual_review_entity_counts', {})}\n"
            f"Block references: {quality.get('block_reference_counts', {})}\n"
            f"Unresolved block references: {quality.get('unresolved_block_references', []) or 'None'}\n"
            f"External references (XREF): {quality.get('external_reference_names', []) or 'None'}\n"
            f"Paper-space entities: {quality.get('paper_space_entity_count', 0)}\n"
            f"Scale warnings: {'; '.join(quality['scale_warnings']) or 'None'}\n"
            f"Removed duplicate polylines in output: {repair_result['removed_duplicates']}\n"
            f"Removed duplicate LINE entities in output: {repair_result['removed_duplicate_lines']}\n"
            f"Closed near-closed polylines in output: {repair_result['closed_polylines']}\n"
            f"Merged non-branching fragment groups: {repair_result['merged_fragment_groups']}\n"
            f"Source fragments merged: {repair_result['merged_source_entities']}\n"
            f"Fragment entity reduction: {repair_result['fragment_entity_reduction']}\n"
            f"Branching components skipped: {repair_result['branching_components_skipped']}\n"
            f"Maximum endpoint snap distance: {repair_result['max_endpoint_snap_distance']:.6g}\n"
            f"Simplified polylines: {repair_result['simplified_polylines']}\n"
            f"Removed collinear vertices: {repair_result['removed_collinear_vertices']}\n"
            f"Removed short/duplicate vertices: {repair_result['removed_short_vertices']}\n"
            f"Standardized layer assignments: {repair_result['standardized_layer_count']}\n"
            f"Recorded changes: {repair_result['change_count']}\n"
            "\nRepair boundary: only matching-style, non-branching straight fragments are merged. "
            "Curves, blocks, self-intersections and junctions remain for manual review.\n",
            encoding="utf-8",
        )
        self.progress_signal.emit(100, "图纸质量检查与安全修复完成！")
        output_files = [
            ("质量检查报告", str(report_file)),
            ("安全修复 DXF", repair_result["output_file"]),
            ("逐项修改记录 CSV", repair_result["change_log_file"]),
        ]
        if semantic_scene:
            output_files.append(("全链路语义场景 JSON", semantic_scene["path"]))
        self.finished_signal.emit({
            "task_type": "quality_check",
            "source_file": str(dxf_path),
            "source_sha256": quality["source_sha256"],
            **quality,
            "repair": repair_result,
            "semantic_scene_file": semantic_scene["path"] if semantic_scene else None,
            "semantic_scene_summary": semantic_scene.get("summary", {})
            if semantic_scene
            else {},
            "output_files": output_files,
        })

    def _run_concept_plan_task(self):
        from planning_toolbox.cad.planning.concept_generator import generate_concept_plan

        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        self.progress_signal.emit(20, "正在读取有效地块并准备概念方案参数...")
        result = generate_concept_plan(
            dxf_path=dxf_path,
            output_dir=out_dir,
            building_count=int(self.params.get("building_count", 1)),
            coverage_ratio=float(self.params.get("coverage_ratio", 0.25)),
            setback_m=float(self.params.get("setback_m", 5.0)),
            parcel_layer=self.params.get("parcel_layer", "PARCEL"),
            fallback_unit=self.params.get("fallback_unit"),
            floors=self.params.get("floors"),
            parking_ratio=self.params.get("parking_ratio"),
            building_gap_m=float(self.params.get("building_gap_m", 0.0)),
            access_width_m=float(self.params.get("access_width_m", 0.0)),
            standards_profile_id=self.params.get("standards_profile_id", "custom_local"),
            layout_style=self.params.get("layout_style", "organic"),
        )
        if self._cancel_requested():
            return
        self.progress_signal.emit(100, "概念方案草图已生成，请在 CAD 中继续人工调整...")
        self.finished_signal.emit(result)

    def _run_image_to_dxf_task(self):
        # Keep the heavyweight raster stack out of normal GUI startup; it is
        # loaded only when the user actually runs the image conversion task.
        from planning_toolbox.cad.planning.image_to_dxf import convert_image_to_dxf
        from planning_toolbox.utils.file_integrity import (
            assert_file_unchanged,
            sha256_file,
        )

        image_path = Path(self.params["image_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        source_hash_before = sha256_file(image_path)
        conversion_mode = self.params.get("conversion_mode", "color_regions")
        guide_path = (
            Path(self.params["semantic_guide_path"])
            if conversion_mode == "semantic_guide"
            else None
        )
        guide_hash_before = sha256_file(guide_path) if guide_path else ""
        mode_message = {
            "black_white_linework": "正在读取黑白线稿并提取清晰轮廓...",
            "semantic_guide": "正在校验原图与语义引导图，并提取标准颜色范围...",
        }.get(conversion_mode, "正在读取效果图并识别标准颜色区域...")
        self.progress_signal.emit(20, mode_message)
        detail_presets = {
            "standard": (1200, 0.35, "outline"),
            "fine": (2400, 0.15, "centerline"),
            "ultra": (4000, 0.07, "centerline"),
        }
        max_dimension, simplify_factor, trace_method = detail_presets.get(
            self.params.get("detail_level", "fine")
            if conversion_mode == "black_white_linework"
            else "standard",
            detail_presets["fine"],
        )
        knowledge_profile = None
        if (
            conversion_mode == "black_white_linework"
            and bool(self.params.get("use_knowledge_assist", True))
        ):
            from planning_toolbox.knowledge.image_cards import (
                build_image_to_cad_quality_profile,
            )

            self.progress_signal.emit(24, "正在匹配已确认的本地精修 CAD 样本...")
            knowledge_profile = build_image_to_cad_quality_profile(
                out_dir / "knowledge_cards",
                project_type=str(self.params.get("knowledge_project_type", "待确认")),
                conversion_mode=conversion_mode,
            )
        result = convert_image_to_dxf(
            image_path=image_path,
            output_dir=out_dir,
            reference_width_m=float(self.params["reference_width_m"]),
            color_tolerance=int(self.params.get("color_tolerance", 55)),
            min_component_pixels=int(self.params.get("min_component_pixels", 80)),
            focus_site_only=bool(self.params.get("focus_site_only", False)),
            conversion_mode=conversion_mode,
            line_threshold=int(self.params.get("line_threshold", 220)),
            max_dimension=max_dimension,
            line_simplify_factor=simplify_factor,
            line_trace_method=trace_method,
            optimize_linework=bool(self.params.get("optimize_linework", True)),
            line_polarity=str(self.params.get("line_polarity", "auto")),
            knowledge_profile=knowledge_profile,
            semantic_guide_path=guide_path,
        )
        assert_file_unchanged(image_path, source_hash_before)
        if guide_path:
            assert_file_unchanged(guide_path, guide_hash_before)
        result["zero_mutation_verified"] = True
        result["source_sha256_before"] = source_hash_before
        result["semantic_guide_zero_mutation_verified"] = bool(guide_path)
        result["knowledge_assist_requested"] = bool(
            self.params.get("use_knowledge_assist", True)
        )
        if self._cancel_requested():
            return
        create_card = bool(self.params.get("create_knowledge_card", True))
        collect_cad = bool(self.params.get("collect_cad_sample", False))
        if create_card or collect_cad:
            from planning_toolbox.knowledge.image_cards import (
                attach_cad_reference_to_card,
                create_image_knowledge_card,
            )

            self.progress_signal.emit(92, "正在生成轻量图纸知识卡，不复制原图...")
            card = create_image_knowledge_card(
                result,
                out_dir,
                project_type=str(self.params.get("knowledge_project_type", "待确认")),
                tags=str(self.params.get("knowledge_tags", "")),
                expected_source_sha256=source_hash_before,
            )
            result["knowledge_card"] = card
            result["output_files"].append(("Markdown 图纸知识卡", card["card_path"]))
            if collect_cad:
                generated_dxf = next(
                    (
                        Path(path)
                        for _label, path in result.get("output_files", [])
                        if Path(path).suffix.lower() == ".dxf"
                    ),
                    None,
                )
                if generated_dxf is None:
                    raise RuntimeError("没有找到可收藏的图转 CAD 输出文件。")
                reference = attach_cad_reference_to_card(
                    card["card_path"],
                    generated_dxf,
                    title="图转 CAD 候选参考样本",
                    review_status="candidate_unreviewed",
                )
                result["cad_knowledge_reference"] = reference
                result["output_files"].append(
                    ("知识库 CAD 候选样本", reference["path"])
                )
        finish_message = {
            "black_white_linework": "黑白线稿已转换为 CAD 线条，请继续人工复核...",
            "semantic_guide": "原图与语义引导图已转换为分层 CAD，请先查看叠加检查图...",
        }.get(conversion_mode, "效果图已转换为分层 CAD 草图，请继续人工复核...")
        self.progress_signal.emit(100, finish_message)
        self.finished_signal.emit(result)

    def _run_dwg_convert_task(self):
        from planning_toolbox.cad.io.dwg_bridge import convert_dwg_to_dxf

        self.progress_signal.emit(20, "正在调用本机 DWG 转换组件；文件不会上传...")
        result = convert_dwg_to_dxf(
            self.params["dwg_path"],
            self.params.get("output_dir", "output"),
        )
        if self._cancel_requested():
            return
        self.progress_signal.emit(100, "DWG 已安全转换为新的 DXF 文件！")
        self.finished_signal.emit(result)

    def _run_sketchup_export_task(self):
        """Create the handoff and installer without launching SketchUp."""
        from planning_toolbox.sketchup import (
            build_sketchup_extension,
            export_sketchup_handoff,
        )

        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        handoff_path = out_dir / f"{dxf_path.stem}_sketchup.ptsu.json"
        plugin_path = out_dir / "PlanningToolbox_SketchUp_Importer.rbz"

        self.progress_signal.emit(20, "正在只读解析 CAD 图层与可交接几何...")
        result = export_sketchup_handoff(
            dxf_path,
            handoff_path,
            self.params["chain_manifest"],
            floors=int(self.params.get("floors", 0)),
            floor_height_m=float(self.params.get("floor_height_m", 0.0)),
            building_layers=self.params.get("building_layers"),
            include_open_linework=bool(
                self.params.get("include_open_linework", True)
            ),
            include_blocks=bool(self.params.get("include_blocks", True)),
            include_faces=bool(self.params.get("include_faces", True)),
            include_text=bool(self.params.get("include_text", False)),
            model_detail_level=str(self.params.get("model_detail_level", "course")),
            road_design_preset=str(self.params.get("road_design_preset", "auto")),
            building_type=str(self.params.get("building_type", "auto")),
            roof_type=str(self.params.get("roof_type", "flat")),
            incremental_update=bool(self.params.get("incremental_update", True)),
            building_overrides=self.params.get("building_overrides"),
            centerline_corridor=bool(self.params.get("centerline_corridor", False)),
            centerline_width_m=float(self.params.get("centerline_width_m", 0.0)),
            centerline_confidence_policy=str(
                self.params.get("centerline_confidence_policy", "trusted_only")
            ),
        )
        if self._cancel_requested():
            return
        self.progress_signal.emit(82, "正在生成可安装的 SketchUp RBZ 插件...")
        plugin = build_sketchup_extension(plugin_path)
        result["plugin_file"] = plugin["path"]
        result["plugin_sha256"] = plugin["sha256"]
        result["plugin_size_bytes"] = plugin["size_bytes"]
        result["output_files"].append(("SketchUp 导入插件 RBZ", plugin["path"]))
        self.progress_signal.emit(
            100, "SketchUp 交接已生成；请在扩展程序管理器安装 RBZ 后导入交接文件。"
        )
        self.finished_signal.emit(result)
