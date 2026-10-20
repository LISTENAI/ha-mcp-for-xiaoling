"""Tests for synchronizing HA device names to Xiaoling."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.xiaoling_mcp import _device_registry_updated
from custom_components.xiaoling_mcp.const import (
    CONF_API_TOKEN,
    CONF_CONNECTOR_ID,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    DOMAIN,
)


class DeviceNameSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_rename_updates_cloud_connector_name(self) -> None:
        await self._assert_name_synced(
            name_by_user="Living room HA",
            default_name="Original name",
            expected_name="Living room HA",
        )

    async def test_clearing_user_name_restores_default_cloud_name(self) -> None:
        await self._assert_name_synced(
            name_by_user=None,
            default_name="Original name",
            expected_name="Original name",
        )

    async def _assert_name_synced(
        self,
        *,
        name_by_user: str | None,
        default_name: str,
        expected_name: str,
    ) -> None:
        tasks: list[asyncio.Task[None]] = []
        api = MagicMock()
        api.async_update_connector_name = AsyncMock()
        device_id = "device-001"
        entry_id = "entry-001"
        device_entry = SimpleNamespace(
            config_entries={entry_id},
            identifiers={(DOMAIN, device_id)},
            disabled=False,
            name_by_user=name_by_user,
            name=default_name,
        )
        registry = MagicMock()
        registry.async_get.return_value = device_entry

        def create_task(coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task

        hass = SimpleNamespace(
            async_create_task=create_task,
        )
        device = {
            CONF_DEVICE_ID: device_id,
            CONF_API_TOKEN: "connector-token",
            CONF_CONNECTOR_ID: "connector-001",
        }
        entry = SimpleNamespace(
            hass=hass,
            entry_id=entry_id,
            runtime_data=SimpleNamespace(start_device=MagicMock()),
            data={CONF_DEVICES: [device]},
        )
        event = SimpleNamespace(
            data={
                "action": "update",
                "device_id": "registry-device-001",
                "changes": {"name_by_user": "Previous name"},
            }
        )

        with (
            patch("custom_components.xiaoling_mcp.dr.async_get", return_value=registry),
            patch(
                "custom_components.xiaoling_mcp.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.xiaoling_mcp.XiaolingMcpApi", return_value=api),
        ):
            _device_registry_updated(hass, entry)(event)
            await asyncio.gather(*tasks)

        api.async_update_connector_name.assert_awaited_once_with(
            "connector-token",
            "connector-001",
            expected_name,
        )


if __name__ == "__main__":
    unittest.main()
