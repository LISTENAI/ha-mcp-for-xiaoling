"""HTTP client for Xiaoling MCP Connector pairing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    CONNECTOR_TYPE,
    EXCHANGE_PATH,
    PROTOCOL_VERSION,
    USER_AGENT,
    XIAOLING_API_BASE,
)


class XiaolingMcpError(Exception):
    """Base exception for Xiaoling MCP errors."""


class CannotConnect(XiaolingMcpError):
    """The remote MCP service cannot be reached."""


class InvalidAuth(XiaolingMcpError):
    """The pairing code or authentication is invalid."""


class ConnectorLimit(XiaolingMcpError):
    """The device already has the maximum number of connectors."""


class ApiError(XiaolingMcpError):
    """The remote MCP service returned an invalid response."""


@dataclass(frozen=True, slots=True)
class PairingResult:
    """Data returned after a successful pairing code exchange."""

    device_id: str
    device_name: str
    api_token: str
    binding_id: str
    connector_id: str
    product_id: str


class XiaolingMcpApi:
    """Client for Xiaoling Connector HTTP APIs."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_exchange(self, pairing_code: str) -> PairingResult:
        """Exchange a pairing code for a Connector token."""
        payload = await self._async_request(
            EXCHANGE_PATH,
            {
                "pairing_code": pairing_code,
                "protocol_version": PROTOCOL_VERSION,
            },
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

        api_token = data.get("api_token")
        binding_id = data.get("binding_id")
        connector_id = data.get("connector_id")
        product_id = data.get("product_id")
        device_id = data.get("device_id")

        if not all(
            isinstance(value, str) and value
            for value in (api_token, binding_id, connector_id, device_id)
        ):
            raise ApiError("Exchange response is missing required Connector fields")

        if not isinstance(product_id, str):
            product_id = ""

        device_name = data.get("device_name") or data.get("name")
        if not isinstance(device_name, str) or not device_name:
            device_name = f"Xiaoling {device_id[:8]}"

        return PairingResult(
            device_id=device_id,
            device_name=device_name,
            api_token=api_token,
            binding_id=binding_id,
            connector_id=connector_id,
            product_id=product_id,
        )

    async def _async_request(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a pairing request to Xiaoling."""
        try:
            async with self._session.post(
                f"{XIAOLING_API_BASE}{path}",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                    "X-Connector-Type": CONNECTOR_TYPE,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                data = await _async_parse_json(response)
                code = data.get("code") if isinstance(data, dict) else None
                if response.status in (401, 403) or code == "MCP_PAIRING_EXPIRED":
                    raise InvalidAuth
                if response.status == 409 or code == "MCP_CONNECTOR_LIMIT":
                    raise ConnectorLimit
                if response.status >= 400:
                    raise ApiError(f"MCP service returned HTTP {response.status}")
                if isinstance(data, dict) and code not in (None, "SUCCESS"):
                    raise ApiError(f"MCP service returned {code}")
                if response.status == 204:
                    return {}
                if not isinstance(data, dict):
                    raise ApiError("MCP service returned a non-object response")
                return data
        except (InvalidAuth, ConnectorLimit, ApiError):
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise CannotConnect from err


async def _async_parse_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
    """Parse a JSON body, allowing empty responses."""
    if response.status == 204:
        return {}
    try:
        data = await response.json(content_type=None)
    except (TypeError, ValueError) as err:
        raise ApiError("MCP service returned invalid JSON") from err
    return data if isinstance(data, dict) else {}
