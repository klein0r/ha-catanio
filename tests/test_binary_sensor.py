"""Tests for the CatanIO binary sensors."""

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@pytest.fixture
def platforms() -> list[Platform]:
    """Only set up binary sensors."""
    return [Platform.BINARY_SENSOR]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_binary_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the binary sensors of a Catan C1."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


async def test_disabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test which binary sensors are disabled by default."""
    for entity_id in (
        "binary_sensor.catan_c1_display_connection",
        "binary_sensor.catan_c1_device_button",
    ):
        entry = entity_registry.async_get(entity_id)
        assert entry
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("binary_sensor.catan_c1_ui_2").state == "on"
