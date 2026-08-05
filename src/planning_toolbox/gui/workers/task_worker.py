"""QThread 异步任务执行器 (处理耗时 CAD/GIS 计算，防止 UI 界面卡死)."""
from pathlib import Path
from typing import Dict, Any
from PySide6.QtCore import QThread, Signal

from planning_toolbox.config import load_config
from planning_toolbox.cad.parcels.calculator import process_parcels
from planning_toolbox.indicators.calculator import process_dxf_indicators, calculate_parcel_indicators
from planning_toolbox.validators.topology import validate_polyline_topology
from planning_toolbox.validators.setback import check_building_setback
from planning_toolbox.gis.io.exporter import export_parcels_to_geojson
from planning_toolbox.gis.io.importer import import_geojson_to_dxf
from planning_toolbox.core.units.unit_manager import UnitError, resolve_unit, get_dxf_unit_code
from planning_toolbox.core.geometry.parser import points_from_dxf_polyline, parse_parcel_geometry
from planning_toolbox.utils.i18n import ERR_UNIT_UNKNOWN, ERR_GEOJSON_PARSE_FAILED, ERR_PATH_COLLISION
import ezdxf
import shapely.geometry

class TaskWorker(QThread):
    """
    后台计算线程 Worker，支持 parcel, indicator, validate, gis_export, gis_import 五大任务。
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

    def run(self):
        try:
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
            else:
                self.error_signal.emit("未知的任务类型", f"暂不支持任务类型 '{self.task_type}'")

        except UnitError as e:
            self.error_signal.emit(
                "单位核验失败",
                f"无法确认 DXF 单位 ($INSUNITS)。\n\n建议步骤：\n"
                f"1. 在 AutoCAD 中打开 DXF 文件，输入 UNITS 命令将单位设为【米】。\n"
                f"2. 或在配置文件中指定 fallback_unit。"
            )
        except ValueError as e:
            msg = str(e)
            if "Direct overwrite is forbidden" in msg:
                self.error_signal.emit("输出路径错误", ERR_PATH_COLLISION)
            else:
                self.error_signal.emit("参数校验错误", msg)
        except FileNotFoundError as e:
            self.error_signal.emit("文件未找到", str(e))
        except Exception as e:
            self.error_signal.emit("计算过程异常", f"处理过程中发生错误:\n{str(e)}")

    def _run_parcel_task(self):
        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        cfg_path = self.params.get("config_path")
        cfg = load_config(cfg_path)

        if "target_layer" in self.params and self.params["target_layer"]:
            cfg.setdefault("parcel", {})["input_layers"] = [self.params["target_layer"]]

        self.progress_signal.emit(30, f"正在解析 CAD 地块多边形: {dxf_path.name}...")
        parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, cfg, out_dir)

        if self._is_cancelled:
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
        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        floors = int(self.params["floors"])
        
        cfg_path = self.params.get("config_path")
        cfg = load_config(cfg_path)
        cfg["default_floors"] = floors

        if "building_layer" in self.params and self.params["building_layer"]:
            cfg["building_layer"] = self.params["building_layer"]
        if "green_layer" in self.params and self.params["green_layer"]:
            cfg["green_layer"] = self.params["green_layer"]

        self.progress_signal.emit(40, f"正在计算地块内部建筑与绿地空间求交 (楼层倍数: {floors})...")
        results, csv_file, report_file = process_dxf_indicators(dxf_path, config=cfg, output_dir=out_dir)

        self.progress_signal.emit(100, "指标计算完成！")
        self.finished_signal.emit({
            "task_type": "indicator",
            "source_file": str(dxf_path),
            "parcels_count": len(results),
            "floors": floors,
            "indicators": [r.to_dict() for r in results],
            "output_files": [
                ("指标 CSV 统计表", str(csv_file)),
                ("指标文本报告", str(report_file))
            ]
        })

    def _run_validate_task(self):
        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        setback_m = float(self.params["setback_m"])
        parcel_layer = self.params.get("parcel_layer", "PARCEL").upper()
        building_layer = self.params.get("building_layer", "BUILDING").upper()
        fallback_unit = self.params.get("fallback_unit")

        self.progress_signal.emit(30, "正在检查 CAD 拓扑有效性...")
        doc = ezdxf.readfile(dxf_path)
        
        # 显式校验单位安全
        unit_code = get_dxf_unit_code(doc)
        unit_name = resolve_unit(unit_code, fallback_unit=fallback_unit, strict_check=(fallback_unit is None))
        
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
        if parcel_polys and building_polys:
            for idx, p_poly in enumerate(parcel_polys, start=1):
                pid = f"P{idx:03d}"
                res = check_building_setback(p_poly, building_polys, setback_m, parcel_id=pid)
                setback_results.append({
                    "parcel_id": pid,
                    "status": res.status,
                    "violations": res.violations_count,
                    "min_distance_m": res.min_distance_m,
                    "error_message": res.error_message or ""
                })

        self.progress_signal.emit(100, "规则与拓扑检查完成！")
        self.finished_signal.emit({
            "task_type": "validate",
            "source_file": str(dxf_path),
            "unit_name": unit_name,
            "scanned_polylines": len(topology_results),
            "valid_count": valid_count,
            "open_count": open_count,
            "invalid_count": invalid_count,
            "setback_m": setback_m,
            "setback_results": setback_results
        })

    def _run_gis_export_task(self):
        dxf_path = Path(self.params["dxf_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        cfg = load_config(self.params.get("config_path"))

        self.progress_signal.emit(50, "正在导出 GeoJSON 矢量 FeatureCollection...")
        parcels, labeled_dxf, csv_file, report_file = process_parcels(dxf_path, cfg, out_dir)
        geojson_file = out_dir / f"{dxf_path.stem}.geojson"

        self.progress_signal.emit(100, "GIS 导出完成！")
        self.finished_signal.emit({
            "task_type": "gis_export",
            "source_file": str(dxf_path),
            "parcels_count": len(parcels),
            "crs_warning": "当前未进行 CRS 坐标转换。请不要把本地 CAD 坐标直接当作真实经纬度使用。",
            "output_files": [
                ("GeoJSON 矢量文件", str(geojson_file))
            ]
        })

    def _run_gis_import_task(self):
        geojson_path = Path(self.params["geojson_path"])
        out_dir = Path(self.params.get("output_dir", "output"))
        unit_str = self.params.get("unit", "m")

        # 检查 GeoJSON 是否包含 WGS84 / 经纬度
        import json
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        crs_name = str(data.get("crs", {})).upper()
        if "4326" in crs_name or "CRS84" in crs_name or "WGS84" in crs_name:
            raise ValueError(
                "当前 GeoJSON 使用经纬度坐标，系统尚未实现自动投影转换。\n"
                "请先在 QGIS 或 ArcGIS 中转换为适合测距和面积计算的平面坐标系 (如 CGCS2000 高斯投影)。"
            )

        out_dxf = out_dir / f"{geojson_path.stem}_from_gis.dxf"
        self.progress_signal.emit(60, f"正在将 GeoJSON 矢量多边形写入 DXF (单位: {unit_str})...")
        res_dxf, stats = import_geojson_to_dxf(geojson_path, out_dxf, unit=unit_str)

        self.progress_signal.emit(100, "GIS 导入完成！")
        self.finished_signal.emit({
            "task_type": "gis_import",
            "source_file": str(geojson_path),
            "imported_polygons": stats["imported_polygons"],
            "skipped_unsupported": stats["skipped_unsupported"],
            "output_files": [
                ("导入生成 DXF", str(res_dxf))
            ]
        })
