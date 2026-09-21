"""Sensor platform for Felicity Solar ESS."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_TYPE_BATTERY,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import FelicityDataUpdateCoordinator, safe_float, safe_int

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FelicitySensorEntityDescription(SensorEntityDescription):
    """Describes Felicity sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any]


# Plant / System wide sensors
PLANT_SENSORS: tuple[FelicitySensorEntityDescription, ...] = (
    FelicitySensorEntityDescription(
        key="pv_power",
        translation_key="pv_power",
        name="Solar PV Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: safe_float(
            d.get("realtime", {}).get("pvPower")
            or d.get("battery_details", {}).get("pvPower")
        ),
    ),
    FelicitySensorEntityDescription(
        key="feed_power",
        translation_key="feed_power",
        name="Grid Feed-in Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: safe_float(
            d.get("realtime", {}).get("feedPower")
            or d.get("battery_details", {}).get("feedPower")
        ),
    ),
    FelicitySensorEntityDescription(
        key="load_power",
        translation_key="load_power",
        name="Home Load Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: safe_float(
            d.get("realtime", {}).get("loadPower")
            or d.get("battery_details", {}).get("loadPower")
        ),
    ),
    FelicitySensorEntityDescription(
        key="total_pv_energy_today",
        translation_key="total_pv_energy_today",
        name="Solar Generation Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: safe_float(
            d.get("realtime", {}).get("todayPv")
            or d.get("battery_details", {}).get("todayPv")
        ),
    ),
    FelicitySensorEntityDescription(
        key="total_load_energy_today",
        translation_key="total_load_energy_today",
        name="Load Consumption Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: safe_float(
            d.get("realtime", {}).get("todayLoad")
            or d.get("battery_details", {}).get("todayLoad")
        ),
    ),
)


