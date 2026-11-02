"""Fixtures for the CatanIO client tests."""

from collections.abc import AsyncGenerator
import socket

import aiocoap
import pytest
import pytest_socket

from custom_components.catanio.api import CatanIOClient

from .fake_device import FakeCatanDevice


@pytest.fixture
def mock_coap_context() -> None:
    """Use real CoAP contexts in the client tests."""


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Allow the timers aiocoap keeps to detect duplicate messages."""
    return True


@pytest.fixture(autouse=True)
def allow_localhost(socket_enabled: None) -> None:
    """Allow UDP to localhost, aiocoap uses IPv4-mapped IPv6 addresses."""
    pytest_socket.socket_allow_hosts(["127.0.0.1", "::ffff:127.0.0.1"])


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
async def fake_device() -> AsyncGenerator[FakeCatanDevice]:
    """Run a fake CatanIO device on localhost."""
    device = FakeCatanDevice()
    device.port = _free_udp_port()
    server = await aiocoap.Context.create_server_context(
        device.site, bind=("127.0.0.1", device.port)
    )
    yield device
    await server.shutdown()


@pytest.fixture
async def coap_context() -> AsyncGenerator[aiocoap.Context]:
    """Return a CoAP client context."""
    context = await aiocoap.Context.create_client_context(transports=["udp6"])
    yield context
    await context.shutdown()


@pytest.fixture
def client(
    fake_device: FakeCatanDevice, coap_context: aiocoap.Context
) -> CatanIOClient:
    """Return a client connected to the fake device."""
    return CatanIOClient("127.0.0.1", coap_context, port=fake_device.port, timeout=2)
