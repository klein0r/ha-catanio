"""Tests for the CatanIO client using CoAP over localhost."""

from enum import IntEnum

import aiocoap
import pytest

from custom_components.catanio.api import (
    CatanIOClient,
    CatanIOConnectionError,
    CatanIOProtocolError,
    CatanIOResponseError,
    Channel,
    ChannelConfigUpdate,
    ChannelMode,
    Interface,
    IoErrorCode,
    PointStatus,
    UiType,
    find_module_type,
    proto,
)
from custom_components.catanio.api.models import (
    BooleanSetting,
    DiscoverOption,
    Setting,
    UoiType,
)

from .fake_device import FakeCatanDevice

UI1 = Channel(Interface.UI, 1)
UOI13 = Channel(Interface.UOI, 13)
DOR1 = Channel(Interface.DOR, 1)


async def test_identity(client: CatanIOClient, fake_device: FakeCatanDevice) -> None:
    """Test reading the identity of the device."""
    identity = await client.get_identity()
    assert identity.model_name == "CATAN C1"
    assert identity.model_number == "1886438"
    assert identity.serial_number == "1234567890"
    assert identity.mac_address == "00:a0:45:12:34:56"
    assert identity.hardware_revision == 2
    assert identity.unique_id == "1234567890"

    method, path, request = fake_device.requests[0]
    assert (method, path) == ("PATCH", "sys")
    assert request.HasField("req_resp_empty")


async def test_status_firmware_and_name(client: CatanIOClient) -> None:
    """Test reading the system status, firmware and name."""
    status = await client.get_status()
    assert status.points_in_failure == 2
    assert status.ctrl_connected is True
    assert status.button_pressed is True
    assert status.display_connected is False

    assert await client.get_firmware_version() == "1.4.2.17"
    assert await client.get_name() == "Boiler room"


