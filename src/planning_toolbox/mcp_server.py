"""Small dependency-free MCP server for the local SketchUp bridge.

The server speaks MCP JSON-RPC over stdio and forwards only the allow-listed
tools to the Planning Toolbox SketchUp extension over authenticated loopback
HTTP.  It intentionally does not evaluate model code or expose a shell.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SERVER_VERSION = "0.60.0"
DEFAULT_CONFIG = Path(
    os.environ.get("APPDATA", str(Path.home()))
) / "PlanningToolbox" / "mcp_bridge.json"


class BridgeUnavailable(RuntimeError):
    """Raised when SketchUp is not running or its bridge is not ready."""


class SketchUpBridgeClient:
    def __init__(self, config_path: str | os.PathLike[str] | None = None) -> None:
        configured = config_path or os.environ.get("PLANNING_TOOLBOX_MCP_CONFIG")
        self.config_path = Path(configured) if configured else DEFAULT_CONFIG

    def _config(self) -> dict[str, Any]:
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise BridgeUnavailable(
                "SketchUp 尚未启动 Planning Toolbox MCP 桥接。请先启动 SketchUp，"
                "并确认已加载 Planning Toolbox 插件。"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeUnavailable(f"无法读取 MCP 桥接配置：{exc}") from exc

    def call(self, command: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        last_config: dict[str, Any] = {}
        for attempt in range(2):
            config = self._config()
            last_config = config
            host = str(config.get("host", "127.0.0.1"))
            port = int(config.get("port", 0))
            token = str(config.get("token", ""))
            if host not in {"127.0.0.1", "localhost"} or not (1024 <= port <= 65535) or not token:
                raise BridgeUnavailable("MCP 桥接配置无效或不安全。")
            payload = json.dumps(
                {"command": command, "arguments": arguments or {}},
                ensure_ascii=False,
            ).encode("utf-8")
            request = Request(
                f"http://127.0.0.1:{port}/command",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "Content-Length": str(len(payload)),
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=90) as response:
                    data = json.loads(response.read().decode("utf-8"))
                if not isinstance(data, dict):
                    raise BridgeUnavailable("SketchUp 返回了无法识别的 MCP 结果。")
                return data
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = BridgeUnavailable(
                    f"SketchUp 桥接请求失败（HTTP {exc.code}）：{detail}"
                )
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
            if attempt == 0:
                time.sleep(0.35)

        port = last_config.get("port", "未知")
        process_id = last_config.get("process_id", "未知")
        raise BridgeUnavailable(
            f"无法连接 SketchUp MCP 桥接（端口 {port}，配置进程 {process_id}）。"
            "插件会自动尝试恢复；请稍等数秒后重试，或确认只打开一个 SketchUp 测试模型。"
        ) from last_error


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "health",
        "description": "检查 SketchUp 中的 Planning Toolbox MCP 桥接是否在线。",
        "inputSchema": _schema({}, []),
    },
    {
        "name": "inspect_model",
        "description": "只读查看当前 SketchUp 模型、图层、建筑项目根组和几何数量。",
        "inputSchema": _schema({}, []),
    },
    {
        "name": "list_tags",
        "description": "只读列出当前 SketchUp 图层/标签及可见性。",
        "inputSchema": _schema({}, []),
    },
    {
        "name": "set_tag_visibility",
        "description": "显示或隐藏一个已有的 SketchUp 图层/标签。",
        "inputSchema": _schema(
            {
                "name": {"type": "string", "description": "已有标签名称，例如 PT_ROAD。"},
                "visible": {"type": "boolean"},
            },
            ["name", "visible"],
        ),
    },
    {
        "name": "import_handoff",
        "description": "将 Planning Toolbox 生成的 .ptsu.json 增量导入当前 SketchUp 模型。",
        "inputSchema": _schema(
            {
                "path": {
                    "type": "string",
                    "description": "桥接配置允许根目录内的 .ptsu.json 文件路径。",
                }
            },
            ["path"],
        ),
    },
    {
        "name": "place_component",
        "description": "在指定米制坐标放置一个白名单规划组件。",
        "inputSchema": _schema(
            {
                "asset_id": {
                    "type": "string",
                    "enum": [
                        "tree_large",
                        "tree_small",
                        "planter",
                        "street_light",
                        "awning_wide",
                        "overhang_wide",
                        "parasol",
                        "road_crossing",
                        "traffic_light",
                        "parked_car",
                        "bench",
                        "shrub_cluster",
                        "bollard",
                        "bus_shelter",
                    ],
                },
                "point_m": {
                    "type": "array",
                    "description": "米制坐标 [x, y, z]；z 可省略，默认 0。",
                    "minItems": 2,
                    "maxItems": 3,
                    "items": {"type": "number"},
                },
                "rotation_deg": {"type": "number", "default": 0},
                "tag": {"type": "string", "default": "PT_DETAIL"},
            },
            ["asset_id", "point_m"],
        ),
    },
    {
        "name": "save_model_as",
        "description": "将当前 SketchUp 模型保存为指定的 .skp 文件。路径必须在桥接配置允许根目录内。",
        "inputSchema": _schema(
            {"path": {"type": "string", "description": "桥接配置允许根目录内的 .skp 路径。"}},
            ["path"],
        ),
    },
    {
        "name": "export_preview",
        "description": "缩放到当前模型范围并导出 PNG/JPG 预览图。",
        "inputSchema": _schema(
            {
                "path": {"type": "string", "description": "桥接配置允许根目录内的图片输出路径。"},
                "width": {"type": "integer", "minimum": 640, "maximum": 4000, "default": 1600},
                "height": {"type": "integer", "minimum": 480, "maximum": 4000, "default": 1000},
            },
            ["path"],
        ),
    },
    {
        "name": "quality_check",
        "description": "只读检查是否存在 Planning Toolbox 项目根组和空组件定义。",
        "inputSchema": _schema({}, []),
    },
]


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _text_result(text: str, *, is_error: bool = False, structured: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
    }
    if is_error:
        result["isError"] = True
    if structured is not None:
        result["structuredContent"] = structured
    return result


def _dispatch(message: dict[str, Any], bridge: SketchUpBridgeClient) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "initialize":
        requested = message.get("params", {}).get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "planning-toolbox-sketchup", "version": SERVER_VERSION},
                "instructions": "这是 Planning Toolbox 的本地 SketchUp 安全控制桥。",
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method != "tools/call":
        return _jsonrpc_error(request_id, -32601, f"Unsupported method: {method}")

    params = message.get("params", {})
    name = str(params.get("name", ""))
    if name not in {tool["name"] for tool in TOOLS}:
        return _jsonrpc_error(request_id, -32602, f"Unknown tool: {name}")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _jsonrpc_error(request_id, -32602, "Tool arguments must be an object")
    try:
        data = bridge.call(name, arguments)
        if not data.get("ok", False):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _text_result(str(data.get("error", "SketchUp command failed")), is_error=True),
            }
        encoded = json.dumps(data.get("data"), ensure_ascii=False, indent=2)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _text_result(encoded, structured=data.get("data")),
        }
    except BridgeUnavailable as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _text_result(str(exc), is_error=True),
        }
    except Exception as exc:  # pragma: no cover - final protocol guard
        return _jsonrpc_error(request_id, -32000, str(exc))


def main() -> int:
    bridge = SketchUpBridgeClient()
    for raw_line in sys.stdin:
        if not raw_line.strip():
            continue
        try:
            message = json.loads(raw_line)
            if not isinstance(message, dict):
                response = _jsonrpc_error(None, -32600, "JSON-RPC message must be an object")
            else:
                response = _dispatch(message, bridge)
        except json.JSONDecodeError as exc:
            response = _jsonrpc_error(None, -32700, f"Parse error: {exc.msg}")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