# Battery specific sensor descriptions
BATTERY_SENSORS: tuple[FelicitySensorEntityDescription, ...] = (
    FelicitySensorEntityDescription(
        key="soc",
        translation_key="soc",
        name="State of Charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: safe_float(b.get("emsSoc") or b.get("soc")),
    ),
    FelicitySensorEntityDescription(
        key="soh",
        translation_key="soh",
        name="State of Health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("emsSoh") or b.get("soh")),
    ),
    FelicitySensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        name="Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: safe_float(b.get("emsVoltage") or b.get("voltage") or b.get("packVolt")),
    ),
    FelicitySensorEntityDescription(
        key="current",
        translation_key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: safe_float(b.get("emsCurrent") or b.get("current") or b.get("packCurr")),
    ),
    FelicitySensorEntityDescription(
        key="power",
        translation_key="power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: safe_float(b.get("emsPower") or b.get("power") or b.get("batteryPower")),
    ),
    FelicitySensorEntityDescription(
        key="capacity",
        translation_key="capacity",
        name="Capacity",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("emsCapacity") or b.get("capacity")),
    ),
    FelicitySensorEntityDescription(
        key="bms_charge_current_limit",
        translation_key="bms_charge_current_limit",
        name="BMS Charge Current Limit",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("bmslccurr") or b.get("bmsChargeCurrentLimit")),
    ),
    FelicitySensorEntityDescription(
        key="bms_discharge_current_limit",
        translation_key="bms_discharge_current_limit",
        name="BMS Discharge Current Limit",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("bmsldcurr") or b.get("bmsDischargeCurrentLimit")),
    ),
    FelicitySensorEntityDescription(
        key="bms_charge_voltage_limit",
        translation_key="bms_charge_voltage_limit",
        name="BMS Charge Voltage Limit",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("BMSLCVolt") or b.get("bmsChargeVoltageLimit")),
    ),
    FelicitySensorEntityDescription(
        key="bms_discharge_voltage_limit",
        translation_key="bms_discharge_voltage_limit",
        name="BMS Discharge Voltage Limit",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("BMSLDVolt") or b.get("bmsDischargeVoltageLimit")),
    ),
    FelicitySensorEntityDescription(
        key="today_battery_charge",
        translation_key="today_battery_charge",
        name="Energy Charged Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda b: safe_float(b.get("ebatCharToday") or b.get("todayBatteryCharging")),
    ),
    FelicitySensorEntityDescription(
        key="today_battery_discharge",
        translation_key="today_battery_discharge",
        name="Energy Discharged Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda b: safe_float(b.get("ebatDisCharToday") or b.get("todayBatteryDischarge")),
    ),
    FelicitySensorEntityDescription(
        key="max_cell_voltage",
        translation_key="max_cell_voltage",
        name="Max Cell Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("maxVoltage2bms") or b.get("maxCellVolt")),
    ),
    FelicitySensorEntityDescription(
        key="min_cell_voltage",
        translation_key="min_cell_voltage",
        name="Min Cell Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("minVoltage2bms") or b.get("minCellVolt")),
    ),
    FelicitySensorEntityDescription(
        key="max_cell_voltage_num",
        translation_key="max_cell_voltage_num",
        name="Max Cell Voltage Number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_int(b.get("maxVoltageNum2bms") or b.get("maxCellVoltNum")),
    ),
    FelicitySensorEntityDescription(
        key="min_cell_voltage_num",
        translation_key="min_cell_voltage_num",
        name="Min Cell Voltage Number",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_int(b.get("minVoltageNum2bms") or b.get("minCellVoltNum")),
    ),
    FelicitySensorEntityDescription(
        key="max_cell_temperature",
        translation_key="max_cell_temperature",
        name="Max Cell Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("tempMax") or b.get("maxCellTemp")),
    ),
    FelicitySensorEntityDescription(
        key="min_cell_temperature",
        translation_key="min_cell_temperature",
        name="Min Cell Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: safe_float(b.get("tempMin") or b.get("minCellTemp")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Felicity ESS sensors based on a config entry."""
    coordinator: FelicityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = []

    # 1. Add plant-level sensors
    for desc in PLANT_SENSORS:
        entities.append(FelicityPlantSensor(coordinator, desc))

    # 2. Add battery-level sensors
    # Find batteries from coordinator devices or default to plant battery
    devices = coordinator.devices
    battery_devices = [
        dev for dev in devices.values() if dev.get("deviceType") == DEVICE_TYPE_BATTERY
    ]

    if battery_devices:
        for b_dev in battery_devices:
            sn = str(b_dev.get("deviceSn"))
            model = b_dev.get("deviceModel", "Felicity Battery")
            for desc in BATTERY_SENSORS:
                entities.append(FelicityBatterySensor(coordinator, desc, sn, model))

            # Add individual cell voltage sensors 1..16 (disabled by default)
            for cell_idx in range(1, 17):
                entities.append(
                    FelicityCellVoltageSensor(coordinator, sn, model, cell_idx)
                )

            # Add cell temperature sensors 1..4 (disabled by default)
            for temp_idx in range(1, 5):
                entities.append(
                    FelicityCellTemperatureSensor(coordinator, sn, model, temp_idx)
                )
    else:
        # If devices list doesn't explicitly return battery separately, attach to plant battery
        default_sn = f"battery_{coordinator.plant_id}"
        default_model = "Felicity Solar Battery"
        for desc in BATTERY_SENSORS:
            entities.append(FelicityBatterySensor(coordinator, desc, default_sn, default_model))

        for cell_idx in range(1, 17):
            entities.append(
                FelicityCellVoltageSensor(coordinator, default_sn, default_model, cell_idx)
            )
        for temp_idx in range(1, 5):
            entities.append(
                FelicityCellTemperatureSensor(coordinator, default_sn, default_model, temp_idx)
            )

    async_add_entities(entities)


class FelicityPlantSensor(CoordinatorEntity[FelicityDataUpdateCoordinator], SensorEntity):
    """Sensor for plant-wide PV and load telemetry."""

    entity_description: FelicitySensorEntityDescription

    def __init__(
        self,
        coordinator: FelicityDataUpdateCoordinator,
        description: FelicitySensorEntityDescription,
    ) -> None:
        """Initialize plant sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.plant_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{coordinator.plant_id}")},
            name=f"Felicity ESS ({coordinator.plant_name})",
            manufacturer=MANUFACTURER,
            model="Felicity Solar Plant",
        )

    @property
    def native_value(self) -> Any:
        """Return current sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)


