"""Config flow for the CatanIO integration."""

import asyncio
import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)
from homeassistant.helpers.typing import DiscoveryInfoType

from .api import (
    CatanIOClient,
    CatanIOConnectionError,
    CatanIOError,
    CatanIOProtocolError,
    find_module_type,
)
from .coap import async_get_coap_context
from .const import DOMAIN
from .discovery import DiscoveredDevice, async_discover_devices

_LOGGER = logging.getLogger(__name__)

CONF_DEVICE = "device"
MANUAL_ENTRY = "manual"
PROBE_TIMEOUT = 5.0

HOST_SCHEMA = probatio.Schema({probatio.Required(CONF_HOST): TextSelector()})


class UnsupportedModelError(CatanIOError):
    """The device is a CatanIO device of an unsupported model."""


class CatanIOConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CatanIO devices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery_task: asyncio.Task[list[DiscoveredDevice]] | None = None
        self._discovered: dict[str, DiscoveredDevice] = {}
        self._device: DiscoveredDevice | None = None

    async def _async_probe(self, host: str) -> DiscoveredDevice:
        """Read the identity of the device at the given address."""
        client = CatanIOClient(
            host, await async_get_coap_context(self.hass), timeout=PROBE_TIMEOUT
        )
        identity = await client.get_identity()
        if identity.unique_id is None:
            raise CatanIOProtocolError("Device reported neither serial number nor MAC")
        module_type = find_module_type(identity.model_number, identity.model_name)
        if module_type is None:
            raise UnsupportedModelError(identity.model_name or identity.model_number)
        return DiscoveredDevice(
            host=host, unique_id=identity.unique_id, model=module_type.name
        )

    async def _async_validate_host(
        self, host: str
    ) -> tuple[DiscoveredDevice | None, dict[str, str]]:
        """Probe a host entered by the user and map failures to form errors."""
        try:
            device = await self._async_probe(host.strip())
        except CatanIOConnectionError:
            return None, {"base": "cannot_connect"}
        except UnsupportedModelError:
            return None, {"base": "unsupported_model"}
        except CatanIOError:
            return None, {"base": "not_catanio"}
        except Exception:
            _LOGGER.exception("Unexpected exception while probing %s", host)
            return None, {"base": "unknown"}
        return device, {}

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search the local bus of the Catan C1 for devices."""
        if self._discovery_task is None:
            self._discovery_task = self.hass.async_create_task(
                async_discover_devices(self.hass)
            )
            if self._discovery_task.done():
                return await self.async_step_pick_device()
        if not self._discovery_task.done():
            return self.async_show_progress(
                step_id="user",
                progress_action="discovering",
                progress_task=self._discovery_task,
            )
        return self.async_show_progress_done(next_step_id="pick_device")

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick one of the discovered devices."""
        if user_input is not None:
            if user_input[CONF_DEVICE] == MANUAL_ENTRY:
                return await self.async_step_manual()
            device = self._discovered[user_input[CONF_DEVICE]]
            await self.async_set_unique_id(device.unique_id, raise_on_progress=False)
            self._abort_if_unique_id_configured(updates={CONF_HOST: device.host})
            return self.async_create_entry(
                title=device.model, data={CONF_HOST: device.host}
            )

        assert self._discovery_task is not None
        configured = self._async_current_ids(include_ignore=False)
        self._discovered = {
            device.unique_id: device
            for device in self._discovery_task.result()
            if device.unique_id not in configured
        }
        if not self._discovered:
            return await self.async_step_manual()

        options = [
            SelectOptionDict(
                value=device.unique_id, label=f"{device.model} ({device.host})"
            )
            for device in self._discovered.values()
        ]
        options.append(SelectOptionDict(value=MANUAL_ENTRY, label=MANUAL_ENTRY))
        return self.async_show_form(
            step_id="pick_device",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_DEVICE): SelectSelector(
                        SelectSelectorConfig(
                            options=options, translation_key=CONF_DEVICE
                        )
                    )
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a device by its address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device, errors = await self._async_validate_host(user_input[CONF_HOST])
            if device is not None:
                await self.async_set_unique_id(
                    device.unique_id, raise_on_progress=False
                )
                self._abort_if_unique_id_configured(updates={CONF_HOST: device.host})
                return self.async_create_entry(
                    title=device.model, data={CONF_HOST: device.host}
                )
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(HOST_SCHEMA, user_input),
            errors=errors,
        )

    @override
    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle a device found by the discovery of the integration."""
        device = DiscoveredDevice.from_dict(discovery_info)
        await self.async_set_unique_id(device.unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: device.host})
        self._device = device
        self.context["title_placeholders"] = {"name": device.model, "host": device.host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup of a discovered device."""
        assert self._device is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._device.model, data={CONF_HOST: self._device.host}
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._device.model,
                "host": self._device.host,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of a configured device."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            device, errors = await self._async_validate_host(user_input[CONF_HOST])
            if device is not None:
                await self.async_set_unique_id(device.unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: device.host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                HOST_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )
