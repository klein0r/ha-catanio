"""Tests for the CatanIO numbers."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.catanio.api import CatanIOResponseError, Channel, Interface
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er


@pytest.fixture
def platforms() -> list[Platform]:
    """Only set up numbers."""
    return [Platform.NUMBER]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_numbers(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the numbers of a Catan C1."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_set_value(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test setting an analog output."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.catan_c1_uoi_13", ATTR_VALUE: 7.5},
        blocking=True,
    )
    mock_client.set_analog.assert_awaited_once_with(Channel(Interface.UOI, 13), 7.5)
    assert hass.states.get("number.catan_c1_uoi_13").state == "7.5"


@pytest.mark.usefixtures("init_integration")
async def test_set_value_failed(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test a rejected write request raises a translated error."""
    mock_client.set_analog.side_effect = CatanIOResponseError(
        "uoi/13", "4.00 Bad Request"
    )

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: "number.catan_c1_uoi_13", ATTR_VALUE: 7.5},
            blocking=True,
        )
    assert err.value.translation_key == "command_failed"
    assert hass.states.get("number.catan_c1_uoi_13").state == "5.0"
