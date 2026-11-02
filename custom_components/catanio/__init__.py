"""The Phoenix Contact CatanIO integration."""

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import CatanIOClient
from .coap import async_get_coap_context
from .const import DOMAIN
from .coordinator import CatanIOConfigEntry, CatanIOCoordinator
from .discovery import async_setup_discovery

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the CatanIO integration."""
    async_setup_discovery(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CatanIOConfigEntry) -> bool:
    """Set up a CatanIO device from a config entry."""
    client = CatanIOClient(entry.data[CONF_HOST], await async_get_coap_context(hass))
    coordinator = CatanIOCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CatanIOConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
