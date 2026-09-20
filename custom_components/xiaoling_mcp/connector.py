"""Xiaoling MCP Connector WebSocket client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import json
import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_TOKEN,
    CONF_BINDING_ID,
    CONF_CONNECTOR_ID,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_MANIFEST_VERSION,
    CONNECTOR_WS_PATH,
    DEFAULT_CALL_TIMEOUT,
    DEFAULT_HEARTBEAT_SECONDS,
    DEFAULT_MAX_FRAME_SIZE,
    HELLO_TIMEOUT,
    INTEGRATION_VERSION,
    MAX_RECONNECT_DELAY,
    PROTOCOL_VERSION,
    USER_AGENT,
    XIAOLING_API_BASE,
)
from .ha_mcp import async_build_server, async_call_tool

_LOGGER = logging.getLogger(__name__)

_CLOSE_RETRY = frozenset({
    aiohttp.WSMsgType.CLOSE,
    aiohttp.WSMsgType.CLOSING,
    aiohttp.WSMsgType.CLOSED,
})


class XiaolingConnector:
    """Maintain one cloud Connector WebSocket for a paired device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: Mapping[str, Any],
        on_manifest_version: Callable[[int], None] | None = None,
    ) -> None:
        self._hass = hass
        self._device_id = str(device[CONF_DEVICE_ID])
        self._api_token = str(device[CONF_API_TOKEN])
        self._binding_id = str(device[CONF_BINDING_ID])
        self._connector_id = str(device[CONF_CONNECTOR_ID])
        self._manifest_version = int(device.get(CONF_MANIFEST_VERSION) or 0)
        self._on_manifest_version = on_manifest_version
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session_id: str | None = None
        self._connection_epoch: int | None = None
        self._heartbeat_seconds = DEFAULT_HEARTBEAT_SECONDS
        self._max_frame_size = DEFAULT_MAX_FRAME_SIZE
        self._frame_id = 0
        self._synced = False

    @property
    def device_id(self) -> str:
        """Return the paired Xiaoling device id."""
        return self._device_id

    @property
    def connector_id(self) -> str:
        """Return the cloud Connector id."""
        return self._connector_id

    @property
    def manifest_version(self) -> int:
        """Return the last persisted server_sync version."""
        return self._manifest_version

    def start(self) -> None:
        """Start the reconnect loop."""
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = self._hass.async_create_background_task(
                self._async_run(),
                name=f"xiaoling_mcp_connector_{self._device_id}",
            )

    async def async_stop(self) -> None:
        """Stop the reconnect loop and close the socket."""
        self._stop.set()
        await self._async_close_ws()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _async_run(self) -> None:
        """Reconnect with backoff until the connector is stopped."""
        delay = 1
        while not self._stop.is_set():
            try:
                await self._async_connect()
                delay = 1
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Xiaoling Connector %s disconnected",
                    self._connector_id,
                )
            if self._stop.is_set():
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)

    async def _async_connect(self) -> None:
        """Open one WebSocket session and process messages."""
        session = async_get_clientsession(self._hass)
        query = urlencode(
            {
                "connector_id": self._connector_id,
                "protocol_version": PROTOCOL_VERSION,
            }
        )
        url = f"{_ws_base(XIAOLING_API_BASE)}{CONNECTOR_WS_PATH}?{query}"
        self._session_id = None
        self._connection_epoch = None
        self._synced = False
        self._frame_id = 0

        _LOGGER.debug("Connecting Xiaoling Connector %s", self._connector_id)
        async with session.ws_connect(
            url,
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "User-Agent": USER_AGENT,
            },
            max_msg_size=self._max_frame_size,
        ) as ws:
            self._ws = ws
            try:
                await self._async_send(
                    "hello",
                    {
                        "connector_version": INTEGRATION_VERSION,
                        "protocol_version": PROTOCOL_VERSION,
                    },
                    include_session=False,
                )
                await self._async_listen(ws)
            finally:
                self._ws = None

    async def _async_listen(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Read messages until the socket closes."""
        heartbeat_task: asyncio.Task[None] | None = None
        hello_watchdog = asyncio.create_task(self._async_hello_watchdog())
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._async_handle_message(msg.data)
                    if (
                        heartbeat_task is None
                        and self._session_id
                        and not self._stop.is_set()
                    ):
                        heartbeat_task = self._hass.async_create_background_task(
                            self._async_heartbeat(),
                            name=f"xiaoling_mcp_heartbeat_{self._device_id}",
                        )
                    continue
                if msg.type == aiohttp.WSMsgType.ERROR:
                    raise ConnectionError(f"WebSocket error: {ws.exception()}")
                if msg.type in _CLOSE_RETRY:
                    extra = str(msg.extra or "")
                    if extra == "BINDING_REVOKED" or "revoked" in extra.lower():
                        _LOGGER.warning(
                            "Xiaoling Connector %s was revoked; stopping reconnect",
                            self._connector_id,
                        )
                        self._stop.set()
                    return
        finally:
            hello_watchdog.cancel()
            if heartbeat_task is not None:
                heartbeat_task.cancel()
            for task in (hello_watchdog, heartbeat_task):
                if task is None:
                    continue
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _async_hello_watchdog(self) -> None:
        """Close the socket if hello ack never arrives."""
        await asyncio.sleep(HELLO_TIMEOUT)
        if self._session_id is None and not self._stop.is_set():
            _LOGGER.warning(
                "Xiaoling Connector %s did not receive hello ack",
                self._connector_id,
            )
            await self._async_close_ws()

    async def _async_heartbeat(self) -> None:
        """Send business heartbeats at the interval from hello ack."""
        while not self._stop.is_set():
            await asyncio.sleep(self._heartbeat_seconds)
            try:
                await self._async_send("heartbeat", {})
            except (ConnectionError, aiohttp.ClientError):
                return

    async def _async_handle_message(self, raw: str) -> None:
        """Dispatch one inbound JSON frame."""
        if len(raw.encode()) > self._max_frame_size:
            _LOGGER.warning("Ignoring oversized Xiaoling Connector frame")
            return
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            _LOGGER.warning("Ignoring invalid Xiaoling Connector JSON")
            return
        if not isinstance(message, dict):
            return

        msg_type = message.get("type")
        payload = message.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        if msg_type == "ack":
            await self._async_handle_ack(message, payload)
            return
        if msg_type == "heartbeat":
            await self._async_send("heartbeat_ack", {})
            return
        if msg_type == "heartbeat_ack":
            return
        if msg_type == "server_refresh":
            await self._async_sync_servers()
            return
        if msg_type == "call":
            await self._async_handle_call(payload)
            return
        if msg_type == "revoke":
            _LOGGER.warning(
                "Xiaoling Connector %s received revoke: %s",
                self._connector_id,
                payload.get("reason"),
            )
            self._stop.set()
            await self._async_close_ws()
            return
        if msg_type == "error":
            _LOGGER.error(
                "Xiaoling Connector error %s: %s",
                payload.get("code"),
                payload.get("message"),
            )
            return
        _LOGGER.debug("Ignoring Xiaoling Connector message type %s", msg_type)

    async def _async_handle_ack(
        self,
        message: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        """Handle hello and server_sync acknowledgements."""
        ack_type = payload.get("ack_type")
        if ack_type == "hello":
            session_id = message.get("session_id")
            connection_epoch = message.get("connection_epoch")
            if isinstance(session_id, str) and session_id:
                self._session_id = session_id
            if isinstance(connection_epoch, int):
                self._connection_epoch = connection_epoch
            heartbeat = payload.get("heartbeat_seconds")
            if isinstance(heartbeat, int) and heartbeat > 0:
                self._heartbeat_seconds = heartbeat
            max_frame_size = payload.get("max_frame_size")
            if isinstance(max_frame_size, int) and max_frame_size > 0:
                self._max_frame_size = max_frame_size
            if self._session_id and self._connection_epoch is not None and not self._synced:
                await self._async_sync_servers()
            return
        if ack_type == "server_sync":
            _LOGGER.debug(
                "Xiaoling Connector %s synced %s tools",
                self._connector_id,
                payload.get("tool_count"),
            )

    async def _async_sync_servers(self) -> None:
        """Send the current Home Assistant MCP Server list."""
        server = await async_build_server(self._hass)
        self._manifest_version += 1
        if self._on_manifest_version is not None:
            self._on_manifest_version(self._manifest_version)
        await self._async_send(
            "server_sync",
            {
                "manifest_version": self._manifest_version,
                "servers": [server],
            },
        )
        self._synced = True

    async def _async_handle_call(self, payload: dict[str, Any]) -> None:
        """Execute a tool call and return the result."""
        call_id = payload.get("call_id")
        name = payload.get("name") or "Home Assistant"
        tool_name = payload.get("tool_name")
        arguments = payload.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        if not isinstance(call_id, str) or not isinstance(tool_name, str):
            return

        timeout = _deadline_timeout(payload.get("deadline_at"))
        result_payload: dict[str, Any] = {
            "call_id": call_id,
            "name": name,
            "tool_name": tool_name,
        }
        try:
            result = await asyncio.wait_for(
                async_call_tool(self._hass, tool_name, arguments),
                timeout=timeout,
            )
            result_payload["status"] = "SUCCESS"
            result_payload["result"] = _as_mcp_result(result)
        except TimeoutError:
            result_payload["status"] = "ERROR"
            result_payload["error_code"] = "TIMEOUT"
            result_payload["result"] = {
                "content": [{"type": "text", "text": "Tool call timed out"}]
            }
        except HomeAssistantError as err:
            result_payload["status"] = "ERROR"
            result_payload["error_code"] = "TOOL_ERROR"
            result_payload["result"] = {
                "content": [{"type": "text", "text": str(err)}]
            }
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Xiaoling tool call %s failed", tool_name)
            result_payload["status"] = "ERROR"
            result_payload["error_code"] = "INTERNAL_ERROR"
            result_payload["result"] = {
                "content": [{"type": "text", "text": "Tool call failed"}]
            }

        await self._async_send("call_result", result_payload)

    async def _async_send(
        self,
        msg_type: str,
        payload: dict[str, Any],
        *,
        include_session: bool = True,
    ) -> None:
        """Send one outbound Connector frame."""
        ws = self._ws
        if ws is None or ws.closed:
            raise ConnectionError("Xiaoling Connector WebSocket is not connected")

        self._frame_id += 1
        message: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "type": msg_type,
            "connector_id": self._connector_id,
            "binding_id": self._binding_id,
            "frame_id": self._frame_id,
            "payload": payload,
        }
        if include_session:
            if not self._session_id or self._connection_epoch is None:
                raise ConnectionError("Xiaoling Connector session is not ready")
            message["session_id"] = self._session_id
            message["connection_epoch"] = self._connection_epoch

        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > self._max_frame_size:
            raise ConnectionError("Xiaoling Connector frame exceeds max_frame_size")
        await ws.send_str(encoded)

    async def _async_close_ws(self) -> None:
        """Close the current WebSocket if it is open."""
        ws = self._ws
        if ws is not None and not ws.closed:
            await ws.close()


class ConnectorManager:
    """Start and stop one Connector per paired device."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._connectors: dict[str, XiaolingConnector] = {}

    def start_device(self, device: Mapping[str, Any]) -> XiaolingConnector:
        """Start a Connector for a paired device if it is not already running."""
        device_id = str(device[CONF_DEVICE_ID])
        existing = self._connectors.get(device_id)
        if existing is not None:
            return existing

        def _store_manifest(version: int) -> None:
            self._store_manifest_version(device_id, version)

        connector = XiaolingConnector(
            self._hass,
            device,
            on_manifest_version=_store_manifest,
        )
        self._connectors[device_id] = connector
        connector.start()
        return connector

    async def async_stop_device(self, device_id: str) -> None:
        """Stop the Connector for one device."""
        connector = self._connectors.pop(device_id, None)
        if connector is not None:
            await connector.async_stop()

    async def async_stop_all(self) -> None:
        """Stop every Connector."""
        connectors = list(self._connectors.values())
        self._connectors.clear()
        for connector in connectors:
            await connector.async_stop()

    def _store_manifest_version(self, device_id: str, version: int) -> None:
        """Persist the latest server_sync version for reconnects."""
        entry = self._hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return
        devices = []
        for item in entry.data.get(CONF_DEVICES, []):
            if item.get(CONF_DEVICE_ID) == device_id:
                devices.append({**item, CONF_MANIFEST_VERSION: version})
            else:
                devices.append(item)
        self._hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_DEVICES: devices},
        )


def _ws_base(http_base: str) -> str:
    """Convert an HTTPS API host to a WebSocket URL."""
    if http_base.startswith("https://"):
        return f"wss://{http_base[8:]}"
    if http_base.startswith("http://"):
        return f"ws://{http_base[7:]}"
    return http_base


def _deadline_timeout(deadline_at: Any) -> float:
    """Convert an ISO deadline into a remaining timeout."""
    if isinstance(deadline_at, str) and deadline_at:
        try:
            deadline = datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
            remaining = (deadline - datetime.now(UTC)).total_seconds()
            if remaining > 0:
                return min(remaining, DEFAULT_CALL_TIMEOUT)
        except ValueError:
            pass
    return DEFAULT_CALL_TIMEOUT


def _as_mcp_result(result: Any) -> dict[str, Any]:
    """Wrap a Home Assistant tool response as Connector call_result content."""
    if isinstance(result, dict) and "content" in result:
        return result
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}]}
