"""Device registry helpers for the Xiaoling MCP integration."""

from __future__ import annotations

from collections.abc import Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)


def device_identifier(device_entry: dr.DeviceEntry) -> str | None:
    """Return the Xiaoling device id stored on a registry device."""
    return next(
        (
            identifier
            for domain, identifier in device_entry.identifiers
            if domain == DOMAIN
        ),
        None,
    )


def register_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: Mapping[str, str],
) -> None:
    """Register one paired device in Home Assistant's device registry."""
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device[CONF_DEVICE_ID])},
        name=device[CONF_DEVICE_NAME],
        manufacturer=MANUFACTURER,
        model=MODEL,
    )
