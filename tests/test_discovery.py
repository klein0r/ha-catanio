"""Tests for the discovery of CatanIO devices."""

from collections.abc import Generator
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.catanio.api import CatanIOConnectionError, CatanIOError
from custom_components.catanio.const import C1_BACKEND_HOST, C1_IO_HOST
from custom_components.catanio.discovery import DiscoveredDevice, async_discover_devices
from homeassistant.core import HomeAssistant

from .const import IDENTITY, SERIAL

DOR_HOST = "169.254.250.10"
UNKNOWN_HOST = "169.254.250.11"
OFFLINE_HOST = "169.254.250.12"

IDENTITIES = {
    C1_IO_HOST: IDENTITY,
    DOR_HOST: replace(
        IDENTITY,
        model_name="CATAN DOR6 UI8",
        model_number="1371364",
        serial_number="222",
    ),
    UNKNOWN_HOST: replace(
        IDENTITY, model_name="Something else", model_number="1", serial_number="333"
    ),
    OFFLINE_HOST: CatanIOConnectionError("timeout"),
}


@pytest.fixture
def backend_result() -> list[str] | CatanIOError:
    """Return the addresses the backend finds."""
    return [C1_IO_HOST, DOR_HOST, UNKNOWN_HOST, OFFLINE_HOST, DOR_HOST]


@pytest.fixture
def mock_clients(backend_result: list[str] | CatanIOError) -> Generator[MagicMock]:
    """Return clients answering with the identities above."""

    def create_client(host: str, context: object, *, timeout: float) -> MagicMock:
        client = MagicMock()
        client.host = host
        if host == C1_BACKEND_HOST:
            client.discover_modules = AsyncMock(
                side_effect=[backend_result]
                if not isinstance(backend_result, Exception)
                else backend_result
            )
        identity = IDENTITIES[host] if host in IDENTITIES else CatanIOConnectionError()
        client.get_identity = AsyncMock(
            side_effect=identity if isinstance(identity, Exception) else [identity]
        )
        return client

    with patch(
        "custom_components.catanio.discovery.CatanIOClient", side_effect=create_client
    ) as mock:
        yield mock


@pytest.mark.usefixtures("mock_clients")
async def test_discover_devices(hass: HomeAssistant) -> None:
    """Test the I/O of the C1 and supported extension modules are found once."""
    assert await async_discover_devices(hass) == [
        DiscoveredDevice(host=C1_IO_HOST, unique_id=SERIAL, model="CATAN C1"),
        DiscoveredDevice(host=DOR_HOST, unique_id="222", model="CATAN DOR6 UI8"),
    ]


@pytest.mark.usefixtures("mock_clients")
@pytest.mark.parametrize("backend_result", [CatanIOConnectionError("timeout")])
async def test_discover_devices_without_backend(hass: HomeAssistant) -> None:
    """Test the I/O of the C1 is found when the backend does not answer."""
    assert await async_discover_devices(hass) == [
        DiscoveredDevice(host=C1_IO_HOST, unique_id=SERIAL, model="CATAN C1"),
    ]
