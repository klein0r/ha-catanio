"""Tests for the CatanIO selects."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.catanio.api import (
    CatanIOResponseError,
    Channel,
    ChannelConfigUpdate,
    ChannelMode,
    Interface,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

DOI9 = Channel(Interface.DOI, 9)


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize("platforms", [[Platform.SELECT]])
async def test_selects(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the selects of a Catan C1."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


async def test_disabled_by_default(
    entity_registry: er.EntityRegistry, init_integration: MockConfigEntry
) -> None:
    """Test the mode has to be enabled before it can be changed."""
    entry = entity_registry.async_get("select.catan_c1_pump_mode")
    assert entry
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_change_mode(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test changing the mode replaces the entities of the channel."""
    assert hass.states.get("select.catan_c1_pump_mode").state == "digital_output"
    assert hass.states.get("switch.catan_c1_pump").state == STATE_ON
    assert hass.states.get("binary_sensor.catan_c1_pump") is None

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.catan_c1_pump_mode", ATTR_OPTION: "digital_input"},
        blocking=True,
    )
    await hass.async_block_till_done()

    mock_client.set_channel_config.assert_awaited_once_with(
        DOI9, ChannelConfigUpdate(mode=ChannelMode.DIGITAL_INPUT)
    )
    assert hass.states.get("select.catan_c1_pump_mode").state == "digital_input"
    assert hass.states.get("switch.catan_c1_pump") is None
    assert hass.states.get("binary_sensor.catan_c1_pump").state == STATE_ON


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_unknown_mode(
    hass: HomeAssistant, mock_client: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test a channel without a known mode can be configured."""
    mock_client.configs[DOI9] = replace(
        mock_client.configs[DOI9], mode=ChannelMode.UNKNOWN
    )
    mock_client.states[DOI9] = replace(mock_client.states[DOI9], mode=None)
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("select.catan_c1_pump_mode").state == STATE_UNKNOWN
    assert hass.states.get("switch.catan_c1_pump") is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_runtime_mode_is_used(
    hass: HomeAssistant, mock_client: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the mode reported at runtime wins over a default type."""
    mock_client.configs[DOI9] = replace(
        mock_client.configs[DOI9], mode=ChannelMode.UNKNOWN
    )
    await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get("select.catan_c1_pump_mode").state == "digital_output"
    assert hass.states.get("switch.catan_c1_pump").state == STATE_ON
    # No further reload is scheduled.
    assert mock_client.get_identity.await_count == 2


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_change_mode_failed(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test a rejected configuration raises a translated error."""
    mock_client.set_channel_config.side_effect = CatanIOResponseError(
        "doi/9/cfg", "4.00 Bad Request"
    )

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: "select.catan_c1_pump_mode", ATTR_OPTION: "counter"},
            blocking=True,
        )
    assert err.value.translation_key == "command_failed"
    assert hass.states.get("select.catan_c1_pump_mode").state == "digital_output"
