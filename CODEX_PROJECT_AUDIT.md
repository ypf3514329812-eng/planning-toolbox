# Planning Toolbox — Independent Codex Audit

审计日期：2026-08-04  
审计性质：只读优先的独立工程审计；本轮未修改源码、测试或 Git 历史。

## Executive Assessment

当前阶段：**Stage 2 — Working Prototype（工作原型，偏稳定性验证阶段）**

Overall：项目已经形成可运行的 CAD 地块面积、编号、标注和图层工具链；线性多边形的基础路径真实可用，但曲线精度、孔洞语义、单位 API 默认值和证据归档仍不足以支撑稳定发布。

是否可标 STABLE：**NO**

是否建议进入 MVP-2：**B — 先完成稳定性验证，再继续开发下一功能**。当前架构没有需要大规模重构的根本问题，但不应在关键输入边界尚未锁定前继续扩展功能。

项目身份已确认：`pyproject.toml` 的项目名为 `planning-toolbox`，描述为城乡规划 CAD–GIS 自动化辅助工具箱，源码从 `C:\AutoOS\OS1\src` 加载。

## Verified Project State

### Git

- Branch：`main`
- 当前 HEAD：`38b42896f8b3ceff09a2edd79996ceadd41b559e`
- 当前标签：`v0.1.1-rc1`
- 用户提供的 `64ffd8314a4a7832aed6503681eabe90119c3c7f` 是当前 HEAD 的上一提交，不是当前 HEAD。
- 当前没有已跟踪文件的未提交差异；工作树存在两个未跟踪文件：`sample_data/output/sample_parcels_layer_report.txt`、`sample_data/output/sample_parcels_standardized.dxf`。
- 最近提交总体按功能/审计主题划分，未发现一次性大规模重构；但证据归档曾把大体积二进制输出放进提交，降低了审计材料的新鲜度和可复核性。

### Python / Dependencies

- Python：`3.13.9`
- `planning_toolbox.__version__`：`0.1.1`
- `ezdxf`：`1.4.4`
- `shapely`：`2.1.2`
- `PyYAML`：`6.0.3`
- pytest：`8.4.2`
- 当前 `pip show planning-toolbox` 的分发元数据仍显示 `0.1.0`，而源码、运行时和 `pyproject.toml` 显示 `0.1.1`；这是环境/发布元数据不同步，不影响本次导入，但会影响版本追踪和复现。

### Tests

独立执行命令：`python -m pytest -v`

- collected：19
- passed：19
- failed：0
- skipped：0
- warnings：未输出 warnings summary
- exit code：0
- execution time：3.73 s

独立 CLI 复核也通过：对 `sample_data/sample_parcels.dxf` 生成 CSV、标注 DXF 和报告；CSV 有 5 行候选地块，3 个 `VALID`、1 个 `OPEN`、1 个 `INVALID_GEOMETRY`；输出 DXF 可由 ezdxf 重新读取，包含原有 5 个 LWPOLYLINE 和 3 个 MTEXT；源 DXF 的 SHA-256 前后保持一致。

### Implemented Capabilities

| Capability | Code Exists | Automated Test | Current E2E / External | Status |
|---|---:|---:|---:|---|
| 按目标图层读取 LWPOLYLINE / POLYLINE | YES | 部分 | sample DXF E2E；AutoCAD 未测 | **VERIFIED（受限）** |
| 线性多边形面积计算与已知单位换算 | YES | YES | 当前 CLI E2E | **VERIFIED** |
| 开放边界、自交、退化几何保护 | YES | YES | 合成数据 | **VERIFIED（覆盖有限）** |
| DXF bulge / arc 展开 | YES | 当前仓库无正式 bulge pytest | sample 实际可运行；无独立 CAD 验证 | **PARTIAL** |
| 内点标注位置 | YES | L 形多边形测试 | 当前标注 DXF 可重读 | **VERIFIED（基础情况）** |
| 地块排序与编号 | YES | YES | 只覆盖无并列排序键的案例 | **VERIFIED（受限）** |
| CSV / 文本报告输出 | YES | 部分 | 当前 CLI E2E、重新读取 CSV | **VERIFIED（受限）** |
| 标注 DXF 输出 | YES | YES | ezdxf 可重读；AutoCAD 未测 | **PARTIAL** |
| 原始 DXF 非破坏处理 | YES | YES | 当前 CLI SHA-256 复核 | **VERIFIED（用户路径）** |
| CAD 标准图层模板与别名归一化 | YES | YES | ezdxf 级别；AutoCAD 未测 | **VERIFIED（受限）** |
| 实际 5m setback 运算 | NO | NO | GS-003 只是预先写好的内缩多边形 | **NOT IMPLEMENTED** |
| FAR / 建筑密度指标计算 | NO | NO | 仅有未使用的 fixture 定义 | **NOT IMPLEMENTED** |
| GIS ↔ CAD、CRS 转换 | NO | NO | 无 GIS 模块 | **NOT IMPLEMENTED** |
| 孔洞、多环地块语义 | NO | NO | 内环会被独立处理 | **NOT IMPLEMENTED / UNSAFE** |

