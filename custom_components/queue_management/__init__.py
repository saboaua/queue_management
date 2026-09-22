"""The Queue Management integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    ATTR_QUEUE_ID,
    ATTR_TICKET,
    ATTR_NAME,
    ATTR_PREFIX,
    ATTR_START_NUMBER,
    SERVICE_TAKE_TICKET,
    SERVICE_CALL_NEXT,
    SERVICE_CALL_TICKET,
    SERVICE_RESET_QUEUE,
    SERVICE_CREATE_QUEUE,
    SERVICE_DELETE_QUEUE,
    PLATFORMS,
)
from .http import async_setup_http
from .queue import QueueManager

_LOGGER = logging.getLogger(__name__)

PANEL_ICON = "mdi:ticket-confirmation"
PANEL_TITLE = "Queue Management"
PANEL_URL_PATH = "queue-management"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Queue Management from a config entry."""
    manager = QueueManager(hass)
    await manager.async_load()
    hass.data[DOMAIN] = manager

    # HTTP API + static frontend
    await async_setup_http(hass)

    # Sidebar panel – opens the full Queue Management UI (no Lovelace needed)
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            config={"url": "/queue_management/static/index.html"},
            require_admin=False,
        )
        _LOGGER.info(
            "Queue Management panel registered. Open sidebar → Queue Management "
            "or go to /%s",
            PANEL_URL_PATH,
        )
    except ValueError:
        # Panel already registered (e.g. after reload)
        _LOGGER.debug("Queue Management panel already registered")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass, manager)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        try:
            frontend.async_remove_panel(hass, PANEL_URL_PATH)
        except Exception:
            pass
        hass.data.pop(DOMAIN, None)
    return unload_ok


def _register_services(hass: HomeAssistant, manager: QueueManager) -> None:
    """Register integration services."""

    async def handle_take_ticket(call: ServiceCall) -> dict[str, Any]:
        queue_id = call.data.get(ATTR_QUEUE_ID)
        try:
            return await manager.async_take_ticket(queue_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_call_next(call: ServiceCall) -> dict[str, Any] | None:
        queue_id = call.data.get(ATTR_QUEUE_ID)
        try:
            return await manager.async_call_next(queue_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_call_ticket(call: ServiceCall) -> dict[str, Any]:
        queue_id = call.data.get(ATTR_QUEUE_ID)
        ticket = call.data[ATTR_TICKET]
        try:
            return await manager.async_call_ticket(ticket, queue_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_reset_queue(call: ServiceCall) -> None:
        queue_id = call.data.get(ATTR_QUEUE_ID)
        try:
            await manager.async_reset_queue(queue_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_create_queue(call: ServiceCall) -> None:
        try:
            await manager.async_create_queue(
                queue_id=call.data[ATTR_QUEUE_ID],
                name=call.data.get(ATTR_NAME, call.data[ATTR_QUEUE_ID]),
                prefix=call.data.get(ATTR_PREFIX, ""),
                start_number=call.data.get(ATTR_START_NUMBER, 1),
            )
            entries = hass.config_entries.async_entries(DOMAIN)
            if entries:
                await hass.config_entries.async_reload(entries[0].entry_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_delete_queue(call: ServiceCall) -> None:
        try:
            await manager.async_delete_queue(call.data[ATTR_QUEUE_ID])
            entries = hass.config_entries.async_entries(DOMAIN)
            if entries:
                await hass.config_entries.async_reload(entries[0].entry_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_TAKE_TICKET,
        handle_take_ticket,
        schema=vol.Schema({vol.Optional(ATTR_QUEUE_ID): cv.string}),
        supports_response=True,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALL_NEXT,
        handle_call_next,
        schema=vol.Schema({vol.Optional(ATTR_QUEUE_ID): cv.string}),
        supports_response=True,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALL_TICKET,
        handle_call_ticket,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_QUEUE_ID): cv.string,
                vol.Required(ATTR_TICKET): cv.positive_int,
            }
        ),
        supports_response=True,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_QUEUE,
        handle_reset_queue,
        schema=vol.Schema({vol.Optional(ATTR_QUEUE_ID): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_QUEUE,
        handle_create_queue,
        schema=vol.Schema(
            {
                vol.Required(ATTR_QUEUE_ID): cv.string,
                vol.Optional(ATTR_NAME): cv.string,
                vol.Optional(ATTR_PREFIX, default=""): cv.string,
                vol.Optional(ATTR_START_NUMBER, default=1): cv.positive_int,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_QUEUE,
        handle_delete_queue,
        schema=vol.Schema({vol.Required(ATTR_QUEUE_ID): cv.string}),
    )
