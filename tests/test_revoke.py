"""Tests for removing locally stored devices after remote revocation."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import WSMsgType

from custom_components.xiaoling_mcp import _async_remove_revoked_device
from custom_components.xiaoling_mcp.connector import ConnectorManager, XiaolingConnector
from custom_components.xiaoling_mcp.const import (
    CONF_API_TOKEN,
    CONF_CONNECTOR_ID,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    DOMAIN,
)


class RemoteRevokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_revoke_message_stops_connector_and_forgets_device(self) -> None:
        connector = object.__new__(XiaolingConnector)
        connector._device_id = "device-001"
        connector._connector_id = "connector-001"
        connector._max_frame_size = 655360
        connector._stop = asyncio.Event()
        connector._revoked = False
        connector._async_close_ws = AsyncMock()

        manager = object.__new__(ConnectorManager)
        manager._connectors = {connector._device_id: connector}
        manager._on_revoked = AsyncMock()
        connector._on_revoked = manager._async_handle_revoked

        await connector._async_handle_message(
            json.dumps({"type": "revoke", "payload": {"reason": "binding revoked"}})
        )

        self.assertTrue(connector._stop.is_set())
        connector._async_close_ws.assert_awaited_once_with()
        self.assertNotIn(connector._device_id, manager._connectors)
        manager._on_revoked.assert_awaited_once_with(connector._device_id)

    async def test_revoked_close_reason_removes_device(self) -> None:
        connector = object.__new__(XiaolingConnector)
        connector._device_id = "device-001"
        connector._connector_id = "connector-001"
        connector._session_id = None
        connector._stop = asyncio.Event()
        connector._revoked = False
        connector._async_close_ws = AsyncMock()

        manager = object.__new__(ConnectorManager)
        manager._connectors = {connector._device_id: connector}
        manager._on_revoked = AsyncMock()
        connector._on_revoked = manager._async_handle_revoked

        async def close_message():
            yield SimpleNamespace(
                type=WSMsgType.CLOSE,
                extra="BINDING_REVOKED",
            )

        await connector._async_listen(close_message())

        self.assertTrue(connector._stop.is_set())
        connector._async_close_ws.assert_awaited_once_with()
        self.assertNotIn(connector._device_id, manager._connectors)
        manager._on_revoked.assert_awaited_once_with(connector._device_id)

    async def test_remote_revoke_removes_entry_data_and_registry_device(self) -> None:
        entry_id = "entry-001"
        revoked_device = {
            CONF_DEVICE_ID: "device-001",
            CONF_API_TOKEN: "token-001",
            CONF_CONNECTOR_ID: "connector-001",
        }
        remaining_device = {
            CONF_DEVICE_ID: "device-002",
            CONF_API_TOKEN: "token-002",
            CONF_CONNECTOR_ID: "connector-002",
        }
        entry = SimpleNamespace(
            entry_id=entry_id,
            data={CONF_DEVICES: [revoked_device, remaining_device], "other": "kept"},
        )
        hass = SimpleNamespace(config_entries=MagicMock())
        device_entry = SimpleNamespace(id="registry-device-001", config_entries={entry_id})
        registry = MagicMock()
        registry.async_get_device.return_value = device_entry

        with patch("custom_components.xiaoling_mcp.dr.async_get", return_value=registry):
            await _async_remove_revoked_device(hass, entry, "device-001")

        hass.config_entries.async_update_entry.assert_called_once_with(
            entry,
            data={CONF_DEVICES: [remaining_device], "other": "kept"},
        )
        registry.async_remove_device.assert_called_once_with("registry-device-001")


if __name__ == "__main__":
    unittest.main()
