(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  let state = { queues: [], history: [], settings: {} };
  let currentQueueId = "main";
  let lastTicketShown = null;

  // ---------- API ----------
  async function api(path, options = {}) {
    const res = await fetch(`/api/queue_management/${path}`, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || res.statusText || "Request failed");
    }
    return res.json();
  }

  async function loadState() {
    try {
      state = await api("state");
      if (!currentQueueId || !state.queues.find((q) => q.queue_id === currentQueueId)) {
        currentQueueId = state.queues[0]?.queue_id || "main";
      }
      render();
    } catch (e) {
      toast("Cannot load queue data. Are you logged in?", true);
      console.error(e);
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
    el._t = setTimeout(() => (el.hidden = true), 3200);
  }

  function q() {
    return state.queues.find((x) => x.queue_id === currentQueueId) || state.queues[0] || {};
  }

  function render() {
    // Queue selector
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

    // Reception
    $("#rWaiting").textContent = queue.waiting_count ?? 0;
    $("#rCurrent").textContent = queue.current_display || "—";

    // Calling
    $("#cCurrent").textContent = queue.current_display || "—";
    $("#cWaiting").textContent = queue.waiting_count ?? 0;
    $("#cLast").textContent = queue.last_issued_display || "—";
    $("#cStatus").textContent = queue.status || "idle";

    const ul = $("#waitingList");
    ul.innerHTML = "";
    (queue.waiting_display || []).forEach((t) => {
      const li = document.createElement("li");
      li.textContent = t;
      li.title = "Click to call this ticket";
      li.style.cursor = "pointer";
      li.onclick = () => {
        const raw = queue.waiting[queue.waiting_display.indexOf(t)];
        doAction("call_ticket", { ticket: raw }).then(() => toast(`Called ${t}`));
      };
      ul.appendChild(li);
    });
    if (!(queue.waiting_display || []).length) {
      ul.innerHTML = "<li style='opacity:0.5'>No one waiting</li>";
    }

    // Display
    $("#dCurrent").textContent = queue.current_display || "—";
    $("#dWaiting").textContent = queue.waiting_count ?? 0;

    // Admin settings
    const s = state.settings || {};
    $("#printerEnabled").checked = !!s.printer_enabled;
    $("#printerName").value = s.printer_name || "";
    $("#announceEnabled").checked = !!s.announce_enabled;
    $("#announceEntity").value = s.announce_entity || "";

    // History
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

  // ---------- Mode switching ----------
  $$(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".mode-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      $$(".mode-panel").forEach((p) => p.classList.remove("active"));
      $(`#mode-${btn.dataset.mode}`).classList.add("active");
    });
  });

  $("#queueSelect").addEventListener("change", (e) => {
    currentQueueId = e.target.value;
    lastTicketShown = null;
    $("#ticketResult").hidden = true;
    render();
  });

  // ---------- Actions ----------
  $("#btnTake").addEventListener("click", async () => {
    const res = await doAction("take_ticket");
    if (res?.result) {
      lastTicketShown = res.result.ticket_display;
      $("#ticketNumber").textContent = lastTicketShown;
      $("#ticketResult").hidden = false;
      toast(`Ticket ${lastTicketShown} issued`);
      // Optional: trigger browser print of a simple ticket
      if (state.settings?.printer_enabled) {
        // User can also automate via HA event; here we offer a simple print dialog
        // window.print() could be used with a print stylesheet if desired
      }
    }
  });

  $("#btnCallNext").addEventListener("click", async () => {
    const res = await doAction("call_next");
    if (res?.result) {
      toast(`Now serving ${res.result.ticket_display}`);
    } else {
      toast("No tickets waiting", true);
    }
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
    await doAction("create_queue", {
      new_queue_id: id,
      name,
      prefix,
    });
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

  // Auto refresh every 3s so multiple devices stay in sync
  loadState();
  setInterval(loadState, 3000);
})();
EOF
