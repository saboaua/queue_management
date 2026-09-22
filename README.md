# Queue Management for Home Assistant

A complete **queue / ticket management system** that runs entirely inside Home Assistant. Perfect for reception desks, clinics, government offices, shops, or any waiting-line scenario.

Home Assistant acts as the **central server**. Tablets or computers in the reception area and calling area simply open Lovelace dashboards (or the companion app) to:

- Print / display a ticket number
- See the current serving number
- Call the next person
- Monitor waiting count

Everything stays local – no external cloud required.

## Features

- Multiple independent queues (e.g. `main`, `vip`, `counter_2`)
- Ticket issuance with optional prefix (`A12`, `VIP-5`, etc.)
- Call next / call specific ticket
- Reset queue
- Live sensors: Current serving, Last issued, Waiting count, Status
- Buttons for one-tap actions on tablets
- Persistent storage (survives restarts)
- Events for automations, TTS announcements, printing, etc.
- Fully configurable via UI + services
- HACS installable

## Screenshots / Typical Setup

**Reception tablet dashboard**
- Large “Take Ticket” button
- Big display of the issued number
- Waiting count

**Calling desk / counter dashboard**
- Large “Call Next” button
- Current number being served
- List of waiting tickets (via attributes)

## Installation

### HACS (recommended)

1. Open **HACS → Integrations**
2. Click the three dots (⋮) → **Custom repositories**
3. Add: `https://github.com/saboaua/queue_management`  
   Category: **Integration**
4. Search for **Queue Management** and download it
5. **Restart Home Assistant**
6. Go to **Settings → Devices & Services → Add Integration** → search **Queue Management**
7. Click Submit (no extra configuration needed)

### Manual

1. Copy the `custom_components/queue_management` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via the UI as above

## Entities created (per queue)

| Entity type | Example entity_id | Description |
|-------------|-------------------|-------------|
| Sensor | `sensor.main_queue_current_serving` | Currently called ticket |
| Sensor | `sensor.main_queue_last_ticket_issued` | Last ticket given out |
| Sensor | `sensor.main_queue_waiting` | Number of people waiting |
| Sensor | `sensor.main_queue_status` | `idle` / `active` / `serving` |
| Button | `button.main_queue_take_ticket` | Issue next ticket |
| Button | `button.main_queue_call_next` | Call next ticket |
| Button | `button.main_queue_reset_queue` | Reset the queue |

Each queue appears as a **Device** in Home Assistant.

## Services

| Service | Description |
|---------|-------------|
| `queue_management.take_ticket` | Issue next ticket (returns ticket data) |
| `queue_management.call_next` | Call the next waiting ticket |
| `queue_management.call_ticket` | Call a specific number |
| `queue_management.reset_queue` | Clear waiting list & reset counter |
| `queue_management.create_queue` | Create a new queue |
| `queue_management.delete_queue` | Delete a queue (not the main one) |

### Example: Create a VIP queue

```yaml
service: queue_management.create_queue
data:
  queue_id: vip
  name: VIP Counter
  prefix: "V"
  start_number: 1
```

### Example: Take a ticket (and get the number back)

```yaml
service: queue_management.take_ticket
data:
  queue_id: main
# Response contains ticket, ticket_display, waiting_count, etc.
```

## Events

You can listen for these events in automations:

- `queue_management_ticket_issued`
- `queue_management_ticket_called`
- `queue_management_queue_reset`

**Example – TTS announcement when a ticket is called**

```yaml
automation:
  - alias: "Announce next ticket"
    trigger:
      - platform: event
        event_type: queue_management_ticket_called
    action:
      - service: tts.speak
        data:
          media_player_entity_id: media_player.reception_speaker
          message: >
            Ticket {{ trigger.event.data.ticket_display }} please proceed to the counter.
```

**Example – Print ticket (using a browser or printer integration)**

Many users open a dedicated dashboard view that shows the latest ticket in large font and use the tablet’s print function, or trigger a network printer via an integration (e.g. `ipp`, `cups`, or a script).

## Recommended Lovelace dashboards

### Reception (tablet)

```yaml
title: Reception
views:
  - title: Take Ticket
    path: take
    cards:
      - type: vertical-stack
        cards:
          - type: markdown
            content: |
              # Welcome
              Please take a ticket
          - type: button
            entity: button.main_queue_take_ticket
            name: TAKE TICKET
            icon: mdi:ticket
            show_state: false
            tap_action:
              action: call-service
              service: queue_management.take_ticket
          - type: entity
            entity: sensor.main_queue_last_ticket_issued
            name: Your Number
          - type: entity
            entity: sensor.main_queue_waiting
            name: People waiting
```

### Calling desk

```yaml
title: Counter
views:
  - title: Call
    path: call
    cards:
      - type: vertical-stack
        cards:
          - type: entity
            entity: sensor.main_queue_current_serving
            name: NOW SERVING
          - type: button
            entity: button.main_queue_call_next
            name: CALL NEXT
            icon: mdi:bell-ring
          - type: entity
            entity: sensor.main_queue_waiting
            name: Waiting
```

Tip: Use the **Fullscreen** mode or the Companion App kiosk mode on tablets so the dashboard fills the whole screen.

## Advanced tips

- Use **Browser Mod** or **Kiosk Mode** custom cards for true kiosk experience.
- Combine with a thermal printer via IPP or a local CUPS add-on for automatic ticket printing.
- Create one queue per counter/service.
- The `waiting` sensor attributes contain the full list of waiting ticket numbers – useful for custom cards.

## Development / Contributing

This is a standard HACS custom integration.

```
custom_components/queue_management/
├── __init__.py
├── manifest.json
├── const.py
├── config_flow.py
├── queue.py          # Core logic + persistence
├── sensor.py
├── button.py
├── services.yaml
├── strings.json
└── translations/en.json
```

Feel free to open issues or PRs.

## License

MIT
