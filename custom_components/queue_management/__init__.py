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

# Config-entry only (no YAML configuration)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PANEL_ICON = "mdi:ticket-confirmation"
PANEL_TITLE = "Queue Management"
PANEL_URL_PATH = "queue-management"
# Served by QueueIndexView (requires_auth=False) – never 401
PANEL_IFRAME_URL = "/queue_management/"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (config entry only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Queue Management from a config entry."""
    manager = QueueManager(hass)
    await manager.async_load()
    hass.data[DOMAIN] = manager

    try:
        await async_setup_http(hass)
    except Exception:
        _LOGGER.exception("HTTP setup failed")

    _register_panel(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass, manager)

    _LOGGER.info(
        "Queue Management ready. Open sidebar '%s' or %s",
        PANEL_TITLE,
        PANEL_IFRAME_URL,
    )
    return True


def _register_panel(hass: HomeAssistant) -> None:
    try:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    except Exception:
        pass
    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            config={"url": PANEL_IFRAME_URL},
            require_admin=False,
        )
        _LOGGER.info("Panel registered at /%s → %s", PANEL_URL_PATH, PANEL_IFRAME_URL)
    except ValueError:
        _LOGGER.debug("Panel already registered")
    except Exception:
        _LOGGER.exception("Panel registration failed")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        try:
            frontend.async_remove_panel(hass, PANEL_URL_PATH)
        except Exception:
            pass
        hass.data.pop(DOMAIN, None)
    return unload_ok


def _register_services(hass: HomeAssistant, manager: QueueManager) -> None:
    async def handle_take_ticket(call: ServiceCall) -> dict[str, Any]:
        try:
            return await manager.async_take_ticket(call.data.get(ATTR_QUEUE_ID))
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_call_next(call: ServiceCall) -> dict[str, Any] | None:
        try:
            return await manager.async_call_next(call.data.get(ATTR_QUEUE_ID))
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_call_ticket(call: ServiceCall) -> dict[str, Any]:
        try:
            return await manager.async_call_ticket(
                call.data[ATTR_TICKET], call.data.get(ATTR_QUEUE_ID)
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_reset_queue(call: ServiceCall) -> None:
        try:
            await manager.async_reset_queue(call.data.get(ATTR_QUEUE_ID))
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
            entries = list(hass.config_entries.async_entries(DOMAIN))
            if entries:
                await hass.config_entries.async_reload(entries[0].entry_id)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_delete_queue(call: ServiceCall) -> None:
        try:
            await manager.async_delete_queue(call.data[ATTR_QUEUE_ID])
            entries = list(hass.config_entries.async_entries(DOMAIN))
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
