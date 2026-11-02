"""Data models of the CatanIO API."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum
import re


class Interface(StrEnum):
    """Channel interface, used as the first segment of a channel URI."""

    UI = "ui"
    UOI = "uoi"
    DOI = "doi"
    UV = "uv"
    DOR = "dor"


class PointStatus(IntEnum):
    """General state of an I/O point (``PointStatus`` in shared.proto)."""

    OK = 0
    FAILURE = 1
    OVERRIDDEN = 2
    DISABLED = 3
    UNCONFIGURED = 4


class IoErrorCode(IntEnum):
    """Detailed I/O diagnostic state (``IoErrorCode`` in shared.proto)."""

    OK = 0
    PERIPHERY = 5
    RES_HIGH = 10
    TEMP_HIGH = 11
    IN_VOLT_HIGH = 12
    IN_CURR_SHUNT_RES_HIGH = 13
    OUT_VOLT_HIGH = 14
    WARN_LIM_HIGH = 15
    TEMP_LOW = 20
    NEG_IN_VOLT = 21
    IN_CURR_SMALL = 22
    NEG_IN_CURR = 23
    NEG_IN_CURR_SENSOR_NOT_CONN = 24
    OUT_VOLT_SMALL = 25
    WARN_LIM_LOW = 26
    SENSOR_NOT_CONN = 30
    LOW_LEVEL_EXCEEDS_VOLT_LIMIT = 31
    OUT_OVERLOAD = 40
    VIRT_NULL = 50
    VIRT_ALARM = 51
    VIRT_STALE = 52
    VIRT_DOWN = 53
    VIRT_FAULT = 54
    VIRT_DISABLED = 55


class UiType(IntEnum):
    """Universal input type (``UiType`` in ui.proto)."""

    DONT_CHANGE = 0
    DEFAULT = 1
    AI_VOLTAGE = 2
    AI_CURRENT_0_20 = 3
    AI_RESISTOR_10K = 4
    AI_RESISTOR_180K = 5
    AI_TEMPERATURE_PT1000_DIN = 6
    AI_TEMPERATURE_PT1000_SAMA = 7
    AI_TEMPERATURE_NI1000_DIN = 8
    AI_TEMPERATURE_NI1000_SAMA = 9
    AI_TEMPERATURE_NI1000_LG = 10
    DI = 11
    COUNTER = 12
    AI_TEMPERATURE_NTC_10K = 13
    AI_TEMPERATURE_NTC_10K_PRE = 14
    AI_TEMPERATURE_NTC_20K = 15
    AI_CURRENT_4_20 = 16


class UoiType(IntEnum):
    """Universal output/input type (``UoiType`` in uoi.proto)."""

    DONT_CHANGE = 0
    DEFAULT = 1
    DO = 2
    DI = 3
    COUNTER = 4
    AO_VOLTAGE = 5


class BooleanSetting(IntEnum):
    """Combined Boolean setting operation (``BooleanSetting`` in shared.proto)."""

    DONT_CHANGE = 0
    DEFAULT = 1
    FALSE = 2
    TRUE = 3


class Setting(IntEnum):
    """Setting operation selector (``Setting`` in shared.proto)."""

    DONT_CHANGE = 0
    DEFAULT = 1
    VAL = 2


class SysMsgType(IntEnum):
    """Operations of the generic ``PATCH /sys`` endpoint (``SysMessage.MsgType``)."""

    REQ_READ_INFO = 1
    RESP_READ_INFO = 2
    REQ_READ_STATUS = 3
    RESP_READ_STATUS = 4
    REQ_REBOOT = 9
    RESP_REBOOT = 15
    REQ_READ_FW_UPDATE_INFO = 21
    RESP_READ_FW_UPDATE_INFO = 22
    REQ_IDENTIFY = 24


class DiscoverOption(IntEnum):
    """Operation of the ``PATCH /sys/discover`` endpoint."""

    GET_STATUS = 0
    START_READ_ONLY = 1
    START_ADDRESS_ALL = 2
    GET_RESULT = 3
    ABORT = 4


class DiscoverStatus(IntEnum):
    """State of a backend discovery run."""

    IDLE = 0
    BUSY = 1


class ChannelMode(StrEnum):
    """Functional processing mode of a channel."""

    DIGITAL_INPUT = "digital_input"
    COUNTER = "counter"
    ANALOG_INPUT = "analog_input"
    DIGITAL_OUTPUT = "digital_output"
    ANALOG_OUTPUT = "analog_output"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, order=True)
class Channel:
    """A single channel of a CatanIO device."""

    interface: Interface
    number: int

    @property
    def path(self) -> str:
        """Return the URI path of the runtime resource."""
        return f"{self.interface}/{self.number}"

    @property
    def key(self) -> str:
        """Return a compact identifier, e.g. ``ui1``."""
        return f"{self.interface}{self.number}"

    @property
    def label(self) -> str:
        """Return the terminal designation, e.g. ``UI 1``."""
        return f"{self.interface.upper()} {self.number}"


def _channels(interface: Interface, first: int, last: int) -> tuple[Channel, ...]:
    return tuple(Channel(interface, number) for number in range(first, last + 1))


@dataclass(frozen=True, slots=True)
class ModuleType:
    """A CatanIO device model and the channels it provides."""

    article_number: str
    name: str
    marker: str
    channels: tuple[Channel, ...]


# Channel ranges as documented in the CatanIO protobuf READMEs.
MODULE_TYPES: tuple[ModuleType, ...] = (
    ModuleType(
        article_number="1886438",
        name="CATAN C1",
        marker="C1",
        channels=(
            *_channels(Interface.UI, 1, 8),
            *_channels(Interface.DOI, 9, 12),
            *_channels(Interface.UOI, 13, 14),
            *_channels(Interface.UV, 1, 8),
        ),
    ),
    ModuleType(
        article_number="1371364",
        name="CATAN DOR6 UI8",
        marker="DOR6",
        channels=(
            *_channels(Interface.UI, 1, 8),
            *_channels(Interface.DOR, 1, 6),
        ),
    ),
    ModuleType(
        article_number="1818583",
        name="CATAN DOI8 UOI8 UI8",
        marker="UOI8",
        channels=(
            *_channels(Interface.UI, 1, 8),
            *_channels(Interface.DOI, 9, 16),
            *_channels(Interface.UOI, 17, 24),
            *_channels(Interface.UV, 1, 8),
        ),
    ),
    ModuleType(
        article_number="1371363",
        name="CATAN DALI MM4 DOI8",
        marker="DALI",
        channels=(
            *_channels(Interface.DOI, 1, 8),
            *_channels(Interface.UV, 1, 8),
        ),
    ),
)


def find_module_type(model_number: str, model_name: str) -> ModuleType | None:
    """Return the module type matching the device information, if known."""
    for module_type in MODULE_TYPES:
        if model_number.strip() == module_type.article_number:
            return module_type
    tokens = set(re.split(r"[^A-Z0-9]+", model_name.upper()))
    for module_type in MODULE_TYPES:
        if module_type.marker in tokens:
            return module_type
    return None


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    """Identity of a device (``SysMessage.ReqRespInfo``)."""

    model_name: str
    model_number: str
    serial_number: str
    mac_address: str | None
    hardware_revision: int
    model_revision: str

    @property
    def unique_id(self) -> str | None:
        """Return a stable identifier of the device."""
        return self.serial_number or self.mac_address


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """System status of a device (``SysMessage.RespStatus``)."""

    points_in_failure: int
    points_overridden: int
    display_connected: bool
    ctrl_connected: bool
    button_pressed: bool
    ctrl_connect_failure: bool


@dataclass(frozen=True, slots=True)
class ChannelConfig:
    """Effective configuration of a channel."""

    channel: Channel
    enabled: bool
    configured: bool
    name: str
    mode: ChannelMode
    ui_type: UiType | None
    unit: str
    inverted: bool
    minimum: float | None
    maximum: float | None
    override_enabled: bool
    debounced: bool
    digital_default: bool
    default_on_start: bool
    default_on_failure: bool

    @property
    def display_name(self) -> str:
        """Return the user-defined name, or the terminal designation."""
        return self.name.strip() or self.channel.label


@dataclass(frozen=True, slots=True, kw_only=True)
class ChannelConfigUpdate:
    """Changes to the configuration of a channel.

    The fields match ``ChannelConfig``, None keeps the current value.
    """

    mode: ChannelMode | None = None
    inverted: bool | None = None
    debounced: bool | None = None
    digital_default: bool | None = None
    default_on_start: bool | None = None
    default_on_failure: bool | None = None


@dataclass(frozen=True, slots=True)
class ChannelState:
    """Runtime values of a channel.

    Which values are meaningful depends on ``mode``, see the validity matrices
    in the upstream documentation.
    """

    mode: ChannelMode | None
    status: PointStatus | None
    error_code: IoErrorCode | None
    override_remaining_ms: int
    digital_value: bool
    digital_set_value: bool
    analog_value: float | None
    analog_set_value: float | None
    sensor_value: float | None
    actuator_value: float | None
    counter_value: int
    on_time_s: int
