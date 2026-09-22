"""Button platform for Queue Management."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .queue import QueueManager, SIGNAL_UPDATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons."""
    manager: QueueManager = hass.data[DOMAIN]

    entities: list[ButtonEntity] = []
    for queue in manager.queues.values():
        entities.extend(
            [
                TakeTicketButton(manager, queue.queue_id),
                CallNextButton(manager, queue.queue_id),
                ResetQueueButton(manager, queue.queue_id),
            ]
        )

    async_add_entities(entities)


class QueueBaseButton(ButtonEntity):
    """Base class for queue buttons."""

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
            via_device=(DOMAIN, "system"),
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


class TakeTicketButton(QueueBaseButton):
    """Button to take a new ticket."""

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        super().__init__(manager, queue_id)
        self._attr_unique_id = f"{DOMAIN}_{queue_id}_take_ticket"
        self._attr_translation_key = "take_ticket"
        self._attr_icon = "mdi:ticket"

    async def async_press(self) -> None:
        await self._manager.async_take_ticket(self._queue_id)


class CallNextButton(QueueBaseButton):
    """Button to call the next ticket."""

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        super().__init__(manager, queue_id)
        self._attr_unique_id = f"{DOMAIN}_{queue_id}_call_next"
        self._attr_translation_key = "call_next"
        self._attr_icon = "mdi:bell-ring"

    async def async_press(self) -> None:
        await self._manager.async_call_next(self._queue_id)


class ResetQueueButton(QueueBaseButton):
    """Button to reset the queue."""

    def __init__(self, manager: QueueManager, queue_id: str) -> None:
        super().__init__(manager, queue_id)
        self._attr_unique_id = f"{DOMAIN}_{queue_id}_reset"
        self._attr_translation_key = "reset"
        self._attr_icon = "mdi:restart"
        self._attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self._manager.async_reset_queue(self._queue_id)
