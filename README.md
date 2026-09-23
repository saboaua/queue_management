# 🎫 Queue Management for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/saboaua/queue_management?style=for-the-badge&color=blue)](https://github.com/saboaua/queue_management/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

A standalone, professional **Queue & Ticket Management System** running directly inside Home Assistant. 

No complex Lovelace card setup required—it registers its own dedicated sidebar panel and provides multi-device UI syncing across tablets, TVs, and desktops.

---

## ✨ Features

- **Dedicated Sidebar Panel:** Clean web application accessible right from your HA sidebar.
- **Multi-Role UI:** Single interface supporting 4 distinct operational modes (Reception, Calling Desk, Display, Admin).
- **Real-Time Synchronization:** Active UI updates every 3 seconds across all connected screens.
- **Hardware & Automation Ready:** Native support for thermal receipt printers (IPP/Automations) and TTS voice announcements.
- **Multiple Queue Support:** Manage general, express, VIP, or departmental lines independently.
- **Full History Tracking:** Logs for issued, called, and completed tickets.
- **Persistent Data:** Queue state and history survive Home Assistant system restarts.
- **Native HA Entities:** Generates sensors, buttons, and custom events (`queue_management_ticket_issued`, `_called`, `_queue_reset`) for custom automations.

---

## 🖥️ Operational Modes

The web interface dynamically adapts to four operating roles from a single access URL:

| Mode | Target Device | Description |
| :--- | :--- | :--- |
| **🎟️ Reception** | Kiosk / Tablet | Touch-friendly "Take Ticket" screen displaying issued numbers. |
| **📢 Calling Desk** | Staff Counter / Tablet | Controls to call next ticket, complete service, and view queue status. |
| **📺 Display** | Waiting Area TV | Large visual display showing currently served tickets and call updates. |
| **⚙️ Admin** | Back-Office PC | System management: reset queues, configure TTS/printers, view analytics. |

---

## 🏗️ System Architecture

```text
  ┌─────────────────────────────────────────────────────────────┐
  │                    HOME ASSISTANT CORE                      │
  │  ┌───────────────────────────────────────────────────────┐  │
  │  │               Queue Management Engine                 │  │
  │  │  • Panel Handler  • REST API  • Real-Time Sync (3s)   │  │
  │  └──────────┬───────────────────┬───────────────────┬────┘  │
  └─────────────┼───────────────────┼───────────────────┼───────┘
                │                   │                   │
  ┌─────────────▼─────────┐ ┌───────▼─────────┐ ┌───────▼─────────┐
  │   RECEPTION KIOSK     │ │  CALLING DESK   │ │  DISPLAY SCREEN │
  │   (Tablet / Phone)    │ │ (Staff Counter) │ │  (Waiting TV)   │
  │ ┌───────────────────┐ │ │ ┌─────────────┐ │ │ ┌─────────────┐ │
  │ │  Mode: Reception  │ │ │ │ CallingDesk │ │ │ │ Mode:Display│ │
  │ │  [ Take Ticket ]  │ │ │ │[ Call Next ]│ │ │ │ NOW SERVING │ │
  │ └───────────────────┘ │ │ └─────────────┘ │ │ └─────────────┘ │
  └───────────────────────┘ └─────────────────┘ └─────────────────┘
                │                   │                   │
                └───────────────────┼───────────────────┘
                                    │ (Native Events)
                          ┌─────────▼─────────┐
                          │   HARDWARE OUT    │
                          │ • Thermal Printer │
                          │ • TTS Speakers    │
                          └───────────────────┘
```

> **Note for Repository Maintainers:** To replace this diagram with a custom graphic image, upload your PNG or SVG file to `docs/architecture.png` and update this section with `![System Architecture](docs/architecture.png)`.

---

## 🚀 Getting Started

### Accessing the Panel

After installation and a restart, access the interface via:

1. **Sidebar Navigation:** Click on **Queue Management** 🎫 in your Home Assistant sidebar.
2. **Direct Local URL:** `http://homeassistant.local:8123/queue-management`
3. **Fullscreen Web Kiosk:** `http://homeassistant.local:8123/queue_management/static/index.html`

> **Tip:** On iOS or Android tablets, open the Fullscreen Kiosk URL in Safari or Chrome and select **"Add to Home Screen"** for an app-like experience.

---

## 📦 Installation

### Option 1: HACS (Recommended)

1. Open **HACS** → **Integrations** → **⋮ Menu** (top right) → **Custom Repositories**.
2. Add Repository URL: `https://github.com/saboaua/queue_management`
3. Select Category: **Integration**
4. Click **Download** and restart Home Assistant.
5. Go to **Settings** → **Devices & Services** → **Add Integration** → search for **Queue Management**.

### Option 2: Manual Installation

1. Download the latest release source code.
2. Copy the `custom_components/queue_management` directory to your HA configuration directory:
   ```text
   config/custom_components/queue_management
   ```
3. Restart Home Assistant and add the integration via **Devices & Services**.

---

## ⚙️ Hardware & Automations

### Printer Setup

Enable receipt printing directly via **Admin Mode** using an IPP printer entity, or trigger physical print jobs via native Home Assistant events:

```yaml
automation:
  - alias: "Print Ticket on Issue"
    trigger:
      - platform: event
        event_type: queue_management_ticket_issued
    action:
      - service: notify.thermal_printer
        data:
          message: "Ticket {{ trigger.event.data.ticket_display }}"
```

### Voice Announcements

- **Built-in:** Navigate to **Admin Mode** → enable **Voice Announcements** → assign your TTS `media_player` entity.
- **Blueprints:** Ready-to-use blueprints are provided in the `/blueprints/automation/` directory.

---

## 📊 Entities & Services

### Default Entities (`Main Queue`)

- `sensor.main_queue_current_serving`
- `sensor.main_queue_last_ticket_issued`
- `sensor.main_queue_waiting`
- `sensor.main_queue_status`
- Buttons for: *Take Ticket*, *Call Next*, *Reset*

### Available Services

| Service Name | Description |
| :--- | :--- |
| `queue_management.take_ticket` | Issues the next numerical ticket in sequence. |
| `queue_management.call_next` | Advances queue and calls the next waiting ticket. |
| `queue_management.call_ticket` | Calls a specific ticket number directly. |
| `queue_management.reset_queue` | Resets counters, ticket logs, and active lists. |
| `queue_management.create_queue` | Provisions a new independent queue instance. |
| `queue_management.delete_queue` | Removes an existing queue instance. |

---

## 📂 Project Structure

```text
custom_components/queue_management/
├── __init__.py          # Panel registration & service handlers
├── http.py              # REST API & static web serving
├── queue.py             # Core queue engine & persistence state
├── sensor.py / button.py# Platform entity platforms
└── frontend/            # Dedicated standalone UI app
    ├── index.html       # Web application UI
    ├── style.css        # Responsive stylesheet
    └── app.js           # Client sync engine
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).