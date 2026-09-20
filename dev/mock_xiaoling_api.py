"""Local mock for Xiaoling Connector pairing and WebSocket."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from typing import Any

from aiohttp import WSMsgType, web

PORT = 8124

DEVICES = {
    "ABC123": {
        "api_token": "token-001",
        "binding_id": "binding-001",
        "connector_id": "connector-001",
        "product_id": "product-001",
        "device_id": "device-001",
        "device_name": "客厅小聆",
        "token_type": "Bearer",
    },
    "XYZ789": {
        "api_token": "token-002",
        "binding_id": "binding-002",
        "connector_id": "connector-002",
        "product_id": "product-001",
        "device_id": "device-002",
        "device_name": "卧室小聆",
        "token_type": "Bearer",
    },
}

TOKENS = {
    item["api_token"]: item
    for item in DEVICES.values()
}


async def handle_exchange(request: web.Request) -> web.Response:
    """Exchange a pairing code for Connector credentials."""
    body = await request.json()
    print(f"POST {request.path}: {body}", flush=True)
    pairing_code = str(body.get("pairing_code", "")).strip().upper()
    pairing = DEVICES.get(pairing_code)
    if pairing is None:
        return web.json_response(
            {"code": "MCP_PAIRING_EXPIRED", "message": "expired"},
            status=400,
        )
    return web.json_response(
        {"code": "SUCCESS", "message": "success", "data": pairing}
    )


async def handle_connector(request: web.Request) -> web.WebSocketResponse:
    """Accept one Connector WebSocket and complete hello/server_sync."""
    connector_id = request.query.get("connector_id", "")
    protocol_version = request.query.get("protocol_version", "")
    auth = request.headers.get("Authorization", "")
    token = ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    token = token or request.query.get("api_token", "")
    pairing = TOKENS.get(token)
    print(
        f"WS {request.path}?connector_id={connector_id}&protocol_version={protocol_version}",
        flush=True,
    )
    if pairing is None or pairing["connector_id"] != connector_id or protocol_version != "1":
        raise web.HTTPUnauthorized(text="INVALID_API_TOKEN")

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    session_id = f"session-{pairing['device_id']}"
    connection_epoch = int(datetime.now(UTC).timestamp() * 1000)
    request.app["connections"][pairing["device_id"]] = {
        "connector_id": connector_id,
        "messages": [],
        "hello": False,
        "server_sync": False,
        "ws": ws,
        "session_id": session_id,
        "connection_epoch": connection_epoch,
        "binding_id": pairing["binding_id"],
    }
    state = request.app["connections"][pairing["device_id"]]

    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            break
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            print(f"WS invalid JSON: {msg.data}", flush=True)
            continue
        state["messages"].append(payload)
        msg_type = payload.get("type")
        print(f"WS <- {msg_type}: {json.dumps(payload, ensure_ascii=False)[:500]}", flush=True)
        if msg_type == "hello":
            state["hello"] = True
            await ws.send_json(
                {
                    "protocol_version": 1,
                    "type": "ack",
                    "connector_id": connector_id,
                    "binding_id": pairing["binding_id"],
                    "session_id": session_id,
                    "connection_epoch": connection_epoch,
                    "frame_id": payload.get("frame_id", 1),
                    "payload": {
                        "ack_type": "hello",
                        "protocol_version": 1,
                        "heartbeat_seconds": 30,
                        "max_frame_size": 655360,
                        "session_expiry_seconds": 0,
                    },
                }
            )
            continue
        if msg_type == "server_sync":
            state["server_sync"] = True
            servers = (payload.get("payload") or {}).get("servers") or []
            tool_count = sum(len(server.get("tools") or []) for server in servers)
            await ws.send_json(
                {
                    "protocol_version": 1,
                    "type": "ack",
                    "connector_id": connector_id,
                    "binding_id": pairing["binding_id"],
                    "session_id": session_id,
                    "connection_epoch": connection_epoch,
                    "payload": {
                        "ack_type": "server_sync",
                        "code": 0,
                        "message": "ok",
                        "manifest_version": (payload.get("payload") or {}).get(
                            "manifest_version"
                        ),
                        "server_count": len(servers),
                        "tool_count": tool_count,
                    },
                }
            )
            continue
        if msg_type == "heartbeat":
            await ws.send_json(
                {
                    "protocol_version": 1,
                    "type": "heartbeat_ack",
                    "connector_id": connector_id,
                    "binding_id": pairing["binding_id"],
                    "session_id": session_id,
                    "connection_epoch": connection_epoch,
                    "payload": {
                        "observed_at": int(datetime.now(UTC).timestamp() * 1000)
                    },
                }
            )
            continue
        if msg_type == "call_result":
            continue

    state["closed"] = True
    print(f"WS closed {connector_id}", flush=True)
    return ws


async def handle_status(request: web.Request) -> web.Response:
    """Expose connection state for local verification."""
    connections = {}
    for device_id, state in request.app["connections"].items():
        connections[device_id] = {
            key: value
            for key, value in state.items()
            if key != "ws"
        }
    return web.json_response(connections)


async def handle_debug_call(request: web.Request) -> web.Response:
    """Send a tool call to a connected Connector."""
    body = await request.json()
    device_id = body.get("device_id", "device-001")
    state = request.app["connections"].get(device_id)
    if state is None or state.get("ws") is None:
        raise web.HTTPNotFound(text="connector not connected")
    await state["ws"].send_json(
        {
            "protocol_version": 1,
            "type": "call",
            "connector_id": state["connector_id"],
            "binding_id": state["binding_id"],
            "session_id": state["session_id"],
            "connection_epoch": state["connection_epoch"],
            "payload": {
                "call_id": body.get("call_id", "call-debug"),
                "name": "Home Assistant",
                "tool_name": body.get("tool_name", "GetLiveContext"),
                "arguments": body.get("arguments", {}),
            },
        }
    )
    return web.json_response({"status": "sent"})


def create_app() -> web.Application:
    """Create the mock Xiaoling API app."""
    app = web.Application()
    app["connections"] = {}
    app.router.add_post("/external/mcp/auth/exchange", handle_exchange)
    app.router.add_get("/v1/mcp/connector", handle_connector)
    app.router.add_get("/debug/connections", handle_status)
    app.router.add_post("/debug/call", handle_debug_call)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT, print=lambda msg: print(msg, flush=True))
