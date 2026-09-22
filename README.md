# Queue Management for Home Assistant

Professional **queue / ticket management system** that runs entirely inside Home Assistant.  
Perfect for reception desks, clinics, offices, shops, or any waiting-line scenario.

Home Assistant acts as the **central server**.  
Tablets and computers simply open browser dashboards – no extra software needed.

---

## Important: Why the pages are not live right after install

Home Assistant custom integrations **cannot automatically create Lovelace dashboards**.  
This is a platform limitation (not a bug).

After installing the integration you will see:

- Devices & entities (sensors + buttons)
- A new sensor called **Access links** that shows the exact tablet URLs

You must create the three dashboards **once** (takes ~2 minutes). After that the links work forever.

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

### Direct links (after you create the dashboards)

| Station              | URL                                                    | Device          |
|----------------------|--------------------------------------------------------|-----------------|
| **Reception**        | `http://homeassistant.local:8123/lovelace/reception`   | Tablet / PC     |
| **Calling Desk**     | `http://homeassistant.local:8123/lovelace/calling`     | Tablet / PC     |
| **Waiting Area**     | `http://homeassistant.local:8123/lovelace/display`     | TV / tablet     |

Replace `homeassistant.local` with your Home Assistant IP if needed.

The integration also creates a sensor:

**`sensor.queue_management_access_links`**

Open it → look at the **Attributes**. You will see the exact URLs for your installation plus a short howto.

---

## Installation

### Via HACS (recommended)

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add: `https://github.com/saboaua/queue_management`  
   Category: **Integration**
3. Download **Queue Management**
4. **Restart Home Assistant**
5. Settings → Devices & Services → **Add Integration** → search **Queue Management** → Submit

### Manual

Copy `custom_components/queue_management` into `config/custom_components/` and restart.

---

## One-time dashboard setup (required)

1. Go to **Settings → Dashboards → Add Dashboard**
2. Create these three dashboards:

   | Title          | URL path    |
   |----------------|-------------|
   | Reception      | `reception` |
   | Calling        | `calling`   |
   | Waiting Area   | `display`   |

3. For each dashboard:
   - Open it
   - Click **⋮ → Raw configuration editor**
   - Delete the existing content
   - Paste the matching file from the `examples/` folder of this repository:
     - `examples/dashboard_reception.yaml`
     - `examples/dashboard_calling.yaml`
     - `examples/dashboard_display.yaml`
   - Save

4. Open the URLs on your tablets (see table above).

**Tip:** On tablets use “Add to Home Screen” so it opens almost fullscreen.

---

## After install – what you should see

### Devices

- **Queue Management** (system device) → contains the **Access links** sensor
- **Main Queue** → contains all sensors and buttons for the default queue

### Entities (Main Queue)

| Entity (typical ID)                     | Purpose                    |
|-----------------------------------------|----------------------------|
| `sensor.main_queue_current_serving`     | Number currently being served |
| `sensor.main_queue_last_ticket_issued`  | Last ticket given out      |
| `sensor.main_queue_waiting`             | How many people are waiting|
| `sensor.main_queue_status`              | idle / active / serving    |
| `button.main_queue_take_ticket`         | Issue next ticket          |
| `button.main_queue_call_next`           | Call next ticket           |
| `button.main_queue_reset_queue`         | Reset the queue            |

If the entity IDs are slightly different on your system, open the **Main Queue** device page and copy the real IDs into the dashboard YAML.

---

## Blueprint – Automatic voice announcement

1. Copy  
   `blueprints/automation/queue_announce_ticket.yaml`  
   into `config/blueprints/automation/`
2. Reload automations or restart HA
3. Settings → Automations → Create Automation → **Use Blueprint**
4. Choose **“Queue Management – Announce Ticket”**
5. Select your speaker and save

---

## Services

| Service                          | Description                              |
|----------------------------------|------------------------------------------|
| `queue_management.take_ticket`   | Issue next ticket                        |
| `queue_management.call_next`     | Call the next waiting ticket             |
| `queue_management.call_ticket`   | Call a specific number                   |
| `queue_management.reset_queue`   | Clear waiting list & reset counter       |
| `queue_management.create_queue`  | Create a new queue                       |
| `queue_management.delete_queue`  | Delete a queue (not the main one)        |

---

## Events

- `queue_management_ticket_issued`
- `queue_management_ticket_called`
- `queue_management_queue_reset`

---

## Folder structure

```
queue_management/
├── custom_components/queue_management/
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

1. Install **Kiosk Mode** custom card or use the Companion App in fullscreen.
2. Hide the sidebar on the tablets.
3. Create one queue per counter if you have several desks.
4. Add a daily reset automation at opening time.

---

## License

MIT
