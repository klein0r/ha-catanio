"""Base entities for the CatanIO integration."""

from collections.abc import Awaitable, Iterable
from dataclasses import dataclass
from typing import override

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    CatanIOError,
    Channel,
    ChannelConfig,
    ChannelConfigUpdate,
    ChannelMode,
    ChannelState,
    Interface,
    PointStatus,
)
from .const import DOMAIN
from .coordinator import CatanIOConfigEntry, CatanIOCoordinator

# Process values are only valid in these point states.
VALID_STATUSES = frozenset({PointStatus.OK, PointStatus.OVERRIDDEN})
# Outputs keep a meaningful value while a hardware failure is reported, so
# they stay controllable.
VALID_OUTPUT_STATUSES = VALID_STATUSES | {PointStatus.FAILURE}


@dataclass(frozen=True, kw_only=True)
class CatanIOChannelEntityDescription(EntityDescription):
    """Describes an entity of a channel."""

    modes: frozenset[ChannelMode]
    # None creates the entity for channels of every interface.
    interfaces: frozenset[Interface] | None = None
    # None makes the entity available in every point state.
    valid_statuses: frozenset[PointStatus] | None = VALID_STATUSES


class CatanIOEntity(CoordinatorEntity[CatanIOCoordinator]):
    """Base entity of a CatanIO device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CatanIOCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        self._attr_device_info = coordinator.device_info

    async def _async_call[T](self, request: Awaitable[T]) -> T:
        """Run a request triggered by the user."""
        try:
            return await request
        except CatanIOError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err


class CatanIOChannelEntity(CatanIOEntity):
    """Entity representing a value of a channel."""

    entity_description: CatanIOChannelEntityDescription

    def __init__(
        self,
        coordinator: CatanIOCoordinator,
        channel: Channel,
        description: CatanIOChannelEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, f"{channel.key}_{description.key}")
        self.entity_description = description
        self.channel = channel
        self._attr_translation_placeholders = {
            "channel": self.channel_config.display_name
        }
        if channel.interface is Interface.UV:
            # Virtual display data points are rarely used from Home Assistant.
            self._attr_entity_registry_enabled_default = False

    @property
    def channel_config(self) -> ChannelConfig:
        """Return the current configuration of the channel."""
        return self.coordinator.channel_configs[self.channel]

    @property
    def channel_state(self) -> ChannelState | None:
        """Return the latest runtime values of the channel."""
        return self.coordinator.data.channels.get(self.channel)

    @override
    @property
    def available(self) -> bool:
        """Return if the value of the channel is valid."""
        if not super().available or (state := self.channel_state) is None:
            return False
        valid_statuses = self.entity_description.valid_statuses
        return valid_statuses is None or state.status in valid_statuses

    async def _async_write_channel(self, request: Awaitable[ChannelState]) -> None:
        """Send a write request and store the returned state."""
        state = await self._async_call(request)
        self.coordinator.async_set_channel_state(self.channel, state)

    async def _async_write_config(self, update: ChannelConfigUpdate) -> None:
        """Change the configuration of the channel."""
        config = await self._async_call(
            self.coordinator.client.set_channel_config(self.channel, update)
        )
        await self.coordinator.async_apply_channel_config(config)


def channel_entity_descriptions[D: CatanIOChannelEntityDescription](
    coordinator: CatanIOCoordinator, descriptions: Iterable[D]
) -> list[tuple[Channel, D]]:
    """Return the descriptions applying to the enabled channels of a device."""
    return [
        (channel, description)
        for channel, config in coordinator.channel_configs.items()
        if config.enabled
        for description in descriptions
        if config.mode in description.modes
        and (
            description.interfaces is None
            or channel.interface in description.interfaces
        )
    ]


@callback
def async_remove_stale_entities(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    domain: str,
    entities: Iterable[Entity],
) -> None:
    """Remove entities of a platform the current channel configuration lacks.

    Channels can be disabled or switched to another mode, which replaces
    their entities.
    """
    unique_ids = {entity.unique_id for entity in entities}
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if entity_entry.domain == domain and entity_entry.unique_id not in unique_ids:
            entity_registry.async_remove(entity_entry.entity_id)
