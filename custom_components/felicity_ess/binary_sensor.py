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
from .coordinator import FelicityDataUpdateCoordinator, FelicityLocalCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Felicity ESS binary sensors."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = entry_data["coordinator"]

    entities: list[BinarySensorEntity] = []

    # Local TCP mode
    if isinstance(coordinator, FelicityLocalCoordinator):
        dev_sn = coordinator.dev_sn or coordinator.host
        model = coordinator.profile.name if coordinator.profile else "Felicity Solar Battery"
        entities.extend([
            FelicityLocalBatteryOnlineBinarySensor(coordinator, dev_sn, model),
            FelicityLocalBatteryProblemBinarySensor(coordinator, dev_sn, model),
        ])
        async_add_entities(entities)
        return

    # Cloud mode
    assert isinstance(coordinator, FelicityDataUpdateCoordinator)
    entities.append(FelicityPlantOnlineBinarySensor(coordinator))

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


# =========================================================================
# Local Entity Classes
# =========================================================================

class FelicityLocalBatteryOnlineBinarySensor(
    CoordinatorEntity[FelicityLocalCoordinator], BinarySensorEntity
):
    """Binary sensor for local battery connectivity status."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "battery_online"
    _attr_name = "Battery Online"

    def __init__(
        self,
        coordinator: FelicityLocalCoordinator,
        device_sn: str,
        device_model: str,
    ) -> None:
        """Initialize local binary sensor."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"local_{device_sn}_battery_online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"Felicity Battery ({device_sn})",
            manufacturer=MANUFACTURER,
            model=device_model,
        )

    @property
    def is_on(self) -> bool:
        """Return True if battery response was received successfully."""
        return bool(self.coordinator.data and self.coordinator.last_update_success)


class FelicityLocalBatteryProblemBinarySensor(
    CoordinatorEntity[FelicityLocalCoordinator], BinarySensorEntity
):
    """Binary sensor for BMS alarm/fault states via local TCP."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "battery_problem"
    _attr_name = "Battery Alarm"

    def __init__(
        self,
        coordinator: FelicityLocalCoordinator,
        device_sn: str,
        device_model: str,
    ) -> None:
        """Initialize local problem sensor."""
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._attr_unique_id = f"local_{device_sn}_battery_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_sn)},
            name=f"Felicity Battery ({device_sn})",
            manufacturer=MANUFACTURER,
            model=device_model,
        )

    @property
    def is_on(self) -> bool:
        """Return True if any fault or warning register is non-zero."""
        parsed = self.coordinator.data.get("parsed", {})
        fault = parsed.get("fault") or 0
        warning = parsed.get("warning") or 0
        bms_fault = parsed.get("bms_fault") or 0
        bms_warning = parsed.get("bms_warning") or 0
        return any(v != 0 for v in (fault, warning, bms_fault, bms_warning) if isinstance(v, (int, float)))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return raw fault and warning register values."""
        parsed = self.coordinator.data.get("parsed", {})
        return {
            "fault": parsed.get("fault"),
            "warning": parsed.get("warning"),
            "bms_fault": parsed.get("bms_fault"),
            "bms_warning": parsed.get("bms_warning"),
        }


# =========================================================================
# Cloud Entity Classes
# =========================================================================

class FelicityPlantOnlineBinarySensor(
    CoordinatorEntity[FelicityDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for overall plant online status (Cloud)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "plant_online"
    _attr_name = "Plant Online"

    def __init__(self, coordinator: FelicityDataUpdateCoordinator) -> None:
        """Initialize plant binary sensor."""
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
        return bool(self.coordinator.data and self.coordinator.last_update_success)


class FelicityBatteryOnlineBinarySensor(
    CoordinatorEntity[FelicityDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for battery communication status (Cloud)."""

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
        """Initialize battery binary sensor."""
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
        return str(status) in ("1", "online", "true", "True")


class FelicityBatteryProblemBinarySensor(
    CoordinatorEntity[FelicityDataUpdateCoordinator], BinarySensorEntity
):
    """Binary sensor for BMS alarm/fault state (Cloud)."""

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
        if bms_state is not None:
            try:
                return int(bms_state) != 0
            except (ValueError, TypeError):
                return str(bms_state).lower() not in ("normal", "ok", "0", "")
        return False
