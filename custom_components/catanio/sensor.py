"""Sensors for CatanIO devices."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    LIGHT_LUX,
    EntityCategory,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import (
    Channel,
    ChannelConfig,
    ChannelMode,
    ChannelState,
    Interface,
    IoErrorCode,
    PointStatus,
    SystemStatus,
    UiType,
)
from .coordinator import CatanIOConfigEntry, CatanIOCoordinator
from .entity import (
    CatanIOChannelEntity,
    CatanIOChannelEntityDescription,
    CatanIOEntity,
    async_remove_stale_entities,
    channel_entity_descriptions,
)

PARALLEL_UPDATES = 0

ALL_MODES = frozenset(ChannelMode)
DIGITAL_MODES = frozenset({ChannelMode.DIGITAL_INPUT, ChannelMode.DIGITAL_OUTPUT})

# Device classes for the free-text units of measured values.
MEASUREMENT_DEVICE_CLASSES: dict[str, SensorDeviceClass] = {
    UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
    UnitOfTemperature.FAHRENHEIT: SensorDeviceClass.TEMPERATURE,
    UnitOfTemperature.KELVIN: SensorDeviceClass.TEMPERATURE,
    UnitOfElectricPotential.VOLT: SensorDeviceClass.VOLTAGE,
    UnitOfElectricPotential.MILLIVOLT: SensorDeviceClass.VOLTAGE,
    UnitOfElectricCurrent.AMPERE: SensorDeviceClass.CURRENT,
    UnitOfElectricCurrent.MILLIAMPERE: SensorDeviceClass.CURRENT,
    UnitOfPower.WATT: SensorDeviceClass.POWER,
    UnitOfPower.KILO_WATT: SensorDeviceClass.POWER,
    UnitOfPressure.PA: SensorDeviceClass.PRESSURE,
    UnitOfPressure.HPA: SensorDeviceClass.PRESSURE,
    UnitOfPressure.KPA: SensorDeviceClass.PRESSURE,
    UnitOfPressure.MBAR: SensorDeviceClass.PRESSURE,
    UnitOfPressure.BAR: SensorDeviceClass.PRESSURE,
    LIGHT_LUX: SensorDeviceClass.ILLUMINANCE,
}
# Device classes for the free-text units of scaled counters.
TOTAL_DEVICE_CLASSES: dict[str, SensorDeviceClass] = {
    UnitOfEnergy.WATT_HOUR: SensorDeviceClass.ENERGY,
    UnitOfEnergy.KILO_WATT_HOUR: SensorDeviceClass.ENERGY,
    UnitOfEnergy.MEGA_WATT_HOUR: SensorDeviceClass.ENERGY,
}


def sensor_unit(config: ChannelConfig) -> str | None:
    """Return the unit of the sensor-level value of an analog input."""
    match config.ui_type:
        case UiType.DEFAULT | UiType.AI_VOLTAGE:
            return UnitOfElectricPotential.VOLT
        case UiType.AI_CURRENT_0_20 | UiType.AI_CURRENT_4_20:
            return UnitOfElectricCurrent.MILLIAMPERE
        case UiType.AI_RESISTOR_10K | UiType.AI_RESISTOR_180K | None:
            return None
    return UnitOfTemperature.CELSIUS


def application_unit(config: ChannelConfig) -> str | None:
    """Return the unit configured for the processed value of a channel."""
    if config.unit:
        return config.unit
    if config.mode is ChannelMode.ANALOG_INPUT:
        # Without calibration the processed value equals the sensor value.
        return sensor_unit(config)
    return None


@dataclass(frozen=True, kw_only=True)
class CatanIOChannelSensorEntityDescription(
    SensorEntityDescription, CatanIOChannelEntityDescription
):
    """Describes a sensor of a channel."""

    value_fn: Callable[[ChannelState], StateType]
    unit_fn: Callable[[ChannelConfig], str | None] | None = None
    unit_device_classes: dict[str, SensorDeviceClass] | None = None


@dataclass(frozen=True, kw_only=True)
class CatanIOSystemSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor of the system status."""

    value_fn: Callable[[SystemStatus], StateType]


