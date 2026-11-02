"""Selects for the configuration of CatanIO channels."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ChannelConfigUpdate, ChannelMode, Interface
from .coordinator import CatanIOConfigEntry
from .entity import (
    CatanIOChannelEntity,
    CatanIOChannelEntityDescription,
    async_remove_stale_entities,
    channel_entity_descriptions,
)

PARALLEL_UPDATES = 1

DOI_MODES = (
    ChannelMode.DIGITAL_OUTPUT,
    ChannelMode.DIGITAL_INPUT,
    ChannelMode.COUNTER,
)


@dataclass(frozen=True, kw_only=True)
class CatanIOSelectEntityDescription(
    SelectEntityDescription, CatanIOChannelEntityDescription
):
    """Describes a select of a channel."""


SELECTS: tuple[CatanIOSelectEntityDescription, ...] = (
    CatanIOSelectEntityDescription(
        key="mode",
        translation_key="mode",
        modes=frozenset({*DOI_MODES, ChannelMode.UNKNOWN}),
        interfaces=frozenset({Interface.DOI}),
        valid_statuses=None,
        entity_category=EntityCategory.CONFIG,
        # Switching a wired input to an output drives 24 V into the circuit,
        # so the select has to be enabled deliberately.
        entity_registry_enabled_default=False,
        options=[str(mode) for mode in DOI_MODES],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CatanIO selects."""
    coordinator = entry.runtime_data
    entities = [
        CatanIOModeSelect(coordinator, channel, description)
        for channel, description in channel_entity_descriptions(coordinator, SELECTS)
    ]
    async_add_entities(entities)
    async_remove_stale_entities(hass, entry, Platform.SELECT, entities)


class CatanIOModeSelect(CatanIOChannelEntity, SelectEntity):
    """Operating mode of a channel."""

    entity_description: CatanIOSelectEntityDescription

    @override
    @property
    def current_option(self) -> str | None:
        """Return the configured mode."""
        if (mode := self.channel_config.mode) in DOI_MODES:
            return str(mode)
        return None

    @override
    async def async_select_option(self, option: str) -> None:
        """Change the mode, the entry reloads to replace the entities."""
        await self._async_write_config(ChannelConfigUpdate(mode=ChannelMode(option)))
