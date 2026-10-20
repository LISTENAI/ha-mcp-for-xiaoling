"""Config flow for Xiaoling MCP."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import (
    ApiError,
    CannotConnect,
    ConnectorLimit,
    InvalidAuth,
    XiaolingMcpApi,
)
from .const import (
    CONF_API_TOKEN,
    CONF_BINDING_ID,
    CONF_CONNECTOR_ID,
    CONF_CONNECTOR_INSTANCE_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    CONF_MANIFEST_VERSION,
    CONF_PAIRING_CODE,
    CONF_PRODUCT_ID,
    DOMAIN,
)
from .connector import ConnectorManager
from .device import register_device

_LOGGER = logging.getLogger(__name__)


def _get_connector_instance_id(
    hass: Any,
    entry: config_entries.ConfigEntry,
) -> str:
    """Return and persist the integration-wide Connector instance ID."""
    connector_instance_id = entry.data.get(CONF_CONNECTOR_INSTANCE_ID)
    if isinstance(connector_instance_id, str) and connector_instance_id:
        return connector_instance_id

    connector_instance_id = str(uuid4())
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_CONNECTOR_INSTANCE_ID: connector_instance_id,
        },
    )
    return connector_instance_id


class XiaolingMcpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the integration setup and device pairing flow."""

    VERSION = 2

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Create the integration or open the add-device flow."""
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if entries:
            self._config_entry = entries[0]
            return await self.async_step_add_device(user_input)

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="小聆 MCP",
            data={CONF_DEVICES: []},
        )

    async def async_step_add_device(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Pair a device, then connect its selected MCP server APIs."""
        errors: dict[str, str] = {}
        entry = self._config_entry
        llm_apis = {api.id: api.name for api in llm.async_get_apis(self.hass)}
        default_api_ids = (
            [llm.LLM_API_ASSIST]
            if llm.LLM_API_ASSIST in llm_apis
            else list(llm_apis)[:1]
        )
        selected_api_ids_for_form = default_api_ids

        if user_input is not None:
            pairing_code = str(user_input.get(CONF_PAIRING_CODE, "")).strip()
            selected_api_ids = user_input.get(CONF_LLM_HASS_API, default_api_ids)
            if not isinstance(selected_api_ids, list):
                selected_api_ids = list(selected_api_ids) if isinstance(
                    selected_api_ids, tuple
                ) else []
            selected_api_ids = [
                api_id
                for api_id in selected_api_ids
                if isinstance(api_id, str) and api_id
            ]
            selected_api_ids_for_form = [
                api_id for api_id in selected_api_ids if api_id in llm_apis
            ] or default_api_ids
            if not pairing_code:
                errors["base"] = "invalid_pairing_code"
            elif not selected_api_ids:
                errors[CONF_LLM_HASS_API] = "llm_api_required"
            elif any(api_id not in llm_apis for api_id in selected_api_ids):
                errors[CONF_LLM_HASS_API] = "invalid_llm_api"
            else:
                api = XiaolingMcpApi(async_get_clientsession(self.hass))
                connector_instance_id = _get_connector_instance_id(self.hass, entry)
                try:
                    pairing = await api.async_exchange(
                        pairing_code,
                        connector_instance_id,
                    )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except ConnectorLimit:
                    errors["base"] = "connector_limit"
                except ApiError as err:
                    _LOGGER.warning("Xiaoling pairing failed: %s", err)
                    errors["base"] = "api_error"
                else:
                    devices = list(entry.data.get(CONF_DEVICES, []))
                    if any(
                        device.get(CONF_DEVICE_ID) == pairing.device_id
                        or device.get(CONF_CONNECTOR_ID) == pairing.connector_id
                        for device in devices
                    ):
                        errors["base"] = "already_configured"
                    else:
                        device = {
                            CONF_DEVICE_ID: pairing.device_id,
                            CONF_DEVICE_NAME: pairing.device_name,
                            CONF_API_TOKEN: pairing.api_token,
                            CONF_BINDING_ID: pairing.binding_id,
                            CONF_CONNECTOR_ID: pairing.connector_id,
                            CONF_PRODUCT_ID: pairing.product_id,
                            CONF_LLM_HASS_API: selected_api_ids,
                            CONF_MANIFEST_VERSION: 0,
                        }
                        devices.append(device)
                        self.hass.config_entries.async_update_entry(
                            entry,
                            data={
                                **entry.data,
                                CONF_DEVICES: devices,
                            },
                        )
                        register_device(self.hass, entry, device)
                        manager = getattr(entry, "runtime_data", None)
                        if isinstance(manager, ConnectorManager):
                            manager.start_device(device)
                        else:
                            self.hass.async_create_task(
                                self.hass.config_entries.async_reload(entry.entry_id)
                            )
                        return self.async_abort(reason="device_added")

        return self.async_show_form(
            step_id="add_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PAIRING_CODE): vol.All(
                        str,
                        vol.Length(min=1),
                    ),
                    vol.Optional(
                        CONF_LLM_HASS_API,
                        default=selected_api_ids_for_form,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(label=name, value=api_id)
                                for api_id, name in llm_apis.items()
                            ],
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=errors,
        )
