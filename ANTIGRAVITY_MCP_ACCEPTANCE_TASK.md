# Planning Toolbox × Antigravity MCP 使用验收任务书

版本：Planning Toolbox 0.58.1  
项目目录：`C:\AutoOS\OS1`  
任务性质：只使用、只验证，不开发、不修改项目

可直接复制给 Antigravity 的简明启动提示词见：

`C:\AutoOS\OS1\ANTIGRAVITY_MCP_START_PROMPT.md`

## 一、给 Antigravity 的角色说明

你现在是 Planning Toolbox 的 SketchUp 使用验收员，不是软件开发员。

你的任务是通过已连接的 `planning-toolbox-sketchup` MCP，实际操作 SketchUp，验证 Planning Toolbox 的建模链路、组件调用和结果导出效果。

不要修改源码、插件、MCP 服务端、配置文件、测试代码、项目文档或 Git 状态。不要安装依赖、不要执行任意 Ruby、不要执行命令行脚本、不要删除文件。

允许修改的内容只有：

- 一个新的、可丢弃的 SketchUp 测试模型；
- `C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\` 内由 MCP 测试产生的 `.skp`、`.png` 等结果文件。

禁止打开或修改用户原有的正式模型。所有会改变 SketchUp 模型的操作都必须先确认当前模型是临时测试模型。

## 二、Planning Toolbox 能做什么

Planning Toolbox 是城乡规划 CAD–GIS–SketchUp 辅助工具，主要负责：

1. 读取和检查 DXF、GeoJSON 等规划数据；
2. 检查 DXF 单位、坐标系、图层和几何质量；
3. 识别地块、建筑、道路、绿地、停车位和水体等规划对象；
4. 计算面积、容积率、建筑密度、退线等规划指标；
5. 将规划对象导出为 SketchUp 交接文件 `.ptsu.json`；
6. 在 SketchUp 中生成分层、可编辑的建筑、道路、绿地和底图；
7. 生成道路面、路缘、人行道、中心线、方向箭头和斑马线等道路表达；
8. 按需放置树木、路灯、车辆、座椅、灌木、隔离柱、公交站等组件；
9. 保存 SketchUp 模型并导出预览图；
10. 对模型执行基础质量检查。

## 三、MCP 工具边界

本次只允许使用以下已公开工具：

| 工具 | 用途 | 是否改变模型 |
|---|---|---:|
| `health` | 检查 MCP 桥接是否在线 | 否 |
| `inspect_model` | 查看当前模型、图层、范围和对象数量 | 否 |
| `list_tags` | 查看 SketchUp 图层/标签 | 否 |
| `set_tag_visibility` | 显示或隐藏已有标签 | 是，临时 |
| `import_handoff` | 导入 `.ptsu.json` 生成规划模型 | 是 |
| `place_component` | 放置白名单规划组件 | 是 |
| `save_model_as` | 保存测试模型副本 | 是，输出文件 |
| `export_preview` | 导出 PNG/JPG 预览图 | 是，输出文件 |
| `quality_check` | 检查项目根组和空组件定义 | 否 |

禁止寻找或调用不存在的工具，例如：

- `eval_ruby`；
- `run_shell`；
- `delete_model`；
- `edit_source`；
- `install_plugin`。

## 四、测试前提

请先让用户确认：

1. SketchUp 已保存正式模型；
2. 当前打开的是一个新的空白 SketchUp 测试模型；
3. Planning Toolbox SketchUp 插件已经加载；
4. MCP 工具状态为在线；
5. 测试结果目录可以创建：

`C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\`

推荐测试输入文件：

`C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\standard_site_plan.ptsu.json`

如果该文件不存在，不要自行搜索其他用户目录，也不要猜测路径；直接报告缺失并停止导入测试。

## 五、执行规则

每个会改变模型的步骤，都必须先在对话中说明：

- 将调用哪个 MCP 工具；
- 会对测试模型产生什么变化；
- 输出文件会保存到哪里。

得到用户确认后才执行。

不要批量尝试不同参数。出现错误时，先读取错误信息并报告，不要自行修改源码或绕过安全限制。

## 六、测试用例

### TC-01：MCP 连接测试

调用：

```text
health
```

验收标准：

- 返回状态为 `ready`；
- 能看到 Planning Toolbox MCP 版本；
- 不修改 SketchUp 模型。

### TC-02：只读模型检查

依次调用：

```text
inspect_model
list_tags
quality_check
```

验收标准：

- 能返回 SketchUp 版本和当前模型路径；
- 能返回模型范围和几何数量；
- 能返回图层列表；
- 能说明当前是否存在 Planning Toolbox 项目根组；
- 此步骤不得产生模型变化。

### TC-03：导入规划交接文件

先向用户确认当前是临时空白测试模型，然后调用：

```text
import_handoff
path = C:\AutoOS\OS1\test_artifacts\native_component_runtime_v058\native_component_validation.ptsu.json
```

导入完成后再次调用：

```text
inspect_model
```

验收标准：

- 导入返回成功；
- 出现 Planning Toolbox 项目根组；
- 建筑、道路或其他规划几何数量大于导入前；
- 没有 Python Traceback 或 Ruby 堆栈弹窗；
- 记录导入前后 groups、faces、edges、components 的变化。

### TC-04：图层显示控制

先调用 `list_tags`，只从返回的真实标签中选择一个 Planning Toolbox 标签。

执行：

1. 记录该标签原始可见状态；
2. 调用 `set_tag_visibility` 将其隐藏；
3. 调用 `inspect_model` 或再次调用 `list_tags` 确认状态变化；
4. 恢复原始可见状态。

验收标准：

- 只能操作已有标签；
- 隐藏和恢复都成功；
- 没有创建错误标签；
- 测试结束时图层状态恢复原样。

### TC-05：白名单组件放置

根据 `inspect_model` 返回的模型范围，选择不与主要建筑重叠的测试位置。只放置以下 3 个组件：

1. `bench`；
2. `parked_car`；
3. `bollard`。

每个组件只放置 1 个，使用米制坐标，并记录坐标、旋转角度和返回结果。

验收标准：

- 3 个组件均返回成功；
- 组件位于模型范围附近且没有明显飞离场地；
- SketchUp 中组件可以被选择和编辑；
- 不得重复放置或无限循环调用。

### TC-06：预览图导出

先向用户说明将导出文件，然后调用：

```text
export_preview
path = C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\mcp_model_preview.png
width = 1600
height = 1000
```

验收标准：

- 返回成功；
- 文件存在且大小大于 0；
- 预览图能看到建筑、道路或组件；
- 不覆盖项目原有图片。

### TC-07：保存测试模型

调用：

```text
save_model_as
path = C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\mcp_model_acceptance.skp
```

验收标准：

- 返回成功；
- 文件存在且大小大于 0；
- 保存的是测试副本；
- 不覆盖用户正式模型。

### TC-08：最终质量检查

依次调用：

```text
inspect_model
quality_check
```

最终报告必须说明：

- 模型是否存在 Planning Toolbox 项目根组；
- 建筑、道路、组件数量；
- 当前图层数量；
- 是否存在空组件定义；
- 是否有警告；
- 预览图路径；
- 测试模型路径；
- 总耗时和 MCP 工具调用次数。

## 七、最终报告格式

请严格按下面格式回复，不要修改项目文件：

```text
Planning Toolbox × Antigravity MCP 验收结果

总体结论：PASS / PASS WITH WARNINGS / BLOCKED

1. MCP 连接：通过 / 失败
2. 只读模型检查：通过 / 失败
3. 规划交接导入：通过 / 失败
4. 图层显示控制：通过 / 失败
5. 组件放置：通过 / 失败
6. 预览图导出：通过 / 失败
7. 测试模型保存：通过 / 失败
8. 最终质量检查：通过 / 警告 / 失败

模型统计：
- 建筑：
- 道路：
- 绿地：
- 组件：
- 图层：

输出文件：
- SKP：
- PNG：

发现的问题：
- 

人工仍需调整的内容：
- 

禁止修改确认：
- 源码未修改；
- 插件未修改；
- 配置未修改；
- Git 未修改；
- 未删除任何文件。
```

## 八、结论判定

- `PASS`：所有核心测试成功，且无阻断性问题；
- `PASS WITH WARNINGS`：核心链路成功，但存在需要人工复核的对位、组件位置或显示问题；
- `BLOCKED`：MCP 未连接、SketchUp 插件未加载、输入交接文件缺失，或测试需要修改源码才能继续。

本次测试的目标是验证“AI 能否正确使用 Planning Toolbox”，不是要求 AI 自动完成审批级城乡规划设计。
