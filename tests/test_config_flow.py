"""Tests for the CatanIO config flow."""

import asyncio
from collections.abc import Generator
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.catanio.api import CatanIOConnectionError, CatanIOProtocolError
from custom_components.catanio.config_flow import CONF_DEVICE, MANUAL_ENTRY
from custom_components.catanio.const import DOMAIN
from custom_components.catanio.discovery import DiscoveredDevice
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .const import HOST, IDENTITY, SERIAL

DOR_HOST = "169.254.250.10"
DOR_SERIAL = "222"
C1 = DiscoveredDevice(host=HOST, unique_id=SERIAL, model="CATAN C1")
DOR = DiscoveredDevice(host=DOR_HOST, unique_id=DOR_SERIAL, model="CATAN DOR6 UI8")


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    """Do not set up the created entries."""
    with patch(
        "custom_components.catanio.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_flow_discovery() -> Generator[AsyncMock]:
    """Return the devices found by the user flow."""
    with patch(
        "custom_components.catanio.config_flow.async_discover_devices",
        return_value=[C1, DOR],
    ) as mock:
        yield mock


@pytest.fixture
def mock_probe_client() -> Generator[MagicMock]:
    """Return the client probing an address entered by the user."""
    client = MagicMock()
    client.get_identity = AsyncMock(return_value=IDENTITY)
    with patch(
        "custom_components.catanio.config_flow.CatanIOClient", return_value=client
    ):
        yield client


@pytest.mark.usefixtures("mock_flow_discovery")
async def test_user_pick_device(hass: HomeAssistant) -> None:
    """Test setting up a discovered device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick_device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: DOR_SERIAL}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "CATAN DOR6 UI8"
    assert result["data"] == {CONF_HOST: DOR_HOST}
    assert result["result"].unique_id == DOR_SERIAL


async def test_user_discovery_progress(hass: HomeAssistant) -> None:
    """Test the progress is shown while the discovery runs."""
    discovered: asyncio.Future[list[DiscoveredDevice]] = hass.loop.create_future()

    async def discover(hass: HomeAssistant) -> list[DiscoveredDevice]:
        return await discovered

    with patch(
        "custom_components.catanio.config_flow.async_discover_devices",
        side_effect=discover,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.SHOW_PROGRESS
        assert result["progress_action"] == "discovering"

        discovered.set_result([C1])
        await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick_device"


@pytest.mark.usefixtures("mock_flow_discovery")
async def test_user_skips_configured_devices(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test configured devices are not offered again."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    options = result["data_schema"].schema[CONF_DEVICE].config["options"]
    assert [option["value"] for option in options] == [DOR_SERIAL, MANUAL_ENTRY]


@pytest.mark.usefixtures("mock_flow_discovery", "mock_probe_client")
async def test_user_manual_entry(hass: HomeAssistant) -> None:
    """Test picking the manual entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: MANUAL_ENTRY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f" {HOST} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "CATAN C1"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == SERIAL


@pytest.mark.usefixtures("mock_probe_client")
async def test_user_nothing_found(hass: HomeAssistant) -> None:
    """Test the manual entry is shown when no device was found."""
    with patch(
        "custom_components.catanio.config_flow.async_discover_devices",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (CatanIOConnectionError("timeout"), "cannot_connect"),
        (CatanIOProtocolError("garbage"), "not_catanio"),
        ([replace(IDENTITY, serial_number="", mac_address=None)], "not_catanio"),
        (
            [replace(IDENTITY, model_number="1", model_name="Other")],
            "unsupported_model",
        ),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_manual_errors(
    hass: HomeAssistant,
    mock_probe_client: MagicMock,
    side_effect: Exception | list[object],
    error: str,
) -> None:
    """Test errors of the manual entry and the recovery."""
    with patch(
        "custom_components.catanio.config_flow.async_discover_devices",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

    mock_probe_client.get_identity.side_effect = side_effect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_probe_client.get_identity.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_probe_client")
async def test_manual_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test entering the new address of a configured device updates the entry."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.catanio.config_flow.async_discover_devices",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "169.254.250.30"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == "169.254.250.30"


async def test_integration_discovery(hass: HomeAssistant) -> None:
    """Test confirming a device found by the background discovery."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={CONF_HOST: DOR_HOST, "unique_id": DOR_SERIAL, "model": DOR.model},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {
        "name": "CATAN DOR6 UI8",
        "host": DOR_HOST,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "CATAN DOR6 UI8"
    assert result["data"] == {CONF_HOST: DOR_HOST}
    assert result["result"].unique_id == DOR_SERIAL


async def test_integration_discovery_updates_host(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the discovery updates the address of a configured device."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={CONF_HOST: "169.254.250.30", "unique_id": SERIAL, "model": "CATAN C1"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_HOST] == "169.254.250.30"


async def test_reconfigure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_probe_client: MagicMock,
) -> None:
    """Test changing the address of a device."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    mock_probe_client.get_identity.side_effect = CatanIOConnectionError("timeout")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "169.254.250.30"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_probe_client.get_identity.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "169.254.250.30"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == "169.254.250.30"


async def test_reconfigure_wrong_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_probe_client: MagicMock,
) -> None:
    """Test the address of another device is rejected."""
    mock_config_entry.add_to_hass(hass)
    mock_probe_client.get_identity.return_value = replace(
        IDENTITY, serial_number="other"
    )
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: DOR_HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert mock_config_entry.data[CONF_HOST] == HOST