async def test_identify_and_reboot(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test the identify and reboot requests."""
    await client.identify(30)
    await client.reboot()
    identify, reboot = (request for _, _, request in fake_device.requests)
    assert identify.req_identify.duration_s == 30
    assert reboot.HasField("req_resp_empty")


async def test_reboot_without_answer(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test a reboot is accepted when the device restarts before answering."""
    fake_device.silent_paths.add("sys")
    client._timeout = 0.2
    await client.reboot()


async def test_analog_input(client: CatanIOClient) -> None:
    """Test reading configuration and values of an analog input."""
    config = await client.get_channel_config(UI1)
    assert config.mode is ChannelMode.ANALOG_INPUT
    assert config.ui_type is UiType.AI_TEMPERATURE_PT1000_DIN
    assert config.name == "Outdoor"
    assert config.display_name == "Outdoor"
    assert config.unit == "°C"
    assert (config.minimum, config.maximum) == (-50.0, 150.0)

    state = await client.get_channel_state(UI1)
    assert state.mode is ChannelMode.ANALOG_INPUT
    assert state.status is PointStatus.OK
    assert state.error_code is IoErrorCode.OK
    # The 32 bit float noise is removed.
    assert state.analog_value == 21.3
    assert state.sensor_value == 21.25


async def test_analog_output(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test setting an analog output."""
    config = await client.get_channel_config(UOI13)
    assert config.mode is ChannelMode.ANALOG_OUTPUT
    assert (config.minimum, config.maximum) == (None, None)
    assert config.display_name == "UOI 13"

    state = await client.set_analog(UOI13, 7.5)
    assert state.analog_value == 7.5
    assert state.actuator_value == 7.5

    _, path, request = fake_device.requests[-1]
    assert path == "uoi/13"
    assert request.analog_set_val.setting == Setting.VAL
    assert request.analog_set_val.val == 7.5
    assert request.digital_set_val == BooleanSetting.DONT_CHANGE


async def test_relay_output(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test switching a relay output."""
    config = await client.get_channel_config(DOR1)
    assert config.mode is ChannelMode.DIGITAL_OUTPUT
    assert config.inverted is True

    state = await client.get_channel_state(DOR1)
    assert state.mode is ChannelMode.DIGITAL_OUTPUT
    assert state.counter_value == 3

    state = await client.set_digital(DOR1, True)
    assert state.digital_value is True
    assert state.digital_set_value is True
    assert fake_device.requests[-1][2].digital_set_val == BooleanSetting.TRUE

    await client.set_digital(DOR1, False)
    assert fake_device.requests[-1][2].digital_set_val == BooleanSetting.FALSE


async def test_invalid_writes(client: CatanIOClient) -> None:
    """Test writes to channels without the matching output are rejected."""
    with pytest.raises(ValueError, match="UI 1 is an input"):
        await client.set_digital(UI1, True)
    with pytest.raises(ValueError, match="DOR 1 has no analog output"):
        await client.set_analog(DOR1, 1.0)


async def test_discover_modules(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test the backend discovery waits for the result."""
    assert await client.discover_modules(poll_interval=0) == ["169.254.250.10"]
    options = [request.option for _, _, request in fake_device.requests]
    assert options == [
        DiscoverOption.START_READ_ONLY,
        DiscoverOption.GET_STATUS,
        DiscoverOption.GET_STATUS,
        DiscoverOption.GET_RESULT,
    ]


async def test_not_found(client: CatanIOClient) -> None:
    """Test an unknown resource raises a response error."""
    with pytest.raises(CatanIOResponseError) as err:
        await client.get_channel_state(Channel(Interface.UI, 2))
    assert err.value.path == "ui/2"
    assert err.value.code.startswith("4.04")


async def test_invalid_payload(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test an undecodable payload raises a protocol error."""
    fake_device.raw_responses["ui/1"] = b"\xff\xff\xff"
    with pytest.raises(CatanIOProtocolError):
        await client.get_channel_state(UI1)


async def test_unexpected_sys_response(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test a response of the wrong type raises a protocol error."""
    fake_device.wrong_sys_response = True
    with pytest.raises(CatanIOProtocolError):
        await client.get_status()


async def test_timeout(
    coap_context: aiocoap.Context, fake_device: FakeCatanDevice
) -> None:
    """Test a device that does not answer raises a connection error."""
    fake_device.silent_paths.add("sys")
    client = CatanIOClient(
        "127.0.0.1", coap_context, port=fake_device.port, timeout=0.2
    )
    with pytest.raises(CatanIOConnectionError):
        await client.get_status()


@pytest.mark.parametrize(
    ("enum_cls", "proto_enum"),
    [
        (PointStatus, proto.UiResp.DESCRIPTOR.fields_by_name["status"].enum_type),
        (IoErrorCode, proto.UiResp.DESCRIPTOR.fields_by_name["error_code"].enum_type),
        (UiType, proto.UiResp.DESCRIPTOR.fields_by_name["type"].enum_type),
        (UoiType, proto.UoiResp.DESCRIPTOR.fields_by_name["type"].enum_type),
        (
            BooleanSetting,
            proto.UoiReq.DESCRIPTOR.fields_by_name["digital_set_val"].enum_type,
        ),
    ],
)
def test_enums_match_schema(enum_cls: type[IntEnum], proto_enum) -> None:
    """Test the enums mirror the protobuf schema."""
    prefix = proto_enum.values_by_number[0].name.removesuffix(enum_cls(0).name)
    assert {value.name: value.number for value in proto_enum.values} == {
        f"{prefix}{member.name}": member.value for member in enum_cls
    }


@pytest.mark.parametrize(
    ("model_number", "model_name", "expected"),
    [
        ("1886438", "", "CATAN C1"),
        ("", "CATAN DOR6 UI8", "CATAN DOR6 UI8"),
        ("", "Catan-DOI8-UOI8-UI8", "CATAN DOI8 UOI8 UI8"),
        ("1371363", "CATAN DALI MM4 DOI8", "CATAN DALI MM4 DOI8"),
        ("", "CATAN C10", None),
    ],
)
def test_find_module_type(
    model_number: str, model_name: str, expected: str | None
) -> None:
    """Test the module type is found by article number or model name."""
    module_type = find_module_type(model_number, model_name)
    assert (module_type.name if module_type else None) == expected


def test_ipv6_uri(coap_context: aiocoap.Context) -> None:
    """Test IPv6 addresses are put in brackets."""
    client = CatanIOClient("fe80::1", coap_context)
    assert client._base_uri == "coap://[fe80::1]:5683"


async def test_set_channel_config(
    client: CatanIOClient, fake_device: FakeCatanDevice
) -> None:
    """Test only the changed settings are sent and the channel is marked configured."""
    doi9 = Channel(Interface.DOI, 9)
    config = await client.set_channel_config(
        doi9, ChannelConfigUpdate(mode=ChannelMode.DIGITAL_INPUT, debounced=True)
    )
    assert config.mode is ChannelMode.DIGITAL_INPUT
    assert config.debounced is True
    assert config.default_on_failure is True
    assert config.configured is True

    _, path, request = fake_device.requests[-1]
    assert path == "doi/9/cfg"
    assert request.type == UoiType.DI
    assert request.debounced == BooleanSetting.TRUE
    assert request.configured == BooleanSetting.TRUE
    assert request.inverted == BooleanSetting.DONT_CHANGE
    assert request.use_default_val_on_failure == BooleanSetting.DONT_CHANGE
    assert request.enabled == BooleanSetting.DONT_CHANGE

    await client.set_channel_config(doi9, ChannelConfigUpdate(inverted=False))
    request = fake_device.requests[-1][2]
    assert request.type == UoiType.DONT_CHANGE
    assert request.inverted == BooleanSetting.FALSE


async def test_set_channel_config_invalid(client: CatanIOClient) -> None:
    """Test settings that do not apply to a channel are rejected."""
    with pytest.raises(ValueError, match="UI 1 cannot be configured"):
        await client.set_channel_config(UI1, ChannelConfigUpdate(inverted=True))
    with pytest.raises(ValueError, match="unknown is not a mode of DOI 9"):
        await client.set_channel_config(
            Channel(Interface.DOI, 9), ChannelConfigUpdate(mode=ChannelMode.UNKNOWN)
        )
