"""CoAP client for CatanIO devices."""

import asyncio
from enum import IntEnum
import ipaddress
import logging
import math
from typing import Any

import aiocoap
from aiocoap.numbers.contentformat import ContentFormat
from google.protobuf.message import DecodeError, Message

from . import proto
from .exceptions import (
    CatanIOConnectionError,
    CatanIOProtocolError,
    CatanIOResponseError,
)
from .models import (
    BooleanSetting,
    Channel,
    ChannelConfig,
    ChannelMode,
    ChannelState,
    DeviceIdentity,
    DiscoverOption,
    DiscoverStatus,
    Interface,
    IoErrorCode,
    PointStatus,
    Setting,
    SysMsgType,
    SystemStatus,
    UiType,
    UoiType,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 5683
DEFAULT_TIMEOUT = 10.0

UI_TYPE_MODES = {
    UiType.DI: ChannelMode.DIGITAL_INPUT,
    UiType.COUNTER: ChannelMode.COUNTER,
}
UOI_TYPE_MODES = {
    UoiType.DO: ChannelMode.DIGITAL_OUTPUT,
    UoiType.DI: ChannelMode.DIGITAL_INPUT,
    UoiType.COUNTER: ChannelMode.COUNTER,
    UoiType.AO_VOLTAGE: ChannelMode.ANALOG_OUTPUT,
}

_CONFIG_RESPONSES: dict[Interface, type[Message]] = {
    Interface.UI: proto.UiCfgResp,
    Interface.UOI: proto.UoiCfgResp,
    Interface.DOI: proto.UoiCfgResp,
    Interface.UV: proto.UoiCfgResp,
    Interface.DOR: proto.DorCfgResp,
}
_RUNTIME_REQUESTS: dict[Interface, type[Message]] = {
    Interface.UI: proto.UiReq,
    Interface.UOI: proto.UoiReq,
    Interface.DOI: proto.UoiReq,
    Interface.UV: proto.UoiReq,
    Interface.DOR: proto.DorReq,
}
_RUNTIME_RESPONSES: dict[Interface, type[Message]] = {
    Interface.UI: proto.UiResp,
    Interface.UOI: proto.UoiResp,
    Interface.DOI: proto.UoiResp,
    Interface.UV: proto.UoiResp,
    Interface.DOR: proto.DorResp,
}


def ui_type_mode(ui_type: UiType | None) -> ChannelMode:
    """Return the processing mode of a universal input type."""
    if ui_type is None or ui_type is UiType.DONT_CHANGE:
        return ChannelMode.UNKNOWN
    # Every UI_TYPE_AI_* type and UI_TYPE_DEFAULT (an analog voltage input)
    # use the analog input path.
    return UI_TYPE_MODES.get(ui_type, ChannelMode.ANALOG_INPUT)


def uoi_type_mode(uoi_type: UoiType | None) -> ChannelMode:
    """Return the processing mode of a UOI, DOI or UV type."""
    if uoi_type is None:
        return ChannelMode.UNKNOWN
    return UOI_TYPE_MODES.get(uoi_type, ChannelMode.UNKNOWN)


def _enum[E: IntEnum](enum_cls: type[E], value: int) -> E | None:
    try:
        return enum_cls(value)
    except ValueError:
        return None


def _float(value: float) -> float | None:
    """Convert a protobuf float, dropping the noise of the 32 bit encoding."""
    if not math.isfinite(value):
        return None
    return float(f"{value:.7g}")


def _limit(minimum: float, maximum: float) -> tuple[float | None, float | None]:
    if not (math.isfinite(minimum) and math.isfinite(maximum)) or minimum >= maximum:
        return None, None
    return _float(minimum), _float(maximum)


def _format_mac(raw: bytes) -> str | None:
    if len(raw) != 6 or not any(raw):
        return None
    return ":".join(f"{octet:02x}" for octet in raw)


def _base_uri(host: str, port: int) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return f"coap://{host}:{port}"
    if address.version == 6:
        return f"coap://[{host}]:{port}"
    return f"coap://{host}:{port}"


def parse_channel_config(channel: Channel, message: Any) -> ChannelConfig:
    """Convert a ``*CfgResp`` message into a channel configuration."""
    if channel.interface is Interface.DOR:
        return ChannelConfig(
            channel=channel,
            enabled=message.enabled,
            configured=message.configured,
            name=message.name,
            mode=ChannelMode.DIGITAL_OUTPUT,
            ui_type=None,
            unit="",
            inverted=message.inverted,
            minimum=None,
            maximum=None,
            override_enabled=message.override_enabled,
        )
    ui_type: UiType | None = None
    if channel.interface is Interface.UI:
        ui_type = _enum(UiType, message.type)
        mode = ui_type_mode(ui_type)
    else:
        mode = uoi_type_mode(_enum(UoiType, message.type))
    minimum, maximum = _limit(message.minimum, message.maximum)
    return ChannelConfig(
        channel=channel,
        enabled=message.enabled,
        configured=message.configured,
        name=message.name,
        mode=mode,
        ui_type=ui_type,
        unit=message.unit.strip(),
        inverted=message.inverted,
        minimum=minimum,
        maximum=maximum,
        override_enabled=message.override_enabled,
    )


def parse_channel_state(channel: Channel, message: Any) -> ChannelState:
    """Convert a ``*Resp`` runtime message into a channel state."""
    common: dict[str, Any] = {
        "status": _enum(PointStatus, message.status),
        "error_code": _enum(IoErrorCode, message.error_code),
        "override_remaining_ms": message.override_remaining_ms,
        "digital_value": message.digital_val,
        "counter_value": message.counter_val,
        "on_time_s": message.on_time_s,
    }
    if channel.interface is Interface.DOR:
        return ChannelState(
            mode=ChannelMode.DIGITAL_OUTPUT,
            digital_set_value=message.digital_set_val,
            analog_value=None,
            analog_set_value=None,
            sensor_value=None,
            actuator_value=None,
            **common,
        )
    # A type of 0 (DONT_CHANGE) means the device did not report the type.
    if channel.interface is Interface.UI:
        mode = ui_type_mode(_enum(UiType, message.type)) if message.type else None
        return ChannelState(
            mode=mode,
            digital_set_value=False,
            analog_value=_float(message.analog_val),
            analog_set_value=None,
            sensor_value=_float(message.sensor_val),
            actuator_value=None,
            **common,
        )
    mode = uoi_type_mode(_enum(UoiType, message.type)) if message.type else None
    return ChannelState(
        mode=mode,
        digital_set_value=message.digital_set_val,
        analog_value=_float(message.analog_val),
        analog_set_value=_float(message.analog_set_val),
        sensor_value=None,
        actuator_value=_float(message.actuator_val),
        **common,
    )


def parse_identity(info: Any) -> DeviceIdentity:
    """Convert a ``SysMessage.ReqRespInfo`` message into a device identity."""
    return DeviceIdentity(
        model_name=info.model_name.strip(),
        model_number=info.model_number.strip(),
        serial_number=info.serial_no.strip(),
        mac_address=_format_mac(info.mac_id),
        hardware_revision=info.hardware_revision,
        model_revision=info.model_revision.strip(),
    )


class CatanIOClient:
    """Client for the CoAP API of a single CatanIO device.

    Requests are serialized per client, which matches the default CoAP
    ``NSTART`` of one outstanding interaction per server (RFC 7252).
    """

    def __init__(
        self,
        host: str,
        context: aiocoap.Context,
        *,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.port = port
        self._context = context
        self._timeout = timeout
        self._base_uri = _base_uri(host, port)
        self._lock = asyncio.Lock()

    async def _request(
        self, code: aiocoap.Code, path: str, payload: bytes = b""
    ) -> bytes:
        message = aiocoap.Message(code=code, uri=f"{self._base_uri}/{path}")
        if code is aiocoap.PATCH:
            message.payload = payload
            # The reference client (Node-RED example in PLCnext/CatanIO) sends
            # binary protobuf payloads as text/plain, do the same.
            message.opt.content_format = ContentFormat.TEXT
        async with self._lock:
            try:
                async with asyncio.timeout(self._timeout):
                    response = await self._context.request(message).response
            except TimeoutError as err:
                raise CatanIOConnectionError(
                    f"Timeout while requesting /{path} from {self.host}"
                ) from err
            except aiocoap.error.Error as err:
                raise CatanIOConnectionError(
                    f"Error while requesting /{path} from {self.host}: {err}"
                ) from err
        if not response.code.is_successful():
            raise CatanIOResponseError(path, str(response.code))
        content: bytes = response.payload
        return content

    async def _call[M: Message](
        self,
        code: aiocoap.Code,
        path: str,
        response_type: type[M],
        request: Message | None = None,
    ) -> M:
        payload = request.SerializeToString() if request is not None else b""
        raw = await self._request(code, path, payload)
        try:
            return response_type.FromString(raw)
        except DecodeError as err:
            raise CatanIOProtocolError(
                f"Invalid {response_type.DESCRIPTOR.name} from /{path}: {err}"
            ) from err

    async def _sys(
        self,
        msg_type: SysMsgType,
        expected: SysMsgType | None,
        *,
        payload_field: str = "req_resp_empty",
        **payload: Any,
    ) -> Any:
        request: Any = proto.SysMessage(msg_type=msg_type)
        getattr(request, payload_field).SetInParent()
        for field, value in payload.items():
            setattr(getattr(request, payload_field), field, value)
        response: Any = await self._call(
            aiocoap.PATCH, "sys", proto.SysMessage, request
        )
        if expected is not None and response.msg_type != expected:
            raise CatanIOProtocolError(
                f"Expected {expected.name} from /sys, got {response.msg_type}"
            )
        return response

    async def get_identity(self) -> DeviceIdentity:
        """Read model, serial number and MAC address of the device."""
        response = await self._sys(SysMsgType.REQ_READ_INFO, SysMsgType.RESP_READ_INFO)
        return parse_identity(response.req_resp_info)

    async def get_status(self) -> SystemStatus:
        """Read the system status of the device."""
        response = await self._sys(
            SysMsgType.REQ_READ_STATUS, SysMsgType.RESP_READ_STATUS
        )
        status = response.resp_status
        return SystemStatus(
            points_in_failure=status.points_in_failure,
            points_overridden=status.points_overridden,
            display_connected=status.display_connected,
            ctrl_connected=status.ctrl_connected,
            button_pressed=status.button_pressed,
            ctrl_connect_failure=status.ctrl_connect_failure,
        )

    async def get_firmware_version(self) -> str | None:
        """Read the version of the primary firmware image."""
        response = await self._sys(
            SysMsgType.REQ_READ_FW_UPDATE_INFO, SysMsgType.RESP_READ_FW_UPDATE_INFO
        )
        info = response.resp_fw_update_info
        if not info.HasField("fw_primary"):
            return None
        image = info.fw_primary
        return f"{image.major}.{image.minor}.{image.revision}.{image.build}"

    async def get_name(self) -> str:
        """Read the user-defined device name from the system configuration."""
        response: Any = await self._call(aiocoap.GET, "sys/cfg", proto.SysCfgResp)
        # SysCfgResp also carries the password slots, never expose them.
        return str(response.name).strip()

    async def identify(self, duration_s: int) -> None:
        """Let the device identify itself for the given time."""
        await self._sys(
            SysMsgType.REQ_IDENTIFY,
            None,
            payload_field="req_identify",
            duration_s=duration_s,
        )

    async def reboot(self) -> None:
        """Reboot the device."""
        try:
            await self._sys(SysMsgType.REQ_REBOOT, None)
        except CatanIOConnectionError:
            # The device may restart before it acknowledges the request.
            _LOGGER.debug("No answer to reboot request from %s", self.host)

    async def get_channel_config(self, channel: Channel) -> ChannelConfig:
        """Read the effective configuration of a channel."""
        response = await self._call(
            aiocoap.GET, f"{channel.path}/cfg", _CONFIG_RESPONSES[channel.interface]
        )
        return parse_channel_config(channel, response)

    async def get_channel_state(self, channel: Channel) -> ChannelState:
        """Read the runtime values of a channel."""
        response = await self._call(
            aiocoap.GET, channel.path, _RUNTIME_RESPONSES[channel.interface]
        )
        return parse_channel_state(channel, response)

    async def _write_channel(self, channel: Channel, request: Message) -> ChannelState:
        response = await self._call(
            aiocoap.PATCH, channel.path, _RUNTIME_RESPONSES[channel.interface], request
        )
        return parse_channel_state(channel, response)

    async def set_digital(self, channel: Channel, value: bool) -> ChannelState:
        """Set the digital output value of a channel."""
        if channel.interface is Interface.UI:
            raise ValueError(f"{channel.label} is an input")
        request = _RUNTIME_REQUESTS[channel.interface](
            digital_set_val=BooleanSetting.TRUE if value else BooleanSetting.FALSE
        )
        return await self._write_channel(channel, request)

    async def set_analog(self, channel: Channel, value: float) -> ChannelState:
        """Set the analog output value of a channel."""
        if channel.interface not in (Interface.UOI, Interface.UV):
            raise ValueError(f"{channel.label} has no analog output")
        request: Any = proto.UoiReq()
        request.analog_set_val.setting = Setting.VAL
        request.analog_set_val.val = value
        return await self._write_channel(channel, request)

    async def _discover(self, option: DiscoverOption) -> Any:
        return await self._call(
            aiocoap.PATCH,
            "sys/discover",
            proto.RespDiscover,
            proto.ReqDiscover(option=option),
        )

    async def discover_modules(
        self, *, max_duration: float = 30.0, poll_interval: float = 1.0
    ) -> list[str]:
        """Run a read-only discovery on a controller backend.

        Returns the IPv4 addresses of the devices the backend found.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_duration
        response = await self._discover(DiscoverOption.START_READ_ONLY)
        while response.status == DiscoverStatus.BUSY and loop.time() < deadline:
            await asyncio.sleep(poll_interval)
            response = await self._discover(DiscoverOption.GET_STATUS)
        response = await self._discover(DiscoverOption.GET_RESULT)
        if response.error:
            _LOGGER.debug(
                "Discovery on %s reported error %s", self.host, response.error
            )
        return [
            str(ipaddress.IPv4Address(entry.ip_address))
            for entry in response.discover_entries
            if entry.error == 0 and len(entry.ip_address) == 4
        ]
