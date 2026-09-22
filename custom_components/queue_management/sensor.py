"""Sensor platform for Queue Management."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.network import get_url

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

    # One system-level sensor that shows the tablet access links
    entities.append(AccessLinksSensor(hass, manager))

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


class AccessLinksSensor(SensorEntity):
    """Shows the recommended dashboard URLs for tablets."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:link-variant"
    _attr_translation_key = "access_links"
    _attr_unique_id = f"{DOMAIN}_access_links"

    def __init__(self, hass: HomeAssistant, manager: QueueManager) -> None:
        self.hass = hass
        self._manager = manager
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "system")},
            name="Queue Management",
            manufacturer="Queue Management",
            model="System",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str:
        return "Open sidebar → Queue Management"

    @property
    def extra_state_attributes(self) -> dict:
        try:
            base = get_url(self.hass, prefer_external=False)
        except Exception:
            base = "http://homeassistant.local:8123"

        base = base.rstrip("/")

        return {
            "panel_url": f"{base}/queue-management",
            "direct_ui": f"{base}/queue_management/",
            "reception_note": "Open the Queue Management sidebar item, then choose Reception mode",
            "calling_note": "Open the Queue Management sidebar item, then choose Calling Desk mode",
            "display_note": "Open the Queue Management sidebar item, then choose Display mode (or open direct_ui on a TV)",
            "howto": (
                "After installing, open the sidebar → Queue Management. "
                "Or go directly to /queue-management. "
                "Use the mode buttons (Reception / Calling Desk / Display / Admin) "
                "for each tablet or computer. No Lovelace setup required."
            ),
            "queues": list(self._manager.queues.keys()),
        }


class QueueBaseSensor(SensorEntity):
    """Base class for queue sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        self._manager = manager
        self._queue_id = queue_id
        q = manager.queues[queue_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, queue_id)},
            name=q.name,
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
