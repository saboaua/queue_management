(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  let state = { queues: [], history: [], settings: {} };
  let currentQueueId = "main";
  let currentMode = "reception";
  let authToken = null;

  // ---------- Auth: HA stores tokens in localStorage (same-origin with iframe) ----------
  function readTokensFromStorage(storage) {
    if (!storage) return null;
    try {
      const raw = storage.getItem("hassTokens");
      if (raw) {
        const data = JSON.parse(raw);
        if (data && data.access_token) return data.access_token;
      }
    } catch (_) {}
    try {
      for (let i = 0; i < storage.length; i++) {
        const key = storage.key(i);
        if (!key) continue;
        const lk = key.toLowerCase();
        if (!lk.includes("token") && !lk.includes("hass")) continue;
        try {
          const v = JSON.parse(storage.getItem(key));
          if (v && typeof v === "object" && v.access_token) return v.access_token;
        } catch (_) {}
      }
    } catch (_) {}
    return null;
  }

  function loadAuthToken() {
    // 1) Own localStorage (same-origin iframe shares this with HA)
    let token = readTokensFromStorage(window.localStorage);
    // 2) Parent frame localStorage (when embedded as sidebar iframe)
    if (!token) {
      try {
        if (window.parent && window.parent !== window) {
          token = readTokensFromStorage(window.parent.localStorage);
        }
      } catch (e) {
        console.warn("Cannot read parent storage", e);
      }
    }
    // 3) sessionStorage fallback
    if (!token) {
      try {
        token = readTokensFromStorage(window.sessionStorage);
      } catch (_) {}
    }
    authToken = token;
    return !!authToken;
  }

  function authHeaders() {
    const h = { "Content-Type": "application/json" };
    // Primary: secret injected by authenticated UI view (works in iframe)
    if (window.QM_SECRET) {
      h["X-Queue-Management-Secret"] = window.QM_SECRET;
    }
    // Fallback: HA access token from localStorage
    if (authToken) {
      h["Authorization"] = `Bearer ${authToken}`;
    }
    return h;
  }

  // ---------- API ----------
  async function api(path, options = {}) {
    if (!authToken) loadAuthToken();

    const res = await fetch(`/api/queue_management/${path}`, {
      credentials: "same-origin",
      headers: { ...authHeaders(), ...(options.headers || {}) },
      ...options,
    });

    const body = await res.json().catch(() => ({}));

    if (res.status === 401 || res.status === 403) {
      // Token might have expired – reload once from storage
      loadAuthToken();
      if (authToken && !options._retried) {
        return api(path, { ...options, _retried: true });
      }
      const err = new Error("Not authenticated");
      err.status = res.status;
      throw err;
    }

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
      if (!authToken) loadAuthToken();
      if (!authToken && !window.QM_SECRET) {
        toast(
          "Open Queue Management from the Home Assistant sidebar while logged in.",
          true
        );
        return;
      }
      state = await api("state");
      if (!currentQueueId || !state.queues.find((q) => q.queue_id === currentQueueId)) {
        currentQueueId = state.queues[0]?.queue_id || "main";
      }
      render();
      hideToast();
    } catch (e) {
      console.error("loadState", e);
      if (e.status === 401 || e.status === 403) {
        toast(
          "Not authenticated. Log into Home Assistant in this browser, then open Queue Management from the sidebar.",
          true
        );
      } else if (e.status === 503) {
        toast("Integration not ready – restart Home Assistant.", true);
      } else if (e.status === 404) {
        toast("API not found – update the integration and restart Home Assistant.", true);
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
    $("#toast").hidden = true;
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

    const app = $("#app");
    if (mode === "admin") {
      app.classList.remove("kiosk");
    } else {
      app.classList.add("kiosk");
    }
    app.classList.remove("show-menu");
  }

  function render() {
    const sel = $("#queueSelect");
    if (!sel) return;
    const prev = currentQueueId;
    sel.innerHTML = (state.queues || [])
      .map(
        (x) =>
          `<option value="${x.queue_id}" ${x.queue_id === currentQueueId ? "selected" : ""}>${escapeHtml(x.name)}</option>`
      )
      .join("");
    currentQueueId = sel.value || prev;

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
          li.title = "Click to call this ticket";
          li.style.cursor = "pointer";
          li.onclick = () => {
            const raw = queue.waiting[idx];
            doAction("call_ticket", { ticket: raw }).then(() => toast(`Called ${t}`));
          };
          ul.appendChild(li);
        });
      }
    }

    const s = state.settings || {};
    const pe = $("#printerEnabled");
    const pn = $("#printerName");
    const ae = $("#announceEnabled");
    const an = $("#announceEntity");
    if (pe) pe.checked = !!s.printer_enabled;
    if (pn) pn.value = s.printer_name || "";
    if (ae) ae.checked = !!s.announce_enabled;
    if (an) an.value = s.announce_entity || "";

    const hist = $("#historyList");
    if (hist) {
      hist.innerHTML = (state.history || [])
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
          return `<div class="history-item"><span><span class="type">${escapeHtml(
            h.type || ""
          )}</span> ${escapeHtml(label)}</span><span>${escapeHtml(time)}</span></div>`;
        })
        .join("") || "<div class='muted'>No history yet</div>";
    }
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Mode buttons (topbar + fab)
  $$(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });

  $("#fabMenu")?.addEventListener("click", () => {
    $("#app").classList.toggle("show-menu");
  });

  $("#queueSelect")?.addEventListener("change", (e) => {
    currentQueueId = e.target.value;
    const tr = $("#ticketResult");
    if (tr) tr.hidden = true;
    render();
  });

  $("#btnTake")?.addEventListener("click", async () => {
    const res = await doAction("take_ticket");
    if (res?.result) {
      setText("ticketNumber", res.result.ticket_display);
      const tr = $("#ticketResult");
      if (tr) tr.hidden = false;
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
    if (!confirm("Reset this queue? Waiting list will be cleared.")) return;
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
    if ($("#newQueueId")) $("#newQueueId").value = "";
    if ($("#newQueueName")) $("#newQueueName").value = "";
    if ($("#newQueuePrefix")) $("#newQueuePrefix").value = "";
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

  // Boot
  loadAuthToken();
  setMode("reception");
  loadState();
  setInterval(loadState, 3000);
})();
