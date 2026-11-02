"""Tests for the CatanIO buttons."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.catanio.api import CatanIOConnectionError
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er


@pytest.fixture
def platforms() -> list[Platform]:
    """Only set up buttons."""
    return [Platform.BUTTON]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_buttons(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    init_integration: MockConfigEntry,
) -> None:
    """Test the buttons of a Catan C1."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_press(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test identifying and restarting the device."""
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.catan_c1_identify"},
        blocking=True,
    )
    mock_client.identify.assert_awaited_once_with(30)

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.catan_c1_restart"},
        blocking=True,
    )
    mock_client.reboot.assert_awaited_once_with()


@pytest.mark.usefixtures("init_integration")
async def test_press_failed(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test a failing request raises a translated error."""
    mock_client.identify.side_effect = CatanIOConnectionError("timeout")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.catan_c1_identify"},
            blocking=True,
        )
    assert err.value.translation_key == "command_failed"
