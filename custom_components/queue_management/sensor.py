"""Sensor platform for Queue Management."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .queue import QueueManager, SIGNAL_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    manager: QueueManager = hass.data[DOMAIN]

    entities: list[SensorEntity] = []
    for queue in manager.queues.values():
        entities.extend(
            [
                QueueCurrentSensor(manager, queue.queue_id),
                QueueLastIssuedSensor(manager, queue.queue_id),
                QueueWaitingSensor(manager, queue.queue_id),
                QueueStatusSensor(manager, queue.queue_id),
            ]
        )

    async_add_entities(entities)


class QueueBaseSensor(SensorEntity):
    """Base class for queue sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        self._manager = manager
        self._queue_id = queue_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, queue_id)},
            name=manager.queues[queue_id].name,
            manufacturer="Queue Management",
            model="Virtual Queue",
        )

    @property
    def available(self) -> bool:
        return self._queue_id in self._manager.queues

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class QueueCurrentSensor(QueueBaseSensor):
    """Currently serving ticket."""

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        super().__init__(manager, queue_id)
        self._attr_unique_id = f"{DOMAIN}_{queue_id}_current"
        self._attr_translation_key = "current"
        self._attr_icon = "mdi:account-voice"

    @property
    def native_value(self) -> str | int:
        q = self._manager.get_queue(self._queue_id)
        if not q or q.current == 0:
            return "—"
        return q.format_ticket(q.current)

    @property
    def extra_state_attributes(self) -> dict:
        q = self._manager.get_queue(self._queue_id)
        if not q:
            return {}
        return {
            "raw_number": q.current,
            "queue_id": q.queue_id,
            "queue_name": q.name,
        }


class QueueLastIssuedSensor(QueueBaseSensor):
    """Last ticket issued."""

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        super().__init__(manager, queue_id)
        self._attr_unique_id = f"{DOMAIN}_{queue_id}_last_issued"
        self._attr_translation_key = "last_issued"
        self._attr_icon = "mdi:ticket-confirmation"

    @property
    def native_value(self) -> str | int:
        q = self._manager.get_queue(self._queue_id)
        if not q or q.last_issued == 0:
            return "—"
        return q.format_ticket(q.last_issued)

    @property
    def extra_state_attributes(self) -> dict:
        q = self._manager.get_queue(self._queue_id)
        if not q:
            return {}
        return {
            "raw_number": q.last_issued,
            "queue_id": q.queue_id,
        }


class QueueWaitingSensor(QueueBaseSensor):
    """Number of people waiting."""

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        super().__init__(manager, queue_id)
        self._attr_unique_id = f"{DOMAIN}_{queue_id}_waiting"
        self._attr_translation_key = "waiting"
        self._attr_icon = "mdi:account-group"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "tickets"

    @property
    def native_value(self) -> int:
        q = self._manager.get_queue(self._queue_id)
        return q.waiting_count if q else 0

    @property
    def extra_state_attributes(self) -> dict:
        q = self._manager.get_queue(self._queue_id)
        if not q:
            return {}
        return {
            "waiting_tickets": [q.format_ticket(n) for n in q.waiting],
            "raw_waiting": q.waiting,
            "queue_id": q.queue_id,
        }


class QueueStatusSensor(QueueBaseSensor):
    """Queue status (idle / active / serving)."""

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        super().__init__(manager, queue_id)
        self._attr_unique_id = f"{DOMAIN}_{queue_id}_status"
        self._attr_translation_key = "status"
        self._attr_icon = "mdi:information-outline"

    @property
    def native_value(self) -> str:
        q = self._manager.get_queue(self._queue_id)
        return q.status if q else "unknown"
