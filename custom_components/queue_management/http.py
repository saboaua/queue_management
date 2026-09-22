"""HTTP views and frontend for Queue Management panel.

Auth model (works in sidebar iframe + tablets):
1. UI page (/queue_management/ui) requires a normal HA login.
2. When serving the page we inject a server-side secret into the HTML.
3. API endpoints accept either:
   - standard HA auth (Bearer / session), OR
   - header X-Queue-Management-Secret matching the server secret.
This avoids broken cookie/token behaviour inside iframes.
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .queue import QueueManager

_LOGGER = logging.getLogger(__name__)

FRONTEND_PATH = Path(__file__).parent / "frontend"
SECRET_HEADER = "X-Queue-Management-Secret"


def _manager(hass: HomeAssistant) -> QueueManager | None:
    return hass.data.get(DOMAIN)


def _get_secret(hass: HomeAssistant) -> str:
    meta = hass.data.setdefault(f"{DOMAIN}_meta", {})
    if "ui_secret" not in meta:
        meta["ui_secret"] = secrets.token_urlsafe(32)
    return meta["ui_secret"]


def _check_secret(request: web.Request, hass: HomeAssistant) -> bool:
    expected = _get_secret(hass)
    got = request.headers.get(SECRET_HEADER, "")
    if not expected or not got or len(expected) != len(got):
        return False
    return secrets.compare_digest(got, expected)


async def _authorized(request: web.Request, hass: HomeAssistant) -> bool:
    """Accept UI secret header or HA Bearer token or hass_user on request."""
    if _check_secret(request, hass):
        return True
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        try:
            user = await hass.auth.async_validate_access_token(token)
            if user:
                return True
        except Exception:
            pass
    if request.get("hass_user") is not None:
        return True
    return False


class QueueUIView(HomeAssistantView):
    """Serve the SPA HTML (requires HA login). Injects API secret."""

    url = "/queue_management/ui"
    name = "queue_management:ui"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        index_path = FRONTEND_PATH / "index.html"
        try:
            html = index_path.read_text(encoding="utf-8")
        except OSError as err:
            return web.Response(text=f"Frontend missing: {err}", status=500)

        secret = _get_secret(hass)
        inject = (
            f"<script>window.QM_SECRET={secret!r};"
            f"window.QM_BASE='';</script>"
        )
        if "<head>" in html:
            html = html.replace("<head>", f"<head>{inject}", 1)
        else:
            html = inject + html

        return web.Response(text=html, content_type="text/html; charset=utf-8")


class QueueStateView(HomeAssistantView):
    """Return current state of all queues + history + settings."""

    url = "/api/queue_management/state"
    name = "api:queue_management:state"
    requires_auth = False  # we enforce secret OR HA auth below
    cors_allowed = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not await _authorized(request, hass):
            return self.json({"error": "Not authenticated"}, status_code=401)

        manager = _manager(hass)
        if not manager or not isinstance(manager, QueueManager):
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
    requires_auth = False
    cors_allowed = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not await _authorized(request, hass):
            return self.json({"error": "Not authenticated"}, status_code=401)

        manager = _manager(hass)
        if not manager or not isinstance(manager, QueueManager):
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
    requires_auth = False
    cors_allowed = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        if not await _authorized(request, hass):
            return self.json({"error": "Not authenticated"}, status_code=401)

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
    """Register HTTP views and static assets (CSS/JS)."""
    # Ensure secret exists
    _get_secret(hass)

    hass.http.register_view(QueueUIView())
    hass.http.register_view(QueueStateView())
    hass.http.register_view(QueueActionView())
    hass.http.register_view(QueueSettingsView())

    # Static assets only (css/js) – HTML is served by QueueUIView
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
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig("/queue_management/static", str(FRONTEND_PATH), False)]
            )
        except Exception as err:
            _LOGGER.warning("static path: %s", err)
            try:
                hass.http.register_static_path(
                    "/queue_management/static", str(FRONTEND_PATH), cache_headers=False
                )
            except Exception as err2:
                _LOGGER.error("Could not register static path: %s", err2)

    _LOGGER.info(
        "Queue Management UI at /queue_management/ui  |  panel path /queue-management"
    )
