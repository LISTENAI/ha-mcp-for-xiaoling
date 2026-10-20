"""Tests for Xiaoling Connector heartbeat handling."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from custom_components.xiaoling_mcp.connector import XiaolingConnector


class ConnectorHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    def _connector(self) -> XiaolingConnector:
        connector = object.__new__(XiaolingConnector)
        connector._stop = asyncio.Event()
        connector._heartbeat_seconds = 3600
        connector._heartbeat_ack_event = asyncio.Event()
        connector._heartbeat_waiting_for_ack = False
        connector._max_frame_size = 655360
        connector._frame_id = 0
        connector._connector_id = "connector-test"
        connector._async_send = AsyncMock()
        connector._async_close_ws = AsyncMock()
        return connector

    async def test_first_heartbeat_is_immediate(self) -> None:
        connector = self._connector()

        async def send_heartbeat(msg_type: str, payload: dict[str, object]) -> None:
            self.assertEqual(msg_type, "heartbeat")
            self.assertEqual(payload, {})
            await connector._async_handle_message(json.dumps({"type": "heartbeat_ack"}))
            connector._stop.set()

        connector._async_send.side_effect = send_heartbeat

        await asyncio.wait_for(connector._async_heartbeat(), timeout=1)

        connector._async_send.assert_awaited_once_with("heartbeat", {})
        connector._async_close_ws.assert_not_awaited()
        self.assertFalse(connector._heartbeat_waiting_for_ack)

    async def test_missing_ack_closes_connection(self) -> None:
        connector = self._connector()
        connector._heartbeat_seconds = 0.001

        with patch(
            "custom_components.xiaoling_mcp.connector.DEFAULT_HEARTBEAT_ACK_TIMEOUT_SECONDS",
            0.001,
        ):
            await connector._async_heartbeat()

        connector._async_send.assert_awaited_once_with("heartbeat", {})
        connector._async_close_ws.assert_awaited_once_with()
        self.assertFalse(connector._heartbeat_waiting_for_ack)


if __name__ == "__main__":
    unittest.main()
