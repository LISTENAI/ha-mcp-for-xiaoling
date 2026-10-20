"""Tests for Xiaoling MCP HTTP requests."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from custom_components.xiaoling_mcp.api import ApiError, XiaolingMcpApi
from custom_components.xiaoling_mcp.const import (
    CONNECTORS_PATH,
    EXCHANGE_PATH,
    PROTOCOL_VERSION,
)


class XiaolingMcpApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_exchange_sends_saved_connector_instance_id(self) -> None:
        api = XiaolingMcpApi(AsyncMock())
        api._async_request = AsyncMock(
            return_value={
                "code": "SUCCESS",
                "data": {
                    "api_token": "token",
                    "binding_id": "binding",
                    "connector_id": "connector",
                    "device_id": "device",
                },
            }
        )
        connector_instance_id = "aa9aeeb5-43ea-4d70-8b62-5a32847306c2"

        await api.async_exchange("ABC123", connector_instance_id)

        api._async_request.assert_awaited_once_with(
            EXCHANGE_PATH,
            {
                "pairing_code": "ABC123",
                "connector_instance_id": connector_instance_id,
                "protocol_version": PROTOCOL_VERSION,
            },
        )

    async def test_update_connector_name_uses_authenticated_put(self) -> None:
        api = XiaolingMcpApi(AsyncMock())
        api._async_request = AsyncMock(return_value={"code": "SUCCESS"})

        await api.async_update_connector_name(
            "connector-token",
            "d0ea55bb-92ef-4eb4-a67e-602b777250b7",
            "客厅 Home Assistant",
        )

        api._async_request.assert_awaited_once_with(
            f"{CONNECTORS_PATH}/d0ea55bb-92ef-4eb4-a67e-602b777250b7",
            {
                "token": "connector-token",
                "connector_name": "客厅 Home Assistant",
                "protocol_version": PROTOCOL_VERSION,
            },
            method="PUT",
        )

    async def test_update_connector_name_rejects_invalid_length(self) -> None:
        api = XiaolingMcpApi(AsyncMock())
        api._async_request = AsyncMock()

        with self.assertRaisesRegex(ApiError, "1 and 24"):
            await api.async_update_connector_name("token", "connector-id", "x" * 25)

        api._async_request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
