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
from .local_client import (
    FelicityLocalClient,
    FelicityLocalConnectionError,
    FelicityLocalError,
    FelicityLocalProtocolError,
    FelicityLocalTimeoutError,
)
from .profiles import BatteryProfile, select_profile

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


class FelicityLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for direct local TCP monitoring of Felicity Solar batteries."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FelicityLocalClient,
        host: str,
        port: int,
        update_interval: int,
        invert_current: bool = False,
        dev_sn: str = "",
    ) -> None:
        """Initialize the local TCP coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"Felicity ESS Local ({host})",
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self.host = host
        self.port = port
        self.invert_current = invert_current
        self.dev_sn = dev_sn
        self.profile: BatteryProfile | None = None
        self._tz_offset_minutes: int | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch telemetry from the battery via local TCP."""
        try:
            # Query timezone offset once per coordinator lifecycle (best-effort)
            if self._tz_offset_minutes is None:
                try:
                    self._tz_offset_minutes = await self.client.async_get_timezone_offset_minutes()
                except Exception as err:
                    _LOGGER.debug("Could not fetch device timezone offset from %s: %s", self.host, err)

            raw = await self.client.async_get_data()

            if self._tz_offset_minutes is not None:
                raw["timeZMin"] = self._tz_offset_minutes

            if self.profile is None:
                self.profile = select_profile(raw)
                _LOGGER.info(
                    "Selected profile '%s' (confidence: %s) for battery at %s",
                    self.profile.name,
                    self.profile.confidence,
                    self.host,
                )

            parsed = self.profile.parse(raw)

            # Invert current sign if requested
            if self.invert_current and parsed.get("current") is not None:
                parsed["current"] = -parsed["current"]
                if parsed.get("power") is not None and parsed.get("voltage") is not None:
                    parsed["power"] = round(parsed["voltage"] * parsed["current"], 1)

            sn = parsed.get("serial_number") or raw.get("DevSN") or raw.get("wifiSN")
            if sn and not self.dev_sn:
                self.dev_sn = str(sn)

            return {
                "parsed": parsed,
                "raw": raw,
                "profile_name": self.profile.name,
                "serial_number": self.dev_sn or self.host,
            }

        except FelicityLocalTimeoutError as err:
            raise UpdateFailed(f"Timeout communicating with battery at {self.host}:{self.port}") from err
        except FelicityLocalConnectionError as err:
            raise UpdateFailed(f"Connection failed to battery at {self.host}:{self.port}: {err}") from err
        except FelicityLocalProtocolError as err:
            raise UpdateFailed(f"Protocol error from battery at {self.host}:{self.port}: {err}") from err
        except FelicityLocalError as err:
            raise UpdateFailed(f"Error communicating with battery at {self.host}:{self.port}: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error updating Felicity local battery: {err}") from err


class FelicityDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching Felicity Solar telemetry data from Cloud API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: FelicityApiClient,
        plant_id: str,
        plant_name: str,
        update_interval: int,
    ) -> None:
        """Initialize the cloud coordinator."""
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
