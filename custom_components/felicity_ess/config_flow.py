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
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_INVERT_CURRENT,
    CONF_PASSWORD,
    CONF_PLANT_ID,
    CONF_PLANT_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_LOCAL,
    DEFAULT_INVERT_CURRENT,
    DEFAULT_LOCAL_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .local_client import (
    FelicityLocalClient,
    FelicityLocalConnectionError,
    FelicityLocalError,
    FelicityLocalProtocolError,
    FelicityLocalTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


def map_auth_error(err: FelicityAuthError) -> str:
    """Map API error code to translation key."""
    if err.code == 1002001:
        return "user_not_found"
    if err.code == 1002002:
        return "invalid_password"
    if err.code == 10010027:
        return "rsa_error"
    return "invalid_auth"


class FelicityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Felicity Solar ESS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._connection_type: str = CONNECTION_TYPE_LOCAL
        self._username: str | None = None
        self._password: str | None = None
        self._plants: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle first step: select between Local TCP connection and Felicity Cloud."""
        if user_input is not None:
            conn_type = user_input[CONF_CONNECTION_TYPE]
            self._connection_type = conn_type
            if conn_type == CONNECTION_TYPE_LOCAL:
                return await self.async_step_local()
            return await self.async_step_cloud()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONNECTION_TYPE,
                        default=CONNECTION_TYPE_LOCAL,
                    ): vol.In(
                        {
                            CONNECTION_TYPE_LOCAL: "local",
                            CONNECTION_TYPE_CLOUD: "cloud",
                        }
                    ),
                }
            ),
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle direct local TCP configuration for battery."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            invert_current = bool(user_input.get(CONF_INVERT_CURRENT, DEFAULT_INVERT_CURRENT))
            scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_LOCAL_SCAN_INTERVAL))

            # Validate connection directly to the battery TCP port
            client = FelicityLocalClient(host, port, timeout=5.0, persistent=False)
            try:
                data = await client.async_get_data()
            except FelicityLocalTimeoutError:
                errors["base"] = "timeout"
            except FelicityLocalConnectionError:
                errors["base"] = "cannot_connect"
            except FelicityLocalProtocolError:
                errors["base"] = "protocol_error"
            except FelicityLocalError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error connecting to battery at %s:%s", host, port)
                errors["base"] = "unknown"
            else:
                dev_sn = str(data.get("DevSN") or data.get("wifiSN") or host)
                await self.async_set_unique_id(f"felicity_local_{dev_sn}")
                self._abort_if_unique_id_configured()

                title = f"Felicity Battery ({host})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_INVERT_CURRENT: invert_current,
                        CONF_SCAN_INTERVAL: scan_interval,
                        "serial_number": dev_sn,
                    },
                )

        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_INVERT_CURRENT, default=DEFAULT_INVERT_CURRENT): bool,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_LOCAL_SCAN_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=MAX_SCAN_INTERVAL)),
                }
            ),
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Felicity Cloud authentication step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD].strip()

            session = async_get_clientsession(self.hass)
            client = FelicityApiClient(session, username, password)

            try:
                await client.login()
                plants = await client.get_plants()
            except FelicityAuthError as err:
                _LOGGER.warning("Felicity login failed for '%s': %s (code %s)", username, err, err.code)
                errors["base"] = map_auth_error(err)
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
                            CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD,
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
            step_id="cloud",
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
        """Handle selection of a plant when multiple exist in cloud account."""
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
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD,
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
            except FelicityAuthError as err:
                _LOGGER.warning("Felicity reauth failed: %s (code %s)", err, err.code)
                errors["base"] = map_auth_error(err)
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

        is_local = self.config_entry.data.get(CONF_CONNECTION_TYPE) == CONNECTION_TYPE_LOCAL or CONF_HOST in self.config_entry.data

        default_interval = DEFAULT_LOCAL_SCAN_INTERVAL if is_local else DEFAULT_SCAN_INTERVAL
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, default_interval),
        )

        schema_dict: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current_interval,
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
            ),
        }

        if is_local:
            current_invert = self.config_entry.options.get(
                CONF_INVERT_CURRENT,
                self.config_entry.data.get(CONF_INVERT_CURRENT, DEFAULT_INVERT_CURRENT),
            )
            schema_dict[
                vol.Optional(
                    CONF_INVERT_CURRENT,
                    default=current_invert,
                )
            ] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
