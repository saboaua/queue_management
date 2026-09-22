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


@dataclass
class Queue:
    """Represents a single queue."""

    queue_id: str
    name: str
    prefix: str = ""
    start_number: int = 1
    last_issued: int = 0
    current: int = 0  # currently serving (0 = none)
    waiting: list[int] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def format_ticket(self, number: int) -> str:
        """Return human-readable ticket string."""
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
            waiting=list(data.get("waiting", [])),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


class QueueManager:
    """Manages all queues, history and persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.queues: dict[str, Queue] = {}
        self.history: list[dict[str, Any]] = []
        self._loaded = False

    async def async_load(self) -> None:
        """Load queues from storage."""
        data = await self._store.async_load()
        if data and "queues" in data:
            for qdata in data["queues"]:
                q = Queue.from_dict(qdata)
                self.queues[q.queue_id] = q
            self.history = list(data.get("history", []))[-MAX_HISTORY:]
            _LOGGER.debug("Loaded %d queues from storage", len(self.queues))
        else:
            self.queues[DEFAULT_QUEUE_ID] = Queue(
                queue_id=DEFAULT_QUEUE_ID,
                name=DEFAULT_QUEUE_NAME,
            )
            await self.async_save()
            _LOGGER.info("Created default queue '%s'", DEFAULT_QUEUE_ID)
        self._loaded = True

    async def async_save(self) -> None:
        """Persist queues and history to storage."""
        data = {
            "queues": [q.to_dict() for q in self.queues.values()],
            "history": self.history[-MAX_HISTORY:],
        }
        await self._store.async_save(data)

    def add_history(self, entry: dict[str, Any]) -> None:
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self.history.append(entry)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    def get_queue(self, queue_id: str | None = None) -> Queue | None:
        qid = queue_id or DEFAULT_QUEUE_ID
        return self.queues.get(qid)

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
        _LOGGER.info("Created queue '%s' (%s)", queue_id, name)
        return q

    async def async_delete_queue(self, queue_id: str) -> None:
        if queue_id == DEFAULT_QUEUE_ID:
            raise ValueError("Cannot delete the main queue")
        if queue_id not in self.queues:
            raise ValueError(f"Queue '{queue_id}' not found")
        del self.queues[queue_id]
        await self.async_save()
        self._notify()
        _LOGGER.info("Deleted queue '%s'", queue_id)

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
        self.hass.bus.async_fire(EVENT_TICKET_ISSUED, event_data)
        _LOGGER.info("Ticket %s issued on queue %s", ticket_str, q.queue_id)
        return event_data

    async def async_call_next(self, queue_id: str | None = None) -> dict[str, Any] | None:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")

        if not q.waiting:
            _LOGGER.debug("No tickets waiting in queue %s", q.queue_id)
            return None

        next_num = q.waiting.pop(0)
        q.current = next_num
        ticket_str = q.format_ticket(next_num)
        event_data = {
            "queue_id": q.queue_id,
            "queue_name": q.name,
            "ticket": next_num,
            "ticket_display": ticket_str,
            "waiting_count": q.waiting_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.add_history({**event_data, "type": "called"})
        await self.async_save()
        self._notify()
        self.hass.bus.async_fire(EVENT_TICKET_CALLED, event_data)
        _LOGGER.info("Called ticket %s on queue %s", ticket_str, q.queue_id)
        return event_data

    async def async_call_ticket(
        self, ticket: int, queue_id: str | None = None
    ) -> dict[str, Any]:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")

        if ticket in q.waiting:
            q.waiting.remove(ticket)
        q.current = ticket
        ticket_str = q.format_ticket(ticket)
        event_data = {
            "queue_id": q.queue_id,
            "queue_name": q.name,
            "ticket": ticket,
            "ticket_display": ticket_str,
            "waiting_count": q.waiting_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.add_history({**event_data, "type": "called"})
        await self.async_save()
        self._notify()
        self.hass.bus.async_fire(EVENT_TICKET_CALLED, event_data)
        _LOGGER.info("Called specific ticket %s on queue %s", ticket_str, q.queue_id)
        return event_data

    async def async_reset_queue(self, queue_id: str | None = None) -> None:
        q = self.get_queue(queue_id)
        if not q:
            raise ValueError(f"Queue '{queue_id or DEFAULT_QUEUE_ID}' not found")

        q.last_issued = q.start_number - 1
        q.current = 0
        q.waiting.clear()
        self.add_history(
            {
                "type": "reset",
                "queue_id": q.queue_id,
                "queue_name": q.name,
            }
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
        _LOGGER.info("Reset queue %s", q.queue_id)

    @callback
    def _notify(self) -> None:
        """Notify entities that data has changed."""
        async_dispatcher_send(self.hass, SIGNAL_UPDATE)
