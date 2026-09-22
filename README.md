# Queue Management for Home Assistant

Professional **queue / ticket management system** that runs entirely inside Home Assistant.  
Perfect for reception desks, clinics, offices, shops, or any waiting-line scenario.

Home Assistant acts as the **central server**.  
Tablets and computers simply open browser dashboards – no extra software needed.

---

## How a professional setup works

```
┌─────────────────────┐       ┌──────────────────────┐       ┌─────────────────────┐
│  RECEPTION TABLET   │       │   HOME ASSISTANT     │       │  CALLING DESK       │
│                     │       │      (Server)        │       │                     │
│  • Take Ticket      │◄─────►│  Queue Management    │◄─────►│  • Call Next        │
│  • Show number      │       │  Stores all queues   │       │  • Now Serving      │
│  • Waiting count    │       │  Fires events        │       │  • Announce (TTS)   │
└─────────────────────┘       └──────────────────────┘       └─────────────────────┘
         ▲                                                              │
         │                                                              │
         └────────────── WAITING AREA DISPLAY (TV / tablet) ────────────┘
                         Shows large “NOW SERVING” number
```

### Direct links for each station

After you create the dashboards (see below), open these URLs on each device:

| Station              | Recommended URL                                      | Use on          |
|----------------------|------------------------------------------------------|-----------------|
| **Reception**        | `http://homeassistant.local:8123/lovelace/reception` | Tablet / PC     |
| **Calling Desk**     | `http://homeassistant.local:8123/lovelace/calling`   | Tablet / PC     |
| **Waiting Area**     | `http://homeassistant.local:8123/lovelace/display`   | TV / large tablet |

Replace `homeassistant.local` with your Home Assistant IP address if needed  
(e.g. `http://192.168.1.50:8123/lovelace/reception`).

**Tip for tablets:**  
In the browser menu choose **“Add to Home Screen”** → open the icon → it runs almost fullscreen.  
For true kiosk mode install the custom card **Kiosk Mode** or use the Companion App in fullscreen.

---

## Features

- Multiple independent queues (`main`, `vip`, `counter_2`…)
- Ticket numbers with optional prefix (`A12`, `VIP-7`…)
- Call next / call specific ticket
- Reset queue
- Live sensors + one-tap buttons
- Persistent storage (survives restarts)
- Events for TTS announcements, printing, notifications
- Ready-made dashboards & blueprint included

---

## Installation

### Via HACS (recommended)

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add: `https://github.com/saboaua/queue_management`  
   Category: **Integration**
3. Download **Queue Management**
4. Restart Home Assistant
5. Settings → Devices & Services → **Add Integration** → search **Queue Management**

### Manual

Copy the folder `custom_components/queue_management` into your  
`config/custom_components/` directory and restart.

---

## Quick start – create the three dashboards

1. Go to **Settings → Dashboards → Add Dashboard**
2. Create three dashboards with these URL paths:

   | Title          | URL path   |
   |----------------|------------|
   | Reception      | `reception`|
   | Calling        | `calling`  |
   | Waiting Area   | `display`  |

3. Open each dashboard → **⋮ → Raw configuration editor**
4. Copy the content from the corresponding file in the `examples/` folder of this repository:

   - `examples/dashboard_reception.yaml`
   - `examples/dashboard_calling.yaml`
   - `examples/dashboard_display.yaml`

5. Save.

You can now open the links shown in the table above on any tablet or computer.

---

## Blueprint – Automatic voice announcement

A ready blueprint is included so the system can speak the ticket number when it is called.

1. Copy the file  
   `blueprints/automation/queue_announce_ticket.yaml`  
   into your Home Assistant folder:  
   `config/blueprints/automation/`
2. Restart Home Assistant (or reload automations)
3. Go to **Settings → Automations → Create Automation → Use Blueprint**
4. Select **“Queue Management – Announce Ticket”**
5. Choose your speaker (Google Home, Nest Mini, Sonos, browser_mod, etc.)
6. Save

Now every time someone presses **Call Next**, the speaker will announce:

> “Ticket number 42, please proceed to the counter.”

---

## Entities created (per queue)

| Type   | Example entity_id                        | Description              |
|--------|------------------------------------------|--------------------------|
| Sensor | `sensor.main_queue_current_serving`      | Currently called ticket  |
| Sensor | `sensor.main_queue_last_ticket_issued`   | Last ticket given out    |
| Sensor | `sensor.main_queue_waiting`              | People waiting           |
| Sensor | `sensor.main_queue_status`               | idle / active / serving  |
| Button | `button.main_queue_take_ticket`          | Issue next ticket        |
| Button | `button.main_queue_call_next`            | Call next ticket         |
| Button | `button.main_queue_reset_queue`          | Reset the queue          |

Each queue appears as a **Device** in Home Assistant.

---

## Services

| Service                          | Description                              |
|----------------------------------|------------------------------------------|
| `queue_management.take_ticket`   | Issue next ticket (returns the number)   |
| `queue_management.call_next`     | Call the next waiting ticket             |
| `queue_management.call_ticket`   | Call a specific number                   |
| `queue_management.reset_queue`   | Clear waiting list & reset counter       |
| `queue_management.create_queue`  | Create a new queue                       |
| `queue_management.delete_queue`  | Delete a queue (not the main one)        |

### Create a VIP queue example

```yaml
service: queue_management.create_queue
data:
  queue_id: vip
  name: VIP Counter
  prefix: "V"
  start_number: 1
```

---

## Events (for advanced automations)

- `queue_management_ticket_issued`
- `queue_management_ticket_called`
- `queue_management_queue_reset`

All events contain `ticket`, `ticket_display`, `queue_id`, `queue_name`, `waiting_count`, `timestamp`.

---

## Folder structure

```
queue_management/
├── custom_components/queue_management/   ← the integration
├── examples/
│   ├── dashboard_reception.yaml
│   ├── dashboard_calling.yaml
│   ├── dashboard_display.yaml
│   └── automation_announce_ticket.yaml
├── blueprints/automation/
│   └── queue_announce_ticket.yaml
├── hacs.json
├── LICENSE
└── README.md
```

---

## Tips for a professional look

1. **Fullscreen / Kiosk**  
   Install the custom card [Kiosk Mode](https://github.com/NemesisRE/kiosk-mode) or use the Home Assistant Companion App in fullscreen.

2. **Hide the sidebar** on the tablets  
   Use Kiosk Mode or a browser extension.

3. **Thermal printer**  
   Trigger a print when a ticket is issued using an IPP printer integration or a script that sends the ticket number to a network printer.

4. **Multiple counters**  
   Create one queue per counter (`counter1`, `counter2`…) and make separate calling dashboards.

5. **Daily reset**  
   Create a simple automation that runs every morning:

   ```yaml
   service: queue_management.reset_queue
   data:
     queue_id: main
   ```

---

## License

MIT
