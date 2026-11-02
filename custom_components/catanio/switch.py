"""Switches for the digital outputs and channel settings of CatanIO devices."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ChannelConfig, ChannelConfigUpdate, ChannelMode, Interface, PointStatus
from .coordinator import CatanIOConfigEntry
from .entity import (
    VALID_OUTPUT_STATUSES,
    CatanIOChannelEntity,
    CatanIOChannelEntityDescription,
    async_remove_stale_entities,
    channel_entity_descriptions,
)

PARALLEL_UPDATES = 1

CONFIGURABLE_INTERFACES = frozenset({Interface.DOI})
DIGITAL_MODES = frozenset({ChannelMode.DIGITAL_INPUT, ChannelMode.DIGITAL_OUTPUT})


@dataclass(frozen=True, kw_only=True)
class CatanIOSwitchEntityDescription(
    SwitchEntityDescription, CatanIOChannelEntityDescription
):
    """Describes a switch of a channel."""


@dataclass(frozen=True, kw_only=True)
class CatanIOConfigSwitchEntityDescription(
    SwitchEntityDescription, CatanIOChannelEntityDescription
):
    """Describes a switch changing a setting of a channel."""

    interfaces: frozenset[Interface] | None = CONFIGURABLE_INTERFACES
    valid_statuses: frozenset[PointStatus] | None = None
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    value_fn: Callable[[ChannelConfig], bool]
    update_fn: Callable[[bool], ChannelConfigUpdate]


SWITCHES: tuple[CatanIOSwitchEntityDescription, ...] = (
    CatanIOSwitchEntityDescription(
        key="output",
        translation_key="digital_output",
        modes=frozenset({ChannelMode.DIGITAL_OUTPUT}),
        valid_statuses=VALID_OUTPUT_STATUSES,
    ),
)

CONFIG_SWITCHES: tuple[CatanIOConfigSwitchEntityDescription, ...] = (
    CatanIOConfigSwitchEntityDescription(
        key="inverted",
        translation_key="inverted",
        modes=DIGITAL_MODES,
        value_fn=lambda config: config.inverted,
        update_fn=lambda value: ChannelConfigUpdate(inverted=value),
    ),
    CatanIOConfigSwitchEntityDescription(
        key="debounced",
        translation_key="debounced",
        modes=frozenset({ChannelMode.DIGITAL_INPUT}),
        value_fn=lambda config: config.debounced,
        update_fn=lambda value: ChannelConfigUpdate(debounced=value),
    ),
    CatanIOConfigSwitchEntityDescription(
        key="digital_default",
        translation_key="digital_default",
        modes=frozenset({ChannelMode.DIGITAL_OUTPUT}),
        value_fn=lambda config: config.digital_default,
        update_fn=lambda value: ChannelConfigUpdate(digital_default=value),
    ),
    CatanIOConfigSwitchEntityDescription(
        key="default_on_start",
        translation_key="default_on_start",
        modes=frozenset({ChannelMode.DIGITAL_OUTPUT}),
        value_fn=lambda config: config.default_on_start,
        update_fn=lambda value: ChannelConfigUpdate(default_on_start=value),
    ),
    CatanIOConfigSwitchEntityDescription(
        key="default_on_failure",
        translation_key="default_on_failure",
        modes=frozenset({ChannelMode.DIGITAL_OUTPUT}),
        value_fn=lambda config: config.default_on_failure,
        update_fn=lambda value: ChannelConfigUpdate(default_on_failure=value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CatanIO switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        CatanIOSwitch(coordinator, channel, description)
        for channel, description in channel_entity_descriptions(coordinator, SWITCHES)
    ]
    entities.extend(
        CatanIOConfigSwitch(coordinator, channel, description)
        for channel, description in channel_entity_descriptions(
            coordinator, CONFIG_SWITCHES
        )
    )
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


class CatanIOConfigSwitch(CatanIOChannelEntity, SwitchEntity):
    """Setting of a channel."""

    entity_description: CatanIOConfigSwitchEntityDescription

    @override
    @property
    def is_on(self) -> bool:
        """Return the configured value."""
        return self.entity_description.value_fn(self.channel_config)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the setting."""
        await self._async_write_config(self.entity_description.update_fn(True))

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the setting."""
        await self._async_write_config(self.entity_description.update_fn(False))
