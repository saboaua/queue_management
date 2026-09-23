"""Queue data model and manager for Queue Management."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send

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

DEFAULT_THEME = {
    "bg": "#0f172a",
    "card": "#1e293b",
    "text": "#f1f5f9",
    "muted": "#94a3b8",
    "accent": "#3b82f6",
    "success": "#22c55e",
    "warning": "#f97316",
    "danger": "#ef4444",
}

DEFAULT_PRINT_TEMPLATE = {
    "title": "QUEUE TICKET",
    "show_number": True,
    "show_queue_name": True,
    "show_datetime": True,
    "show_waiting_count": True,
    "header": "Please wait for your number",
    "footer": "Thank you for your patience",
    "extra_line": "",
    "paper_width": "58mm",
}

DEFAULT_CASHIERS = [
    {"id": "cashier_1", "name": "Cashier 1", "enabled": True},
    {"id": "cashier_2", "name": "Cashier 2", "enabled": True},
    {"id": "cashier_3", "name": "Cashier 3", "enabled": True},
]


@dataclass
class Cashier:
    """A service point / cashier / counter."""

    id: str
    name: str
    enabled: bool = True
    current_ticket: int = 0
    current_ticket_display: str = ""
    queue_id: str = DEFAULT_QUEUE_ID
    status: str = "idle"  # idle | serving
    last_call_at: str | None = None
    served_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Cashier":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            enabled=data.get("enabled", True),
            current_ticket=data.get("current_ticket", 0),
            current_ticket_display=data.get("current_ticket_display", ""),
            queue_id=data.get("queue_id", DEFAULT_QUEUE_ID),
            status=data.get("status", "idle"),
            last_call_at=data.get("last_call_at"),
            served_count=data.get("served_count", 0),
        )


@dataclass
class Queue:
    """Represents a single queue."""

    queue_id: str
    name: str
    prefix: str = ""
    start_number: int = 1
    last_issued: int = 0
    current: int = 0
    current_cashier_id: str | None = None
    current_cashier_name: str | None = None
    waiting: list[int] = field(default_factory=list)
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
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Queue":
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
            created_at=data.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
        )


class QueueManager:
    """Manages queues, cashiers, theme and history."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.queues: dict[str, Queue] = {}
        self.cashiers: dict[str, Cashier] = {}
        self.theme: dict[str, str] = dict(DEFAULT_THEME)
        self.print_template: dict[str, Any] = dict(DEFAULT_PRINT_TEMPLATE)
        self.history: list[dict[str, Any]] = []
        self._loaded = False

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data and "queues" in data:
            for qdata in data["queues"]:
                q = Queue.from_dict(qdata)
                self.queues[q.queue_id] = q
            self.history = list(data.get("history", []))[-MAX_HISTORY:]
            for cdata in data.get("cashiers", []):
                c = Cashier.from_dict(cdata)
                self.cashiers[c.id] = c
            self.theme = {**DEFAULT_THEME, **(data.get("theme") or {})}
            self.print_template = {**DEFAULT_PRINT_TEMPLATE, **(data.get("print_template") or {})}
            _LOGGER.debug("Loaded %d queues, %d cashiers", len(self.queues), len(self.cashiers))
        else:
            self.queues[DEFAULT_QUEUE_ID] = Queue(
                queue_id=DEFAULT_QUEUE_ID,
                name=DEFAULT_QUEUE_NAME,
            )
            await self.async_save()

        if not self.cashiers:
            for c in DEFAULT_CASHIERS:
                self.cashiers[c["id"]] = Cashier(
                    id=c["id"], name=c["name"], enabled=c["enabled"]
                )
            await self.async_save()

        self._loaded = True

    async def async_save(self) -> None:
        data = {
            "queues": [q.to_dict() for q in self.queues.values()],
            "cashiers": [c.to_dict() for c in self.cashiers.values()],
            "theme": self.theme,
            "print_template": self.print_template,
            "history": self.history[-MAX_HISTORY:],
        }
        await self._store.async_save(data)

    def add_history(self, entry: dict[str, Any]) -> None:
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self.history.append(entry)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    def get_queue(self, queue_id: str | None = None) -> Queue | None:
        return self.queues.get(queue_id or DEFAULT_QUEUE_ID)

    def get_cashier(self, cashier_id: str | None) -> Cashier | None:
        if not cashier_id:
            return None
        return self.cashiers.get(cashier_id)

    def overview(self) -> dict[str, Any]:
        """Manager live overview."""
        total_waiting = sum(q.waiting_count for q in self.queues.values())
        total_serving = sum(1 for c in self.cashiers.values() if c.status == "serving")
        idle_cashiers = [
            {"id": c.id, "name": c.name}
            for c in self.cashiers.values()
            if c.enabled and c.status == "idle"
        ]
        busy_cashiers = [
            {
                "id": c.id,
                "name": c.name,
                "ticket": c.current_ticket_display,
                "ticket_raw": c.current_ticket,
                "queue_id": c.queue_id,
                "last_call_at": c.last_call_at,
                "served_count": c.served_count,
            }
            for c in self.cashiers.values()
            if c.enabled and c.status == "serving"
        ]
        disabled = [
            {"id": c.id, "name": c.name}
            for c in self.cashiers.values()
            if not c.enabled
        ]
        return {
            "total_waiting": total_waiting,
            "total_serving": total_serving,
            "cashiers_enabled": sum(1 for c in self.cashiers.values() if c.enabled),
            "cashiers_idle": idle_cashiers,
            "cashiers_busy": busy_cashiers,
            "cashiers_disabled": disabled,
            "queues": [
                {
                    "queue_id": q.queue_id,
                    "name": q.name,
                    "waiting": q.waiting_count,
                    "current_display": q.format_ticket(q.current) if q.current else "—",
                    "current_cashier_name": q.current_cashier_name,
                    "status": q.status,
                }
                for q in self.queues.values()
            ],
        }

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

    async def async_take_ticket(self, queue_id: str | None = None) -> dict[str, Any]:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")

        next_num = q.last_issued + 1
        q.last_issued = next_num
        q.waiting.append(next_num)
        ticket_str = q.format_ticket(next_num)
        event_data = {
            "queue_id": q.queue_id,
            "queue_name": q.name,
            "ticket": next_num,
            "ticket_display": ticket_str,
            "waiting_count": q.waiting_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.add_history({**event_data, "type": "issued"})
        await self.async_save()
        self._notify()
        print_payload = self.build_print_payload(event_data)
        event_data["print"] = print_payload
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

        cashier = self.get_cashier(cashier_id) if cashier_id else None
        if cashier_id and not cashier:
            raise ValueError(f"Cashier '{cashier_id}' not found")
        if cashier and not cashier.enabled:
            raise ValueError(f"Cashier '{cashier.name}' is disabled")

        next_num = q.waiting.pop(0)
        q.current = next_num
        ticket_str = q.format_ticket(next_num)
        now = datetime.now(timezone.utc).isoformat()

        if cashier:
            # Free previous ticket on this cashier if any
            cashier.current_ticket = next_num
            cashier.current_ticket_display = ticket_str
            cashier.queue_id = q.queue_id
            cashier.status = "serving"
            cashier.last_call_at = now
            q.current_cashier_id = cashier.id
            q.current_cashier_name = cashier.name
        else:
            q.current_cashier_id = None
            q.current_cashier_name = None

        event_data = {
            "queue_id": q.queue_id,
            "queue_name": q.name,
            "ticket": next_num,
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
        return event_data

    async def async_call_ticket(
        self,
        ticket: int,
        queue_id: str | None = None,
        cashier_id: str | None = None,
    ) -> dict[str, Any]:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")

        cashier = self.get_cashier(cashier_id) if cashier_id else None
        if cashier_id and not cashier:
            raise ValueError(f"Cashier '{cashier_id}' not found")

        if ticket in q.waiting:
            q.waiting.remove(ticket)
        q.current = ticket
        ticket_str = q.format_ticket(ticket)
        now = datetime.now(timezone.utc).isoformat()

        if cashier:
            cashier.current_ticket = ticket
            cashier.current_ticket_display = ticket_str
            cashier.queue_id = q.queue_id
            cashier.status = "serving"
            cashier.last_call_at = now
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
        return event_data

    async def async_complete(
        self,
        queue_id: str | None = None,
        cashier_id: str | None = None,
    ) -> None:
        """Mark current service complete for queue and/or cashier."""
        q = self.get_queue(queue_id)
        cashier = self.get_cashier(cashier_id) if cashier_id else None

        ticket = 0
        ticket_display = ""
        if cashier and cashier.current_ticket:
            ticket = cashier.current_ticket
            ticket_display = cashier.current_ticket_display
            cashier.served_count += 1
            cashier.current_ticket = 0
            cashier.current_ticket_display = ""
            cashier.status = "idle"
        if q and q.current:
            if not ticket:
                ticket = q.current
                ticket_display = q.format_ticket(q.current)
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
        # Clear cashiers bound to this queue
        for c in self.cashiers.values():
            if c.queue_id == q.queue_id:
                c.current_ticket = 0
                c.current_ticket_display = ""
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
        """Replace cashier list from admin UI."""
        new_map: dict[str, Cashier] = {}
        for item in cashiers:
            cid = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            if not cid or not name:
                continue
            existing = self.cashiers.get(cid)
            c = Cashier(
                id=cid,
                name=name,
                enabled=bool(item.get("enabled", True)),
                current_ticket=existing.current_ticket if existing else 0,
                current_ticket_display=existing.current_ticket_display if existing else "",
                queue_id=existing.queue_id if existing else DEFAULT_QUEUE_ID,
                status=existing.status if existing else "idle",
                last_call_at=existing.last_call_at if existing else None,
                served_count=existing.served_count if existing else 0,
            )
            new_map[cid] = c
        if not new_map:
            raise ValueError("At least one cashier is required")
        self.cashiers = new_map
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

    def build_print_payload(self, event: dict[str, Any]) -> dict[str, Any]:
        """Build ticket content for printing from template + event."""
        tpl = self.print_template
        lines = []
        if tpl.get("title"):
            lines.append(str(tpl["title"]))
        if tpl.get("header"):
            lines.append(str(tpl["header"]))
        if tpl.get("show_queue_name") and event.get("queue_name"):
            lines.append(f"Queue: {event['queue_name']}")
        if tpl.get("show_number") and event.get("ticket_display"):
            lines.append(f"Number: {event['ticket_display']}")
        if tpl.get("show_waiting_count") and "waiting_count" in event:
            lines.append(f"Waiting ahead: {max(0, int(event['waiting_count']) - 1)}")
        if tpl.get("show_datetime"):
            lines.append(event.get("timestamp") or datetime.now(timezone.utc).isoformat())
        if tpl.get("extra_line"):
            lines.append(str(tpl["extra_line"]))
        if tpl.get("footer"):
            lines.append(str(tpl["footer"]))
        return {
            "lines": lines,
            "ticket_display": event.get("ticket_display"),
            "queue_id": event.get("queue_id"),
            "queue_name": event.get("queue_name"),
            "paper_width": tpl.get("paper_width", "58mm"),
            "template": {
                "title": tpl.get("title"),
                "header": tpl.get("header"),
                "footer": tpl.get("footer"),
                "extra_line": tpl.get("extra_line"),
                "paper_width": tpl.get("paper_width", "58mm"),
            },
        }

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
