"""The Xiaoling MCP integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import (
    EVENT_DEVICE_REGISTRY_UPDATED,
    EventDeviceRegistryUpdatedData,
)

from .api import XiaolingMcpApi, XiaolingMcpError
from .const import (
    CONF_API_TOKEN,
    CONF_BINDING_ID,
    CONF_CONNECTOR_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    DOMAIN,
)
from .connector import ConnectorManager
from .device import device_identifier, register_device

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
    async def _async_remove_revoked(device_id: str) -> None:
        await _async_remove_revoked_device(hass, entry, device_id)

    manager = ConnectorManager(
        hass,
        entry.entry_id,
        on_revoked=_async_remove_revoked,
    )
    entry.runtime_data = manager
    registry = dr.async_get(hass)

    for device in entry.data.get(CONF_DEVICES, []):
        if not all(device.get(key) for key in _REQUIRED_DEVICE_KEYS):
            _LOGGER.warning(
                "Skipping Xiaoling device without Connector credentials: %s",
                device.get(CONF_DEVICE_ID),
            )
            continue
        register_device(hass, entry, device)
        if not _device_disabled(registry, device[CONF_DEVICE_ID]):
            manager.start_device(device)

    entry.async_on_unload(
        hass.bus.async_listen(
            EVENT_DEVICE_REGISTRY_UPDATED,
            _device_registry_updated(hass, entry),
        )
    )
    return True


async def _async_remove_revoked_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
) -> None:
    """Remove a remotely revoked device from entry data and the device registry."""
    devices = list(entry.data.get(CONF_DEVICES, []))
    remaining = [
        device
        for device in devices
        if device.get(CONF_DEVICE_ID) != device_id
    ]
    if len(remaining) != len(devices):
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_DEVICES: remaining},
        )

    registry = dr.async_get(hass)
    device_entry = registry.async_get_device(identifiers={(DOMAIN, device_id)})
    if device_entry is not None and entry.entry_id in device_entry.config_entries:
        registry.async_remove_device(device_entry.id)

    _LOGGER.warning(
        "Removed Xiaoling device %s after remote Connector revocation",
        device_id,
    )


def _device_registry_updated(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> callback:
    """Disconnect disabled devices and sync user-renamed device names."""

    @callback
    def _handle(event: Event[EventDeviceRegistryUpdatedData]) -> None:
        changes = event.data.get("changes", {})
        if event.data["action"] != "update" or not {
            "disabled_by",
            "name_by_user",
            "name",
        }.intersection(changes):
            return
        device_entry = dr.async_get(hass).async_get(event.data["device_id"])
        if device_entry is None or entry.entry_id not in device_entry.config_entries:
            return
        device_id = device_identifier(device_entry)
        if device_id is None:
            return

        manager: ConnectorManager | None = getattr(entry, "runtime_data", None)
        if manager is None:
            return
        device = next(
            (
                item
                for item in entry.data.get(CONF_DEVICES, [])
                if item.get(CONF_DEVICE_ID) == device_id
            ),
            None,
        )
        if device is None:
            return
        if "disabled_by" in changes:
            if device_entry.disabled:
                hass.async_create_task(manager.async_stop_device(device_id))
            else:
                manager.start_device(device)
        if {"name_by_user", "name"}.intersection(changes):
            hass.async_create_task(
                _async_update_connector_name(hass, device, device_entry)
            )

    return _handle


async def _async_update_connector_name(
    hass: HomeAssistant,
    device: dict[str, Any],
    device_entry: dr.DeviceEntry,
) -> None:
    """Sync the active Home Assistant display name to the cloud."""
    api_token = device.get(CONF_API_TOKEN)
    connector_id = device.get(CONF_CONNECTOR_ID)
    connector_name = (
        device_entry.name_by_user
        or device_entry.name
        or device.get(CONF_DEVICE_NAME)
    )
    if not all(
        isinstance(value, str) and value
        for value in (api_token, connector_id, connector_name)
    ):
        return

    try:
        await XiaolingMcpApi(async_get_clientsession(hass)).async_update_connector_name(
            api_token,
            connector_id,
            connector_name,
        )
    except XiaolingMcpError as err:
        _LOGGER.warning(
            "Failed to update Xiaoling Connector %s name: %s",
            connector_id,
            err,
        )
    else:
        _LOGGER.debug(
            "Updated Xiaoling Connector %s name to %s",
            connector_id,
            connector_name,
        )


def _device_disabled(registry: dr.DeviceRegistry, device_id: str) -> bool:
    """Return whether the registered Xiaoling device is disabled."""
    device_entry = registry.async_get_device(identifiers={(DOMAIN, device_id)})
    return device_entry is not None and device_entry.disabled


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
    device_id = device_identifier(device_entry)
    if device_id is None:
        return False

    devices = list(config_entry.data.get(CONF_DEVICES, []))
    device = next(
        (item for item in devices if item.get(CONF_DEVICE_ID) == device_id),
        None,
    )
    if device is None:
        return True

    api_token = device.get(CONF_API_TOKEN)
    connector_id = device.get(CONF_CONNECTOR_ID)
    if isinstance(api_token, str) and api_token and isinstance(connector_id, str) and connector_id:
        try:
            await XiaolingMcpApi(async_get_clientsession(hass)).async_revoke(
                api_token,
                connector_id,
            )
        except XiaolingMcpError as err:
            _LOGGER.warning(
                "Failed to revoke Xiaoling Connector %s; device removal continues: %s",
                connector_id,
                err,
            )

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
