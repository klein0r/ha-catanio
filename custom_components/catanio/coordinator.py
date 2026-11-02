"""Data update coordinator for CatanIO devices."""

from collections.abc import Awaitable
from dataclasses import dataclass, replace
import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CatanIOClient,
    CatanIOConnectionError,
    CatanIOError,
    Channel,
    ChannelConfig,
    ChannelState,
    DeviceIdentity,
    ModuleType,
    SystemStatus,
    find_module_type,
)
from .const import DOMAIN, MANUFACTURER, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type CatanIOConfigEntry = ConfigEntry[CatanIOCoordinator]


@dataclass(frozen=True, slots=True)
class CatanIOData:
    """Runtime data of a CatanIO device."""

    status: SystemStatus
    channels: dict[Channel, ChannelState]


class CatanIOCoordinator(DataUpdateCoordinator[CatanIOData]):
    """Poll the system status and all enabled channels of a device."""

    config_entry: CatanIOConfigEntry
    identity: DeviceIdentity
    module_type: ModuleType
    channel_configs: dict[Channel, ChannelConfig]
    device_info: DeviceInfo

    def __init__(
        self, hass: HomeAssistant, entry: CatanIOConfigEntry, client: CatanIOClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self._reload_scheduled = False

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the device."""
        assert self.config_entry.unique_id is not None
        return self.config_entry.unique_id

    @override
    async def _async_setup(self) -> None:
        """Read identity, firmware and channel configuration once."""
        try:
            identity = await self.client.get_identity()
            if identity.unique_id != self.config_entry.unique_id:
                # DHCP may have assigned the address to another module, the
                # discovery updates the host once the device shows up again.
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="unexpected_device",
                    translation_placeholders={"host": self.client.host},
                )
            module_type = find_module_type(identity.model_number, identity.model_name)
            if module_type is None:
                raise ConfigEntryError(
                    translation_domain=DOMAIN,
                    translation_key="unsupported_model",
                    translation_placeholders={
                        "model": identity.model_name or identity.model_number
                    },
                )
            firmware_version = await self._async_get_optional(
                self.client.get_firmware_version()
            )
            name = await self._async_get_optional(self.client.get_name())
            channel_configs: dict[Channel, ChannelConfig] = {}
            for channel in module_type.channels:
                if config := await self._async_get_optional(
                    self.client.get_channel_config(channel)
                ):
                    channel_configs[channel] = config
        except CatanIOError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"host": self.client.host, "error": str(err)},
            ) from err

        self.identity = identity
        self.module_type = module_type
        self.channel_configs = channel_configs
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            connections=(
                {(CONNECTION_NETWORK_MAC, identity.mac_address)}
                if identity.mac_address
                else set()
            ),
            manufacturer=MANUFACTURER,
            model=module_type.name,
            model_id=module_type.article_number,
            name=name or module_type.name,
            serial_number=identity.serial_number or None,
            sw_version=firmware_version,
            hw_version=(
                str(identity.hardware_revision) if identity.hardware_revision else None
            ),
        )

    async def _async_get_optional[T](self, request: Awaitable[T]) -> T | None:
        """Return the result of a request the device may not support."""
        try:
            return await request
        except CatanIOConnectionError:
            raise
        except CatanIOError as err:
            _LOGGER.debug("Optional request to %s failed: %s", self.client.host, err)
            return None

    @override
    async def _async_update_data(self) -> CatanIOData:
        """Fetch the system status and the runtime values of all channels."""
        try:
            status = await self.client.get_status()
            channels: dict[Channel, ChannelState] = {}
            for channel, config in self.channel_configs.items():
                if not config.enabled:
                    continue
                if state := await self._async_get_optional(
                    self.client.get_channel_state(channel)
                ):
                    channels[channel] = state
        except CatanIOError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"host": self.client.host, "error": str(err)},
            ) from err
        self._async_check_modes(channels)
        return CatanIOData(status=status, channels=channels)

    @callback
    def _async_check_modes(self, channels: dict[Channel, ChannelState]) -> None:
        """Reload the entry when a channel was switched to another mode."""
        if self._reload_scheduled:
            return
        for channel, state in channels.items():
            if state.mode is None or state.mode is self.channel_configs[channel].mode:
                continue
            _LOGGER.info(
                "%s of %s changed from %s to %s, reloading",
                channel.label,
                self.client.host,
                self.channel_configs[channel].mode,
                state.mode,
            )
            self._reload_scheduled = True
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            return

    @callback
    def async_set_channel_state(self, channel: Channel, state: ChannelState) -> None:
        """Store the state returned by a write request."""
        self.async_set_updated_data(
            replace(self.data, channels={**self.data.channels, channel: state})
        )
