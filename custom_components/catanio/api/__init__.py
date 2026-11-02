"""Client for the CoAP/Protobuf API of Phoenix Contact CatanIO devices.

This package has no Home Assistant dependencies so it can be moved into a
standalone library.
"""

from .client import DEFAULT_PORT, CatanIOClient
from .exceptions import (
    CatanIOConnectionError,
    CatanIOError,
    CatanIOProtocolError,
    CatanIOResponseError,
)
from .models import (
    MODULE_TYPES,
    Channel,
    ChannelConfig,
    ChannelConfigUpdate,
    ChannelMode,
    ChannelState,
    DeviceIdentity,
    Interface,
    IoErrorCode,
    ModuleType,
    PointStatus,
    SystemStatus,
    UiType,
    find_module_type,
)

__all__ = [
    "DEFAULT_PORT",
    "MODULE_TYPES",
    "CatanIOClient",
    "CatanIOConnectionError",
    "CatanIOError",
    "CatanIOProtocolError",
    "CatanIOResponseError",
    "Channel",
    "ChannelConfig",
    "ChannelConfigUpdate",
    "ChannelMode",
    "ChannelState",
    "DeviceIdentity",
    "Interface",
    "IoErrorCode",
    "ModuleType",
    "PointStatus",
    "SystemStatus",
    "UiType",
    "find_module_type",
]
