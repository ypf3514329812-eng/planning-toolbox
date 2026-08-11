from __future__ import annotations

import json

from planning_toolbox import __version__, mcp_server


class FakeBridge:
    def __init__(self):
        self.calls = []

    def call(self, command, arguments=None):
        self.calls.append((command, arguments or {}))
        return {"ok": True, "data": {"command": command, "arguments": arguments or {}}}


def test_mcp_tools_are_allow_listed():
    names = {tool["name"] for tool in mcp_server.TOOLS}
    assert names == {
        "health",
        "inspect_model",
        "list_tags",
        "set_tag_visibility",
        "import_handoff",
        "place_component",
        "save_model_as",
        "export_preview",
        "quality_check",
    }
    assert "eval_ruby" not in names
    assert "run_shell" not in names


def test_initialize_and_tools_list():
    bridge = FakeBridge()
    initialize = mcp_server._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        },
        bridge,
    )
    assert initialize["result"]["serverInfo"]["name"] == "planning-toolbox-sketchup"
    assert initialize["result"]["serverInfo"]["version"] == __version__

    listing = mcp_server._dispatch(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, bridge
    )
    assert len(listing["result"]["tools"]) == 9


def test_tool_call_forwards_only_named_command():
    bridge = FakeBridge()
    response = mcp_server._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "inspect_model", "arguments": {}},
        },
        bridge,
    )
    assert response["result"].get("isError") is not True
    assert bridge.calls == [("inspect_model", {})]
    assert json.loads(response["result"]["content"][0]["text"])["command"] == "inspect_model"


def test_unknown_tool_is_rejected_without_bridge_call():
    bridge = FakeBridge()
    response = mcp_server._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "eval_ruby", "arguments": {"code": "1 + 1"}},
        },
        bridge,
    )
    assert response["error"]["code"] == -32602
    assert bridge.calls == []