CHANNEL_SENSORS: tuple[CatanIOChannelSensorEntityDescription, ...] = (
    CatanIOChannelSensorEntityDescription(
        key="value",
        translation_key="analog_input",
        modes=frozenset({ChannelMode.ANALOG_INPUT}),
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        unit_fn=application_unit,
        unit_device_classes=MEASUREMENT_DEVICE_CLASSES,
        value_fn=lambda state: state.analog_value,
    ),
    CatanIOChannelSensorEntityDescription(
        key="sensor_value",
        translation_key="sensor_value",
        modes=frozenset({ChannelMode.ANALOG_INPUT}),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        unit_fn=sensor_unit,
        unit_device_classes=MEASUREMENT_DEVICE_CLASSES,
        value_fn=lambda state: state.sensor_value,
    ),
    CatanIOChannelSensorEntityDescription(
        key="scaled_counter",
        translation_key="counter",
        modes=frozenset({ChannelMode.COUNTER}),
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit_fn=application_unit,
        unit_device_classes=TOTAL_DEVICE_CLASSES,
        value_fn=lambda state: state.analog_value,
    ),
    CatanIOChannelSensorEntityDescription(
        key="pulses",
        translation_key="pulses",
        modes=frozenset({ChannelMode.COUNTER}),
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda state: state.counter_value,
    ),
    CatanIOChannelSensorEntityDescription(
        key="switching_cycles",
        translation_key="switching_cycles",
        modes=DIGITAL_MODES,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda state: state.counter_value,
    ),
    CatanIOChannelSensorEntityDescription(
        key="on_time",
        translation_key="on_time",
        modes=DIGITAL_MODES,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda state: state.on_time_s,
    ),
    CatanIOChannelSensorEntityDescription(
        key="actuator_value",
        translation_key="actuator_value",
        modes=frozenset({ChannelMode.ANALOG_OUTPUT}),
        # Virtual UV channels have no physical output.
        interfaces=frozenset({Interface.UOI}),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value_fn=lambda state: state.actuator_value,
    ),
    CatanIOChannelSensorEntityDescription(
        key="status",
        translation_key="status",
        modes=ALL_MODES,
        valid_statuses=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.ENUM,
        options=[status.name.lower() for status in PointStatus],
        value_fn=(
            lambda state: (
                state.status.name.lower() if state.status is not None else None
            )
        ),
    ),
    CatanIOChannelSensorEntityDescription(
        key="error",
        translation_key="error",
        modes=ALL_MODES,
        valid_statuses=None,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.ENUM,
        options=[code.name.lower() for code in IoErrorCode],
        value_fn=(
            lambda state: (
                state.error_code.name.lower() if state.error_code is not None else None
            )
        ),
    ),
)

SYSTEM_SENSORS: tuple[CatanIOSystemSensorEntityDescription, ...] = (
    CatanIOSystemSensorEntityDescription(
        key="points_in_failure",
        translation_key="points_in_failure",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.points_in_failure,
    ),
    CatanIOSystemSensorEntityDescription(
        key="points_overridden",
        translation_key="points_overridden",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.points_overridden,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatanIOConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CatanIO sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        CatanIOSystemSensor(coordinator, description) for description in SYSTEM_SENSORS
    ]
    entities.extend(
        CatanIOChannelSensor(coordinator, channel, description)
        for channel, description in channel_entity_descriptions(
            coordinator, CHANNEL_SENSORS
        )
    )
    async_add_entities(entities)
    async_remove_stale_entities(hass, entry, Platform.SENSOR, entities)


class CatanIOSystemSensor(CatanIOEntity, SensorEntity):
    """Sensor of the system status."""

    entity_description: CatanIOSystemSensorEntityDescription

    def __init__(
        self,
        coordinator: CatanIOCoordinator,
        description: CatanIOSystemSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @override
    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data.status)


class CatanIOChannelSensor(CatanIOChannelEntity, SensorEntity):
    """Sensor of a channel."""

    entity_description: CatanIOChannelSensorEntityDescription

    def __init__(
        self,
        coordinator: CatanIOCoordinator,
        channel: Channel,
        description: CatanIOChannelSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, channel, description)
        if description.unit_fn is not None:
            unit = description.unit_fn(self.channel_config)
            self._attr_native_unit_of_measurement = unit
            if unit is not None and description.unit_device_classes is not None:
                self._attr_device_class = description.unit_device_classes.get(unit)

    @override
    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if (state := self.channel_state) is None:
            return None
        return self.entity_description.value_fn(state)
