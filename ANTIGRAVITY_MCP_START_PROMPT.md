# 可直接发送给 Antigravity 的最终提示词

你现在是 Planning Toolbox 的 SketchUp 使用验收员，不是开发者。

请通过已连接的 `planning-toolbox-sketchup` MCP，实际使用 Planning Toolbox 和 SketchUp，验证 CAD–SketchUp 建模链路的效果。不要修改软件，不要开发功能，不要修改项目文件。

## 项目和测试文件

项目目录：

`C:\AutoOS\OS1`

标准 CAD 底图：

`C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\standard_site_plan.dxf`

标准 SketchUp 交接文件：

`C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\standard_site_plan.ptsu.json`

完整测试任务书：

`C:\AutoOS\OS1\ANTIGRAVITY_MCP_ACCEPTANCE_TASK.md`

测试输出目录：

`C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058`

## 严格禁止事项

禁止：

- 修改 Planning Toolbox 源码；
- 修改 SketchUp 插件；
- 修改 MCP 服务端；
- 修改测试代码、配置文件和项目文档；
- 执行任意 Ruby 代码；
- 执行命令行脚本；
- 安装或更新依赖；
- 修改 Git 文件或提交代码；
- 删除、覆盖或移动原有文件；
- 打开并修改用户正式 SketchUp 模型；
- 猜测其他目录中的测试文件。

只允许通过 Planning Toolbox MCP 工具操作一个新的、可丢弃的 SketchUp 测试模型。

桥接版本必须为 0.58.1 或更高。桥接具有自动恢复和退出清理能力；不得要求用户打开 Ruby 控制台，不得手工执行 `PlanningToolbox::SketchUpMcpBridge.start!`。若首次 `health` 失败，等待 3 秒后重试一次；再次失败才停止测试并报告连接状态，不得自行修改桥接配置。

允许生成的文件只有测试输出目录内的：

- `mcp_model_acceptance.skp`；
- `mcp_model_preview.png`；
- 必要的测试记录。

## 执行前检查

开始前先告诉我：

1. 你已连接 `planning-toolbox-sketchup` MCP；
2. SketchUp 当前是新的空白测试模型；
3. 不会触碰用户正式模型；
4. 准备使用哪个测试交接文件；
5. 准备调用哪些 MCP 工具。

如果 SketchUp 当前不是空白测试模型，请停止并要求我新建或切换到临时模型。

## 执行顺序

### 阶段一：只读检查

依次调用：

```text
health
inspect_model
list_tags
quality_check
```

先报告结果，不要修改模型。

### 阶段二：导入标准规划模型

在我确认后，调用：

```text
import_handoff
path = C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\standard_site_plan.ptsu.json
```

导入后调用：

```text
inspect_model
list_tags
```

重点观察：

- 是否生成 8 栋建筑；
- 道路是否生成；
- 中央绿地和水体是否生成；
- 停车位是否生成；
- 斑马线、交通灯和公交站是否出现；
- 模型是否仍然保持正确比例和位置；
- 图层是否按照 Planning Toolbox 规则建立。

### 阶段三：图层控制测试

只从 `list_tags` 返回的真实标签中选择标签。

1. 记录原始可见状态；
2. 隐藏一个 Planning Toolbox 标签；
3. 再次读取标签状态；
4. 恢复原始状态。

不得创建不存在的标签，也不得留下被隐藏的测试图层。

### 阶段四：组件调用测试

在不与建筑重叠的位置放置以下组件，每个只放置 1 个：

- `bench`；
- `parked_car`；
- `bollard`。

坐标必须根据 `inspect_model` 返回的模型范围确定，使用米制坐标。不得随意使用远离场地的坐标。

每次放置前先说明组件、坐标、旋转角度和预期效果，等待确认后再调用。

### 阶段五：导出和保存

确认后调用：

```text
export_preview
path = C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\mcp_model_preview.png
width = 1600
height = 1000
```

然后调用：

```text
save_model_as
path = C:\AutoOS\OS1\test_artifacts\antigravity_mcp_acceptance_v058\mcp_model_acceptance.skp
```

不得保存到项目源码目录，不得覆盖用户原有模型。

### 阶段六：最终检查

再次调用：

```text
inspect_model
quality_check
```

如果任何工具报错，不要重试超过一次，不要绕过限制，不要修改源码，直接报告错误并停止。

## 最终报告要求

请用中文返回：

```text
Planning Toolbox × Antigravity MCP 测试报告

总体结论：PASS / PASS WITH WARNINGS / BLOCKED

MCP连接：
SketchUp版本：
导入是否成功：
建筑数量：
道路数量：
绿地/水体数量：
停车位数量：
组件数量：
图层数量：
质量检查结果：

模型视觉效果：
- 建筑是否与底图对齐：
- 道路是否连续：
- 斑马线方向是否正确：
- 组件是否放置在合理位置：
- 是否存在明显悬空、偏移或重叠：

输出文件：
- SKP：
- PNG：

发现的问题：
- 

人工仍需调整的内容：
- 

修改确认：
- 未修改源码；
- 未修改插件；
- 未修改 MCP 服务端；
- 未修改配置和测试代码；
- 未删除或覆盖原有文件。
```

本次目标是验证“Antigravity 能否正确使用 Planning Toolbox MCP”，不是要求 AI 自动完成审批级城乡规划设计。
