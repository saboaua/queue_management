(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  let state = { queues: [], history: [], settings: {} };
  let currentQueueId = "main";

  async function api(path, options = {}) {
    const res = await fetch(`/api/queue_management/${path}`, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(body.error || body.message || `${res.status} ${res.statusText}`);
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
      toast(e.message || "Cannot load queue data – is the integration loaded?", true);
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

  function toast(msg, isError = false) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.toggle("error", isError);
    el.hidden = false;
    clearTimeout(el._t);
    if (!isError) el._t = setTimeout(() => (el.hidden = true), 3000);
  }
  function hideToast() {
    const el = $("#toast");
    if (el) el.hidden = true;
  }

  function q() {
    return state.queues.find((x) => x.queue_id === currentQueueId) || state.queues[0] || {};
  }

  function setMode(mode) {
    $$(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    $$(".mode-panel").forEach((p) => p.classList.remove("active"));
    const panel = $(`#mode-${mode}`);
    if (panel) panel.classList.add("active");
    const app = $("#app");
    if (app) {
      if (mode === "admin") app.classList.remove("kiosk");
      else app.classList.add("kiosk");
      app.classList.remove("show-menu");
    }
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function render() {
    const sel = $("#queueSelect");
    if (sel) {
      const prev = currentQueueId;
      sel.innerHTML = (state.queues || [])
        .map(
          (x) =>
            `<option value="${x.queue_id}" ${
              x.queue_id === currentQueueId ? "selected" : ""
            }>${x.name}</option>`
        )
        .join("");
      currentQueueId = sel.value || prev;
    }

    const queue = q();
    setText("rWaiting", queue.waiting_count ?? 0);
    setText("rCurrent", queue.current_display || "—");
    setText("cCurrent", queue.current_display || "—");
    setText("cWaiting", queue.waiting_count ?? 0);
    setText("cLast", queue.last_issued_display || "—");
    setText("cStatus", queue.status || "idle");
    setText("dCurrent", queue.current_display || "—");
    setText("dWaiting", queue.waiting_count ?? 0);

    const ul = $("#waitingList");
    if (ul) {
      ul.innerHTML = "";
      const displays = queue.waiting_display || [];
      if (!displays.length) {
        ul.innerHTML = "<li style='opacity:0.5'>No one waiting</li>";
      } else {
        displays.forEach((t, idx) => {
          const li = document.createElement("li");
          li.textContent = t;
          li.style.cursor = "pointer";
          li.onclick = () =>
            doAction("call_ticket", { ticket: queue.waiting[idx] }).then(() =>
              toast(`Called ${t}`)
            );
          ul.appendChild(li);
        });
      }
    }

    const s = state.settings || {};
    if ($("#printerEnabled")) $("#printerEnabled").checked = !!s.printer_enabled;
    if ($("#printerName")) $("#printerName").value = s.printer_name || "";
    if ($("#announceEnabled")) $("#announceEnabled").checked = !!s.announce_enabled;
    if ($("#announceEntity")) $("#announceEntity").value = s.announce_entity || "";

    const hist = $("#historyList");
    if (hist) {
      hist.innerHTML =
        (state.history || [])
          .slice()
          .reverse()
          .map((h) => {
            const time = h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : "";
            const label =
              h.type === "issued"
                ? `Issued ${h.ticket_display || ""}`
                : h.type === "called"
                ? `Called ${h.ticket_display || ""}`
                : h.type === "completed"
                ? `Completed ${h.ticket_display || ""}`
                : h.type === "reset"
                ? `Reset ${h.queue_name || h.queue_id || ""}`
                : h.type || "";
            return `<div class="history-item"><span><span class="type">${
              h.type || ""
            }</span> ${label}</span><span>${time}</span></div>`;
          })
          .join("") || "<div class='muted'>No history yet</div>";
    }
  }

  $$(".mode-btn").forEach((btn) =>
    btn.addEventListener("click", () => setMode(btn.dataset.mode))
  );
  $("#fabMenu")?.addEventListener("click", () =>
    $("#app")?.classList.toggle("show-menu")
  );
  $("#queueSelect")?.addEventListener("change", (e) => {
    currentQueueId = e.target.value;
    if ($("#ticketResult")) $("#ticketResult").hidden = true;
    render();
  });

  $("#btnTake")?.addEventListener("click", async () => {
    const res = await doAction("take_ticket");
    if (res?.result) {
      setText("ticketNumber", res.result.ticket_display);
      if ($("#ticketResult")) $("#ticketResult").hidden = false;
      toast(`Ticket ${res.result.ticket_display} issued`);
    }
  });
  $("#btnCallNext")?.addEventListener("click", async () => {
    const res = await doAction("call_next");
    if (res?.result) toast(`Now serving ${res.result.ticket_display}`);
    else toast("No tickets waiting", true);
  });
  $("#btnComplete")?.addEventListener("click", async () => {
    await doAction("complete");
    toast("Ticket completed");
  });
  $("#btnReset")?.addEventListener("click", async () => {
    if (!confirm("Reset this queue?")) return;
    await doAction("reset");
    toast("Queue reset");
  });
  $("#btnCreateQueue")?.addEventListener("click", async () => {
    const id = ($("#newQueueId")?.value || "").trim().toLowerCase();
    const name = ($("#newQueueName")?.value || "").trim() || id;
    const prefix = ($("#newQueuePrefix")?.value || "").trim();
    if (!id) return toast("Enter a queue ID", true);
    await doAction("create_queue", { new_queue_id: id, name, prefix });
    toast(`Queue "${name}" created`);
  });
  $("#btnSaveSettings")?.addEventListener("click", async () => {
    try {
      await api("settings", {
        method: "POST",
        body: JSON.stringify({
          printer_enabled: !!$("#printerEnabled")?.checked,
          printer_name: ($("#printerName")?.value || "").trim(),
          announce_enabled: !!$("#announceEnabled")?.checked,
          announce_entity: ($("#announceEntity")?.value || "").trim(),
        }),
      });
      toast("Settings saved");
      await loadState();
    } catch (e) {
      toast(e.message, true);
    }
  });

  setMode("reception");
  loadState();
  setInterval(loadState, 3000);
})();
