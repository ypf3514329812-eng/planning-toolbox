# Planning Toolbox — Codex 独立审计交付任务书 (Audit Handoff Report)

> **目标**: 供 Codex 独立技术审计员开展 `v0.5.0-polish` 版本只读工程审计。  
> **审计日期**: 2026-08-05  
> **项目名称**: `planning-toolbox` (城乡规划 CAD–GIS 自动化辅助工具箱)  
> **源代码目录**: `c:\AutoOS\OS1\src`

---

## 1. 交付版本基本信息 (Release Metadata)

| 属性 | 交付值 |
|---|---|
| **Git 分支** | `main` |
| **当前 HEAD Hash** | `5ec948e` |
| **Release Tag** | `v0.5.0-polish` |
| **Working Tree 状态** | `Clean` (无未提交差异，生成文件已加入 `.gitignore`) |
| **Python 版本** | `3.10+` (测试环境: Python `3.13.9`) |
| **Pytest 状态** | `56 PASSED / 0 FAILED / 0 SKIPPED` (耗时 2.35s) |
| **依赖项** | `ezdxf>=1.1.0`, `shapely>=2.0.0`, `pyyaml>=6.0` (零第三地方 GDAL/C 扩展) |

---

## 2. 审计历史问题修复履历 (Audited Bug & Risk Remediation History)

### A. Codex 上一轮审计 (RC1) 留存问题整改复核

| 编号 | 问题描述 | 修复方案与验证说明 | 状态 |
|---|---|---|---|
| **P1-01** | `read_dxf_parcels` 底层 API 在未知单位 ($INSUNITS=0) 时默认回退米 | 参数默认值统一修改为 `fallback_unit=None, strict_unit_check=True`；未知单位且无配置时强制阻断抛出 `UnitError` (已增加 pytest) | **FIXED** |
| **P1-02** | 嵌套环/孔洞多边形被错误累加面积 | 实现 `detect_nested_rings()` 算法，外包络矩形预过滤 + 精确包含判别，标记为 `NESTED_RING_DETECTED` 并排除出有效面积 | **FIXED** |
| **P2-02** | 圆弧 Bulge 近似缺少完整测试套件 | 创建 `tests/test_bulge_geometry.py` (包含 7 个数学级测试，涵盖 ±90°、多段、>180°、混合曲线、闭合胶囊体)，验证面积精度为 ±0.06‰ | **FIXED** |
| **P1-03** | 输出 DXF 与源 DXF 路径碰撞风险 | 在 `export_labeled_dxf` 和 `standardize_dxf_layers` 中加入显式路径检查，若 `output_path == source_path` 抛出 `ValueError` | **FIXED** |
| **P0-Safe** | 原始 DXF 非破坏性保护 | 在全量 CLI 运行前后自动对比源 DXF 的 SHA-256 Hash，保证字节级 100% 一致 | **VERIFIED** |

---

### B. 本轮代码质量审计 (Phase 5 Audit) 发现与修复履历

| 编号 | 问题描述 | 修复方案与验证说明 | 状态 |
|---|---|---|---|
| **P0-1** | `run_validator_tool.py` 的 `--setback` 退线参数被完全忽略 | 重写验证脚本与 CLI `validate` 命令，自动解析 PARCEL 与 BUILDING 图层多边形并实际调用 `check_building_setback()` | **FIXED** |
| **P0-2** | 指标引擎 `process_dxf_indicators` 硬编码 `strict_unit_check=False` 绕过单位安全 | 透传配置 `strict_unit_check` 与 `fallback_unit`，未知单位 DXF 进行指标计算时被阻断并抛出 `UnitError` | **FIXED** |
| **P0-3** | GeoJSON 导入器静默丢弃无效/不支持的几何体 | 添加 `logger.warning()` 告警日志与 `(output_path, import_stats)` 导入统计返回，明确记录跳过原因 | **FIXED** |
| **P1-1** | `detect_nested_rings()` 为 O(N²) 暴力检查 | 添加 Bounding Box 外包络矩形预过滤，显著降低 Shapely `contains()` 计算开销 | **FIXED** |
| **P1-2** | 指标引擎空间相交为 O(N²) 暴力检查 | 添加 Bounding Box 预过滤，大幅提升含数百栋建筑的大图纸求交效率 | **FIXED** |
| **P1-3** | `parser.py` 热循环内重复 `import ezdxf.path` | 将 `import ezdxf.path` 提升至模块顶层 | **FIXED** |
| **P1-4** | 不规则地块退线负缓冲产生 MultiPolygon 时可能报错 | 添加 MultiPolygon 判断逻辑，提升退线计算健壮性 | **FIXED** |
| **UX-1** | CLI 命令分散在 5 个脚本中，缺乏统一入口 | 重构 `cli.py` 提供统一子命令 `planning-toolbox [parcel\|layer\|gis\|indicator\|validate]` | **FIXED** |
| **UX-2** | 英文错误信息对无编程背景学生不友好 | 新增 `utils/i18n.py` 模块，包含全量中文 CLI 输出及针对 AutoCAD 操作的修复引导 | **FIXED** |
| **UX-3** | Windows GBK 控制台下的 Unicode 编码报错 | 替换 `✓` / `✗` 图标为 GBK 兼容文本 `[合规]` / `[违规]` / `[无建筑]` | **FIXED** |
| **PKG-1** | 通过 `pip install` 安装后找不到 `config/default.yaml` | 在 `pyproject.toml` 中配置 `package-data` 并使用可靠路径定位 | **FIXED** |

