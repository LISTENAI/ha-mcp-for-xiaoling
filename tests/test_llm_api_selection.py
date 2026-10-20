"""Tests for selecting LLM APIs exposed by a Xiaoling Connector."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.helpers import llm

from custom_components.xiaoling_mcp.const import (
    CONF_API_TOKEN,
    CONF_BINDING_ID,
    CONF_CONNECTOR_ID,
    CONF_DEVICE_ID,
    DOMAIN,
)
from custom_components.xiaoling_mcp.connector import XiaolingConnector
from custom_components.xiaoling_mcp.ha_mcp import (
    async_build_server,
    async_call_tool,
    async_get_llm_api,
)


class LlmApiSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_api_lookup_uses_selected_ids(self) -> None:
        hass = object()
        selected_api_ids = ["assist", "llm_hass_api"]
        api_instance = object()

        with patch(
            "custom_components.xiaoling_mcp.ha_mcp.llm.async_get_api",
            new=AsyncMock(return_value=api_instance),
        ) as get_api:
            result = await async_get_llm_api(hass, selected_api_ids)

        self.assertIs(result, api_instance)
        args = get_api.await_args.args
        self.assertIs(args[0], hass)
        self.assertEqual(args[1], selected_api_ids)
        self.assertEqual(args[2].platform, DOMAIN)

    async def test_server_manifest_uses_selected_api_ids(self) -> None:
        hass = object()
        selected_api_ids = ["assist", "llm_hass_api"]
        api_instance = SimpleNamespace(tools=[], custom_serializer=None)

        with patch(
            "custom_components.xiaoling_mcp.ha_mcp.async_get_llm_api",
            new=AsyncMock(return_value=api_instance),
        ) as get_api:
            server = await async_build_server(hass, selected_api_ids)

        get_api.assert_awaited_once_with(hass, selected_api_ids)
        self.assertEqual(server["status"], "READY")
        self.assertEqual(server["tools"], [])

    async def test_tool_call_uses_selected_api_ids(self) -> None:
        hass = object()
        selected_api_ids = ["assist", "llm_hass_api"]
        api_instance = SimpleNamespace(async_call_tool=AsyncMock(return_value="ok"))

        with patch(
            "custom_components.xiaoling_mcp.ha_mcp.async_get_llm_api",
            new=AsyncMock(return_value=api_instance),
        ) as get_api:
            result = await async_call_tool(
                hass,
                selected_api_ids,
                "ExampleTool",
                {"value": 1},
            )

        get_api.assert_awaited_once_with(hass, selected_api_ids)
        tool_input = api_instance.async_call_tool.await_args.args[0]
        self.assertIsInstance(tool_input, llm.ToolInput)
        self.assertEqual(tool_input.tool_name, "ExampleTool")
        self.assertEqual(tool_input.tool_args, {"value": 1})
        self.assertEqual(result, "ok")

    async def test_connector_uses_saved_selection_and_defaults_existing_devices(self) -> None:
        device = {
            CONF_DEVICE_ID: "device-001",
            CONF_API_TOKEN: "token",
            CONF_BINDING_ID: "binding",
            CONF_CONNECTOR_ID: "connector",
        }
        connector = XiaolingConnector(MagicMock(), device)
        self.assertEqual(connector._llm_api_ids, [llm.LLM_API_ASSIST])

        device["llm_hass_api"] = ["assist", "llm_hass_api"]
        connector = XiaolingConnector(MagicMock(), device)
        self.assertEqual(connector._llm_api_ids, ["assist", "llm_hass_api"])


if __name__ == "__main__":
    unittest.main()
