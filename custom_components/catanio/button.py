"""Buttons for CatanIO devices."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CatanIOClient
from .const import IDENTIFY_DURATION_S
from .coordinator import CatanIOConfigEntry, CatanIOCoordinator
from .entity import CatanIOEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class CatanIOButtonEntityDescription(ButtonEntityDescription):
    """Describes a button of a device."""

    press_fn: Callable[[CatanIOClient], Awaitable[None]]


BUTTONS: tuple[CatanIOButtonEntityDescription, ...] = (
    CatanIOButtonEntityDescription(
        key="identify",
        device_class=ButtonDeviceClass.IDENTIFY,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda client: client.identify(IDENTIFY_DURATION_S),
    ),
    CatanIOButtonEntityDescription(
        key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda client: client.reboot(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CatanIO buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        CatanIOButton(coordinator, description) for description in BUTTONS
    )


class CatanIOButton(CatanIOEntity, ButtonEntity):
    """Button of a device."""

    entity_description: CatanIOButtonEntityDescription

    def __init__(
        self,
        coordinator: CatanIOCoordinator,
        description: CatanIOButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @override
    async def async_press(self) -> None:
        """Press the button."""
        await self._async_call(
            self.entity_description.press_fn(self.coordinator.client)
        )