## Architecture Assessment

当前模块边界总体合理：`core.geometry` 负责几何，`core.units` 负责单位，`cad.io` 负责 DXF 读取，`cad.parcels` 负责流水线，`cad.annotation` 负责输出标注，`cad.layers` 负责图层，CLI 负责入口，配置放在 YAML 中。对个人 Planning Toolbox 而言，这个规模没有明显过度设计，也没有 giant module、数据库、Web 服务或全局业务状态。

优点：

- 基础数据流清楚：读取 → 几何解析 → 单位换算 → 编号 → CSV / DXF / report。
- CAD、几何和规划领域逻辑没有完全混成一个文件。
- AI 协作规则、空间数据安全规则和非程序员规则已经存在，后续局部修改相对容易。

需要控制的结构性问题：

- 配置没有 schema 校验；缺字段、错误类型或错误单位名会在较深层才失败。
- `config.py` 与 `cad.layers.manager` 各自实现配置目录搜索，长期会造成行为分叉。
- `process_parcels()` 和 `read_dxf_parcels()` 的 Python 默认参数仍是 `fallback_unit="m"`、`strict_unit_check=False`，与生产默认 YAML 的 fail-safe 策略不一致。
- 当前数据模型是一条实体对应一个 `Parcel`，没有 ring / outer-ring / inner-ring 数据结构，因此无法自然表达孔洞。

结论：架构是可继续演进的工作原型架构，不需要大规模重构；应先补齐输入契约和边界语义。

## Test Credibility Assessment

### 可信的部分

- `GS-001` 和 `GS-002` 的期望面积是直接写死的 `10000.0`，没有调用项目自己的面积函数生成 expected；这属于有效的基础 gold standard。
- 自交、开放边界、少于 3 个点、零面积、标注点等基础测试是真实调用源码的测试。
- 当前独立 pytest 运行结果是 19 passed，而不是旧报告中的 18 passed。
- 当前 CLI 输出、CSV、DXF 重读和源文件 hash 已单独复核。

### 不足或不应直接接受的部分

- `TEST_REPORT.md` 和 `test_artifacts/latest/` 记录的是旧提交 `b1c71c075bcf...`、18 passed、Working Tree Clean；当前实际是 `38b42896...`、19 passed，并且有未跟踪输出。因此这些文件不能作为当前版本的最终证据。
- `TEST_EVIDENCE_MATRIX.md` 引用的 `scratch/test_bulge_accuracy.py`、`scratch/test_sha256_verification.py`、`scratch/test_performance.py` 在当前仓库中不存在；对应 PASS 无法从当前仓库重放。
- 矩阵把 SHA-256 PASS 的证据指向 `test_artifacts/latest/git_status.txt`，但该文件只记录旧 Git 状态，没有记录 hash 对比过程。
- `test_artifacts/latest/run_summary.md` 声称还验证了 Empty DXF、Missing layer、Duplicate vertices、Tiny parcel、Non-parcel layers 等边界情况；当前正式 pytest 文件中没有相应测试。
- `GS-003` 只把 `(5,5)` 到 `(95,95)` 的多边形直接交给面积计算器，证明的是一个已内缩多边形的面积，不证明程序能执行 5m setback 运算；不能把它列为 setback 功能已实现。
- `GS-004` FAR 和 `GS-005` density fixture 存在，但没有实现模块，也没有被当前测试使用。
- 当前测试没有正式覆盖负 bulge、多段 bulge、超过 180° 弧段、混合直线/曲线、旧式 POLYLINE、孔洞、多环关系、输出文本内容、单位未知的完整 E2E 阻断路径或 AutoCAD 打开验证。

