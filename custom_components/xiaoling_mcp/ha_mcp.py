"""Home Assistant LLM API helpers used by the Xiaoling Connector."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import probatio

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from .const import DOMAIN, INTEGRATION_VERSION, SERVER_NAME


def _format_tool(
    tool: llm.Tool,
    custom_serializer: Callable[[Any], Any] | None,
) -> dict[str, Any]:
    """Convert a Home Assistant LLM tool to a Connector tool."""
    try:
        input_schema = probatio.to_openapi(
            tool.parameters,
            custom_serializer=custom_serializer,
            openapi_version="3.1.0",
        )
    except (TypeError, ValueError, HomeAssistantError, probatio.SchemaError):
        input_schema = {"type": "object", "properties": {}}
    if not isinstance(input_schema, dict):
        input_schema = {"type": "object", "properties": {}}

    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    required = input_schema.get("required")
    if isinstance(required, list):
        schema["required"] = required

    return {
        "name": tool.name[:64],
        "description": (tool.description or "")[:2000],
        "inputSchema": schema,
    }


async def async_get_llm_api(
    hass: HomeAssistant,
    api_ids: list[str] | None = None,
) -> llm.APIInstance:
    """Return the selected Home Assistant LLM APIs as one API instance."""
    return await llm.async_get_api(
        hass,
        api_ids or llm.LLM_API_ASSIST,
        llm.LLMContext(
            platform=DOMAIN,
            context=Context(),
            language="*",
            assistant=conversation.DOMAIN,
            device_id=None,
        ),
    )


async def async_build_server(
    hass: HomeAssistant,
    api_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build the Home Assistant server manifest for server_sync."""
    try:
        llm_api = await async_get_llm_api(hass, api_ids)
        tools = [_format_tool(tool, llm_api.custom_serializer) for tool in llm_api.tools]
        status = "READY"
        description = "Home Assistant MCP Server"
    except HomeAssistantError:
        tools = []
        status = "ERROR"
        description = "Home Assistant MCP Server is unavailable"

    return {
        "name": SERVER_NAME,
        "version": INTEGRATION_VERSION,
        "capabilities": {"tools": {"listChanged": True}},
        "transport_type": "http",
        "description": description,
        "status": status,
        "tools": tools,
    }


async def async_call_tool(
    hass: HomeAssistant,
    api_ids: list[str] | None,
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> Any:
    """Call a tool from the selected Home Assistant LLM APIs."""
    llm_api = await async_get_llm_api(hass, api_ids)
    return await llm_api.async_call_tool(
        llm.ToolInput(tool_name=tool_name, tool_args=arguments or {})
    )
