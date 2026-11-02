"""Tests for the CatanIO sensors."""

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@pytest.fixture
def platforms() -> list[Platform]:
    """Only set up sensors."""
    return [Platform.SENSOR]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the sensors of a Catan C1."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


async def test_default_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test the primary values are enabled and diagnostics are not."""
    temperature = hass.states.get("sensor.catan_c1_outdoor_temperature")
    assert temperature.state == "21.5"
    assert temperature.attributes["device_class"] == "temperature"
    assert temperature.attributes["unit_of_measurement"] == "°C"

    meter = hass.states.get("sensor.catan_c1_heat_meter")
    assert meter.state == "12.5"
    assert meter.attributes["device_class"] == "energy"
    assert meter.attributes["state_class"] == "total_increasing"

    # The sensor of UI 6 is not connected, so the value is not valid.
    assert hass.states.get("sensor.catan_c1_ui_6").state == STATE_UNAVAILABLE

    for entity_id in (
        "sensor.catan_c1_outdoor_temperature_sensor_value",
        "sensor.catan_c1_outdoor_temperature_status",
        "sensor.catan_c1_outdoor_temperature_error",
        "sensor.catan_c1_ui_2_switching_cycles",
        "sensor.catan_c1_ui_2_on_time",
        "sensor.catan_c1_uv_1_status",
    ):
        entry = entity_registry.async_get(entity_id)
        assert entry, entity_id
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
