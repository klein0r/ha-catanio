"""Diagnostics support for the CatanIO integration."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import CatanIOConfigEntry

TO_REDACT = {"mac_address", "serial_number", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CatanIOConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "identity": async_redact_data(asdict(coordinator.identity), TO_REDACT),
        "module_type": coordinator.module_type.name,
        "firmware_version": coordinator.device_info.get("sw_version"),
        "channel_configs": {
            channel.key: asdict(config)
            for channel, config in coordinator.channel_configs.items()
        },
        "status": asdict(coordinator.data.status),
        "channels": {
            channel.key: asdict(state)
            for channel, state in coordinator.data.channels.items()
        },
    }
