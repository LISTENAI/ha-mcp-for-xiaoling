"""Tests for persistent Connector instance identity."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from custom_components.xiaoling_mcp.config_flow import _get_connector_instance_id
from custom_components.xiaoling_mcp.const import (
    CONF_CONNECTOR_INSTANCE_ID,
    CONF_DEVICES,
)


class ConnectorInstanceIdTests(unittest.TestCase):
    def test_generates_once_and_reuses_saved_id(self) -> None:
        hass = SimpleNamespace(config_entries=MagicMock())
        entry = SimpleNamespace(data={CONF_DEVICES: []})
        connector_instance_id = UUID("aa9aeeb5-43ea-4d70-8b62-5a32847306c2")

        with patch(
            "custom_components.xiaoling_mcp.config_flow.uuid4",
            return_value=connector_instance_id,
        ) as generate_id:
            result = _get_connector_instance_id(hass, entry)

        self.assertEqual(result, str(connector_instance_id))
        generate_id.assert_called_once_with()
        hass.config_entries.async_update_entry.assert_called_once_with(
            entry,
            data={
                CONF_DEVICES: [],
                CONF_CONNECTOR_INSTANCE_ID: str(connector_instance_id),
            },
        )

        entry.data = {
            CONF_DEVICES: [],
            CONF_CONNECTOR_INSTANCE_ID: result,
        }
        hass.config_entries.reset_mock()
        with patch("custom_components.xiaoling_mcp.config_flow.uuid4") as generate_id:
            self.assertEqual(_get_connector_instance_id(hass, entry), result)

        generate_id.assert_not_called()
        hass.config_entries.async_update_entry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
