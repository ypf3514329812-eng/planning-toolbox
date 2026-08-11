# Planning Toolbox 本地 MCP–SketchUp 控制

版本：0.58.1

这是一条本机自动化通道：Planning Toolbox 负责规划数据、单位检查和建模规则，SketchUp 负责显示和编辑模型，MCP 负责把固定的操作变成可调用工具。

## 已部署的能力

SketchUp 启动并加载 Planning Toolbox 插件后，会在本机回环地址启动桥接服务。桥接配置写入：

`%APPDATA%\PlanningToolbox\mcp_bridge.json`

MCP 客户端可以调用以下工具。文件操作只允许访问桥接配置中的项目根目录，公开部署时请通过 `PLANNING_TOOLBOX_ROOT` 明确指定工作区：

- 检查桥接和 SketchUp 是否在线；
- 查看模型范围、图层、对象数量和 Planning Toolbox 项目根组；
- 显示或隐藏已有图层；
- 导入项目根目录内的 `.ptsu.json`；
- 放置 14 类白名单组件；
- 保存 `.skp`；
- 导出 PNG/JPG 预览图；
- 执行基础模型质量检查。

## 启动方式

在已安装项目环境的终端中运行：

```text
planning-toolbox-mcp
```

MCP 客户端应以标准 stdio MCP 方式启动这个命令。SketchUp 必须先启动并加载 Planning Toolbox 插件。若客户端提示 SketchUp 未连接，先重启 SketchUp，再重启 MCP 客户端。

从 0.58.1 起，桥接会自动监视后台线程并在意外停止时重新启动。关闭 SketchUp 时会自动释放端口并清理仅属于当前实例的配置；同时打开多个 SketchUp 时，只有一个实例提供桥接，其余实例保持被动等待，避免争抢 8765。

正常使用不需要打开 Ruby 控制台，也不需要手动调用 `start!`。如果客户端暂时连接失败，请只保留一个需要操作的 SketchUp 模型，等待约 3 秒后重新执行 `health`；仍失败时再完整关闭并重开 SketchUp。

## 可使用的自然语言指令示例

```text
检查当前 SketchUp 模型是否已经连接 Planning Toolbox。
```

```text
导入 C:\AutoOS\OS1\output\sketchup_validation_v018\planning_toolbox_su_validation.ptsu.json，完成后检查模型质量。
```

```text
隐藏 PT_DETAIL 和 PT_FACADE，只显示道路、建筑和绿地图层，然后导出一张 output\mcp_preview.png。
```

```text
在坐标 [36, 18, 0] 放置一盏路灯，在 [40, 18, 0] 放置一个公交站，旋转角度均为 90 度，保存为 output\mcp_demo.skp。
```

## 安全边界

- 只监听 `127.0.0.1`，不接受局域网连接；
- 每次请求都需要本机随机令牌；
- 文件路径限制在 `C:\AutoOS\OS1` 内；
- 只允许白名单命令和白名单组件；
- 不提供任意 Ruby 执行、命令行执行或删除模型命令；
- 导入、放置和保存都在 SketchUp 操作历史中执行，可以使用 SketchUp 的撤销；
- 当前版本是受控自动化，不是“一句话生成完整审批级模型”。复杂道路、建筑细部和图片识别结果仍需人工检查。

## 如果 MCP 客户端找不到命令

可以改用：

```text
python -m planning_toolbox.mcp_server
```

如果项目是源码运行，请先在 `C:\AutoOS\OS1` 环境中安装项目，再启动 MCP 客户端。MCP 桥接本身不需要外部 API；是否需要模型 API 取决于你使用的 AI 客户端。
