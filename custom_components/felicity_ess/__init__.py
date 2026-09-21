"""The Felicity Solar ESS integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FelicityApiClient
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_INVERT_CURRENT,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CONNECTION_TYPE_LOCAL,
    DEFAULT_INVERT_CURRENT,
    DEFAULT_LOCAL_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import FelicityDataUpdateCoordinator, FelicityLocalCoordinator
from .local_client import FelicityLocalClient

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Felicity ESS component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Felicity ESS from a config entry."""
    conn_type = entry.data.get(CONF_CONNECTION_TYPE)
    is_local = conn_type == CONNECTION_TYPE_LOCAL or CONF_HOST in entry.data

    if is_local:
        host = entry.data[CONF_HOST]
        port = int(entry.data.get(CONF_PORT, DEFAULT_PORT))
        invert_current = bool(
            entry.options.get(
                CONF_INVERT_CURRENT,
                entry.data.get(CONF_INVERT_CURRENT, DEFAULT_INVERT_CURRENT),
            )
        )
        scan_interval = int(
            entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_LOCAL_SCAN_INTERVAL),
            )
        )
        dev_sn = entry.data.get("serial_number", host)

        client = FelicityLocalClient(host, port, timeout=5.0, persistent=True)
        coordinator = FelicityLocalCoordinator(
            hass=hass,
            client=client,
            host=host,
            port=port,
            update_interval=scan_interval,
            invert_current=invert_current,
            dev_sn=dev_sn,
        )

        await coordinator.async_config_entry_first_refresh()

        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "client": client,
            "type": CONNECTION_TYPE_LOCAL,
        }
    else:
        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        plant_id = entry.data[CONF_PLANT_ID]
        plant_name = entry.data.get(CONF_PLANT_NAME, f"Plant {plant_id}")

        scan_interval = int(
            entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )
        )

        session = async_get_clientsession(hass)
        client = FelicityApiClient(session, username, password)

        coordinator = FelicityDataUpdateCoordinator(
            hass=hass,
            client=client,
            plant_id=plant_id,
            plant_name=plant_name,
            update_interval=scan_interval,
        )

        await coordinator.async_config_entry_first_refresh()

        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "client": client,
            "type": "cloud",
        }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        client = entry_data.get("client")
        if client and hasattr(client, "async_close"):
            try:
                await client.async_close()
            except Exception as err:
                _LOGGER.debug("Error closing client connection: %s", err)

    return unload_ok
