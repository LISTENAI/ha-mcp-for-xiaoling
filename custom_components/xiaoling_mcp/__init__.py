"""The Xiaoling MCP integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_TOKEN,
    CONF_BINDING_ID,
    CONF_CONNECTOR_ID,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    DOMAIN,
)
from .connector import ConnectorManager
from .device import register_device

_LOGGER = logging.getLogger(__name__)

_REQUIRED_DEVICE_KEYS = (
    CONF_DEVICE_ID,
    CONF_API_TOKEN,
    CONF_BINDING_ID,
    CONF_CONNECTOR_ID,
)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries that connected MCP before pairing."""
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            data={CONF_DEVICES: []},
            version=2,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up paired Xiaoling devices and their Connector sockets."""
    manager = ConnectorManager(hass, entry.entry_id)
    entry.runtime_data = manager

    for device in entry.data.get(CONF_DEVICES, []):
        if not all(device.get(key) for key in _REQUIRED_DEVICE_KEYS):
            _LOGGER.warning(
                "Skipping Xiaoling device without Connector credentials: %s",
                device.get(CONF_DEVICE_ID),
            )
            continue
        register_device(hass, entry, device)
        manager.start_device(device)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Disconnect every Xiaoling Connector."""
    manager: ConnectorManager | None = getattr(entry, "runtime_data", None)
    if manager is not None:
        await manager.async_stop_all()
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: Any,
) -> bool:
    """Remove one paired device and close its Connector."""
    device_id = next(
        (
            identifier
            for domain, identifier in device_entry.identifiers
            if domain == DOMAIN
        ),
        None,
    )
    if device_id is None:
        return False

    devices = list(config_entry.data.get(CONF_DEVICES, []))
    if not any(item.get(CONF_DEVICE_ID) == device_id for item in devices):
        return True

    manager: ConnectorManager | None = getattr(config_entry, "runtime_data", None)
    if manager is not None:
        await manager.async_stop_device(device_id)

    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            CONF_DEVICES: [
                item
                for item in devices
                if item.get(CONF_DEVICE_ID) != device_id
            ],
        },
    )
    return True
