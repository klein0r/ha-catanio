"""Binary sensors for CatanIO devices."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ChannelMode, ChannelState, SystemStatus
from .coordinator import CatanIOConfigEntry, CatanIOCoordinator
from .entity import (
    CatanIOChannelEntity,
    CatanIOChannelEntityDescription,
    CatanIOEntity,
    async_remove_stale_entities,
    channel_entity_descriptions,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CatanIOChannelBinarySensorEntityDescription(
    BinarySensorEntityDescription, CatanIOChannelEntityDescription
):
    """Describes a binary sensor of a channel."""

    value_fn: Callable[[ChannelState], bool]


@dataclass(frozen=True, kw_only=True)
class CatanIOSystemBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a binary sensor of the system status."""

    value_fn: Callable[[SystemStatus], bool]


CHANNEL_BINARY_SENSORS: tuple[CatanIOChannelBinarySensorEntityDescription, ...] = (
    CatanIOChannelBinarySensorEntityDescription(
        key="input",
        translation_key="digital_input",
        modes=frozenset({ChannelMode.DIGITAL_INPUT}),
        value_fn=lambda state: state.digital_value,
    ),
)

SYSTEM_BINARY_SENSORS: tuple[CatanIOSystemBinarySensorEntityDescription, ...] = (
    CatanIOSystemBinarySensorEntityDescription(
        key="controller_connected",
        translation_key="controller_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.ctrl_connected,
    ),
    CatanIOSystemBinarySensorEntityDescription(
        key="controller_connection_failure",
        translation_key="controller_connection_failure",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.ctrl_connect_failure,
    ),
    CatanIOSystemBinarySensorEntityDescription(
        key="display_connected",
        translation_key="display_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.display_connected,
    ),
    CatanIOSystemBinarySensorEntityDescription(
        key="button",
        translation_key="button",
        entity_registry_enabled_default=False,
        value_fn=lambda status: status.button_pressed,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CatanIO binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        CatanIOSystemBinarySensor(coordinator, description)
        for description in SYSTEM_BINARY_SENSORS
    ]
    entities.extend(
        CatanIOChannelBinarySensor(coordinator, channel, description)
        for channel, description in channel_entity_descriptions(
            coordinator, CHANNEL_BINARY_SENSORS
        )
    )
    async_add_entities(entities)
    async_remove_stale_entities(hass, entry, Platform.BINARY_SENSOR, entities)


class CatanIOSystemBinarySensor(CatanIOEntity, BinarySensorEntity):
    """Binary sensor of the system status."""

    entity_description: CatanIOSystemBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: CatanIOCoordinator,
        description: CatanIOSystemBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @override
    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return self.entity_description.value_fn(self.coordinator.data.status)


class CatanIOChannelBinarySensor(CatanIOChannelEntity, BinarySensorEntity):
    """Binary sensor of a channel."""

    entity_description: CatanIOChannelBinarySensorEntityDescription

    @override
    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        if (state := self.channel_state) is None:
            return None
        return self.entity_description.value_fn(state)
