"""Tests for the CatanIO switches."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.catanio.api import CatanIOConnectionError, Channel, Interface
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er


@pytest.fixture
def platforms() -> list[Platform]:
    """Only set up switches."""
    return [Platform.SWITCH]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_switches(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the switches of a Catan C1."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_turn_off_and_on(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test switching a digital output."""
    assert hass.states.get("switch.catan_c1_pump").state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.catan_c1_pump"},
        blocking=True,
    )
    mock_client.set_digital.assert_awaited_once_with(Channel(Interface.DOI, 9), False)
    assert hass.states.get("switch.catan_c1_pump").state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.catan_c1_pump"},
        blocking=True,
    )
    mock_client.set_digital.assert_awaited_with(Channel(Interface.DOI, 9), True)
    assert hass.states.get("switch.catan_c1_pump").state == STATE_ON


@pytest.mark.usefixtures("init_integration")
async def test_inverted_output(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test the state of an inverted output follows the value that was set."""
    # The physical output is off, the logical value is on.
    assert hass.states.get("switch.catan_c1_doi_12").state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.catan_c1_doi_12"},
        blocking=True,
    )
    assert mock_client.states[Channel(Interface.DOI, 12)].digital_value is True
    assert hass.states.get("switch.catan_c1_doi_12").state == STATE_OFF


@pytest.mark.usefixtures("init_integration")
async def test_command_failed(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test a failing write request raises a translated error."""
    mock_client.set_digital.side_effect = CatanIOConnectionError("timeout")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.catan_c1_pump"},
            blocking=True,
        )
    assert err.value.translation_key == "command_failed"
    assert hass.states.get("switch.catan_c1_pump").state == STATE_ON