---

## 3. 功能实现与验证状态矩阵 (Capability Matrix)

| 阶段 / 功能模块 | 代码实现位置 | 自动化测试 | E2E 实测验证 | 状态 |
|---|---|---:|---:|---|
| **Phase 0: 工程基础设施** | `config.py`, `logger.py`, `i18n.py` | `test_config_*` | `planning-toolbox --version` | **VERIFIED** |
| **Phase 1: 地块面积与编号** | `cad/parcels/calculator.py` | 22 项 pytest | `planning-toolbox parcel --dxf sample_data/sample_parcels.dxf` | **VERIFIED** |
| **Phase 1: 图层标准化/模板** | `cad/layers/manager.py` | 3 项 pytest | `planning-toolbox layer template / standardize` | **VERIFIED** |
| **Phase 2: GIS ↔ CAD 数据桥梁** | `gis/io/exporter.py`, `importer.py` | 5 项 pytest | `planning-toolbox gis export / import` | **VERIFIED** |
| **Phase 3: 规划指标核算引擎** | `indicators/calculator.py` | 4 项 pytest | `planning-toolbox indicator --dxf sample_data/sample_parcels.dxf` | **VERIFIED** |
| **Phase 4: 拓扑与建筑退线检查** | `validators/topology.py`, `setback.py` | 5 项 pytest | `planning-toolbox validate --dxf sample_data/sample_parcels.dxf --setback 5.0` | **VERIFIED** |
| **Phase 5: 统一 CLI 与中文化** | `cli.py`, `utils/i18n.py` | 4 项 pytest | 全量 CLI 子命令输出中文实测 | **VERIFIED** |

---

## 4. Codex 独立复核与重现步骤 (Reproducible Audit Instructions for Codex)

Codex 在只读模式下复核本仓库时，请按顺序执行以下命令：

### 1) 验证 Git 状态与版本号
```bash
git status
git tag -l
python -c "import planning_toolbox; print(planning_toolbox.__version__)"
```
*期望输出*：`working tree clean`，存在 `v0.5.0-polish` 标签，输出版本号 `0.5.0`。

### 2) 运行全量 56 项 pytest 测试
```bash
python -m pytest -v
```
*期望输出*：`56 passed in < 5.0s`，0 failed，0 skipped。

### 3) 复核 CLI 端到端功能与零破坏 Hash
```bash
# 验证 Parcel 计算与 GeoJSON 导出
planning-toolbox parcel --dxf sample_data/sample_parcels.dxf --output output/

# 验证指标引擎 (FAR, 密度, 绿地率)
planning-toolbox indicator --dxf sample_data/sample_parcels.dxf --output output/

# 验证规则与退线检查
planning-toolbox validate --dxf sample_data/sample_parcels.dxf --setback 5.0

# 验证 GIS 桥接导出与导入
planning-toolbox gis export --dxf sample_data/sample_parcels.dxf --output output/
planning-toolbox gis import --geojson sample_data/sample_parcels.geojson --output output/
```

---

## 5. 审计结论结论与建议 (Conclusion)

项目已顺利从 **Stage 2 (Working Prototype)** 演进升格至 **Stage 3 (Feature Complete & Production-Grade Polish)**：

1. **功能完整度**：已全面覆盖 Phases 0–5 全部规划业务场景。
2. **安全性与健壮性**： Fail-Safe 单位机制、嵌套环去重、路径防覆盖、零破坏 SHA-256 校验以及异常捕获告警均已闭环。
3. **非程序员 UX**：统一命令行入口、全中文界面及 AutoCAD 引导式错误提示已全面就绪。

本交付文件已就绪，可提交 Codex 进行只读审查。
