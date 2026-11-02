"""Tests for the setup of the CatanIO integration."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.catanio.api import (
    CatanIOConnectionError,
    CatanIOResponseError,
    Channel,
    ChannelMode,
    Interface,
    UiType,
)
from custom_components.catanio.const import DISCOVERY_INTERVAL, DOMAIN, SCAN_INTERVAL
from custom_components.catanio.discovery import DiscoveredDevice
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_INTEGRATION_DISCOVERY,
    ConfigEntryState,
)
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import HOST, IDENTITY, SERIAL


async def test_setup_and_unload(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test setting up and unloading a config entry."""
    assert init_integration.state is ConfigEntryState.LOADED

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, SERIAL), init_integration.entry_id
    )
    assert device
    assert device.name == "CATAN C1"
    assert device.manufacturer == "Phoenix Contact"
    assert device.model == "CATAN C1"
    assert device.model_id == "1886438"
    assert device.serial_number == SERIAL
    assert device.sw_version == "1.2.3.4"
    assert device.hw_version == "2"
    assert device.connections == {(dr.CONNECTION_NETWORK_MAC, "00:a0:45:12:34:56")}

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_device_name(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Test the name configured on the device is used."""
    mock_client.get_name.return_value = "Boiler room"
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, SERIAL), mock_config_entry.entry_id
    )
    assert device
    assert device.name == "Boiler room"


@pytest.mark.parametrize(
    ("method", "side_effect", "state"),
    [
        (
            "get_identity",
            CatanIOConnectionError("timeout"),
            ConfigEntryState.SETUP_RETRY,
        ),
        (
            "get_identity",
            [replace(IDENTITY, serial_number="other")],
            ConfigEntryState.SETUP_RETRY,
        ),
        (
            "get_identity",
            [replace(IDENTITY, model_number="1", model_name="Unknown")],
            ConfigEntryState.SETUP_ERROR,
        ),
        (
            "get_firmware_version",
            CatanIOConnectionError("timeout"),
            ConfigEntryState.SETUP_RETRY,
        ),
        ("get_status", CatanIOConnectionError("timeout"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    method: str,
    side_effect: Exception | list[object],
    state: ConfigEntryState,
) -> None:
    """Test the setup fails when the device cannot be identified or reached."""
    getattr(mock_client, method).side_effect = side_effect
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is state


async def test_unsupported_requests(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Test requests the device rejects do not prevent the setup."""
    configs = mock_client.configs

    async def get_channel_config(channel: Channel):
        if channel.interface is Interface.UV:
            raise CatanIOResponseError(channel.path, "4.04 Not Found")
        return configs[channel]

    mock_client.get_firmware_version.side_effect = CatanIOResponseError(
        "sys", "4.05 Method Not Allowed"
    )
    mock_client.get_name.side_effect = CatanIOResponseError("sys/cfg", "4.04 Not Found")
    mock_client.get_channel_config.side_effect = get_channel_config
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, SERIAL), mock_config_entry.entry_id
    )
    assert device
    assert device.sw_version is None
    assert hass.states.get("switch.catan_c1_uv_2") is None


async def test_update_failed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test entities become unavailable while the device cannot be reached."""
    mock_client.get_status.side_effect = CatanIOConnectionError("timeout")
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("switch.catan_c1_pump").state == STATE_UNAVAILABLE

    mock_client.get_status.side_effect = None
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("switch.catan_c1_pump").state == STATE_ON


async def test_channel_read_failed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_client: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test a channel the device does not answer for becomes unavailable."""
    states = mock_client.states

    async def get_channel_state(channel: Channel):
        if channel == Channel(Interface.DOI, 9):
            raise CatanIOResponseError(channel.path, "5.00 Internal Server Error")
        return states[channel]

    mock_client.get_channel_state.side_effect = get_channel_state
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("switch.catan_c1_pump").state == STATE_UNAVAILABLE
    assert hass.states.get("switch.catan_c1_doi_12").state == STATE_ON


async def test_mode_change_reloads(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    mock_client: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test the entry is reloaded when a channel switches its mode."""
    channel = Channel(Interface.UI, 2)
    assert hass.states.get("binary_sensor.catan_c1_ui_2").state == STATE_ON
    assert hass.states.get("sensor.catan_c1_ui_2") is None

    mock_client.configs[channel] = replace(
        mock_client.configs[channel],
        mode=ChannelMode.ANALOG_INPUT,
        ui_type=UiType.AI_VOLTAGE,
    )
    mock_client.states[channel] = replace(
        mock_client.states[channel], mode=ChannelMode.ANALOG_INPUT, analog_value=3.3
    )
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.catan_c1_ui_2").state == "3.3"
    # The binary sensor of the former digital input was removed.
    assert hass.states.get("binary_sensor.catan_c1_ui_2") is None
    assert entity_registry.async_get("binary_sensor.catan_c1_ui_2") is None


async def test_background_discovery(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_discover_devices: AsyncMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test devices found by the background discovery are offered."""
    assert mock_discover_devices.await_count == 1
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)

    mock_discover_devices.return_value = [
        DiscoveredDevice(host=HOST, unique_id=SERIAL, model="CATAN C1"),
        DiscoveredDevice(
            host="169.254.250.10", unique_id="222", model="CATAN DOR6 UI8"
        ),
    ]
    freezer.tick(DISCOVERY_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert mock_discover_devices.await_count == 2
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_INTEGRATION_DISCOVERY
    assert flows[0]["context"]["unique_id"] == "222"


async def test_background_discovery_updates_host(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_discover_devices: AsyncMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test a configured device that got a new address is updated."""
    mock_discover_devices.return_value = [
        DiscoveredDevice(host="169.254.250.20", unique_id=SERIAL, model="CATAN C1"),
    ]
    freezer.tick(DISCOVERY_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert init_integration.data["host"] == "169.254.250.20"
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_background_discovery_skips_ignored(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_discover_devices: AsyncMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test devices the user ignored are not offered again."""
    MockConfigEntry(domain=DOMAIN, unique_id="222", source=SOURCE_IGNORE).add_to_hass(
        hass
    )
    mock_discover_devices.return_value = [
        DiscoveredDevice(
            host="169.254.250.10", unique_id="222", model="CATAN DOR6 UI8"
        ),
    ]
    freezer.tick(DISCOVERY_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert mock_discover_devices.await_count == 2
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
