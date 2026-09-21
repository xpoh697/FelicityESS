"""Config flow for Felicity Solar ESS integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    FelicityApiClient,
    FelicityAuthError,
    FelicityConnectionError,
    FelicityError,
)
from .const import (
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class FelicityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Felicity Solar ESS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._username: str | None = None
        self._password: str | None = None
        self._plants: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial user authentication step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD].strip()

            session = async_get_clientsession(self.hass)
            client = FelicityApiClient(session, username, password)

            try:
                await client.login()
                plants = await client.get_plants()
            except FelicityAuthError:
                errors["base"] = "invalid_auth"
            except (FelicityConnectionError, FelicityError):
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error during Felicity auth")
                errors["base"] = "unknown"
            else:
                if not plants:
                    errors["base"] = "no_plants"
                elif len(plants) == 1:
                    plant = plants[0]
                    plant_id = str(plant.get("plantId") or plant.get("id"))
                    plant_name = plant.get("plantName") or "Felicity Plant"

                    await self.async_set_unique_id(f"felicity_ess_{plant_id}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"Felicity ESS ({plant_name})",
                        data={
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_PLANT_ID: plant_id,
                            CONF_PLANT_NAME: plant_name,
                        },
                    )
                else:
                    self._username = username
                    self._password = password
                    self._plants = plants
                    return await self.async_step_plant()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle selection of a plant when multiple exist."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_id = str(user_input[CONF_PLANT_ID])
            selected_plant = next(
                (p for p in self._plants if str(p.get("plantId") or p.get("id")) == selected_id),
                None,
            )
            plant_name = selected_plant.get("plantName", f"Plant {selected_id}") if selected_plant else selected_id

            await self.async_set_unique_id(f"felicity_ess_{selected_id}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Felicity ESS ({plant_name})",
                data={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_PLANT_ID: selected_id,
                    CONF_PLANT_NAME: plant_name,
                },
            )

        plants_map = {
            str(p.get("plantId") or p.get("id")): p.get("plantName") or f"Plant {p.get('plantId')}"
            for p in self._plants
        }

        return self.async_show_form(
            step_id="plant",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PLANT_ID): vol.In(plants_map),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauthentication request from coordinator."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm re-authentication dialog."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None and entry:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD].strip()

            session = async_get_clientsession(self.hass)
            client = FelicityApiClient(session, username, password)

            try:
                await client.login()
            except FelicityAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        current_username = entry.data.get(CONF_USERNAME, "") if entry else ""

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=current_username): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FelicityOptionsFlowHandler:
        """Get options flow handler."""
        return FelicityOptionsFlowHandler(config_entry)


class FelicityOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Felicity ESS."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
