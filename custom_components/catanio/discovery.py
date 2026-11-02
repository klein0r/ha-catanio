"""Discovery of CatanIO devices on the local bus of a Catan C1.

Home Assistant's DHCP discovery ignores link-local addresses and the devices
do not announce themselves through zeroconf, so the integration discovers
them itself: it probes the I/O of the Catan C1 and asks the C1 backend for the
extension modules it found on the local bus.
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
import logging
from typing import Any, Self

from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.event import async_track_time_interval

from .api import CatanIOClient, CatanIOError, find_module_type
from .coap import async_get_coap_context
from .const import C1_BACKEND_HOST, C1_IO_HOST, DISCOVERY_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PROBE_TIMEOUT = 3.0
BACKEND_DISCOVERY_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A CatanIO device found on the local bus."""

    host: str
    unique_id: str
    model: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Create from flow discovery data."""
        return cls(
            host=data[CONF_HOST], unique_id=data["unique_id"], model=data["model"]
        )


async def async_probe_device(
    hass: HomeAssistant, host: str, request_timeout: float = PROBE_TIMEOUT
) -> DiscoveredDevice | None:
    """Return the device at the given address if it is a supported device."""
    client = CatanIOClient(
        host, await async_get_coap_context(hass), timeout=request_timeout
    )
    try:
        identity = await client.get_identity()
    except CatanIOError as err:
        _LOGGER.debug("No CatanIO device at %s: %s", host, err)
        return None
    module_type = find_module_type(identity.model_number, identity.model_name)
    if identity.unique_id is None or module_type is None:
        _LOGGER.debug(
            "Ignoring unsupported device %s (%s) at %s",
            identity.model_name,
            identity.model_number,
            host,
        )
        return None
    return DiscoveredDevice(
        host=host, unique_id=identity.unique_id, model=module_type.name
    )


async def async_discover_devices(hass: HomeAssistant) -> list[DiscoveredDevice]:
    """Find the I/O of the Catan C1 and all extension modules."""
    backend = CatanIOClient(
        C1_BACKEND_HOST, await async_get_coap_context(hass), timeout=PROBE_TIMEOUT
    )
    hosts = [C1_IO_HOST]
    try:
        hosts.extend(
            await backend.discover_modules(max_duration=BACKEND_DISCOVERY_TIMEOUT)
        )
    except CatanIOError as err:
        _LOGGER.debug("Discovery on backend %s failed: %s", C1_BACKEND_HOST, err)

    devices: dict[str, DiscoveredDevice] = {}
    for device in await asyncio.gather(
        *(async_probe_device(hass, host) for host in dict.fromkeys(hosts))
    ):
        if device is not None:
            devices.setdefault(device.unique_id, device)
    return list(devices.values())


@callback
def async_trigger_discovery(
    hass: HomeAssistant, devices: list[DiscoveredDevice]
) -> None:
    """Start a discovery flow for every new or moved device."""
    entries = hass.config_entries.async_entries(DOMAIN, include_ignore=True)
    ignored = {entry.unique_id for entry in entries if entry.source == SOURCE_IGNORE}
    known_hosts = {entry.unique_id: entry.data.get(CONF_HOST) for entry in entries}
    for device in devices:
        if (
            device.unique_id in ignored
            or known_hosts.get(device.unique_id) == device.host
        ):
            continue
        discovery_flow.async_create_flow(
            hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=asdict(device),
        )


@callback
def async_setup_discovery(hass: HomeAssistant) -> None:
    """Discover devices now and then periodically."""

    async def _async_discover(_: datetime | None = None) -> None:
        async_trigger_discovery(hass, await async_discover_devices(hass))

    hass.async_create_background_task(_async_discover(), f"{DOMAIN} discovery")
    async_track_time_interval(
        hass, _async_discover, DISCOVERY_INTERVAL, cancel_on_shutdown=True
    )
