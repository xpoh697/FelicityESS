"""Binary sensor platform for Felicity Solar ESS."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEVICE_TYPE_BATTERY,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import FelicityDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Felicity ESS binary sensors."""
    coordinator: FelicityDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[BinarySensorEntity] = [
        FelicityPlantOnlineBinarySensor(coordinator),
    ]

    devices = coordinator.devices
    battery_devices = [
        dev for dev in devices.values() if dev.get("deviceType") == DEVICE_TYPE_BATTERY
    ]

    if battery_devices:
        for b_dev in battery_devices:
            sn = str(b_dev.get("deviceSn"))
            model = b_dev.get("deviceModel", "Felicity Battery")
            entities.extend([
                FelicityBatteryOnlineBinarySensor(coordinator, sn, model),
                FelicityBatteryProblemBinarySensor(coordinator, sn, model),
            ])
    else:
        default_sn = f"battery_{coordinator.plant_id}"
        default_model = "Felicity Solar Battery"
        entities.extend([
            FelicityBatteryOnlineBinarySensor(coordinator, default_sn, default_model),
            FelicityBatteryProblemBinarySensor(coordinator, default_sn, default_model),
        ])

    async_add_entities(entities)


class FelicityPlantOnlineBinarySensor(
    CoordinatorEntity[FelicityDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for overall plant online status."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "plant_online"
    _attr_name = "Plant Online"

    def __init__(self, coordinator: FelicityDataUpdateCoordinator) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.plant_id}_plant_online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{coordinator.plant_id}")},
            name=f"Felicity ESS ({coordinator.plant_name})",
            manufacturer=MANUFACTURER,
            model="Felicity Solar Plant",
        )

    @property
    def is_on(self) -> bool:
        """Return True if plant has received recent data."""
        # Coordinator is available and has data
        return bool(self.coordinator.data and self.coordinator.last_update_success)


class FelicityBatteryOnlineBinarySensor(
    CoordinatorEntity[FelicityDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for battery communication status."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "battery_online"
    _attr_name = "Battery Online"

    def __init__(
        self,
        coordinator: FelicityDataUpdateCoordinator,
        device_sn: str,
        device_model: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"{device_sn}_battery_online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"Felicity Battery ({device_sn})",
            manufacturer=MANUFACTURER,
            model=device_model,
            via_device=(DOMAIN, f"plant_{coordinator.plant_id}"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if battery is online."""
        dev = self.coordinator.devices.get(self._device_sn, {})
        status = dev.get("status")
        # In Fsolar status is "1" or 1 when online
        return str(status) in ("1", "online", "true", "True")


class FelicityBatteryProblemBinarySensor(
    CoordinatorEntity[FelicityDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for BMS alarm/fault state."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "battery_problem"
    _attr_name = "Battery Alarm"

    def __init__(
        self,
        coordinator: FelicityDataUpdateCoordinator,
        device_sn: str,
        device_model: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"{device_sn}_battery_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"Felicity Battery ({device_sn})",
            manufacturer=MANUFACTURER,
            model=device_model,
            via_device=(DOMAIN, f"plant_{coordinator.plant_id}"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if any alarm or warning is active."""
        details = self.coordinator.data.get("battery_details", {})
        dev = self.coordinator.devices.get(self._device_sn, {})
        bms_state = details.get("bmsState") or dev.get("bmsState")
        # Normal states are usually 0 or None; anything non-zero signals alarm
        if bms_state is not None:
            try:
                return int(bms_state) != 0
            except (ValueError, TypeError):
                return str(bms_state).lower() not in ("normal", "ok", "0", "")
        return False