因此，当前 pytest 的“绿色”是真实的，但测试覆盖范围不能支持“空间几何和规划功能已完整验证”的结论。

## Geometry / CAD Assessment

线性多边形路径表现良好：Shapely 有效性检查能够拦截本次覆盖的开放边界、自交和退化几何；`representative_point()` 对 L 形地块能够提供内部标注点。

主要几何边界：

1. bulge 通过 `ezdxf.path.make_path(...).flattening(distance=0.01)` 近似成折线，精度阈值固定在源 CAD 单位中，未根据单位、图形尺度或面积容差进行调整。对 sample 中 90° 弧段，本次用更小 flattening distance 做对照时，生产路径面积约为 `8573.3863 m²`，对照约为 `8572.9924 m²`，差约 `0.394 m²`。这不是灾难性误差，但说明现有报告声称的 `±0.10 m²` 并没有被当前仓库中的独立正式测试证明。
2. 当前仓库没有正式测试负 bulge、多 bulge、超过 180°、混合直线/曲线和闭合曲线地块；这些应标记为 PARTIAL，而不是 Bulge support complete。
3. 孔洞没有数据语义。独立复核构造一个 100×100 外环和同一 `PARCEL` 图层内 20×20 内环后，程序产生两个 `VALID` 地块并合计 `10400 m²`；若用户意图是带 20×20 孔洞的单个地块，正确净面积应为 `9600 m²`。这会直接影响规划面积。
4. 重复连续点目前可能被 Shapely 接受；代码没有显式的重复点策略。很小多边形的 `1e-6` 面积阈值也使用源 CAD 单位，未按单位换算后统一定义。
5. 读取器只扫描 Modelspace 中的 LWPOLYLINE / POLYLINE，未覆盖 ARC、HATCH、SPLINE、实体块引用或纸空间语义。对当前 MVP 可以接受，但必须在输入限制中明确写出。

## Data Safety Assessment

当前用户主路径的数据保护是本项目的强项：

- DXF 读取后在内存中修改，并通过带后缀的新路径 `*_labeled.dxf` 或 `*_standardized.dxf` 保存。
- 当前 CLI E2E 的源 DXF SHA-256 前后完全一致。
- 当前测试也覆盖了输出 DXF 与源文件隔离。
- 未发现源码中的 API key、token、secret 或硬编码用户机器路径。

仍有两个边界：

- `export_labeled_dxf()` 本身没有拒绝 `output_path == source_path` 的保护；当前 CLI 命名规则通常不会触发它，但底层 API 直接调用时仍可覆盖传入的文档路径。建议将路径碰撞检查放在底层写出函数，而不是依赖上层命名约定。
- `sample_data/output/` 没有被 `.gitignore` 忽略；本次审计前工作树已经出现该目录下的两个生成文件，普通用户或 AI 可能误把生成结果提交到 Git。

当前没有 P0 数据破坏证据；正常 CLI 路径可以评价为“已验证的非破坏输出”，但底层 API 仍应补齐最后一道路径安全检查。

## UX Assessment

对非程序员来说，当前 CLI 入口是合理起点：不要求改 Python 源码，输入 DXF、配置和输出目录均可通过参数指定；CSV、DXF、report 三类输出也符合规划学习场景。

UX debt：

- README 只说明 parcel 工具，没有说明图层模板和图层归一化工具的完整用法。
- 默认命令依赖在项目根目录执行；尚未提供 Windows 双击 launcher 或统一的简单入口。
- 默认错误信息基本可读，但复杂 DXF、单位、图层冲突和不支持实体的提示还没有面向规划学生的解释。
- `AGENTS.md` 中的规则链接使用 `file:///.agents/...`，不是当前仓库的可用相对链接。
- 版本显示存在 `pip` 元数据 0.1.0、源码运行时 0.1.1、RC1 标签并存的混乱，用户难以确认自己实际运行了哪个版本。

