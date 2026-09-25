"""Queue data model and manager for Queue Management."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    DEFAULT_QUEUE_ID,
    DEFAULT_QUEUE_NAME,
    EVENT_TICKET_ISSUED,
    EVENT_TICKET_CALLED,
    EVENT_QUEUE_RESET,
)

_LOGGER = logging.getLogger(__name__)

SIGNAL_UPDATE = f"{DOMAIN}_update"
MAX_HISTORY = 200
MAX_SERVICE_SAMPLES = 50
MAX_DAILY_STATS_DAYS = 30

DEFAULT_THEME = {
    "bg": "#f4f6fb",
    "card": "#ffffff",
    "text": "#0b1220",
    "muted": "#5b6578",
    "accent": "#2563eb",
    "success": "#16a34a",
    "warning": "#f59e0b",
    "danger": "#dc2626",
}

DEFAULT_PRINT_TEMPLATE = {
    "title": "QUEUE TICKET",
    "show_number": True,
    "show_queue_name": True,
    "show_datetime": True,
    "show_waiting_count": True,
    "show_eta": True,
    "header": "Please wait for your number",
    "footer": "Thank you for your patience",
    "extra_line": "",
    "paper_width": "58mm",
    "logo_url": "",
    "social_line": "",
}

DEFAULT_ANNOUNCE_TEMPLATES = {
    "with_cashier": "Ticket {ticket}, please go to {cashier}",
    "without_cashier": "Ticket {ticket}, please proceed",
}

DEFAULT_CALL_SOUND = "chime"

DEFAULT_CASHIERS = [
    {"id": "cashier_1", "name": "Cashier 1", "enabled": True},
    {"id": "cashier_2", "name": "Cashier 2", "enabled": True},
    {"id": "cashier_3", "name": "Cashier 3", "enabled": True},
]

DEFAULT_SERVICES = [
    {"id": "general", "name": "General", "queue_id": "main", "enabled": True, "icon": "🎫"},
]


@dataclass
class Cashier:
    id: str
    name: str
    enabled: bool = True
    status: str = "idle"  # idle | serving | break
    current_ticket: int = 0
    current_ticket_display: str = ""
    queue_id: str = DEFAULT_QUEUE_ID
    last_call_at: str | None = None
    call_started_at: str | None = None
    served_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Cashier":
        status = data.get("status", "idle")
        if status not in ("idle", "serving", "break"):
            status = "idle"
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            enabled=data.get("enabled", True),
            status=status,
            current_ticket=data.get("current_ticket", 0),
            current_ticket_display=data.get("current_ticket_display", ""),
            queue_id=data.get("queue_id", DEFAULT_QUEUE_ID),
            last_call_at=data.get("last_call_at"),
            call_started_at=data.get("call_started_at"),
            served_count=data.get("served_count", 0),
        )


@dataclass
class ServiceType:
    id: str
    name: str
    queue_id: str = DEFAULT_QUEUE_ID
    enabled: bool = True
    icon: str = "🎫"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServiceType":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            queue_id=data.get("queue_id", DEFAULT_QUEUE_ID),
            enabled=data.get("enabled", True),
            icon=data.get("icon", "🎫"),
        )


@dataclass
class Queue:
    queue_id: str
    name: str
    prefix: str = ""
    start_number: int = 1
    last_issued: int = 0
    current: int = 0
    current_cashier_id: str | None = None
    current_cashier_name: str | None = None
    waiting: list[int] = field(default_factory=list)
    # ticket -> issued_iso for ETA / wait metrics
    issued_at: dict[str, str] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def format_ticket(self, number: int) -> str:
        if self.prefix:
            return f"{self.prefix}{number}"
        return str(number)

    @property
    def waiting_count(self) -> int:
        return len(self.waiting)

    @property
    def status(self) -> str:
        if self.current == 0 and self.waiting_count == 0:
            return "idle"
        if self.waiting_count > 0:
            return "active"
        return "serving"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Queue":
        issued = data.get("issued_at") or {}
        # keys as str
        issued_at = {str(k): v for k, v in issued.items()}
        return cls(
            queue_id=data["queue_id"],
            name=data["name"],
            prefix=data.get("prefix", ""),
            start_number=data.get("start_number", 1),
            last_issued=data.get("last_issued", 0),
            current=data.get("current", 0),
            current_cashier_id=data.get("current_cashier_id"),
            current_cashier_name=data.get("current_cashier_name"),
            waiting=list(data.get("waiting", [])),
            issued_at=issued_at,
            created_at=data.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
        )


class QueueManager:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.queues: dict[str, Queue] = {}
        self.cashiers: dict[str, Cashier] = {}
        self.services: dict[str, ServiceType] = {}
        self.theme: dict[str, str] = dict(DEFAULT_THEME)
        self.print_template: dict[str, Any] = dict(DEFAULT_PRINT_TEMPLATE)
        self.history: list[dict[str, Any]] = []
        self.daily_stats: dict[str, dict[str, Any]] = {}
        self.admin_pin: str = ""
        self.avg_service_seconds: float = 180.0  # default 3 min
        self._service_samples: list[float] = []
        self.announce_enabled: bool = False
        self.announce_entity: str = ""
        self.announce_tts_entity: str = ""
        self.announce_templates: dict[str, str] = dict(DEFAULT_ANNOUNCE_TEMPLATES)
        self.call_sound: str = DEFAULT_CALL_SOUND
        self.new_ticket_sound: str = "beep"
        self.ui_logo_url: str = ""
        self._loaded = False

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data and "queues" in data:
            for qdata in data["queues"]:
                q = Queue.from_dict(qdata)
                self.queues[q.queue_id] = q
            self.history = list(data.get("history", []))[-MAX_HISTORY:]
            self.daily_stats = dict(data.get("daily_stats") or {})
            self._prune_daily_stats()
            for cdata in data.get("cashiers", []):
                c = Cashier.from_dict(cdata)
                self.cashiers[c.id] = c
            for sdata in data.get("services", []):
                s = ServiceType.from_dict(sdata)
                self.services[s.id] = s
            self.theme = {**DEFAULT_THEME, **(data.get("theme") or {})}
            self.print_template = {
                **DEFAULT_PRINT_TEMPLATE,
                **(data.get("print_template") or {}),
            }
            self.admin_pin = str(data.get("admin_pin") or "")
            self.avg_service_seconds = float(
                data.get("avg_service_seconds") or 180.0
            )
            self._service_samples = list(data.get("service_samples") or [])[
                -MAX_SERVICE_SAMPLES:
            ]
            self.announce_enabled = bool(data.get("announce_enabled", False))
            self.announce_entity = str(data.get("announce_entity") or "")
            self.announce_tts_entity = str(data.get("announce_tts_entity") or "")
            self.announce_templates = {**DEFAULT_ANNOUNCE_TEMPLATES, **(data.get("announce_templates") or {})}
            self.call_sound = str(data.get("call_sound") or DEFAULT_CALL_SOUND)
            self.new_ticket_sound = str(data.get("new_ticket_sound") or "beep")
            self.ui_logo_url = str(data.get("ui_logo_url") or "")
        else:
            self.queues[DEFAULT_QUEUE_ID] = Queue(
                queue_id=DEFAULT_QUEUE_ID, name=DEFAULT_QUEUE_NAME
            )

        if not self.cashiers:
            for c in DEFAULT_CASHIERS:
                self.cashiers[c["id"]] = Cashier(
                    id=c["id"], name=c["name"], enabled=c["enabled"]
                )
        if not self.services:
            for s in DEFAULT_SERVICES:
                self.services[s["id"]] = ServiceType(
                    id=s["id"],
                    name=s["name"],
                    queue_id=s["queue_id"],
                    enabled=s["enabled"],
                    icon=s["icon"],
                )
        await self.async_save()
        self._loaded = True

    async def async_save(self) -> None:
        data = {
            "queues": [q.to_dict() for q in self.queues.values()],
            "cashiers": [c.to_dict() for c in self.cashiers.values()],
            "services": [s.to_dict() for s in self.services.values()],
            "theme": self.theme,
            "print_template": self.print_template,
            "history": self.history[-MAX_HISTORY:],
            "daily_stats": self.daily_stats,
            "admin_pin": self.admin_pin,
            "avg_service_seconds": self.avg_service_seconds,
            "service_samples": self._service_samples[-MAX_SERVICE_SAMPLES:],
            "announce_enabled": self.announce_enabled,
            "announce_entity": self.announce_entity,
            "announce_tts_entity": self.announce_tts_entity,
            "announce_templates": self.announce_templates,
            "call_sound": self.call_sound,
            "new_ticket_sound": self.new_ticket_sound,
            "ui_logo_url": self.ui_logo_url,
        }
        await self._store.async_save(data)

    def add_history(self, entry: dict[str, Any]) -> None:
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self.history.append(entry)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    def _bump_daily(self, kind: str, service_id: str | None = None) -> None:
        """Track per-hour ticket activity so the dashboard survives history
        trimming and HA restarts (history[] is capped and log-shaped; this
        is a compact rolling aggregate purpose-built for analytics)."""
        now = dt_util.now()
        date_key = now.strftime("%Y-%m-%d")
        day = self.daily_stats.setdefault(
            date_key, {"hourly": [0] * 24, "issued": 0, "completed": 0, "services": {}}
        )
        if kind == "issued":
            day["issued"] += 1
            day["hourly"][now.hour] += 1
            if service_id:
                day["services"][service_id] = day["services"].get(service_id, 0) + 1
        elif kind == "completed":
            day["completed"] += 1
        self._prune_daily_stats()

    def _prune_daily_stats(self) -> None:
        if len(self.daily_stats) <= MAX_DAILY_STATS_DAYS:
            return
        for key in sorted(self.daily_stats.keys())[: len(self.daily_stats) - MAX_DAILY_STATS_DAYS]:
            self.daily_stats.pop(key, None)

    def dashboard_stats(self) -> dict[str, Any]:
        """Peak-hours, trend and service-mix analytics for the Manager dashboard."""
        empty_day = {"hourly": [0] * 24, "issued": 0, "completed": 0, "services": {}}
        now = dt_util.now()
        today_key = now.strftime("%Y-%m-%d")
        yesterday_key = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        today = self.daily_stats.get(today_key) or empty_day
        yesterday = self.daily_stats.get(yesterday_key) or empty_day

        hourly_7d = [0] * 24
        services_7d: dict[str, int] = {}
        issued_7d = 0
        completed_7d = 0
        for i in range(7):
            key = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            d = self.daily_stats.get(key)
            if not d:
                continue
            h = d.get("hourly") or [0] * 24
            for idx in range(24):
                hourly_7d[idx] += h[idx] if idx < len(h) else 0
            issued_7d += d.get("issued", 0)
            completed_7d += d.get("completed", 0)
            for sid, cnt in (d.get("services") or {}).items():
                services_7d[sid] = services_7d.get(sid, 0) + cnt

        # Fair "vs yesterday" comparison: same elapsed hours only, not full-day
        # totals against a still-in-progress today.
        cur_hour = now.hour
        today_so_far = sum(today["hourly"][: cur_hour + 1])
        yesterday_so_far = sum(yesterday["hourly"][: cur_hour + 1])
        if yesterday_so_far > 0:
            issued_trend_pct = round(
                ((today_so_far - yesterday_so_far) / yesterday_so_far) * 100, 1
            )
        elif today_so_far > 0:
            issued_trend_pct = 100.0
        else:
            issued_trend_pct = 0.0

        peak_hour = max(range(24), key=lambda h: hourly_7d[h]) if any(hourly_7d) else None

        return {
            "today_issued": today.get("issued", 0),
            "today_completed": today.get("completed", 0),
            "yesterday_issued": yesterday.get("issued", 0),
            "issued_trend_pct": issued_trend_pct,
            "hourly_today": today["hourly"],
            "hourly_7d": hourly_7d,
            "peak_hour": peak_hour,
            "services_7d": services_7d,
            "issued_7d": issued_7d,
            "completed_7d": completed_7d,
        }

    def get_queue(self, queue_id: str | None = None) -> Queue | None:
        return self.queues.get(queue_id or DEFAULT_QUEUE_ID)

    def get_cashier(self, cashier_id: str | None) -> Cashier | None:
        if not cashier_id:
            return None
        return self.cashiers.get(cashier_id)

    def estimate_wait_seconds(self, queue_id: str | None = None) -> int:
        q = self.get_queue(queue_id)
        if not q or not q.waiting:
            return 0
        active = sum(
            1
            for c in self.cashiers.values()
            if c.enabled and c.status in ("idle", "serving")
        )
        active = max(1, active)
        return int(round((q.waiting_count * self.avg_service_seconds) / active))

    def estimate_wait_display(self, queue_id: str | None = None) -> str:
        secs = self.estimate_wait_seconds(queue_id)
        if secs <= 0:
            return "—"
        mins = max(1, int(round(secs / 60)))
        if mins < 60:
            return f"~{mins} min"
        h, m = divmod(mins, 60)
        return f"~{h}h {m}m" if m else f"~{h}h"

    def overview(self) -> dict[str, Any]:
        total_waiting = sum(q.waiting_count for q in self.queues.values())
        busy = [
            c
            for c in self.cashiers.values()
            if c.enabled and c.status == "serving"
        ]
        idle = [
            c
            for c in self.cashiers.values()
            if c.enabled and c.status == "idle"
        ]
        on_break = [
            c
            for c in self.cashiers.values()
            if c.enabled and c.status == "break"
        ]
        return {
            "total_waiting": total_waiting,
            "total_serving": len(busy),
            "avg_service_seconds": int(self.avg_service_seconds),
            "avg_service_display": self._fmt_secs(self.avg_service_seconds),
            "cashiers_enabled": sum(1 for c in self.cashiers.values() if c.enabled),
            "cashiers_busy": [
                {
                    "id": c.id,
                    "name": c.name,
                    "ticket": c.current_ticket_display,
                    "ticket_raw": c.current_ticket,
                    "queue_id": c.queue_id,
                    "last_call_at": c.last_call_at,
                    "served_count": c.served_count,
                }
                for c in busy
            ],
            "cashiers_idle": [{"id": c.id, "name": c.name} for c in idle],
            "cashiers_break": [{"id": c.id, "name": c.name} for c in on_break],
            "queues": [
                {
                    "queue_id": q.queue_id,
                    "name": q.name,
                    "waiting": q.waiting_count,
                    "eta": self.estimate_wait_display(q.queue_id),
                    "eta_seconds": self.estimate_wait_seconds(q.queue_id),
                    "current_display": q.format_ticket(q.current) if q.current else "—",
                    "current_cashier_name": q.current_cashier_name,
                    "status": q.status,
                }
                for q in self.queues.values()
            ],
        }

    @staticmethod
    def _fmt_secs(secs: float) -> str:
        m = int(round(secs / 60))
        if m < 1:
            return f"{int(secs)}s"
        return f"{m} min"

    async def async_create_queue(
        self,
        queue_id: str,
        name: str,
        prefix: str = "",
        start_number: int = 1,
    ) -> Queue:
        if queue_id in self.queues:
            raise ValueError(f"Queue '{queue_id}' already exists")
        if not queue_id or " " in queue_id or not queue_id.islower():
            raise ValueError("queue_id must be lowercase with no spaces")
        q = Queue(
            queue_id=queue_id,
            name=name or queue_id.replace("_", " ").title(),
            prefix=prefix,
            start_number=max(1, start_number),
            last_issued=max(0, start_number - 1),
        )
        self.queues[queue_id] = q
        await self.async_save()
        self._notify()
        return q

    async def async_delete_queue(self, queue_id: str) -> None:
        if queue_id == DEFAULT_QUEUE_ID:
            raise ValueError("Cannot delete the main queue")
        if queue_id not in self.queues:
            raise ValueError(f"Queue '{queue_id}' not found")
        del self.queues[queue_id]
        await self.async_save()
        self._notify()

    async def async_take_ticket(
        self, queue_id: str | None = None, service_id: str | None = None
    ) -> dict[str, Any]:
        if service_id:
            svc = self.services.get(service_id)
            if not svc or not svc.enabled:
                raise ValueError("Service not available")
            queue_id = svc.queue_id

        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")

        next_num = q.last_issued + 1
        q.last_issued = next_num
        q.waiting.append(next_num)
        now = datetime.now(timezone.utc).isoformat()
        q.issued_at[str(next_num)] = now
        ticket_str = q.format_ticket(next_num)
        eta = self.estimate_wait_display(q.queue_id)
        event_data = {
            "queue_id": q.queue_id,
            "queue_name": q.name,
            "ticket": next_num,
            "ticket_display": ticket_str,
            "waiting_count": q.waiting_count,
            "eta": eta,
            "eta_seconds": self.estimate_wait_seconds(q.queue_id),
            "service_id": service_id,
            "service_name": self.services[service_id].name if service_id and service_id in self.services else None,
            "timestamp": now,
        }
        self.add_history({**event_data, "type": "issued"})
        self._bump_daily("issued", service_id=service_id)
        event_data["print"] = self.build_print_payload(event_data)
        await self.async_save()
        self._notify()
        self.hass.bus.async_fire(EVENT_TICKET_ISSUED, event_data)
        return event_data

    async def async_call_next(
        self,
        queue_id: str | None = None,
        cashier_id: str | None = None,
    ) -> dict[str, Any] | None:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")
        if not q.waiting:
            return None

        cashier = self._require_callable_cashier(cashier_id)
        next_num = q.waiting.pop(0)
        return await self._assign_call(q, next_num, cashier)

    async def async_call_ticket(
        self,
        ticket: int,
        queue_id: str | None = None,
        cashier_id: str | None = None,
    ) -> dict[str, Any]:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")
        cashier = self._require_callable_cashier(cashier_id)
        if ticket in q.waiting:
            q.waiting.remove(ticket)
        return await self._assign_call(q, ticket, cashier)

    def _require_callable_cashier(self, cashier_id: str | None) -> Cashier | None:
        if not cashier_id:
            return None
        cashier = self.get_cashier(cashier_id)
        if not cashier:
            raise ValueError(f"Cashier '{cashier_id}' not found")
        if not cashier.enabled:
            raise ValueError(f"Cashier '{cashier.name}' is disabled")
        if cashier.status == "break":
            raise ValueError(f"Cashier '{cashier.name}' is on break")
        return cashier

    async def _assign_call(
        self, q: Queue, ticket: int, cashier: Cashier | None
    ) -> dict[str, Any]:
        q.current = ticket
        ticket_str = q.format_ticket(ticket)
        now = datetime.now(timezone.utc).isoformat()

        if cashier:
            cashier.current_ticket = ticket
            cashier.current_ticket_display = ticket_str
            cashier.queue_id = q.queue_id
            cashier.status = "serving"
            cashier.last_call_at = now
            cashier.call_started_at = now
            q.current_cashier_id = cashier.id
            q.current_cashier_name = cashier.name
        else:
            q.current_cashier_id = None
            q.current_cashier_name = None

        event_data = {
            "queue_id": q.queue_id,
            "queue_name": q.name,
            "ticket": ticket,
            "ticket_display": ticket_str,
            "waiting_count": q.waiting_count,
            "cashier_id": cashier.id if cashier else None,
            "cashier_name": cashier.name if cashier else None,
            "timestamp": now,
        }
        self.add_history({**event_data, "type": "called"})
        await self.async_save()
        self._notify()
        self.hass.bus.async_fire(EVENT_TICKET_CALLED, event_data)
        await self._async_announce(event_data)
        return event_data

    async def async_test_announce(self) -> None:
        """Speak a sample message on the configured media player."""
        await self._async_announce(
            {
                "ticket_display": "42",
                "cashier_name": "Cashier 1",
            }
        )

    def _pick_tts_entity(self) -> str | None:
        """Prefer configured TTS entity, else first available tts.* entity."""
        if self.announce_tts_entity and self.hass.states.get(self.announce_tts_entity):
            return self.announce_tts_entity
        for state in self.hass.states.async_all("tts"):
            return state.entity_id
        return None

    async def _async_announce(self, event: dict[str, Any]) -> None:
        if not self.announce_enabled or not self.announce_entity:
            return
        ticket = str(event.get("ticket_display") or event.get("ticket") or "")
        cashier = event.get("cashier_name") or ""
        tpl = self.announce_templates or DEFAULT_ANNOUNCE_TEMPLATES
        if cashier:
            message = (tpl.get("with_cashier") or DEFAULT_ANNOUNCE_TEMPLATES["with_cashier"]).format(
                ticket=ticket, cashier=cashier
            )
        else:
            message = (tpl.get("without_cashier") or DEFAULT_ANNOUNCE_TEMPLATES["without_cashier"]).format(
                ticket=ticket, cashier=cashier
            )

        media = self.announce_entity
        tts_entity = self._pick_tts_entity()
        errors: list[str] = []

        # 1) Modern HA: tts.speak with TTS entity + media player
        if tts_entity:
            try:
                await self.hass.services.async_call(
                    "tts",
                    "speak",
                    {
                        "entity_id": tts_entity,
                        "media_player_entity_id": media,
                        "message": message,
                    },
                    blocking=False,
                )
                return
            except Exception as err:
                errors.append(f"tts.speak({tts_entity}): {err}")

        # 2) tts.speak without explicit TTS entity (some setups)
        try:
            await self.hass.services.async_call(
                "tts",
                "speak",
                {
                    "media_player_entity_id": media,
                    "message": message,
                },
                blocking=False,
            )
            return
        except Exception as err:
            errors.append(f"tts.speak: {err}")

        # 3) Legacy say services if still registered
        for svc in ("google_translate_say", "cloud_say", "say"):
            if not self.hass.services.has_service("tts", svc):
                continue
            try:
                await self.hass.services.async_call(
                    "tts",
                    svc,
                    {"entity_id": media, "message": message},
                    blocking=False,
                )
                return
            except Exception as err:
                errors.append(f"tts.{svc}: {err}")

        _LOGGER.warning(
            "TTS announce failed (no working TTS service). "
            "Install a TTS integration (e.g. Google Translate, Piper, Home Assistant Cloud) "
            "and pick it in Admin. Details: %s",
            " | ".join(errors) if errors else "none",
        )

    async def async_complete(
        self,
        queue_id: str | None = None,
        cashier_id: str | None = None,
    ) -> None:
        q = self.get_queue(queue_id)
        cashier = self.get_cashier(cashier_id) if cashier_id else None

        ticket = 0
        ticket_display = ""
        if cashier and cashier.current_ticket:
            ticket = cashier.current_ticket
            ticket_display = cashier.current_ticket_display
            # service time sample
            if cashier.call_started_at:
                try:
                    started = datetime.fromisoformat(cashier.call_started_at)
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    elapsed = (
                        datetime.now(timezone.utc) - started
                    ).total_seconds()
                    if 15 < elapsed < 3600:
                        self._service_samples.append(elapsed)
                        self._service_samples = self._service_samples[
                            -MAX_SERVICE_SAMPLES:
                        ]
                        self.avg_service_seconds = sum(self._service_samples) / len(
                            self._service_samples
                        )
                except Exception:
                    pass
            cashier.served_count += 1
            cashier.current_ticket = 0
            cashier.current_ticket_display = ""
            cashier.call_started_at = None
            cashier.status = "idle"
        if q and q.current:
            if not ticket:
                ticket = q.current
                ticket_display = q.format_ticket(q.current)
            q.issued_at.pop(str(q.current), None)
            q.current = 0
            q.current_cashier_id = None
            q.current_cashier_name = None

        if ticket:
            self.add_history(
                {
                    "type": "completed",
                    "queue_id": q.queue_id if q else None,
                    "ticket": ticket,
                    "ticket_display": ticket_display,
                    "cashier_id": cashier.id if cashier else None,
                    "cashier_name": cashier.name if cashier else None,
                }
            )
            self._bump_daily("completed")
        await self.async_save()
        self._notify()

    async def async_set_cashier_status(
        self, cashier_id: str, status: str
    ) -> None:
        if status not in ("idle", "serving", "break"):
            raise ValueError("Invalid status")
        c = self.get_cashier(cashier_id)
        if not c:
            raise ValueError("Cashier not found")
        if status == "break":
            c.status = "break"
            c.current_ticket = 0
            c.current_ticket_display = ""
            c.call_started_at = None
        elif status == "idle":
            c.status = "idle"
            c.current_ticket = 0
            c.current_ticket_display = ""
            c.call_started_at = None
        else:
            c.status = "serving"
        await self.async_save()
        self._notify()

    async def async_reset_queue(self, queue_id: str | None = None) -> None:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")
        q.last_issued = q.start_number - 1
        q.current = 0
        q.current_cashier_id = None
        q.current_cashier_name = None
        q.waiting.clear()
        q.issued_at.clear()
        for c in self.cashiers.values():
            if c.queue_id == q.queue_id:
                c.current_ticket = 0
                c.current_ticket_display = ""
                c.call_started_at = None
                if c.status == "serving":
                    c.status = "idle"
        self.add_history(
            {"type": "reset", "queue_id": q.queue_id, "queue_name": q.name}
        )
        await self.async_save()
        self._notify()
        self.hass.bus.async_fire(
            EVENT_QUEUE_RESET,
            {
                "queue_id": q.queue_id,
                "queue_name": q.name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def async_save_cashiers(self, cashiers: list[dict[str, Any]]) -> None:
        new_map: dict[str, Cashier] = {}
        for item in cashiers:
            cid = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").trim()
            if not cid or not name:
                continue
            existing = self.cashiers.get(cid)
            status = existing.status if existing else "idle"
            c = Cashier(
                id=cid,
                name=name,
                enabled=bool(item.get("enabled", True)),
                status=status if status in ("idle", "serving", "break") else "idle",
                current_ticket=existing.current_ticket if existing else 0,
                current_ticket_display=existing.current_ticket_display if existing else "",
                queue_id=existing.queue_id if existing else DEFAULT_QUEUE_ID,
                last_call_at=existing.last_call_at if existing else None,
                call_started_at=existing.call_started_at if existing else None,
                served_count=existing.served_count if existing else 0,
            )
            new_map[cid] = c
        if not new_map:
            raise ValueError("At least one cashier is required")
        self.cashiers = new_map
        await self.async_save()
        self._notify()

    async def async_save_services(self, services: list[dict[str, Any]]) -> None:
        new_map: dict[str, ServiceType] = {}
        for item in services:
            sid = str(item.get("id") or "").strip().lower().replace(" ", "_")
            name = str(item.get("name") or "").strip()
            if not sid or not name:
                continue
            qid = str(item.get("queue_id") or DEFAULT_QUEUE_ID)
            if qid not in self.queues:
                qid = DEFAULT_QUEUE_ID
            new_map[sid] = ServiceType(
                id=sid,
                name=name,
                queue_id=qid,
                enabled=bool(item.get("enabled", True)),
                icon=str(item.get("icon") or "🎫"),
            )
        if not new_map:
            raise ValueError("At least one service is required")
        self.services = new_map
        await self.async_save()
        self._notify()

    async def async_save_theme(self, theme: dict[str, Any]) -> None:
        cleaned = dict(DEFAULT_THEME)
        for key in DEFAULT_THEME:
            if key in theme and isinstance(theme[key], str) and theme[key].startswith("#"):
                cleaned[key] = theme[key]
        self.theme = cleaned
        await self.async_save()
        self._notify()

    async def async_save_print_template(self, template: dict[str, Any]) -> None:
        cleaned = dict(DEFAULT_PRINT_TEMPLATE)
        for key, default in DEFAULT_PRINT_TEMPLATE.items():
            if key not in template:
                continue
            val = template[key]
            if isinstance(default, bool):
                cleaned[key] = bool(val)
            else:
                cleaned[key] = str(val) if val is not None else default
        self.print_template = cleaned
        await self.async_save()
        self._notify()

    async def async_save_security(self, data: dict[str, Any]) -> None:
        if "admin_pin" in data:
            pin = str(data.get("admin_pin") or "").strip()
            if pin and (not pin.isdigit() or len(pin) < 4):
                raise ValueError("PIN must be at least 4 digits or empty to disable")
            self.admin_pin = pin
        if "announce_enabled" in data:
            self.announce_enabled = bool(data["announce_enabled"])
        if "announce_entity" in data:
            self.announce_entity = str(data.get("announce_entity") or "").strip()
        if "announce_tts_entity" in data:
            self.announce_tts_entity = str(data.get("announce_tts_entity") or "")
        if "announce_templates" in data:
            self.announce_templates = {**DEFAULT_ANNOUNCE_TEMPLATES, **(data.get("announce_templates") or {})}
        if "call_sound" in data:
            self.call_sound = str(data.get("call_sound") or DEFAULT_CALL_SOUND)
        if "new_ticket_sound" in data:
            self.new_ticket_sound = str(data.get("new_ticket_sound") or "beep")
        if "ui_logo_url" in data:
            self.ui_logo_url = str(data.get("ui_logo_url") or "").strip()
        await self.async_save()
        self._notify()

    def verify_pin(self, pin: str | None) -> bool:
        if not self.admin_pin:
            return True
        return str(pin or "") == self.admin_pin

    def build_print_payload(self, event: dict[str, Any]) -> dict[str, Any]:
        tpl = self.print_template
        lines: list[str] = []
        if tpl.get("logo_url"):
            lines.append(f"[LOGO] {tpl['logo_url']}")
        if tpl.get("title"):
            lines.append(str(tpl["title"]))
        if tpl.get("header"):
            lines.append(str(tpl["header"]))
        if tpl.get("show_queue_name") and event.get("queue_name"):
            lines.append(f"Queue: {event['queue_name']}")
        if event.get("service_name"):
            lines.append(f"Service: {event['service_name']}")
        if tpl.get("show_number") and event.get("ticket_display"):
            lines.append(f"Number: {event['ticket_display']}")
        if tpl.get("show_waiting_count") and "waiting_count" in event:
            lines.append(
                f"Waiting ahead: {max(0, int(event['waiting_count']) - 1)}"
            )
        if tpl.get("show_eta") and event.get("eta") and event.get("eta") != "—":
            lines.append(f"Est. wait: {event['eta']}")
        if tpl.get("show_datetime"):
            ts = event.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    lines.append(dt.astimezone().strftime("%Y-%m-%d %H:%M"))
                except Exception:
                    lines.append(str(ts))
        if tpl.get("extra_line"):
            lines.append(str(tpl["extra_line"]))
        if tpl.get("footer"):
            lines.append(str(tpl["footer"]))
        if tpl.get("social_line"):
            lines.append(str(tpl["social_line"]))
        return {
            "lines": lines,
            "ticket_display": event.get("ticket_display"),
            "queue_id": event.get("queue_id"),
            "queue_name": event.get("queue_name"),
            "logo_url": tpl.get("logo_url") or "",
            "social_line": tpl.get("social_line") or "",
            "paper_width": tpl.get("paper_width", "58mm"),
            "template": {
                "title": tpl.get("title"),
                "header": tpl.get("header"),
                "footer": tpl.get("footer"),
                "extra_line": tpl.get("extra_line"),
                "logo_url": tpl.get("logo_url"),
                "social_line": tpl.get("social_line"),
                "paper_width": tpl.get("paper_width", "58mm"),
            },
        }

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
