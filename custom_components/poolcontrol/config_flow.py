"""Config flow for PoolControl integration."""

from __future__ import annotations

import logging
import socket

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

from . import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PoolControlConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PoolControl."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Check if already configured
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            # Test connection
            if await self._test_connection(host, port):
                return self.async_create_entry(
                    title=f"PoolControl ({host}:{port})",
                    data={CONF_HOST: host, CONF_PORT: port},
                )
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def _test_connection(self, host: str, port: int) -> bool:
        """Test if we can connect to the bridge."""
        try:
            result = await self.hass.async_add_executor_job(
                self._try_connect, host, port
            )
            return result
        except Exception:
            return False

    @staticmethod
    def _try_connect(host: str, port: int) -> bool:
        """Try to connect and see if the bridge responds."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            # Wait briefly for any initial data
            try:
                data = sock.recv(64)
                if data:
                    sock.close()
                    return True
            except socket.timeout:
                # No immediate data but connection succeeded is OK
                pass
            sock.close()
            return True  # Connection succeeded even without data
        except (OSError, ConnectionError) as e:
            _LOGGER.error("Cannot connect to %s:%d: %s", host, port, e)
            return False
