"""Battery model profiles and register scaling for Felicity Solar ESS.

Provides model-specific decoding, scaling and validation for direct local TCP packets.
Verified models:
- FLB48314TG1-H (Type=112, SubType=7353): 48V 16S, 2x2 temperature matrix.
- FLA24100 (Type=112, SubType=6100): 24V 8S, temperatures in BtemList.
- FLA48300 (Type=112, SubType=7300): 48V 16S with BmsCnt (cycle count).
- Generic fallback for unverified / newer models.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

try:
    import homeassistant.util.dt as dt_util
    DEFAULT_TZ = dt_util.DEFAULT_TIME_ZONE
except ImportError:
    DEFAULT_TZ = timezone.utc

_LOGGER = logging.getLogger(__name__)

# Sentinels used by battery firmware for unpopulated channels
_SENTINELS = (None, 65535, -1, 32767)

CELL_COUNT = 16

# Bstate bitmask flags
_BSTATE_DISCHARGING_BIT = 1 << 12
_BSTATE_CHARGING_BIT = 1 << 13


def _path(data: dict[str, Any], key: str, row: int, col: int) -> Any:
    """Safely extract data[key][row][col], filtering out sentinel values."""
    try:
        value = data[key][row][col]
    except (KeyError, IndexError, TypeError):
        return None
    return None if value in _SENTINELS else value


def _scaled(
    data: dict[str, Any], key: str, row: int, col: int, divisor: float, precision: int = 3
) -> float | None:
    """Extract and scale raw register value, returning None if sentinel or missing."""
    value = _path(data, key, row, col)
    if value is None:
        return None
    return round(value / divisor, precision)


def _raw(data: dict[str, Any], key: str) -> Any:
    """Extract top-level key value, returning None if sentinel or missing."""
    value = data.get(key)
    return None if value in _SENTINELS else value


def _charging_state(bstate: Any) -> str | None:
    """Decode charging/discharging/standby state from Bstate bitmask."""
    if not isinstance(bstate, int):
        return None
    if bstate & _BSTATE_CHARGING_BIT:
        return "charging"
    if bstate & _BSTATE_DISCHARGING_BIT:
        return "discharging"
    return "standby"


def _device_timestamp(raw: dict[str, Any]) -> datetime | None:
    """Parse device's self-reported date string (YYYYMMDDHHMMSS)."""
    date_value = raw.get("date")
    if not isinstance(date_value, str) or len(date_value) != 14 or not date_value.isdigit():
        return None
    try:
        naive = datetime.strptime(date_value, "%Y%m%d%H%M%S")
    except ValueError:
        return None

    offset_minutes = raw.get("timeZMin")
    tzinfo = (
        timezone(timedelta(minutes=offset_minutes))
        if isinstance(offset_minutes, int)
        else DEFAULT_TZ
    )
    return naive.replace(tzinfo=tzinfo)


