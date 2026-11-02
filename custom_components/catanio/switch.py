"""Switches for the digital outputs of CatanIO devices."""

from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ChannelMode
from .coordinator import CatanIOConfigEntry
from .entity import (
    VALID_OUTPUT_STATUSES,
    CatanIOChannelEntity,
    CatanIOChannelEntityDescription,
    async_remove_stale_entities,
    channel_entity_descriptions,
)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class CatanIOSwitchEntityDescription(
    SwitchEntityDescription, CatanIOChannelEntityDescription
):
    """Describes a switch of a channel."""


SWITCHES: tuple[CatanIOSwitchEntityDescription, ...] = (
    CatanIOSwitchEntityDescription(
        key="output",
        translation_key="digital_output",
        modes=frozenset({ChannelMode.DIGITAL_OUTPUT}),
        valid_statuses=VALID_OUTPUT_STATUSES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CatanIO switches."""
    coordinator = entry.runtime_data
    entities = [
        CatanIOSwitch(coordinator, channel, description)
        for channel, description in channel_entity_descriptions(coordinator, SWITCHES)
    ]
    async_add_entities(entities)
    async_remove_stale_entities(hass, entry, Platform.SWITCH, entities)


class CatanIOSwitch(CatanIOChannelEntity, SwitchEntity):
    """Digital output of a channel."""

    entity_description: CatanIOSwitchEntityDescription

    @override
    @property
    def is_on(self) -> bool | None:
        """Return the logical value of the output.

        The device reports the output after inversion, so undo the inversion
        to match the value that was set. Defaults and overrides are included.
        """
        if (state := self.channel_state) is None:
            return None
        return state.digital_value != self.channel_config.inverted

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the output on."""
        await self._async_write_channel(
            self.coordinator.client.set_digital(self.channel, True)
        )

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the output off."""
        await self._async_write_channel(
            self.coordinator.client.set_digital(self.channel, False)
        )
