"""Fixtures for the CatanIO tests."""

from collections.abc import Generator
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.catanio import PLATFORMS
from custom_components.catanio.api import Channel
from custom_components.catanio.const import DOMAIN
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .const import HOST, IDENTITY, SERIAL, STATUS, c1_configs, c1_states


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable the custom integration in all tests."""


@pytest.fixture(autouse=True)
def mock_coap_context() -> Generator[MagicMock]:
    """Prevent the integration from opening CoAP sockets."""
    context = MagicMock()
    context.shutdown = AsyncMock()
    with patch(
        "custom_components.catanio.coap.aiocoap.Context.create_client_context",
        AsyncMock(return_value=context),
    ):
        yield context


@pytest.fixture(autouse=True)
def mock_discover_devices() -> Generator[AsyncMock]:
    """Disable the discovery of the integration and the config flow."""
    mock = AsyncMock(return_value=[])
    with (
        patch("custom_components.catanio.discovery.async_discover_devices", mock),
        patch("custom_components.catanio.config_flow.async_discover_devices", mock),
    ):
        yield mock


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable all entities, including the ones disabled by default."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the config entry of a Catan C1."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="CATAN C1",
        unique_id=SERIAL,
        data={CONF_HOST: HOST},
    )


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Return a client emulating the I/O of a Catan C1."""
    configs = c1_configs()
    states = c1_states()

    def set_digital(channel: Channel, value: bool):
        states[channel] = replace(
            states[channel],
            digital_set_value=value,
            digital_value=value != configs[channel].inverted,
        )
        return states[channel]

    def set_analog(channel: Channel, value: float):
        states[channel] = replace(
            states[channel], analog_set_value=value, analog_value=value
        )
        return states[channel]

    client = MagicMock()
    client.host = HOST
    client.configs = configs
    client.states = states
    client.get_identity = AsyncMock(return_value=IDENTITY)
    client.get_status = AsyncMock(return_value=STATUS)
    client.get_firmware_version = AsyncMock(return_value="1.2.3.4")
    client.get_name = AsyncMock(return_value="")
    client.get_channel_config = AsyncMock(side_effect=lambda channel: configs[channel])
    client.get_channel_state = AsyncMock(side_effect=lambda channel: states[channel])
    client.set_digital = AsyncMock(side_effect=set_digital)
    client.set_analog = AsyncMock(side_effect=set_analog)
    client.identify = AsyncMock()
    client.reboot = AsyncMock()
    with patch("custom_components.catanio.CatanIOClient", return_value=client):
        yield client


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to set up."""
    return PLATFORMS


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the integration for a Catan C1."""
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.catanio.PLATFORMS", platforms):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return mock_config_entry
