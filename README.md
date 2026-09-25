# 🎫 Queue Management for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/saboaua/queue_management?style=for-the-badge&color=blue)](https://github.com/saboaua/queue_management/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

A standalone, professional **Queue & Ticket Management System** that runs entirely inside Home Assistant.

No complex Lovelace card setup is required. The integration registers its own dedicated sidebar panel and a full-screen web app that syncs across tablets, staff counters, waiting-area TVs, and desktops.

---

## ✨ Features

### Core
- **Dedicated sidebar panel** — one-click access from the Home Assistant sidebar
- **Fullscreen kiosk URL** — ideal for tablets and public displays (Add to Home Screen on iOS/Android)
- **Five operational modes** in a single UI: Reception, Calling Desk, Display, Manager, Admin
- **Real-time sync** — all connected clients refresh about every 3 seconds
- **Persistent storage** — queues, cashiers, services, theme, and history survive HA restarts
- **Multi-queue support** — independent lines (e.g. Main, VIP, Express) with optional ticket prefixes
- **Service categories** — reception shows configurable service types (General, Cashier, Support, …) with wait estimates
- **Cashier / counter management** — staff identities, idle / serving / break status
- **ETA & wait metrics** — estimated wait from recent service duration samples
- **Daily analytics** — issued / completed counts, hourly peaks, service mix (Manager view)
- **Light theme by default** — clean SaaS-style UI with Admin color customization
- **Optional Admin/Manager PIN** — protect settings and analytics
- **Custom logo URL** — branding on reception / header
- **Native HA entities** — sensors and buttons per queue for automations and Lovelace
- **HA events** — `queue_management_ticket_issued`, `queue_management_ticket_called`, `queue_management_queue_reset`
- **TTS announcements** — announce called tickets via any TTS + media_player entity
- **Thermal ticket printing** — configurable print template; lines exposed on the issued event for IPP/notify printers
- **Blueprints & example dashboards** — ready-made automations and Lovelace YAML

### Reception (kiosk / tablet)
- **Welcome + service list** — large touch rows with icon, name, optional description, wait time, and queue depth
- **One-tap ticket issue** — selecting a service issues a ticket immediately
- **Always-visible ticket panel** — number, service name, ETA, “Collect Ticket” CTA
- **Bottom KPI bar** — customers waiting, estimated wait, now serving
- **Self-service badge & live clock** — kiosk-oriented layout optimized for light theme contrast

### Calling Desk (staff counter)
- **Cashier picker** — serve as a specific counter / teller
- **Call next / Complete** — keyboard shortcuts: `N` = call next, `C` = complete
- **Go on break / Resume** — set cashier status without leaving the desk
- **Now serving display** — large ticket number + assigned cashier
- **Waiting list** — ordered queue with position, ticket, wait time; tap to call a specific ticket
- **Live stats** — waiting count, ETA, desk status

### Display (waiting-area TV)
- **Large “Now calling” board** — ticket number, cashier / counter label
- **Per-counter strip** — which desk is serving which ticket
- **Next-up list** — upcoming tickets
- **Meta row** — waiting count and status
- **Kiosk mode** — hides the app chrome for a clean public screen

### Manager (floor overview)
- **Live KPIs** — waiting, busy, idle, on break, average service time
- **Busy / idle / break lists** — who is available
- **Per-queue cards** — status at a glance
- **Charts** — peak hours and service mix (7-day)
- **Recent activity feed** — issued, called, completed, reset events
- **Optional PIN** — same lock as Admin when enabled

### Admin (configuration)
| Tab | What you configure |
|-----|-------------------|
| **Cashiers** | Add/edit/remove counters; names shown on Calling Desk and Display |
| **Services** | Reception service buttons: name, icon, linked queue, enabled |
| **Queues** | Create queues with ID, display name, ticket prefix, start number; reset/delete |
| **Appearance** | Theme colors (background, cards, text, accent, success, warning, danger); reset to light defaults |
| **Announcements** | Admin PIN; TTS on/off; media_player + TTS entity; announce templates (with / without cashier); logo URL; test announcement |
| **Ticket printing** | Logo, title, header, footer, extra line, paper width, show number / queue name / datetime; live preview |

---

## 🖥️ Operational Modes

| Mode | Target device | Description |
|------|---------------|-------------|
| **🎟️ Reception** | Tablet / kiosk | Self-service: pick a service → get a ticket; thermal panel + KPIs |
| **📢 Calling Desk** | Staff counter | Call next, complete, break/resume, waiting list, shortcuts |
| **📺 Display** | Waiting-area TV | Large now-serving board and next-up list |
| **📊 Manager** | Floor lead PC/tablet | Live overview, analytics, history |
| **⚙️ Admin** | Back-office PC | Cashiers, services, queues, theme, TTS, print template, PIN |

Switch modes from the top bar (or the floating menu in kiosk mode).

---

## 🏗️ Architecture

```text
  ┌─────────────────────────────────────────────────────────────┐
  │                    HOME ASSISTANT CORE                      │
  │  ┌───────────────────────────────────────────────────────┐  │
  │  │               Queue Management Engine                 │  │
  │  │  • Panel  • REST API  • Storage  • Events  • Entities │  │
  │  └──────────┬───────────────────┬───────────────────┬────┘  │
  └─────────────┼───────────────────┼───────────────────┼───────┘
                │                   │                   │
  ┌─────────────▼─────────┐ ┌───────▼─────────┐ ┌───────▼─────────┐
  │   RECEPTION KIOSK     │ │  CALLING DESK   │ │  DISPLAY SCREEN │
  │   (Tablet)            │ │ (Staff counter) │ │  (Waiting TV)   │
  │  Services → Ticket    │ │ Call / Complete │ │  NOW SERVING    │
  └───────────────────────┘ └─────────────────┘ └─────────────────┘
                │                   │                   │
                └───────────────────┼───────────────────┘
                                    │ HA events + entities
                          ┌─────────▼─────────┐
                          │  TTS / Printers   │
                          │  Automations      │
                          └───────────────────┘
```

