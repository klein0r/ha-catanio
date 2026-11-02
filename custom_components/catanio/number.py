"""Numbers for the analog outputs of CatanIO devices."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import Platform, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Channel, ChannelMode
from .coordinator import CatanIOConfigEntry, CatanIOCoordinator
from .entity import (
    VALID_OUTPUT_STATUSES,
    CatanIOChannelEntity,
    CatanIOChannelEntityDescription,
    async_remove_stale_entities,
    channel_entity_descriptions,
)

PARALLEL_UPDATES = 1

# Range of the 0-10 V analog outputs when no limits are configured.
DEFAULT_MIN_VALUE = 0.0
DEFAULT_MAX_VALUE = 10.0


@dataclass(frozen=True, kw_only=True)
class CatanIONumberEntityDescription(
    NumberEntityDescription, CatanIOChannelEntityDescription
):
    """Describes a number of a channel."""


NUMBERS: tuple[CatanIONumberEntityDescription, ...] = (
    CatanIONumberEntityDescription(
        key="output",
        translation_key="analog_output",
        modes=frozenset({ChannelMode.ANALOG_OUTPUT}),
        valid_statuses=VALID_OUTPUT_STATUSES,
        native_step=0.01,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CatanIO numbers."""
    coordinator = entry.runtime_data
    entities = [
        CatanIONumber(coordinator, channel, description)
        for channel, description in channel_entity_descriptions(coordinator, NUMBERS)
    ]
    async_add_entities(entities)
    async_remove_stale_entities(hass, entry, Platform.NUMBER, entities)


class CatanIONumber(CatanIOChannelEntity, NumberEntity):
    """Analog output of a channel."""

    entity_description: CatanIONumberEntityDescription

    def __init__(
        self,
        coordinator: CatanIOCoordinator,
        channel: Channel,
        description: CatanIONumberEntityDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, channel, description)
        config = self.channel_config
        if config.minimum is not None and config.maximum is not None:
            self._attr_native_min_value = config.minimum
            self._attr_native_max_value = config.maximum
        else:
            self._attr_native_min_value = DEFAULT_MIN_VALUE
            self._attr_native_max_value = DEFAULT_MAX_VALUE
        unit = config.unit or UnitOfElectricPotential.VOLT
        self._attr_native_unit_of_measurement = unit
        if unit == UnitOfElectricPotential.VOLT:
            self._attr_device_class = NumberDeviceClass.VOLTAGE

    @override
    @property
    def native_value(self) -> float | None:
        """Return the logical output value including defaults and overrides."""
        if (state := self.channel_state) is None:
            return None
        return state.analog_value

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the output value."""
        await self._async_write_channel(
            self.coordinator.client.set_analog(self.channel, value)
        )
