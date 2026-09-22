(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  let state = { queues: [], history: [], settings: {} };
  let currentQueueId = "main";
  let currentMode = "reception";

  // ---------- API ----------
  async function api(path, options = {}) {
    const res = await fetch(`/api/queue_management/${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = body.error || body.message || `${res.status} ${res.statusText}`;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return body;
  }

  async function loadState() {
    try {
      state = await api("state");
      if (!currentQueueId || !state.queues.find((q) => q.queue_id === currentQueueId)) {
        currentQueueId = state.queues[0]?.queue_id || "main";
      }
      render();
      hideToast();
    } catch (e) {
      console.error(e);
      if (e.status === 401 || e.status === 403) {
        toast("Session expired – open Home Assistant and log in, then refresh this page.", true);
      } else if (e.status === 503) {
        toast("Integration not ready – restart Home Assistant.", true);
      } else if (e.status === 404) {
        toast("API not found – reinstall/update the integration and restart.", true);
      } else {
        toast(e.message || "Cannot load queue data", true);
      }
    }
  }

  async function doAction(action, extra = {}) {
    try {
      const result = await api("action", {
        method: "POST",
        body: JSON.stringify({ action, queue_id: currentQueueId, ...extra }),
      });
      await loadState();
      return result;
    } catch (e) {
      toast(e.message, true);
      throw e;
    }
  }

  // ---------- UI helpers ----------
  function toast(msg, isError = false) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.toggle("error", isError);
    el.hidden = false;
    clearTimeout(el._t);
    if (!isError) {
      el._t = setTimeout(() => (el.hidden = true), 3200);
    }
  }
  function hideToast() {
    const el = $("#toast");
    el.hidden = true;
  }

  function q() {
    return state.queues.find((x) => x.queue_id === currentQueueId) || state.queues[0] || {};
  }

  function setMode(mode) {
    currentMode = mode;
    $$(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    $$(".mode-panel").forEach((p) => p.classList.remove("active"));
    const panel = $(`#mode-${mode}`);
    if (panel) panel.classList.add("active");

    // Kiosk: hide top bar on Reception / Calling / Display
    const app = $("#app");
    if (mode === "admin") {
      app.classList.remove("kiosk");
    } else {
      app.classList.add("kiosk");
    }
  }

  function render() {
    const sel = $("#queueSelect");
    const prev = currentQueueId;
    sel.innerHTML = state.queues
      .map(
        (x) =>
          `<option value="${x.queue_id}" ${x.queue_id === currentQueueId ? "selected" : ""}>${x.name}</option>`
      )
      .join("");
    currentQueueId = sel.value || prev;

    const queue = q();

    $("#rWaiting").textContent = queue.waiting_count ?? 0;
    $("#rCurrent").textContent = queue.current_display || "—";

    $("#cCurrent").textContent = queue.current_display || "—";
    $("#cWaiting").textContent = queue.waiting_count ?? 0;
    $("#cLast").textContent = queue.last_issued_display || "—";
    $("#cStatus").textContent = queue.status || "idle";

    const ul = $("#waitingList");
    ul.innerHTML = "";
    (queue.waiting_display || []).forEach((t, idx) => {
      const li = document.createElement("li");
      li.textContent = t;
      li.title = "Click to call this ticket";
      li.style.cursor = "pointer";
      li.onclick = () => {
        const raw = queue.waiting[idx];
        doAction("call_ticket", { ticket: raw }).then(() => toast(`Called ${t}`));
      };
      ul.appendChild(li);
    });
    if (!(queue.waiting_display || []).length) {
      ul.innerHTML = "<li style='opacity:0.5'>No one waiting</li>";
    }

    $("#dCurrent").textContent = queue.current_display || "—";
    $("#dWaiting").textContent = queue.waiting_count ?? 0;

    const s = state.settings || {};
    $("#printerEnabled").checked = !!s.printer_enabled;
    $("#printerName").value = s.printer_name || "";
    $("#announceEnabled").checked = !!s.announce_enabled;
    $("#announceEntity").value = s.announce_entity || "";

    const hist = $("#historyList");
    hist.innerHTML = (state.history || [])
      .slice()
      .reverse()
      .map((h) => {
        const time = h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : "";
        const label =
          h.type === "issued"
            ? `Issued ${h.ticket_display}`
            : h.type === "called"
            ? `Called ${h.ticket_display}`
            : h.type === "completed"
            ? `Completed ${h.ticket_display}`
            : h.type === "reset"
            ? `Reset ${h.queue_name || h.queue_id}`
            : h.type;
        return `<div class="history-item"><span><span class="type">${h.type || ""}</span> ${label}</span><span>${time}</span></div>`;
      })
      .join("") || "<div class='muted'>No history yet</div>";
  }

  // Mode buttons
  $$(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setMode(btn.dataset.mode);
      $("#app").classList.remove("show-menu");
    });
  });

  // Floating menu to switch mode when topbar is hidden
  $("#fabMenu")?.addEventListener("click", () => {
    $("#app").classList.toggle("show-menu");
  });
  $("#fabAdmin")?.addEventListener("click", () => setMode("admin"));

  $("#queueSelect").addEventListener("change", (e) => {
    currentQueueId = e.target.value;
    $("#ticketResult").hidden = true;
    render();
  });

  $("#btnTake").addEventListener("click", async () => {
    const res = await doAction("take_ticket");
    if (res?.result) {
      $("#ticketNumber").textContent = res.result.ticket_display;
      $("#ticketResult").hidden = false;
      toast(`Ticket ${res.result.ticket_display} issued`);
    }
  });

  $("#btnCallNext").addEventListener("click", async () => {
    const res = await doAction("call_next");
    if (res?.result) toast(`Now serving ${res.result.ticket_display}`);
    else toast("No tickets waiting", true);
  });

  $("#btnComplete").addEventListener("click", async () => {
    await doAction("complete");
    toast("Ticket completed");
  });

  $("#btnReset").addEventListener("click", async () => {
    if (!confirm("Reset this queue? Waiting list will be cleared.")) return;
    await doAction("reset");
    toast("Queue reset");
  });

  $("#btnCreateQueue").addEventListener("click", async () => {
    const id = $("#newQueueId").value.trim().toLowerCase();
    const name = $("#newQueueName").value.trim() || id;
    const prefix = $("#newQueuePrefix").value.trim();
    if (!id) return toast("Enter a queue ID", true);
    await doAction("create_queue", { new_queue_id: id, name, prefix });
    toast(`Queue "${name}" created`);
    $("#newQueueId").value = "";
    $("#newQueueName").value = "";
    $("#newQueuePrefix").value = "";
  });

  $("#btnSaveSettings").addEventListener("click", async () => {
    try {
      await api("settings", {
        method: "POST",
        body: JSON.stringify({
          printer_enabled: $("#printerEnabled").checked,
          printer_name: $("#printerName").value.trim(),
          announce_enabled: $("#announceEnabled").checked,
          announce_entity: $("#announceEntity").value.trim(),
        }),
      });
      toast("Settings saved");
      await loadState();
    } catch (e) {
      toast(e.message, true);
    }
  });

  // Start in reception (kiosk)
  setMode("reception");
  loadState();
  setInterval(loadState, 3000);
})();
