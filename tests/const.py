"""Device data used by the CatanIO tests."""

from custom_components.catanio.api import (
    Channel,
    ChannelConfig,
    ChannelMode,
    ChannelState,
    DeviceIdentity,
    Interface,
    IoErrorCode,
    PointStatus,
    SystemStatus,
    UiType,
)

HOST = "169.254.253.1"
SERIAL = "1234567890"

IDENTITY = DeviceIdentity(
    model_name="CATAN C1",
    model_number="1886438",
    serial_number=SERIAL,
    mac_address="00:a0:45:12:34:56",
    hardware_revision=2,
    model_revision="01",
)

STATUS = SystemStatus(
    points_in_failure=1,
    points_overridden=0,
    display_connected=True,
    ctrl_connected=True,
    button_pressed=False,
    ctrl_connect_failure=False,
)


def config(
    channel: Channel,
    mode: ChannelMode,
    *,
    name: str = "",
    unit: str = "",
    ui_type: UiType | None = None,
    enabled: bool = True,
    inverted: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    debounced: bool = False,
    digital_default: bool = False,
    default_on_start: bool = False,
    default_on_failure: bool = False,
) -> ChannelConfig:
    """Return a channel configuration."""
    return ChannelConfig(
        channel=channel,
        enabled=enabled,
        configured=enabled,
        name=name,
        mode=mode,
        ui_type=ui_type,
        unit=unit,
        inverted=inverted,
        minimum=minimum,
        maximum=maximum,
        override_enabled=True,
        debounced=debounced,
        digital_default=digital_default,
        default_on_start=default_on_start,
        default_on_failure=default_on_failure,
    )


def state(
    mode: ChannelMode | None,
    *,
    status: PointStatus = PointStatus.OK,
    error_code: IoErrorCode = IoErrorCode.OK,
    digital_value: bool = False,
    digital_set_value: bool = False,
    analog_value: float | None = None,
    analog_set_value: float | None = None,
    sensor_value: float | None = None,
    actuator_value: float | None = None,
    counter_value: int = 0,
    on_time_s: int = 0,
) -> ChannelState:
    """Return a channel state."""
    return ChannelState(
        mode=mode,
        status=status,
        error_code=error_code,
        override_remaining_ms=0,
        digital_value=digital_value,
        digital_set_value=digital_set_value,
        analog_value=analog_value,
        analog_set_value=analog_set_value,
        sensor_value=sensor_value,
        actuator_value=actuator_value,
        counter_value=counter_value,
        on_time_s=on_time_s,
    )


UI = Interface.UI
DOI = Interface.DOI
UOI = Interface.UOI
UV = Interface.UV

ANALOG = ChannelMode.ANALOG_INPUT
DIGITAL_IN = ChannelMode.DIGITAL_INPUT
COUNTER = ChannelMode.COUNTER
DIGITAL_OUT = ChannelMode.DIGITAL_OUTPUT
ANALOG_OUT = ChannelMode.ANALOG_OUTPUT


def c1_configs() -> dict[Channel, ChannelConfig]:
    """Return the channel configuration of a Catan C1."""
    configs = [
        config(
            Channel(UI, 1),
            ANALOG,
            name="Outdoor temperature",
            unit="°C",
            ui_type=UiType.AI_TEMPERATURE_PT1000_DIN,
        ),
        config(Channel(UI, 2), DIGITAL_IN, ui_type=UiType.DI),
        config(
            Channel(UI, 3),
            COUNTER,
            name="Heat meter",
            unit="kWh",
            ui_type=UiType.COUNTER,
        ),
        config(Channel(UI, 4), ANALOG, ui_type=UiType.AI_VOLTAGE),
        config(Channel(UI, 5), ANALOG, ui_type=UiType.AI_RESISTOR_10K),
        config(Channel(UI, 6), ANALOG, unit="%", ui_type=UiType.AI_CURRENT_4_20),
        config(Channel(UI, 7), ANALOG, ui_type=UiType.AI_VOLTAGE, enabled=False),
        config(Channel(UI, 8), ANALOG, ui_type=UiType.AI_VOLTAGE, enabled=False),
        config(
            Channel(DOI, 9),
            DIGITAL_OUT,
            name="Pump",
            default_on_failure=True,
        ),
        config(Channel(DOI, 10), DIGITAL_IN, debounced=True),
        config(Channel(DOI, 11), COUNTER),
        config(Channel(DOI, 12), DIGITAL_OUT, inverted=True),
        config(Channel(UOI, 13), ANALOG_OUT, minimum=0.0, maximum=10.0),
        config(Channel(UOI, 14), ChannelMode.UNKNOWN),
        config(Channel(UV, 1), ANALOG_OUT, unit="%", minimum=0.0, maximum=100.0),
        config(Channel(UV, 2), DIGITAL_OUT),
        *(
            config(Channel(UV, number), DIGITAL_OUT, enabled=False)
            for number in range(3, 9)
        ),
    ]
    return {item.channel: item for item in configs}


def c1_states() -> dict[Channel, ChannelState]:
    """Return the runtime values of the enabled channels of a Catan C1."""
    return {
        Channel(UI, 1): state(ANALOG, analog_value=21.5, sensor_value=21.4),
        Channel(UI, 2): state(
            DIGITAL_IN, digital_value=True, counter_value=42, on_time_s=3600
        ),
        Channel(UI, 3): state(
            COUNTER, digital_value=False, counter_value=1250, analog_value=12.5
        ),
        Channel(UI, 4): state(ANALOG, analog_value=4.2, sensor_value=4.2),
        Channel(UI, 5): state(ANALOG, analog_value=1080.0, sensor_value=1080.0),
        Channel(UI, 6): state(
            ANALOG,
            status=PointStatus.FAILURE,
            error_code=IoErrorCode.SENSOR_NOT_CONN,
            analog_value=0.0,
            sensor_value=0.0,
        ),
        Channel(DOI, 9): state(DIGITAL_OUT, digital_value=True, digital_set_value=True),
        Channel(DOI, 10): state(DIGITAL_IN, digital_value=False, counter_value=7),
        Channel(DOI, 11): state(COUNTER, counter_value=99, analog_value=99.0),
        Channel(DOI, 12): state(
            DIGITAL_OUT, digital_value=False, digital_set_value=True
        ),
        Channel(UOI, 13): state(
            ANALOG_OUT, analog_value=5.0, analog_set_value=5.0, actuator_value=5.0
        ),
        Channel(UOI, 14): state(None, status=PointStatus.UNCONFIGURED),
        Channel(UV, 1): state(ANALOG_OUT, analog_value=50.0, analog_set_value=50.0),
        Channel(UV, 2): state(
            DIGITAL_OUT, status=PointStatus.OVERRIDDEN, digital_value=True
        ),
    }
