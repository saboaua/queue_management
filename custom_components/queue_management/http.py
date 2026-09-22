"""HTTP API and static frontend for Queue Management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .queue import QueueManager

_LOGGER = logging.getLogger(__name__)
FRONTEND_PATH = Path(__file__).parent / "frontend"


def _manager(hass: HomeAssistant) -> QueueManager | None:
    data = hass.data.get(DOMAIN)
    return data if isinstance(data, QueueManager) else None


def _state_payload(hass: HomeAssistant, manager: QueueManager) -> dict[str, Any]:
    queues_data = []
    for q in manager.queues.values():
        queues_data.append(
            {
                "queue_id": q.queue_id,
                "name": q.name,
                "prefix": q.prefix,
                "current": q.current,
                "current_display": q.format_ticket(q.current) if q.current else "—",
                "last_issued": q.last_issued,
                "last_issued_display": (
                    q.format_ticket(q.last_issued) if q.last_issued else "—"
                ),
                "waiting": list(q.waiting),
                "waiting_display": [q.format_ticket(n) for n in q.waiting],
                "waiting_count": q.waiting_count,
                "status": q.status,
                "start_number": q.start_number,
            }
        )
    entry = next(iter(hass.config_entries.async_entries(DOMAIN)), None)
    options = dict(entry.options) if entry else {}
    return {
        "queues": queues_data,
        "history": manager.history[-50:],
        "settings": {
            "printer_enabled": options.get("printer_enabled", False),
            "printer_name": options.get("printer_name", ""),
            "announce_enabled": options.get("announce_enabled", False),
            "announce_entity": options.get("announce_entity", ""),
        },
    }


async def _handle_action(
    hass: HomeAssistant, manager: QueueManager, data: dict[str, Any]
) -> web.Response:
    action = data.get("action")
    queue_id = data.get("queue_id") or "main"
    try:
        if action == "take_ticket":
            result = await manager.async_take_ticket(queue_id)
            return web.json_response({"ok": True, "result": result})
        if action == "call_next":
            result = await manager.async_call_next(queue_id)
            return web.json_response({"ok": True, "result": result})
        if action == "call_ticket":
            result = await manager.async_call_ticket(int(data["ticket"]), queue_id)
            return web.json_response({"ok": True, "result": result})
        if action == "reset":
            await manager.async_reset_queue(queue_id)
            return web.json_response({"ok": True})
        if action == "complete":
            q = manager.get_queue(queue_id)
            if q and q.current:
                manager.add_history(
                    {
                        "type": "completed",
                        "queue_id": q.queue_id,
                        "ticket": q.current,
                        "ticket_display": q.format_ticket(q.current),
                    }
                )
                q.current = 0
                await manager.async_save()
                manager._notify()
            return web.json_response({"ok": True})
        if action == "create_queue":
            await manager.async_create_queue(
                queue_id=data["new_queue_id"],
                name=data.get("name", data["new_queue_id"]),
                prefix=data.get("prefix", ""),
                start_number=int(data.get("start_number", 1)),
            )
            return web.json_response({"ok": True})
        return web.json_response({"error": f"Unknown action: {action}"}, status=400)
    except (ValueError, KeyError, TypeError) as err:
        return web.json_response({"error": str(err)}, status=400)


class QueueStateView(HomeAssistantView):
    """Queue state – no auth (local network UI)."""

    url = "/api/queue_management/state"
    name = "api:queue_management:state"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        manager = _manager(hass)
        if not manager:
            return self.json({"error": "Integration not loaded"}, status_code=503)
        try:
            return self.json(_state_payload(hass, manager))
        except Exception as err:
            _LOGGER.exception("state payload failed")
            return self.json({"error": str(err)}, status_code=500)


class QueueActionView(HomeAssistantView):
    """Queue actions – no auth (local network UI)."""

    url = "/api/queue_management/action"
    name = "api:queue_management:action"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        manager = _manager(hass)
        if not manager:
            return self.json({"error": "Integration not loaded"}, status_code=503)
        try:
            data = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON"}, status_code=400)
        try:
            return await _handle_action(hass, manager, data)
        except Exception as err:
            _LOGGER.exception("action failed")
            return self.json({"error": str(err)}, status_code=500)


class QueueSettingsView(HomeAssistantView):
    url = "/api/queue_management/settings"
    name = "api:queue_management:settings"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entry = next(iter(hass.config_entries.async_entries(DOMAIN)), None)
        if not entry:
            return self.json({"error": "No config entry"}, status_code=404)
        try:
            data = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON"}, status_code=400)
        new_options = dict(entry.options)
        for key in (
            "printer_enabled",
            "printer_name",
            "announce_enabled",
            "announce_entity",
        ):
            if key in data:
                new_options[key] = data[key]
        hass.config_entries.async_update_entry(entry, options=new_options)
        return self.json({"ok": True, "settings": new_options})


async def async_setup_http(hass: HomeAssistant) -> None:
    """Register API views and static UI files."""
    for view in (QueueStateView(), QueueActionView(), QueueSettingsView()):
        try:
            hass.http.register_view(view)
        except Exception as err:
            _LOGGER.error("Failed to register %s: %s", getattr(view, "name", view), err)

    static_ok = False
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/queue_management/static",
                    str(FRONTEND_PATH),
                    False,
                )
            ]
        )
        static_ok = True
    except Exception as err:
        _LOGGER.warning("async_register_static_paths failed: %s", err)
        try:
            hass.http.register_static_path(
                "/queue_management/static",
                str(FRONTEND_PATH),
                cache_headers=False,
            )
            static_ok = True
        except Exception as err2:
            _LOGGER.error("register_static_path failed: %s", err2)

    if static_ok:
        _LOGGER.info(
            "Queue Management UI: /queue_management/static/index.html | "
            "API: /api/queue_management/state"
        )
    else:
        _LOGGER.error("Static UI not registered – check frontend/ folder exists")