def parse_common(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse common telemetry registers for Felicity battery packs."""
    voltage = _scaled(raw, "BattList", 0, 0, 1000, 2)
    if voltage is None:
        voltage = _scaled(raw, "Batt", 0, 0, 1000, 2)

    current = _scaled(raw, "BattList", 1, 0, 10, 1)
    if current is None:
        current = _scaled(raw, "Batt", 1, 0, 10, 1)

    bstate = _raw(raw, "Bstate")

    # Temperatures for FLB48314 / standard 2x2 matrix
    temp_1 = _scaled(raw, "BTemp", 0, 0, 10, 1)
    temp_2 = _scaled(raw, "BTemp", 0, 1, 10, 1)
    temp_3 = _scaled(raw, "BTemp", 1, 0, 10, 1)
    temp_4 = _scaled(raw, "BTemp", 1, 1, 10, 1)
    valid_temps = [t for t in (temp_1, temp_2, temp_3, temp_4) if t is not None]

    data: dict[str, Any] = {
        "voltage": voltage,
        "current": current,
        "power": round(voltage * current, 1) if voltage is not None and current is not None else None,
        "charging_state": _charging_state(bstate),
        "soc": _scaled(raw, "BatsocList", 0, 0, 100, 1),
        "soh": _scaled(raw, "BatsocList", 0, 1, 10, 1),
        "capacity": _scaled(raw, "BatsocList", 0, 2, 1000, 1),
        "cycle_count": _raw(raw, "BmsCnt"),
        "max_cell_voltage": _scaled(raw, "BMaxMin", 0, 0, 1000, 3),
        "min_cell_voltage": _scaled(raw, "BMaxMin", 0, 1, 1000, 3),
        "max_cell_number": _path(raw, "BMaxMin", 1, 0),
        "min_cell_number": _path(raw, "BMaxMin", 1, 1),
        "temperature_1": temp_1,
        "temperature_2": temp_2,
        "temperature_3": temp_3,
        "temperature_4": temp_4,
        "temperature_max": max(valid_temps) if valid_temps else None,
        "temperature_min": min(valid_temps) if valid_temps else None,
        "charge_voltage_limit": _scaled(raw, "BLVolCu", 0, 0, 10, 1),
        "discharge_voltage_limit": _scaled(raw, "BLVolCu", 0, 1, 10, 1),
        "charge_current_limit": _scaled(raw, "BLVolCu", 1, 0, 10, 1),
        "discharge_current_limit": _scaled(raw, "BLVolCu", 1, 1, 10, 1),
        "serial_number": _raw(raw, "DevSN") or _raw(raw, "wifiSN"),
        "wifi_sn": _raw(raw, "wifiSN"),
        "device_timestamp": _device_timestamp(raw),
        "estate": _raw(raw, "Estate"),
        "state": bstate,
        "fault": _raw(raw, "Bfault"),
        "warning": _raw(raw, "Bwarn"),
        "bms_fault": _raw(raw, "BBfault"),
        "bms_warning": _raw(raw, "BBwarn"),
    }

    # Extract 16 individual cell voltages
    for i in range(CELL_COUNT):
        data[f"cell_{i + 1}_voltage"] = _scaled(raw, "BatcelList", 0, i, 1000, 3)

    return data


def parse_fla24100(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse for FLA24100 (Type=112, SubType=6100) - 24V 8S pack."""
    data = parse_common(raw)
    # FLA24100 uses BtemList for actual temperature probes
    temperatures: list[float] = []
    for i in range(4):
        val = _scaled(raw, "BtemList", 0, i, 10, 1)
        data[f"temperature_{i + 1}"] = val
        if val is not None:
            temperatures.append(val)
    data["temperature_max"] = max(temperatures) if temperatures else None
    data["temperature_min"] = min(temperatures) if temperatures else None
    return data


@dataclass(frozen=True)
class BatteryProfile:
    """Field mapping and scaling configuration for a Felicity battery model."""

    name: str
    confidence: str  # "verified" or "best_effort"
    type_code: int | None
    subtype_code: int | None
    parse: Callable[[dict[str, Any]], dict[str, Any]] = field(default=parse_common)

    def matches(self, raw: dict[str, Any]) -> bool:
        """Check whether profile matches device Type and SubType."""
        if self.type_code is None:
            return True
        return raw.get("Type") == self.type_code and raw.get("SubType") == self.subtype_code


FLB48314TG1H_PROFILE = BatteryProfile(
    name="FLB48314TG1-H",
    confidence="verified",
    type_code=112,
    subtype_code=7353,
)

FLA24100_PROFILE = BatteryProfile(
    name="FLA24100",
    confidence="verified",
    type_code=112,
    subtype_code=6100,
    parse=parse_fla24100,
)

FLA48300_PROFILE = BatteryProfile(
    name="FLA48300",
    confidence="verified",
    type_code=112,
    subtype_code=7300,
)

DEFAULT_PROFILE = BatteryProfile(
    name="Generic Felicity Solar Battery",
    confidence="best_effort",
    type_code=None,
    subtype_code=None,
)

PROFILES: tuple[BatteryProfile, ...] = (
    FLB48314TG1H_PROFILE,
    FLA24100_PROFILE,
    FLA48300_PROFILE,
)


def select_profile(raw: dict[str, Any]) -> BatteryProfile:
    """Select best-matching battery profile for raw device response."""
    for profile in PROFILES:
        if profile.matches(raw):
            return profile
    return DEFAULT_PROFILE
