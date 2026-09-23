(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  let state = {
    queues: [],
    cashiers: [],
    theme: {},
    overview: {},
    history: [],
    settings: {},
  };
  let currentQueueId = "main";
  let selectedCashierId = localStorage.getItem("qm_cashier") || "";

  async function api(path, options = {}) {
    const res = await fetch(`/api/queue_management/${path}`, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || body.message || `${res.status}`);
    return body;
  }

  async function loadState() {
    try {
      state = await api("state");
      if (!currentQueueId || !state.queues.find((q) => q.queue_id === currentQueueId)) {
        currentQueueId = state.queues[0]?.queue_id || "main";
      }
      applyTheme(state.theme || {});
      render();
      hideToast();
    } catch (e) {
      console.error(e);
      toast(e.message || "Cannot load data", true);
    }
  }

  async function doAction(action, extra = {}) {
    const result = await api("action", {
      method: "POST",
      body: JSON.stringify({ action, queue_id: currentQueueId, ...extra }),
    });
    await loadState();
    return result;
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

  function enabledCashiers() {
    return (state.cashiers || []).filter((c) => c.enabled);
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    const map = {
      bg: "--bg",
      card: "--card",
      text: "--text",
      muted: "--muted",
      accent: "--blue",
      success: "--green",
      warning: "--orange",
      danger: "--red",
    };
    Object.entries(map).forEach(([k, cssVar]) => {
      if (theme[k]) root.style.setProperty(cssVar, theme[k]);
    });
    // color inputs
    ["bg", "card", "text", "muted", "accent", "success", "warning", "danger"].forEach((k) => {
      const el = document.getElementById(`theme_${k}`);
      if (el && theme[k]) el.value = theme[k];
    });
  }

  function setMode(mode) {
    $$(".mode-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    $$(".mode-panel").forEach((p) => p.classList.remove("active"));
    const panel = $(`#mode-${mode}`);
    if (panel) panel.classList.add("active");
    const app = $("#app");
    if (app) {
      if (mode === "admin" || mode === "manager") app.classList.remove("kiosk");
      else app.classList.add("kiosk");
      app.classList.remove("show-menu");
    }
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function renderCashierSelect() {
    const sel = $("#cashierSelect");
    if (!sel) return;
    const list = enabledCashiers();
    if (!list.length) {
      sel.innerHTML = `<option value="">No cashiers configured</option>`;
      return;
    }
    if (!selectedCashierId || !list.find((c) => c.id === selectedCashierId)) {
      selectedCashierId = list[0].id;
      localStorage.setItem("qm_cashier", selectedCashierId);
    }
    sel.innerHTML = list
      .map(
        (c) =>
          `<option value="${c.id}" ${c.id === selectedCashierId ? "selected" : ""}>${c.name}${
            c.status === "serving" ? " (busy)" : ""
          }</option>`
      )
      .join("");
  }

  function renderCashierAdmin() {
    const box = $("#cashierAdminList");
    if (!box) return;
    const list = state.cashiers || [];
    box.innerHTML = list
      .map(
        (c, i) => `
      <div class="cashier-edit" data-idx="${i}">
        <input type="text" class="c-id" value="${c.id}" placeholder="id" ${i < 3 ? "" : ""} />
        <input type="text" class="c-name" value="${c.name}" placeholder="Name" />
        <label class="checkbox"><input type="checkbox" class="c-en" ${c.enabled ? "checked" : ""}/> On</label>
        <button type="button" class="btn-x" data-rm="${i}">✕</button>
      </div>`
      )
      .join("");
    box.querySelectorAll("[data-rm]").forEach((btn) => {
      btn.onclick = () => {
        const idx = +btn.getAttribute("data-rm");
        state.cashiers.splice(idx, 1);
        renderCashierAdmin();
      };
    });
  }

  function renderManager() {
    const ov = state.overview || {};
    setText("mWaiting", ov.total_waiting ?? 0);
    setText("mServing", ov.total_serving ?? 0);
    setText("mIdle", (ov.cashiers_idle || []).length);
    setText("mEnabled", ov.cashiers_enabled ?? 0);
    const clock = $("#mgrClock");
    if (clock) clock.textContent = "Updated " + new Date().toLocaleTimeString();

    const busy = $("#mgrBusy");
    if (busy) {
      const rows = ov.cashiers_busy || [];
      busy.innerHTML = rows.length
        ? rows
            .map((c) => {
              const ago = c.last_call_at
                ? Math.max(0, Math.round((Date.now() - new Date(c.last_call_at).getTime()) / 60000))
                : null;
              return `<div class="mgr-cashier busy">
                <div class="mc-name">${c.name}</div>
                <div class="mc-ticket">${c.ticket || "—"}</div>
                <div class="mc-meta">Served today: ${c.served_count || 0}${ago != null ? ` · ${ago} min` : ""}</div>
              </div>`;
            })
            .join("")
        : `<div class="muted empty-state">No cashiers currently serving</div>`;
    }

    const idle = $("#mgrIdle");
    if (idle) {
      const rows = ov.cashiers_idle || [];
      idle.innerHTML = rows.length
        ? rows
            .map(
              (c) =>
                `<div class="mgr-cashier idle">
                  <div class="mc-name">${c.name}</div>
                  <div class="mc-ticket muted">Idle</div>
                  <div class="mc-meta">Available to call next</div>
                </div>`
            )
            .join("")
        : `<div class="muted empty-state">All open cashiers are busy</div>`;
    }

    const queues = $("#mgrQueues");
    if (queues) {
      queues.innerHTML = (ov.queues || [])
        .map((q) => {
          const waitClass = q.waiting > 5 ? "hot" : q.waiting > 0 ? "warm" : "cool";
          return `<div class="queue-card ${waitClass}">
            <div class="qc-top">
              <strong>${q.name}</strong>
              <span class="badge">${q.status}</span>
            </div>
            <div class="qc-metrics">
              <div><span class="qc-num">${q.waiting}</span><span class="qc-lab">waiting</span></div>
              <div><span class="qc-num">${q.current_display || "—"}</span><span class="qc-lab">now serving</span></div>
              <div><span class="qc-num">${q.current_cashier_name || "—"}</span><span class="qc-lab">cashier</span></div>
            </div>
          </div>`;
        })
        .join("") || `<div class="muted">No queues</div>`;
    }

    const hist = $("#mgrHistory");
    if (hist) {
      hist.innerHTML = (state.history || [])
        .slice()
        .reverse()
        .slice(0, 40)
        .map((h) => {
          const time = h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : "";
          const who = h.cashier_name ? ` → ${h.cashier_name}` : "";
          const label =
            h.type === "issued"
              ? `Issued ${h.ticket_display || ""}`
              : h.type === "called"
              ? `Called ${h.ticket_display || ""}${who}`
              : h.type === "completed"
              ? `Completed ${h.ticket_display || ""}${who}`
              : h.type === "reset"
              ? `Reset ${h.queue_name || ""}`
              : h.type || "";
          return `<div class="history-item type-${h.type || ""}"><span><span class="type">${h.type || ""}</span> ${label}</span><span>${time}</span></div>`;
        })
        .join("") || "<div class='muted'>No activity yet</div>";
    }
  }

  function fillPrintForm() {
    const t = state.print_template || {};
    if ($("#pt_title")) $("#pt_title").value = t.title || "";
    if ($("#pt_header")) $("#pt_header").value = t.header || "";
    if ($("#pt_footer")) $("#pt_footer").value = t.footer || "";
    if ($("#pt_extra")) $("#pt_extra").value = t.extra_line || "";
    if ($("#pt_paper")) $("#pt_paper").value = t.paper_width || "58mm";
    if ($("#pt_show_number")) $("#pt_show_number").checked = t.show_number !== false;
    if ($("#pt_show_queue")) $("#pt_show_queue").checked = t.show_queue_name !== false;
    if ($("#pt_show_datetime")) $("#pt_show_datetime").checked = t.show_datetime !== false;
    if ($("#pt_show_waiting")) $("#pt_show_waiting").checked = t.show_waiting_count !== false;
    updatePrintPreview();
  }

  function updatePrintPreview() {
    const pre = $("#pt_preview");
    if (!pre) return;
    const lines = [];
    const title = $("#pt_title")?.value;
    const header = $("#pt_header")?.value;
    const footer = $("#pt_footer")?.value;
    const extra = $("#pt_extra")?.value;
    if (title) lines.push(title);
    if (header) lines.push(header);
    if ($("#pt_show_queue")?.checked) lines.push("Queue: Main Queue");
    if ($("#pt_show_number")?.checked) lines.push("Number: 42");
    if ($("#pt_show_waiting")?.checked) lines.push("Waiting ahead: 3");
    if ($("#pt_show_datetime")?.checked) lines.push(new Date().toLocaleString());
    if (extra) lines.push(extra);
    if (footer) lines.push(footer);
    pre.textContent = lines.join("\n");
  }

  function render() {
    const sel = $("#queueSelect");
    if (sel) {
      const prev = currentQueueId;
      sel.innerHTML = (state.queues || [])
        .map(
          (x) =>
            `<option value="${x.queue_id}" ${x.queue_id === currentQueueId ? "selected" : ""}>${x.name}</option>`
        )
        .join("");
      currentQueueId = sel.value || prev;
    }

    renderCashierSelect();
    const queue = q();

    setText("rWaiting", queue.waiting_count ?? 0);
    setText("rCurrent", queue.current_display || "—");

    setText("cCurrent", queue.current_display || "—");
    setText(
      "cCashierLine",
      queue.current_cashier_name ? `at ${queue.current_cashier_name}` : ""
    );
    setText("cWaiting", queue.waiting_count ?? 0);
    setText("cLast", queue.last_issued_display || "—");
    setText("cStatus", queue.status || "idle");

    const ul = $("#waitingList");
    if (ul) {
      ul.innerHTML = "";
      const displays = queue.waiting_display || [];
      if (!displays.length) ul.innerHTML = "<li style='opacity:0.5'>No one waiting</li>";
      else
        displays.forEach((t, idx) => {
          const li = document.createElement("li");
          li.textContent = t;
          li.style.cursor = "pointer";
          li.onclick = () =>
            doAction("call_ticket", {
              ticket: queue.waiting[idx],
              cashier_id: selectedCashierId || undefined,
            }).then((r) => toast(`Called ${t}${r?.result?.cashier_name ? " → " + r.result.cashier_name : ""}`));
          ul.appendChild(li);
        });
    }

    setText("dCurrent", queue.current_display || "—");
    setText(
      "dCashier",
      queue.current_cashier_name ? `Please go to ${queue.current_cashier_name}` : ""
    );
    setText("dWaiting", queue.waiting_count ?? 0);

    renderManager();
    renderCashierAdmin();
    fillPrintForm();

    const s = state.settings || {};
    if ($("#printerEnabled")) $("#printerEnabled").checked = !!s.printer_enabled;
    if ($("#printerName")) $("#printerName").value = s.printer_name || "";
    if ($("#announceEnabled")) $("#announceEnabled").checked = !!s.announce_enabled;
    if ($("#announceEntity")) $("#announceEntity").value = s.announce_entity || "";

    const hist = $("#historyList");
    if (hist) {
      hist.innerHTML = (state.history || [])
        .slice()
        .reverse()
        .map((h) => {
          const time = h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : "";
          const who = h.cashier_name ? ` → ${h.cashier_name}` : "";
          const label =
            h.type === "issued"
              ? `Issued ${h.ticket_display || ""}`
              : h.type === "called"
              ? `Called ${h.ticket_display || ""}${who}`
              : h.type === "completed"
              ? `Completed ${h.ticket_display || ""}${who}`
              : h.type === "reset"
              ? `Reset ${h.queue_name || ""}`
              : h.type || "";
          return `<div class="history-item"><span><span class="type">${h.type || ""}</span> ${label}</span><span>${time}</span></div>`;
        })
        .join("") || "<div class='muted'>No history yet</div>";
    }
  }

  // Events
  $$(".mode-btn").forEach((btn) =>
    btn.addEventListener("click", () => setMode(btn.dataset.mode))
  );
  $("#fabMenu")?.addEventListener("click", () => $("#app")?.classList.toggle("show-menu"));
  $("#queueSelect")?.addEventListener("change", (e) => {
    currentQueueId = e.target.value;
    if ($("#ticketResult")) $("#ticketResult").hidden = true;
    render();
  });
  $("#cashierSelect")?.addEventListener("change", (e) => {
    selectedCashierId = e.target.value;
    localStorage.setItem("qm_cashier", selectedCashierId);
  });

  $("#btnTake")?.addEventListener("click", async () => {
    try {
      const res = await doAction("take_ticket");
      if (res?.result) {
        setText("ticketNumber", res.result.ticket_display);
        if ($("#ticketResult")) $("#ticketResult").hidden = false;
        toast(`Ticket ${res.result.ticket_display} issued`);
      }
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnCallNext")?.addEventListener("click", async () => {
    try {
      if (!selectedCashierId) return toast("Select a cashier first", true);
      const res = await doAction("call_next", { cashier_id: selectedCashierId });
      if (res?.result)
        toast(
          `Now serving ${res.result.ticket_display}${
            res.result.cashier_name ? " at " + res.result.cashier_name : ""
          }`
        );
      else toast("No tickets waiting", true);
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnComplete")?.addEventListener("click", async () => {
    try {
      await doAction("complete", { cashier_id: selectedCashierId || undefined });
      toast("Ticket completed");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnReset")?.addEventListener("click", async () => {
    if (!confirm("Reset this queue?")) return;
    try {
      await doAction("reset");
      toast("Queue reset");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnCreateQueue")?.addEventListener("click", async () => {
    try {
      const id = ($("#newQueueId")?.value || "").trim().toLowerCase();
      const name = ($("#newQueueName")?.value || "").trim() || id;
      const prefix = ($("#newQueuePrefix")?.value || "").trim();
      if (!id) return toast("Enter a queue ID", true);
      await doAction("create_queue", { new_queue_id: id, name, prefix });
      toast(`Queue "${name}" created`);
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnAddCashier")?.addEventListener("click", () => {
    const n = (state.cashiers || []).length + 1;
    state.cashiers = state.cashiers || [];
    state.cashiers.push({ id: `cashier_${n}`, name: `Cashier ${n}`, enabled: true });
    renderCashierAdmin();
  });

  $("#btnSaveCashiers")?.addEventListener("click", async () => {
    try {
      const rows = [...document.querySelectorAll("#cashierAdminList .cashier-edit")];
      const cashiers = rows.map((row) => ({
        id: (row.querySelector(".c-id")?.value || "").trim(),
        name: (row.querySelector(".c-name")?.value || "").trim(),
        enabled: !!row.querySelector(".c-en")?.checked,
      }));
      await doAction("save_cashiers", { cashiers });
      toast("Cashiers saved");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnSaveTheme")?.addEventListener("click", async () => {
    try {
      const theme = {};
      ["bg", "card", "text", "muted", "accent", "success", "warning", "danger"].forEach((k) => {
        const el = document.getElementById(`theme_${k}`);
        if (el) theme[k] = el.value;
      });
      await doAction("save_theme", { theme });
      toast("Theme saved");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnResetTheme")?.addEventListener("click", async () => {
    try {
      await doAction("save_theme", {
        theme: {
          bg: "#0f172a",
          card: "#1e293b",
          text: "#f1f5f9",
          muted: "#94a3b8",
          accent: "#3b82f6",
          success: "#22c55e",
          warning: "#f97316",
          danger: "#ef4444",
        },
      });
      toast("Theme reset");
    } catch (e) {
      toast(e.message, true);
    }
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


  $("#btnSavePrint")?.addEventListener("click", async () => {
    try {
      await doAction("save_print_template", {
        print_template: {
          title: ($("#pt_title")?.value || "").trim(),
          header: ($("#pt_header")?.value || "").trim(),
          footer: ($("#pt_footer")?.value || "").trim(),
          extra_line: ($("#pt_extra")?.value || "").trim(),
          paper_width: $("#pt_paper")?.value || "58mm",
          show_number: !!$("#pt_show_number")?.checked,
          show_queue_name: !!$("#pt_show_queue")?.checked,
          show_datetime: !!$("#pt_show_datetime")?.checked,
          show_waiting_count: !!$("#pt_show_waiting")?.checked,
        },
      });
      toast("Print layout saved");
    } catch (e) {
      toast(e.message, true);
    }
  });
  ["pt_title","pt_header","pt_footer","pt_extra","pt_paper","pt_show_number","pt_show_queue","pt_show_datetime","pt_show_waiting"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", updatePrintPreview);
    if (el) el.addEventListener("change", updatePrintPreview);
  });

  setMode("reception");
  loadState();
  setInterval(loadState, 3000);
})();
