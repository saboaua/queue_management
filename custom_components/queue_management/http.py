"""HTTP views and static frontend for Queue Management panel."""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .queue import QueueManager

_LOGGER = logging.getLogger(__name__)

FRONTEND_PATH = Path(__file__).parent / "frontend"


def _manager(hass: HomeAssistant) -> QueueManager | None:
    return hass.data.get(DOMAIN)


class QueueStateView(HomeAssistantView):
    """Return current state of all queues + history + settings."""

    url = "/api/queue_management/state"
    name = "api:queue_management:state"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        manager = _manager(hass)
        if not manager:
            return self.json({"error": "Integration not loaded"}, status_code=503)

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
                    "waiting": q.waiting,
                    "waiting_display": [q.format_ticket(n) for n in q.waiting],
                    "waiting_count": q.waiting_count,
                    "status": q.status,
                    "start_number": q.start_number,
                }
            )

        entry = next(iter(hass.config_entries.async_entries(DOMAIN)), None)
        options = dict(entry.options) if entry else {}

        return self.json(
            {
                "queues": queues_data,
                "history": manager.history[-50:],
                "settings": {
                    "printer_enabled": options.get("printer_enabled", False),
                    "printer_name": options.get("printer_name", ""),
                    "announce_enabled": options.get("announce_enabled", False),
                    "announce_entity": options.get("announce_entity", ""),
                },
            }
        )


class QueueActionView(HomeAssistantView):
    """Perform queue actions."""

    url = "/api/queue_management/action"
    name = "api:queue_management:action"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        manager = _manager(hass)
        if not manager:
            return self.json({"error": "Integration not loaded"}, status_code=503)

        try:
            data = await request.json()
        except Exception:
            return self.json({"error": "Invalid JSON"}, status_code=400)

        action = data.get("action")
        queue_id = data.get("queue_id") or "main"

        try:
            if action == "take_ticket":
                result = await manager.async_take_ticket(queue_id)
                return self.json({"ok": True, "result": result})

            if action == "call_next":
                result = await manager.async_call_next(queue_id)
                return self.json({"ok": True, "result": result})

            if action == "call_ticket":
                ticket = int(data["ticket"])
                result = await manager.async_call_ticket(ticket, queue_id)
                return self.json({"ok": True, "result": result})

            if action == "reset":
                await manager.async_reset_queue(queue_id)
                return self.json({"ok": True})

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
                return self.json({"ok": True})

            if action == "create_queue":
                await manager.async_create_queue(
                    queue_id=data["new_queue_id"],
                    name=data.get("name", data["new_queue_id"]),
                    prefix=data.get("prefix", ""),
                    start_number=int(data.get("start_number", 1)),
                )
                return self.json({"ok": True})

            return self.json({"error": f"Unknown action: {action}"}, status_code=400)

        except (ValueError, KeyError, TypeError) as err:
            return self.json({"error": str(err)}, status_code=400)


class QueueSettingsView(HomeAssistantView):
    """Update printer / announcement settings."""

    url = "/api/queue_management/settings"
    name = "api:queue_management:settings"
    requires_auth = True

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
    """Register HTTP views and static frontend (must be awaited)."""
    hass.http.register_view(QueueStateView())
    hass.http.register_view(QueueActionView())
    hass.http.register_view(QueueSettingsView())

    try:
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    url_path="/queue_management/static",
                    path=str(FRONTEND_PATH),
                    cache_headers=False,
                )
            ]
        )
    except TypeError:
        # Older HA signature
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/queue_management/static",
                    str(FRONTEND_PATH),
                    False,
                )
            ]
        )
    except Exception as err:
        _LOGGER.warning("Static path registration issue: %s – trying legacy", err)
        try:
            hass.http.register_static_path(
                "/queue_management/static",
                str(FRONTEND_PATH),
                cache_headers=False,
            )
        except Exception as err2:
            _LOGGER.error("Could not register frontend static path: %s", err2)

    _LOGGER.info("Queue Management API + frontend registered")
