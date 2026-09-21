"""DataUpdateCoordinator for the Felicity Solar ESS integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FelicityApiClient,
    FelicityAuthError,
    FelicityConnectionError,
    FelicityError,
)
from .const import DOMAIN, TOPOLOGY_UPDATE_INTERVAL_CYCLES

_LOGGER = logging.getLogger(__name__)


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Safely parse value to float."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Safely parse value to int."""
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


class FelicityDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Felicity Solar telemetry data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FelicityApiClient,
        plant_id: str,
        plant_name: str,
        update_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Felicity ESS {plant_name}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self.plant_id = str(plant_id)
        self.plant_name = plant_name
        self.devices: dict[str, dict[str, Any]] = {}
        self._topology_counter = 0

    async def _update_devices_inventory(self) -> None:
        """Fetch all devices connected to this plant and update internal dictionary."""
        try:
            device_list = await self.client.get_devices(self.plant_id)
            new_devices: dict[str, dict[str, Any]] = {}
            for dev in device_list:
                sn = dev.get("deviceSn")
                if sn:
                    new_devices[sn] = dev
            if new_devices:
                self.devices = new_devices
                _LOGGER.debug("Loaded %d devices for plant %s", len(self.devices), self.plant_id)
        except Exception as err:
            _LOGGER.warning("Could not refresh device inventory: %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch telemetry and status data from Felicity cloud."""
        try:
            # Refresh topology inventory periodically or on first load
            if not self.devices or self._topology_counter % TOPOLOGY_UPDATE_INTERVAL_CYCLES == 0:
                await self._update_devices_inventory()
            self._topology_counter += 1

            # Concurrently fetch battery details and realtime power telemetry
            battery_details_task = self.client.get_plant_battery_details(self.plant_id)
            realtime_task = self.client.get_storage_realtime_data(self.plant_id)

            battery_details, realtime_data = await asyncio.gather(
                battery_details_task,
                realtime_task,
                return_exceptions=True,
            )

            # Handle potential exceptions
            for res in (battery_details, realtime_data):
                if isinstance(res, FelicityAuthError):
                    raise ConfigEntryAuthFailed("Felicity authentication token expired or invalid") from res
                if isinstance(res, Exception):
                    raise UpdateFailed(f"Error communicating with Felicity API: {res}") from res

            # Construct consolidated state dictionary
            data: dict[str, Any] = {
                "plant_id": self.plant_id,
                "plant_name": self.plant_name,
                "devices": dict(self.devices),
                "battery_details": battery_details if isinstance(battery_details, dict) else {},
                "realtime": realtime_data if isinstance(realtime_data, dict) else {},
            }

            return data

        except ConfigEntryAuthFailed:
            raise
        except (FelicityConnectionError, FelicityError) as err:
            raise UpdateFailed(f"Failed to communicate with Felicity Cloud: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error updating Felicity ESS: {err}") from err