不建议为解决这些问题立即开发大型 GUI；配置文件、简单 launcher、清晰错误消息和输出目录约定已经足够作为下一步。

## Git / AI Collaboration Assessment

Git 基础纪律总体良好：存在 `main`、功能/修复分支、功能标签和可回滚提交；提交主题大体聚焦，适合 Antigravity 与 Codex 分工。

需要改进：

- 当前 `v0.1.1-rc1` 的测试报告没有绑定当前 HEAD，说明“代码提交”和“证据提交”没有形成可靠的一致性门槛。
- `v0.2.0-cad-layers` 标签先于当前 `v0.1.1-rc1`，README 又只记录 `v0.1.0-mvp1`，版本/发布顺序需要重新整理。
- 生成文件落在 `sample_data/output/` 并造成工作树污染，削弱 AI 修改前后的差异判断。
- 现有规则足以限制大范围重构，但还缺少一条自动化规则：只有在当前 HEAD 重新执行的测试和证据通过后，才能更新或创建 release tag。

## Risk Register

### P0 — Critical

**None found.** 当前没有证据表明正常 CLI 会覆盖原始 DXF、泄露秘密或完全不可用。

### P1 — High

#### P1-01：底层处理 API 在未知单位时仍可能默认按米计算

- Evidence：`src/planning_toolbox/cad/parcels/calculator.py:24-36` 将缺失配置默认成 `fallback_unit="m"`、`strict_unit_check=False`；`src/planning_toolbox/cad/io/dxf_reader.py:9-13` 也采用相同的宽松默认。
- 独立复核：对 `$INSUNITS=0` 的 DXF，CLI 使用默认 YAML 时正确退出并不生成输出；但直接调用 `process_parcels(dxf, {}, out)` 会返回 `VALID, 10000.0`。
- Impact：未来任何省略完整配置的 wrapper、脚本或 AI 新入口都可能把未知单位的面积错误地当作平方米，属于规划结果风险。
- Recommended Action：底层默认改为 fail-safe（未知单位直接阻断），让用户必须显式配置 fallback；新增完整 pipeline 的未知单位 E2E 测试，并禁止只依赖 `default.yaml` 的安全值。

#### P1-02：孔洞/多环地块会被当成多个地块并错误累加面积

- Evidence：`dxf_reader.py:37-45` 把每条目标图层实体独立列为候选；`calculator.py:42-88` 对每个候选独立生成 `Parcel`，没有 outer/inner ring 关系。
- 独立复核：100×100 外环加 20×20 内环同图层得到两个 `VALID` 地块、总面积 `10400 m²`，而单地块孔洞语义应为 `9600 m²`。
- Impact：带院落、天井、空洞或多环边界的真实规划数据可能得到错误面积和错误地块编号。
- Recommended Action：在支持完整多环语义前，检测并明确阻断/报告同一图层内的嵌套环；随后再实现 ring grouping、方向和净面积测试。

### P2 — Medium

#### P2-01：当前测试证据归档过期且部分不可重放

- Evidence：独立运行是当前 HEAD 的 19 passed；`test_artifacts/latest/pytest_output.txt` 仍为旧提交的 18 passed；`TEST_REPORT.md:66-68` 仍记录旧 hash 和 Clean；矩阵引用的 `scratch/*.py` 在仓库中不存在。
- Impact：会误导稳定性判断，不能作为当前 RC1 的 release evidence。
- Recommended Action：以当前 HEAD 重新生成 pytest、CLI、hash、性能和几何证据；只引用仓库内可重放的命令；在证据中记录 commit hash 和工作树状态。

#### P2-02：bulge 处理是近似实现，正式覆盖不足

- Evidence：`src/planning_toolbox/core/geometry/parser.py:21-30` 固定使用 `flattening(distance=0.01)`；当前正式测试没有 bulge case，矩阵中的 bulge 测试脚本不存在。
- Impact：不同单位和尺度的曲线边界可能出现未量化的面积误差；用户也无法从 CSV/report 判断曲线结果是否近似。
- Recommended Action：建立独立 expected 的负 bulge、多 bulge、>180°、混合曲线测试；明确 flattening/面积容差；必要时把近似状态写入结果。

