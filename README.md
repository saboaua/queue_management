# Queue Management for Home Assistant

Professional **queue / ticket system** that runs entirely inside Home Assistant.  
No Lovelace cards required — it has its **own dedicated page** in the sidebar.

Works on computers, tablets and TVs. Home Assistant is the server.

---

## Instant access (after install)

After you add the integration and restart:

1. Look in the **Home Assistant sidebar**
2. Click **Queue Management** 🎫
3. Or open directly:  
   `http://homeassistant.local:8123/queue-management`

You get four modes in one page:

| Mode | Use on | What it does |
|------|--------|----------------|
| **Reception** | Reception tablet | Big “Take Ticket” button, shows the issued number |
| **Calling Desk** | Counter / staff tablet | Call next, complete ticket, see waiting list |
| **Display** | Waiting-area TV / tablet | Large “NOW SERVING” number |
| **Admin** | Back-office | Reset, create queues, printer & announcement settings, history |

All devices stay in sync automatically (refreshes every 3 seconds).

---

## How a professional setup works

```
┌─────────────────────┐       ┌──────────────────────┐       ┌─────────────────────┐
│  RECEPTION TABLET   │       │   HOME ASSISTANT     │       │  CALLING DESK       │
│  Mode: Reception    │◄─────►│  Queue Management    │◄─────►│  Mode: Calling Desk │
│  Take Ticket        │       │  + Sidebar Panel     │       │  Call Next / Close  │
└─────────────────────┘       └──────────────────────┘       └─────────────────────┘
         ▲                                                              │
         │                     Mode: Display                            │
         └────────────── WAITING AREA TV / TABLET ──────────────────────┘
```

**Recommended URLs for each device**

| Device | URL |
|--------|-----|
| Any (sidebar) | `http://YOUR-HA:8123/queue-management` |
| Direct UI (fullscreen friendly) | `http://YOUR-HA:8123/queue_management/static/index.html` |

On tablets: open the link → browser menu → **Add to Home Screen** for an app-like experience.

---

## Installation

### HACS

1. HACS → Integrations → ⋮ → Custom repositories  
   Add: `https://github.com/saboaua/queue_management` (Integration)
2. Download **Queue Management**
3. Restart Home Assistant
4. Settings → Devices & Services → Add Integration → **Queue Management**

### Manual

Copy `custom_components/queue_management` into `config/custom_components/` and restart.

---

## Features

- Own sidebar page (no Lovelace setup)
- Multiple queues (main, VIP, counters…)
- Ticket numbers with optional prefix
- Call next / call specific / complete (close)
- Full history of issued / called / completed tickets
- Printer settings (works with IPP / automations on events)
- Voice announcement settings (TTS media player)
- Persistent storage (survives restarts)
- Sensors & buttons still available for automations
- Events: `queue_management_ticket_issued`, `_ticket_called`, `_queue_reset`

---

## Printer configuration

1. Open **Queue Management → Admin**
2. Enable “Printer integration” and enter your printer name / entity
3. Or create an automation on the event:

```yaml
automation:
  - alias: Print ticket when issued
    trigger:
      - platform: event
        event_type: queue_management_ticket_issued
    action:
      # Example: notify a printer integration or script
      - service: notify.your_printer
        data:
          message: "Ticket {{ trigger.event.data.ticket_display }}"
```

---

## Voice announcement

1. Admin → enable announcement → set a `media_player` entity  
2. Or use the included blueprint in `blueprints/automation/`

---

## Entities (for automations)

Still created under the **Main Queue** device:

- `sensor.main_queue_current_serving`
- `sensor.main_queue_last_ticket_issued`
- `sensor.main_queue_waiting`
- `sensor.main_queue_status`
- Buttons: take ticket, call next, reset

Plus system sensor **Access links** with the panel URL.

---

## Services

| Service | Description |
|---------|-------------|
| `queue_management.take_ticket` | Issue next ticket |
| `queue_management.call_next` | Call next waiting ticket |
| `queue_management.call_ticket` | Call a specific number |
| `queue_management.reset_queue` | Reset counter & waiting list |
| `queue_management.create_queue` | Create another queue |
| `queue_management.delete_queue` | Delete a queue |

---

## Folder structure

```
custom_components/queue_management/
├── __init__.py          # Panel + services
├── http.py              # API + static frontend
├── queue.py             # Core logic + history
├── sensor.py / button.py
├── frontend/
│   ├── index.html       # Full UI
│   ├── style.css
│   └── app.js
└── ...
```

---

## License

MIT