---

## 🚀 Accessing the UI

After install and restart:

1. **Sidebar** — **Queue Management** in the Home Assistant sidebar  
2. **Panel URL** — `http://homeassistant.local:8123/queue-management`  
3. **Fullscreen kiosk** — `http://homeassistant.local:8123/queue_management/static/index.html`  

> **Tip:** On a tablet, open the kiosk URL and use **Add to Home Screen** for an app-like experience. Reception and Display modes hide chrome in kiosk view.

---

## 📦 Installation

### Option 1: HACS (recommended)

1. **HACS** → **Integrations** → **⋮** → **Custom repositories**
2. URL: `https://github.com/saboaua/queue_management` — category **Integration**
3. Download, restart Home Assistant
4. **Settings** → **Devices & Services** → **Add Integration** → **Queue Management**

### Option 2: Manual

1. Copy `custom_components/queue_management` into your HA `config/custom_components/` folder  
2. Restart Home Assistant  
3. Add the integration under **Devices & Services**

Minimum Home Assistant: **2024.1.0** (see `hacs.json`).

---

## ⚙️ Hardware & Automations

### Thermal printer

Configure the print layout under **Admin → Ticket printing**. On each issued ticket the event includes printable lines:

```yaml
automation:
  - alias: "Print ticket on issue"
    trigger:
      - platform: event
        event_type: queue_management_ticket_issued
    action:
      - service: notify.your_thermal_printer
        data:
          message: >
            {% for line in trigger.event.data.print.lines %}
            {{ line }}
            {% endfor %}
```

Example dashboards and automations are under `examples/` and `blueprints/automation/`.

### Voice announcements (TTS)

1. **Admin → Announcements**  
2. Enable **Announce when calling**  
3. Select a **media_player** (and TTS entity if required by your setup)  
4. Edit templates (with / without cashier name)  
5. Use **Test announcement**  

Or use the included blueprint: `blueprints/automation/queue_announce_ticket.yaml`.

---

## 📊 Entities

Created per queue (example for **Main Queue**):

| Entity | Role |
|--------|------|
| `sensor.main_queue_current_serving` | Ticket currently being served |
| `sensor.main_queue_last_ticket_issued` | Last issued ticket display |
| `sensor.main_queue_waiting` | Number of people waiting |
| `sensor.main_queue_status` | Queue status (e.g. idle / active) |
| `button.main_queue_take_ticket` | Issue a ticket |
| `button.main_queue_call_next` | Call next ticket |
| `button.main_queue_reset_queue` | Reset the queue |

An access-links sensor exposes panel/kiosk URLs for convenience.

---

## 🛠️ Services

| Service | Description |
|---------|-------------|
| `queue_management.take_ticket` | Issue next ticket (`queue_id` optional, default `main`) |
| `queue_management.call_next` | Call next waiting ticket |
| `queue_management.call_ticket` | Call a specific ticket number |
| `queue_management.reset_queue` | Reset counters and clear waiting list |
| `queue_management.create_queue` | Create queue (`queue_id`, optional `name`, `prefix`, `start_number`) |
| `queue_management.delete_queue` | Delete a queue (cannot delete `main`) |

### Events

| Event | When | Useful data |
|-------|------|-------------|
| `queue_management_ticket_issued` | Ticket taken | `ticket`, `ticket_display`, `queue_id`, `service_id`, `print.lines`, … |
| `queue_management_ticket_called` | Ticket called | `ticket`, `ticket_display`, `queue_id`, `cashier_id`, … |
| `queue_management_queue_reset` | Queue reset | `queue_id` |

---

## 🎨 Theme

- **Default:** light QueueFlow-style palette (soft gray background, white cards, dark text, blue accent)  
- **Admin → Appearance:** customize background, cards, text, muted, accent, success, warning, danger  
- **Reset defaults** restores the built-in light theme  
- Theme is stored with integration data and applied to all modes  

---

## 📂 Project structure

```text
queue_management_hacs/
├── README.md
├── LICENSE
├── hacs.json
├── blueprints/automation/
│   └── queue_announce_ticket.yaml
├── examples/
│   ├── automation_announce_ticket.yaml
│   ├── dashboard_reception.yaml
│   ├── dashboard_calling.yaml
│   └── dashboard_display.yaml
└── custom_components/queue_management/
    ├── __init__.py          # Setup, panel, services
    ├── manifest.json
    ├── const.py
    ├── config_flow.py
    ├── queue.py             # Engine, storage, cashiers, services, analytics
    ├── http.py              # REST state/action API + static files
    ├── sensor.py            # Queue sensors
    ├── button.py            # Take / Call next / Reset buttons
    ├── services.yaml
    ├── strings.json
    ├── translations/en.json
    ├── brand/
    └── frontend/
        ├── index.html       # Multi-mode web app
        ├── style.css        # Light theme + kiosk reception layout
        ├── app.js           # UI logic & 3s poll sync
        └── fonts/           # Geist / Geist Mono
```

---

## 🧪 Example: Lovelace reception (optional)

If you prefer classic Lovelace instead of the built-in panel, see `examples/dashboard_reception.yaml` (button + sensors). The dedicated **Reception** mode in the panel is recommended for tablets.

---

## 📄 License

MIT — see [LICENSE](LICENSE).