#### P2-03：版本元数据与生成输出管理不一致

- Evidence：当前运行时/pyproject 是 0.1.1，`pip show` 是 0.1.0；`sample_data/output/` 生成文件未被忽略；标签和 README 版本记录顺序不一致。
- Impact：降低复现、回滚和 AI 协作时的版本可辨识性，并造成工作树污染。
- Recommended Action：同步分发元数据与运行时版本；明确 RC/stable 标签顺序；将生成输出放入统一忽略目录或补充忽略规则。

### P3 — Low

- README 未覆盖图层工具和完整错误处理流程。
- `AGENTS.md` 的规则链接不是仓库内可用相对链接。
- 当前没有 CI；对个人工具不是阻断条件，但会让“提交前 pytest”依赖人工纪律。

## Progress Estimate

- Phase 0（工程基础设施）：**约 80%**。已有 pyproject、src 布局、配置、测试、Git 标签和非破坏输出；缺少证据自动化、发布元数据一致性和 CI/稳定门禁。
- Phase 1（CAD 自动化：地块计算、图层初始化、标注）：**约 65–75%**。核心线性路径真实可用，图层与标注已存在；bulge、legacy DXF、孔洞、AutoCAD 兼容性和输入契约仍不完整。
- Overall MVP：**约 55–65%**。如果把 MVP 限定为当前 parcel + layer slice，可评为约 75%；如果按工具箱目标包含 GIS bridge、指标和规划规则检查，则明显未完成。

## Dimension Scores

| Dimension | Score /10 |
|---|---:|
| Architecture | 7.5 |
| Code Quality | 7.0 |
| Test Quality | 6.0 |
| Test Credibility | 5.0 |
| Geometry Correctness | 6.0 |
| DXF Reliability | 6.0 |
| Data Safety | 8.0 |
| Git Discipline | 7.0 |
| Non-programmer UX | 6.0 |
| Maintainability | 7.0 |
| Planning-domain usefulness | 6.0 |

### Overall Engineering Readiness

**约 6.3 / 10**。这是一个可以继续使用和验证的工作原型，不是可以把所有 CAD/GIS 输入都当成安全可靠的稳定工具。

## Minimum Stable Gate

在标记 `v0.1.0-mvp1 STABLE` 或类似稳定版本前，最小必要事项是：

1. 在当前 HEAD 上重新生成并核对全部证据，修正 18/19 passed、旧 commit hash、Clean 状态和不存在的 `scratch` 命令；稳定标签必须绑定可重放证据。
2. 让底层处理 API 与 CLI 一样对未知单位 fail-safe，并补一个从 DXF 读取到 pipeline 阻断的测试。
3. 对孔洞/多环输入明确“已支持”或“安全阻断”，同时补齐负、多段、>180°和混合 bulge 的独立几何测试与容差说明。
4. 至少完成一次真实 AutoCAD 打开、图层、MTEXT、线型和中文显示的人工复核；在完成前明确保持 `AutoCAD Validation: NOT TESTED`，不把 ezdxf 重读等同于 AutoCAD 验证。

## Recommended Next Step

选择 **B**：先完成稳定性验证，再开发下一项 MVP 功能。建议下一轮只处理 Minimum Stable Gate，不新增 GUI、Web、数据库、AI Agent、GIS bridge 或大型重构。待地块几何、单位、证据和输出安全形成可靠基线后，再进入下一功能的开发。

## Final Verdict

当前项目已经超过骨架和纯 Proof of Concept，进入了可运行的 Stage 2 工作原型。  
parcel 面积、编号、标注、CSV/report 和基础 CAD 图层处理已在 Python/ezdxf 层面真实跑通。  
线性多边形和基本错误拓扑有可信测试，但曲线只是部分验证，孔洞输入会产生错误净面积。  
当前 `TEST_REPORT` 与证据归档落后于实际 HEAD，不能直接支撑 release 判断。  
未知单位的默认 YAML 路径是安全的，但底层 API 默认值仍存在高风险旁路。  
GIS bridge、真实 setback、FAR、density 和规划规则检查尚未实现。  
因此当前不应标记 STABLE，也不应立即继续堆叠下一功能；先完成最小稳定门禁最合适。
