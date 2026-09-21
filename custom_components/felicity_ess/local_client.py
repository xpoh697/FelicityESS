"""TCP/JSON client for the Felicity Solar battery local WiFi/LAN protocol.

Direct local communication over port 53970 without cloud dependency.
- Plain TCP on port 53970, no TLS, no Modbus framing.
- ASCII command: `wifilocalMonitor:get dev real infor`.
- Response is a single JSON object terminated by `}`.
- Acknowledgement: client sends single byte `.` (`b"."`).
- Timezone command: `wifilocalMonitor:get Date` returning `{"dateTime": ..., "timeZMin": ...}`.
- Serialized by single asyncio.Lock to protect battery microcontroller (ESP/lwIP) from concurrent sockets.
- Persistent socket with SO_KEEPALIVE and buffer flush to maximize stability.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
from typing import Any

from .const import (
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    LOCAL_ACK_BYTE,
    LOCAL_DATE_QUERY_COMMAND,
    LOCAL_QUERY_COMMAND,
    STRAY_BYTES_FLUSH_TIMEOUT,
    TCP_KEEPALIVE_COUNT,
    TCP_KEEPALIVE_IDLE,
    TCP_KEEPALIVE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class FelicityLocalError(Exception):
    """Base error for the Felicity Solar local client."""


class FelicityLocalConnectionError(FelicityLocalError):
    """Raised when the TCP connection to the battery cannot be established."""


class FelicityLocalTimeoutError(FelicityLocalError):
    """Raised when the battery does not respond within the configured timeout."""


class FelicityLocalProtocolError(FelicityLocalError):
    """Raised when the battery's response is not valid/usable JSON."""


def _extract_path(data: dict[str, Any], path: tuple[str, int, int]) -> Any:
    """Safely extract nested list value data[key][row][col]."""
    key, row, col = path
    try:
        return data[key][row][col]
    except (KeyError, IndexError, TypeError):
        return None


