"""Async API client for Felicity Solar ESS cloud service."""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

from .const import (
    API_BASE_URL,
    API_PATH_LIST_DEVICE,
    API_PATH_LIST_PLANT,
    API_PATH_LOGIN,
    API_PATH_PLANT_DETAILS_BATTERY,
    API_PATH_STORAGE_REALTIME,
    APP_VERSION,
    RSA_PUBLIC_KEY_B64,
    SOURCE_ANDROID,
)

_LOGGER = logging.getLogger(__name__)


class FelicityError(Exception):
    """Base exception for Felicity ESS."""


class FelicityAuthError(FelicityError):
    """Authentication failed or token expired."""


class FelicityConnectionError(FelicityError):
    """Connection or timeout error."""


class FelicityApiError(FelicityError):
    """API returned an error code."""


def encrypt_password(password: str) -> str:
    """Encrypt password using Felicity RSA 2048-bit public key (PKCS1v15 padding)."""
    try:
        der_bytes = base64.b64decode(RSA_PUBLIC_KEY_B64)
        public_key = load_der_public_key(der_bytes)
        encrypted = public_key.encrypt(
            password.encode("utf-8"),
            padding.PKCS1v15(),
        )
        return base64.b64encode(encrypted).decode("ascii")
    except Exception as err:
        _LOGGER.error("Failed to encrypt password: %s", err)
        raise FelicityError(f"Password encryption failed: {err}") from err


class FelicityApiClient:
    """Felicity Solar Cloud API Client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        base_url: str = API_BASE_URL,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._user_id: str | None = None
        self._auth_lock = asyncio.Lock()

    @property
    def token(self) -> str | None:
        """Return the current auth token."""
        return self._token

    @property
    def user_id(self) -> str | None:
        """Return the user ID."""
        return self._user_id

    def _get_headers(self) -> dict[str, str]:
        """Build standard headers expected by the Fsolar cloud API."""
        headers = {
            "source": SOURCE_ANDROID,
            "version": APP_VERSION,
            "lang": "en",
            "Content-Type": "application/json; charset=utf-8",
        }
        if self._token:
            headers["token"] = self._token
        return headers

    async def login(self) -> str:
        """Authenticate with username and password, returning token."""
        async with self._auth_lock:
            return await self._login_unlocked()

    async def _login_unlocked(self) -> str:
        """Internal login implementation holding the lock."""
        encrypted_pwd = encrypt_password(self._password)
        payload = {
            "userName": self._username,
            "password": encrypted_pwd,
            "version": "1.0",
            "registrationId": "",
        }
        url = f"{self._base_url}{API_PATH_LOGIN}"

        try:
            async with asyncio.timeout(15):
                async with self._session.post(
                    url,
                    json=payload,
                    headers={
                        "source": SOURCE_ANDROID,
                        "version": APP_VERSION,
                        "lang": "en",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                ) as resp:
                    if resp.status != 200:
                        raise FelicityConnectionError(
                            f"HTTP {resp.status} while attempting login: {await resp.text()}"
                        )
                    data = await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise FelicityConnectionError("Timeout during login to Felicity cloud") from err
        except aiohttp.ClientError as err:
            raise FelicityConnectionError(f"Connection error during login: {err}") from err

        code = data.get("code")
        if code != 200:
            msg = data.get("msg") or "Authentication failed"
            raise FelicityAuthError(f"Login failed (code {code}): {msg}")

        user_data = data.get("data", {})
        token = user_data.get("token")
        if not token:
            raise FelicityAuthError("API response did not contain an auth token")

        self._token = token
        self._user_id = str(user_data.get("id", ""))
        _LOGGER.debug("Successfully logged in to Felicity Cloud as %s", self._username)
        return token

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        """Send authenticated API request with auto token refresh on 3001/401."""
        if not self._token:
            await self.login()

        url = f"{self._base_url}{path}"
        headers = self._get_headers()

        try:
            async with asyncio.timeout(15):
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_data,
                ) as resp:
                    if resp.status == 401 and retry_auth:
                        _LOGGER.debug("Token expired (HTTP 401). Re-authenticating...")
                        await self.login()
                        return await self.request(
                            method,
                            path,
                            params=params,
                            json_data=json_data,
                            retry_auth=False,
                        )

                    if resp.status != 200:
                        raise FelicityConnectionError(
                            f"HTTP {resp.status} on {path}: {await resp.text()}"
                        )

                    body = await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise FelicityConnectionError(f"Timeout requesting {path}") from err
        except aiohttp.ClientError as err:
            raise FelicityConnectionError(f"Network error on {path}: {err}") from err

        code = body.get("code")
        # Felicity code 3001: token invalid / expired
        if code in (3001, 401) and retry_auth:
            _LOGGER.debug("API returned auth expired code %s on %s. Re-authenticating...", code, path)
            await self.login()
            return await self.request(
                method,
                path,
                params=params,
                json_data=json_data,
                retry_auth=False,
            )

        if code != 200:
            msg = body.get("msg") or f"API error code {code}"
            if code in (3001, 401):
                raise FelicityAuthError(f"Unauthorized: {msg}")
            raise FelicityApiError(f"API call to {path} returned code {code}: {msg}")

        return body.get("data")

    async def get_plants(self) -> list[dict[str, Any]]:
        """Retrieve list of solar power plants."""
        data = await self.request(
            "POST",
            API_PATH_LIST_PLANT,
            json_data={"pageNum": 1, "pageSize": 50},
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("list", []) or []
        return []

    async def get_devices(self, plant_id: str) -> list[dict[str, Any]]:
        """Retrieve all devices connected to the given plant."""
        data = await self.request(
            "POST",
            API_PATH_LIST_DEVICE,
            json_data={
                "plantId": plant_id,
                "pageNum": 1,
                "pageSize": 50,
                "deviceType": "ALL",
            },
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("list", []) or []
        return []

    async def get_plant_battery_details(self, plant_id: str) -> dict[str, Any]:
        """Retrieve battery telemetry and cell info for a plant."""
        data = await self.request(
            "POST",
            API_PATH_PLANT_DETAILS_BATTERY,
            json_data={"id": plant_id},
        )
        if isinstance(data, dict):
            return data
        return {}

    async def get_storage_realtime_data(self, plant_id: str) -> dict[str, Any]:
        """Retrieve real-time PV and storage power telemetry."""
        data = await self.request(
            "GET",
            API_PATH_STORAGE_REALTIME,
            params={"plantId": plant_id},
        )
        if isinstance(data, dict):
            return data
        return {}