class FelicityBatterySensor(CoordinatorEntity[FelicityDataUpdateCoordinator], SensorEntity):
    """Sensor for a Felicity battery pack."""

    entity_description: FelicitySensorEntityDescription

    def __init__(
        self,
        coordinator: FelicityDataUpdateCoordinator,
        description: FelicitySensorEntityDescription,
        device_sn: str,
        device_model: str,
    ) -> None:
        """Initialize battery sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_sn = device_sn
        self._attr_unique_id = f"{device_sn}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"Felicity Battery ({device_sn})",
            manufacturer=MANUFACTURER,
            model=device_model,
            via_device=(DOMAIN, f"plant_{coordinator.plant_id}"),
        )

    def _get_battery_data(self) -> dict[str, Any]:
        """Extract battery dict for this device."""
        # Check in coordinator devices
        dev = self.coordinator.devices.get(self._device_sn, {})
        # Merge with plant battery details
        details = self.coordinator.data.get("battery_details", {})
        merged = dict(details)
        merged.update(dev)
        return merged

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        b_data = self._get_battery_data()
        return self.entity_description.value_fn(b_data)


class FelicityCellVoltageSensor(CoordinatorEntity[FelicityDataUpdateCoordinator], SensorEntity):
    """Sensor for individual battery cell voltage."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False  # Disabled by default as agreed in debate

    def __init__(
        self,
        coordinator: FelicityDataUpdateCoordinator,
        device_sn: str,
        device_model: str,
        cell_index: int,
    ) -> None:
        """Initialize cell voltage sensor."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._cell_index = cell_index
        self._attr_unique_id = f"{device_sn}_cell_voltage_{cell_index}"
        self._attr_name = f"Cell {cell_index} Voltage"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"Felicity Battery ({device_sn})",
            manufacturer=MANUFACTURER,
            model=device_model,
            via_device=(DOMAIN, f"plant_{coordinator.plant_id}"),
        )

    @property
    def native_value(self) -> float | None:
        """Return cell voltage."""
        details = self.coordinator.data.get("battery_details", {})
        dev = self.coordinator.devices.get(self._device_sn, {})
        key = f"cellVolt{self._cell_index}"
        val = details.get(key) if key in details else dev.get(key)
        return safe_float(val)


class FelicityCellTemperatureSensor(CoordinatorEntity[FelicityDataUpdateCoordinator], SensorEntity):
    """Sensor for individual battery cell temperature."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False  # Disabled by default as agreed in debate

    def __init__(
        self,
        coordinator: FelicityDataUpdateCoordinator,
        device_sn: str,
        device_model: str,
        temp_index: int,
    ) -> None:
        """Initialize cell temperature sensor."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._temp_index = temp_index
        self._attr_unique_id = f"{device_sn}_cell_temp_{temp_index}"
        self._attr_name = f"Cell Temp {temp_index}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"Felicity Battery ({device_sn})",
            manufacturer=MANUFACTURER,
            model=device_model,
            via_device=(DOMAIN, f"plant_{coordinator.plant_id}"),
        )

    @property
    def native_value(self) -> float | None:
        """Return cell temperature."""
        details = self.coordinator.data.get("battery_details", {})
        dev = self.coordinator.devices.get(self._device_sn, {})
        key = f"cellTemp{self._temp_index}"
        val = details.get(key) if key in details else dev.get(key)
        return safe_float(val)