class FelicityLocalClient:
    """Async client for a single Felicity Solar battery's local TCP endpoint."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        persistent: bool = True,
    ) -> None:
        """Initialize local client."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.persistent = persistent
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def async_get_data(self) -> dict[str, Any]:
        """Query the battery and return the parsed JSON payload."""
        async with self._lock:
            attempts = 2 if self.persistent else 1
            last_err: FelicityLocalError | None = None
            for attempt in range(attempts):
                try:
                    await self._ensure_connected()
                    data = await self._query(LOCAL_QUERY_COMMAND)
                    self._validate(data)
                except FelicityLocalError as err:
                    last_err = err
                    _LOGGER.debug(
                        "Attempt %d/%d failed for %s:%s: %s",
                        attempt + 1,
                        attempts,
                        self.host,
                        self.port,
                        err,
                    )
                    await self._disconnect()
                    continue

                if not self.persistent:
                    await self._disconnect()
                return data

            assert last_err is not None
            raise last_err

    async def async_close(self) -> None:
        """Close the connection, if any. Safe to call anytime."""
        async with self._lock:
            await self._disconnect()

    async def async_get_timezone_offset_minutes(self) -> int | None:
        """Query the device's self-reported UTC offset (wifilocalMonitor:get Date)."""
        async with self._lock:
            try:
                await self._ensure_connected()
                data = await self._query(LOCAL_DATE_QUERY_COMMAND)
            except FelicityLocalError:
                await self._disconnect()
                return None

            if not self.persistent:
                await self._disconnect()

        offset = data.get("timeZMin") if isinstance(data, dict) else None
        return offset if isinstance(offset, int) else None

    async def _ensure_connected(self) -> None:
        """Reuse cached persistent connection if alive, else open a fresh one."""
        if self._writer is None or self._writer.is_closing():
            await self._connect()
        elif self.persistent:
            await self._flush_stray_bytes()

    async def _connect(self) -> None:
        """Establish direct TCP stream connection to battery."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except TimeoutError as err:
            raise FelicityLocalTimeoutError(
                f"Timed out connecting to battery at {self.host}:{self.port}"
            ) from err
        except OSError as err:
            raise FelicityLocalConnectionError(
                f"Could not connect to battery at {self.host}:{self.port}: {err}"
            ) from err

        if self.persistent:
            self._enable_keepalive()

    def _enable_keepalive(self) -> None:
        """Enable and tune TCP keepalive on persistent socket."""
        assert self._writer is not None
        sock = self._writer.get_extra_info("socket")
        if sock is None:
            return
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):  # Linux
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, TCP_KEEPALIVE_IDLE)
            elif hasattr(socket, "TCP_KEEPALIVE"):  # macOS
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, TCP_KEEPALIVE_IDLE)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(
                    socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, TCP_KEEPALIVE_INTERVAL
                )
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, TCP_KEEPALIVE_COUNT)
        except OSError:
            _LOGGER.debug(
                "Could not tune TCP keepalive for %s:%s (non-fatal)", self.host, self.port
            )

    async def _disconnect(self) -> None:
        """Disconnect and close stream sockets."""
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is None:
            return
        writer.close()
        with contextlib.suppress(TimeoutError, OSError):
            await asyncio.wait_for(writer.wait_closed(), timeout=self.timeout)

    async def _flush_stray_bytes(self) -> None:
        """Discard any trailing bytes sitting in read buffer from prior queries."""
        assert self._reader is not None
        try:
            leftover = await asyncio.wait_for(
                self._reader.read(65536), timeout=STRAY_BYTES_FLUSH_TIMEOUT
            )
        except (TimeoutError, OSError):
            return
        if leftover:
            _LOGGER.debug(
                "Flushed %d stray byte(s) from %s:%s before next query",
                len(leftover),
                self.host,
                self.port,
            )

    async def _query(self, command: bytes) -> dict[str, Any]:
        """Send command, read JSON response up to '}', and send ack byte."""
        writer = self._writer
        reader = self._reader
        assert writer is not None
        assert reader is not None

        writer.write(command)
        try:
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
        except OSError as err:
            raise FelicityLocalConnectionError(f"Failed to send query: {err}") from err

        buffer = b""
        try:
            while b"}" not in buffer:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=self.timeout)
                if not chunk:
                    break
                buffer += chunk
        except TimeoutError as err:
            raise FelicityLocalTimeoutError(
                f"Timed out waiting for response from {self.host}:{self.port}"
            ) from err
        except OSError as err:
            raise FelicityLocalConnectionError(
                f"Connection error while reading from {self.host}:{self.port}: {err}"
            ) from err

        if b"}" not in buffer:
            raise FelicityLocalProtocolError(
                f"Response from {self.host}:{self.port} was never terminated with '}}'"
            )

        payload = buffer[: buffer.index(b"}") + 1]

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as err:
            raise FelicityLocalProtocolError(
                f"Could not parse response as JSON: {err} (raw: {payload[:100]!r})"
            ) from err

        if not isinstance(data, dict):
            raise FelicityLocalProtocolError("Response JSON was not a dictionary")

        # Send acknowledgment byte '.'
        try:
            writer.write(LOCAL_ACK_BYTE)
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
        except (TimeoutError, OSError):
            _LOGGER.debug(
                "Failed to send ack byte to %s:%s (non-fatal)", self.host, self.port
            )

        return data

    def _validate(self, data: dict[str, Any]) -> None:
        """Ensure snapshot is valid and not a mid-boot zero-voltage snapshot."""
        # Check pack voltage in BattList[0][0] or Batt[0][0]
        voltage = _extract_path(data, ("BattList", 0, 0))
        if voltage is None:
            voltage = _extract_path(data, ("Batt", 0, 0))

        if not voltage or voltage in (0, 65535, -1):
            raise FelicityLocalProtocolError(
                f"Battery at {self.host}:{self.port} returned an invalid/empty snapshot "
                f"(pack voltage missing or zero: {voltage})"
            )
