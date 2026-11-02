"""End-to-end test of the integration against the fake device, without mocks."""

from collections.abc import AsyncGenerator

import aiocoap
import pytest

from custom_components.catanio.api import DEFAULT_PORT
from custom_components.catanio.const import DOMAIN
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .fake_device import FakeCatanDevice


@pytest.fixture
async def device_on_default_port() -> AsyncGenerator[FakeCatanDevice]:
    """Run the fake device on the default CoAP port of localhost."""
    device = FakeCatanDevice()
    server = await aiocoap.Context.create_server_context(
        device.site, bind=("127.0.0.1", DEFAULT_PORT)
    )
    yield device
    await server.shutdown()


async def test_setup_through_config_flow(
    hass: HomeAssistant, device_on_default_port: FakeCatanDevice
) -> None:
    """Test adding the device manually and controlling an output."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    # The discovery is mocked in all tests, so the manual entry is shown.
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "CATAN C1"
    await hass.async_block_till_done()

    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == "1234567890"

    # Only UI 1 and UOI 13 exist on the fake device, the device name is read
    # from the system configuration.
    temperature = hass.states.get("sensor.boiler_room_outdoor")
    assert temperature.state == "21.3"
    assert temperature.attributes["unit_of_measurement"] == "°C"
    assert hass.states.get("number.boiler_room_uoi_13").state == "2.5"
    assert hass.states.get("sensor.boiler_room_points_in_failure").state == "2"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.boiler_room_uoi_13", ATTR_VALUE: 6.25},
        blocking=True,
    )
    assert hass.states.get("number.boiler_room_uoi_13").state == "6.25"
    method, path, request = device_on_default_port.requests[-1]
    assert (method, path) == ("PATCH", "uoi/13")
    assert request.analog_set_val.val == 6.25

    assert await hass.config_entries.async_unload(entry.entry_id)
