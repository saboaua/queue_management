(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  let state = {
    queues: [],
    cashiers: [],
    services: [],
    theme: {},
    print_template: {},
    overview: {},
    history: [],
    security: {},
  };
  let currentQueueId = "main";
  let selectedCashierId = localStorage.getItem("qm_cashier") || "";
  let selectedServiceId = localStorage.getItem("qm_service") || "";
  let currentMode = "reception";
  let unlocked = sessionStorage.getItem("qm_unlocked") === "1";
  let pendingMode = null;
  let adminDirty = false;
  let printDirty = false;
  let lastWaitingTotal = null;
  let soundArmed = false;

  // Browser call sounds (Calling Desk)
  let audioCtx = null;
  function maybePlayNewTicketSound() {
    const total = (state.queues || []).reduce((n, q) => n + (q.waiting_count || 0), 0);
    if (lastWaitingTotal === null) {
      lastWaitingTotal = total;
      return;
    }
    // New ticket(s) issued — notify calling desk (and any open UI)
    if (total > lastWaitingTotal && soundArmed) {
      const kind = (state.security && state.security.new_ticket_sound) || "beep";
      playCallSound(kind);
    }
    lastWaitingTotal = total;
  }

  function playCallSound(kind) {
    const sound = kind || (state.security && state.security.call_sound) || "chime";
    if (!sound || sound === "none") return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const now = audioCtx.currentTime;
      const beep = (freq, start, dur, type = "sine", gain = 0.2) => {
        const o = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        o.type = type;
        o.frequency.value = freq;
        g.gain.setValueAtTime(gain, now + start);
        g.gain.exponentialRampToValueAtTime(0.001, now + start + dur);
        o.connect(g);
        g.connect(audioCtx.destination);
        o.start(now + start);
        o.stop(now + start + dur + 0.02);
      };
      if (sound === "beep") beep(880, 0, 0.15);
      else if (sound === "double") {
        beep(880, 0, 0.12);
        beep(880, 0.18, 0.12);
      } else if (sound === "alert") {
        beep(523, 0, 0.12, "square", 0.15);
        beep(659, 0.14, 0.12, "square", 0.15);
        beep(784, 0.28, 0.18, "square", 0.15);
      } else {
        // chime
        beep(523.25, 0, 0.2, "sine", 0.18);
        beep(659.25, 0.12, 0.25, "sine", 0.16);
        beep(783.99, 0.24, 0.35, "sine", 0.14);
      }
    } catch (e) {
      console.warn("sound failed", e);
    }
  }

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
      maybePlayNewTicketSound();
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
    if (!isError) el._t = setTimeout(() => (el.hidden = true), 3200);
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

  function enabledServices() {
    return (state.services || []).filter((s) => s.enabled);
  }

  const DEFAULT_THEME = { bg: "#f3f5f8", card: "#ffffff", text: "#0e1726", muted: "#566275", accent: "#0f766e", success: "#1f9d55", warning: "#f59e0b", danger: "#dc2626" };
  const LEGACY_THEME = { bg: "#f7f8fc", card: "#ffffff", text: "#0b0f1e", muted: "#545a72", accent: "#2f6fed", success: "#00b876", warning: "#ff8a00", danger: "#ef3f3f" };
  const isLegacyTheme = (t) => Object.keys(LEGACY_THEME).every((k) => String(t[k] || "").toLowerCase() === LEGACY_THEME[k]);

  function applyTheme(theme) {
    // Installs that still hold the pre-1.9 default palette get the new look; custom palettes are kept.
    if (!theme || !Object.keys(theme).length || isLegacyTheme(theme)) theme = DEFAULT_THEME;
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
    if (!adminDirty) {
      ["bg", "card", "text", "muted", "accent", "success", "warning", "danger"].forEach((k) => {
        const el = document.getElementById(`theme_${k}`);
        if (el && theme[k] && document.activeElement !== el) el.value = theme[k];
      });
    }
  }

  function needsPin(mode) {
    return (mode === "admin" || mode === "manager") && state.security?.pin_enabled && !unlocked;
  }

  function setMode(mode) {
    if (needsPin(mode)) {
      pendingMode = mode;
      openPinModal();
      return;
    }
    currentMode = mode;
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

  function openPinModal() {
    const m = $("#pinModal");
    if (!m) return;
    m.hidden = false;
    const err = $("#pinError");
    if (err) err.hidden = true;
    const input = $("#pinInput");
    if (input) {
      input.value = "";
      setTimeout(() => input.focus(), 50);
    }
  }
  function closePinModal() {
    const m = $("#pinModal");
    if (m) m.hidden = true;
    pendingMode = null;
  }

  function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function renderServiceButtons() {
    const box = $("#serviceButtons");
    if (!box) return;
    const list = enabledServices();
    if (!list.length) {
      box.innerHTML = "";
      return;
    }
    if (!selectedServiceId || !list.find((s) => s.id === selectedServiceId)) {
      selectedServiceId = list[0].id;
    }
    box.innerHTML = list
      .map(
        (s) =>
          `<button type="button" class="service-btn ${
            s.id === selectedServiceId ? "active" : ""
          }" data-service="${s.id}"><span class="svc-icon">${s.icon || "🎫"}</span><span class="svc-name">${
            s.name
          }</span></button>`
      )
      .join("");
    box.querySelectorAll("[data-service]").forEach((btn) => {
      btn.onclick = () => {
        selectedServiceId = btn.getAttribute("data-service");
        localStorage.setItem("qm_service", selectedServiceId);
        const svc = list.find((s) => s.id === selectedServiceId);
        if (svc?.queue_id) currentQueueId = svc.queue_id;
        renderServiceButtons();
        render();
        if (list.length > 1) takeTicket(); // one tap = one ticket
      };
    });
    const single = list.length <= 1;
    box.classList.toggle("one-tap", !single);
    const tb = $("#btnTake"); if (tb) tb.hidden = !single;
    setText("heroHint", single ? "Take your number." : "Tap a service to get your number.");
  }

  function renderCashierSelect() {
    const sel = $("#cashierSelect");
    if (!sel) return;
    const list = enabledCashiers();
    if (!list.length) {
      sel.innerHTML = `<option value="">No cashiers</option>`;
      return;
    }
    if (!selectedCashierId || !list.find((c) => c.id === selectedCashierId)) {
      selectedCashierId = list[0].id;
      localStorage.setItem("qm_cashier", selectedCashierId);
    }
    sel.innerHTML = list
      .map((c) => {
        const tag =
          c.status === "break" ? " (break)" : c.status === "serving" ? " (busy)" : "";
        return `<option value="${c.id}" ${c.id === selectedCashierId ? "selected" : ""}>${c.name}${tag}</option>`;
      })
      .join("");
  }

  function renderCashierAdmin() {
    const box = $("#cashierAdminList");
    if (!box || adminDirty) return;
    const list = state.cashiers || [];
    box.innerHTML = list
      .map(
        (c, i) => `
      <div class="admin-row" data-idx="${i}">
        <input type="text" class="c-id" value="${escapeAttr(c.id)}" placeholder="id" />
        <input type="text" class="c-name" value="${escapeAttr(c.name)}" placeholder="Name" />
        <label class="check-wrap"><input type="checkbox" class="c-en" ${c.enabled ? "checked" : ""}/><span>On</span></label>
        <button type="button" class="btn-x" data-rm="${i}" title="Remove">✕</button>
      </div>`
      )
      .join("");
    box.querySelectorAll("[data-rm]").forEach((btn) => {
      btn.onclick = () => {
        adminDirty = true;
        const idx = +btn.getAttribute("data-rm");
        state.cashiers.splice(idx, 1);
        adminDirty = false;
        renderCashierAdmin();
      };
    });
    box.querySelectorAll("input").forEach((inp) => {
      inp.addEventListener("input", () => {
        adminDirty = true;
      });
    });
  }

  function renderServiceAdmin() {
    const box = $("#serviceAdminList");
    if (!box || adminDirty) return;
    const list = state.services || [];
    const qopts = (state.queues || [])
      .map((q) => `<option value="${q.queue_id}">${q.name}</option>`)
      .join("");
    box.innerHTML = list
      .map(
        (s, i) => `
      <div class="admin-row service-row" data-idx="${i}">
        <input type="text" class="s-icon" value="${escapeAttr(s.icon || "🎫")}" title="Icon" />
        <input type="text" class="s-id" value="${escapeAttr(s.id)}" placeholder="id" />
        <input type="text" class="s-name" value="${escapeAttr(s.name)}" placeholder="Name" />
        <select class="s-queue">${qopts.replace(
          `value="${s.queue_id}"`,
          `value="${s.queue_id}" selected`
        )}</select>
        <label class="check-wrap"><input type="checkbox" class="s-en" ${s.enabled ? "checked" : ""}/><span>On</span></label>
        <button type="button" class="btn-x" data-rms="${i}">✕</button>
      </div>`
      )
      .join("");
    // fix selected queue
    box.querySelectorAll(".service-row").forEach((row, i) => {
      const sel = row.querySelector(".s-queue");
      if (sel && list[i]) sel.value = list[i].queue_id;
    });
    box.querySelectorAll("[data-rms]").forEach((btn) => {
      btn.onclick = () => {
        const idx = +btn.getAttribute("data-rms");
        state.services.splice(idx, 1);
        renderServiceAdmin();
      };
    });
    box.querySelectorAll("input,select").forEach((inp) => {
      inp.addEventListener("input", () => {
        adminDirty = true;
      });
      inp.addEventListener("change", () => {
        adminDirty = true;
      });
    });
  }

  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function fillPrintForm() {
    if (printDirty) return;
    const t = state.print_template || {};
    const set = (id, val, isCheck) => {
      const el = document.getElementById(id);
      if (!el || document.activeElement === el) return;
      if (isCheck) el.checked = !!val;
      else el.value = val ?? "";
    };
    set("pt_title", t.title);
    set("pt_header", t.header);
    set("pt_footer", t.footer);
    set("pt_extra", t.extra_line);
    set("pt_logo", t.logo_url || "");
    set("pt_social", t.social_line || "");
    set("pt_paper", t.paper_width || "58mm");
    updateLogoPreview(t.logo_url || "");
    set("pt_show_number", t.show_number !== false, true);
    set("pt_show_queue", t.show_queue_name !== false, true);
    set("pt_show_datetime", t.show_datetime !== false, true);
    set("pt_show_waiting", t.show_waiting_count !== false, true);
    set("pt_show_eta", t.show_eta !== false, true);
    updatePrintPreview();
  }

  function fillSecurityForm() {
    const s = state.security || {};
    if (!adminDirty) {
      const pin = $("#adminPin");
      if (pin && document.activeElement !== pin) pin.value = "";
      const ae = $("#announceEnabled");
      if (ae && document.activeElement !== ae) ae.checked = !!s.announce_enabled;
      const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el && document.activeElement !== el) el.value = val ?? "";
      };
      const tpl = s.announce_templates || {};
      setVal("announceWithCashier", tpl.with_cashier || "Ticket {ticket}, please go to {cashier}");
      setVal("announceWithoutCashier", tpl.without_cashier || "Ticket {ticket}, please proceed");
      setVal("callSound", s.call_sound || "chime");
      setVal("newTicketSound", s.new_ticket_sound || "beep");
      setVal("uiLogoUrl", s.ui_logo_url || "");
    }
    updateUiLogo(s.ui_logo_url || "");
    fillMediaPlayerSelect(s.announce_entity || "");
    fillTtsEngineSelect(s.announce_tts_entity || "");
  }

  function fillTtsEngineSelect(selected) {
    const sel = $("#announceTtsEntity");
    if (!sel || document.activeElement === sel) return;
    const engines = state.tts_engines || [];
    const current = selected || (state.security && state.security.announce_tts_entity) || sel.value || "";
    let opts = `<option value="">— Auto (first available) —</option>`;
    if (!engines.length) {
      opts += `<option value="" disabled>No tts.* entities found – add a TTS integration</option>`;
    } else {
      opts += engines
        .map((e) => {
          const selAttr = e.entity_id === current ? " selected" : "";
          return `<option value="${e.entity_id}"${selAttr}>${e.name} (${e.entity_id})</option>`;
        })
        .join("");
    }
    if (current && !engines.find((e) => e.entity_id === current)) {
      opts += `<option value="${current}" selected>${current} (saved)</option>`;
    }
    sel.innerHTML = opts;
    if (current) sel.value = current;
    const hint = $("#ttsEngineHint");
    if (hint) {
      hint.textContent = engines.length
        ? `Found ${engines.length} TTS engine(s). Spoken automatically on Call Next.`
        : "No TTS engines found. Settings → Devices & Services → Add integration → Piper / Google / Cloud TTS.";
    }
  }

  function fillMediaPlayerSelect(selected) {
    const sel = $("#announceEntity");
    if (!sel || document.activeElement === sel) return;
    const players = state.media_players || [];
    const current = selected || sel.value || "";
    let opts = `<option value="">— Select a speaker —</option>`;
    if (!players.length) {
      opts += `<option value="" disabled>No media_player entities found</option>`;
    } else {
      opts += players
        .map((p) => {
          const label = `${p.name} (${p.entity_id})`;
          const selAttr = p.entity_id === current ? " selected" : "";
          return `<option value="${p.entity_id}"${selAttr}>${label}</option>`;
        })
        .join("");
    }
    // Keep custom value if saved entity not in list anymore
    if (current && !players.find((p) => p.entity_id === current)) {
      opts += `<option value="${current}" selected>${current} (saved)</option>`;
    }
    sel.innerHTML = opts;
    if (current) sel.value = current;
  }

  let _uiLogoUrl = null;
  let _uiLogoFailed = false;
  function updateUiLogo(url) {
    const bar = $("#uiLogoBar");
    const img = $("#uiLogoImg");
    if (!bar || !img) return;
    const u = (url || "").trim();
    if (!u) {
      _uiLogoUrl = null;
      _uiLogoFailed = false;
      bar.hidden = true;
      return;
    }
    // Only kick off a (re)load when the URL changes, or when the previous
    // attempt failed — setting img.src to the same value again is a no-op
    // in most browsers, so a transient failure (e.g. HA still starting up)
    // would otherwise leave the logo hidden forever.
    if (u === _uiLogoUrl && !_uiLogoFailed) return;
    _uiLogoUrl = u;
    img.onload = () => {
      _uiLogoFailed = false;
      bar.hidden = false;
    };
    img.onerror = () => {
      _uiLogoFailed = true;
      bar.hidden = true;
    };
    img.src = "";
    img.src = u;
  }

  let _ptLogoUrl = null;
  function updateLogoPreview(url) {
    const img = $("#logoImg");
    const ph = document.querySelector(".logo-placeholder");
    const u = url || $("#pt_logo")?.value || "";
    if (!img) return;
    if (u) {
      if (u === _ptLogoUrl) return;
      _ptLogoUrl = u;
      img.onerror = () => {
        img.hidden = true;
        if (ph) ph.hidden = false;
      };
      img.onload = () => {
        img.hidden = false;
        if (ph) ph.hidden = true;
      };
      img.src = "";
      img.src = u;
    } else {
      _ptLogoUrl = null;
      img.hidden = true;
      if (ph) ph.hidden = false;
    }
  }

  function updatePrintPreview() {
    const pre = $("#pt_preview");
    if (!pre) return;
    const lines = [];
    const title = $("#pt_title")?.value;
    const header = $("#pt_header")?.value;
    const footer = $("#pt_footer")?.value;
    const extra = $("#pt_extra")?.value;
    const logo = $("#pt_logo")?.value;
    const social = $("#pt_social")?.value;
    if (logo) lines.push("[LOGO]");
    if (title) lines.push(title);
    if (header) lines.push(header);
    if ($("#pt_show_queue")?.checked) lines.push("Queue: Main Queue");
    if ($("#pt_show_number")?.checked) lines.push("Number: 42");
    if ($("#pt_show_waiting")?.checked) lines.push("Waiting ahead: 3");
    if ($("#pt_show_eta")?.checked) lines.push("Est. wait: ~6 min");
    if ($("#pt_show_datetime")?.checked) lines.push(new Date().toLocaleString());
    if (extra) lines.push(extra);
    if (footer) lines.push(footer);
    if (social) lines.push(social);
    pre.textContent = lines.join("\n");
    updateLogoPreview(logo);
  }

  const DONUT_PALETTE = [
    "var(--blue)", "var(--green)", "var(--orange)", "var(--red)",
    "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16",
  ];

  function fmtHour(h) {
    const period = h < 12 ? "AM" : "PM";
    let hr = h % 12;
    if (hr === 0) hr = 12;
    return `${hr}${period}`;
  }

  function renderDashboard() {
    const d = state.dashboard || {};
    const ov = state.overview || {};
    const hourly = d.hourly_7d || new Array(24).fill(0);
    const peakHour = d.peak_hour;

    const kpis = $("#mgrKpis");
    if (kpis) {
      const trend = d.issued_trend_pct || 0;
      const trendUp = trend >= 0;
      const trendBadge = `<span class="kpi-trend ${trendUp ? "up" : "down"}">${
        trendUp ? "▲" : "▼"
      } ${Math.abs(trend)}% vs yesterday</span>`;
      kpis.innerHTML = `
        <div class="kpi-card">
          <div class="kpi-icon kpi-icon-blue"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9a2 2 0 0 0 0 6v3h18v-3a2 2 0 0 1 0-6V6H3z"/><path d="M14 7v10" stroke-dasharray="2 3"/></svg></div>
          <div class="kpi-body">
            <div class="kpi-value">${d.today_issued ?? 0}</div>
            <div class="kpi-label">Tickets today</div>
            ${trendBadge}
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon kpi-icon-green"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg></div>
          <div class="kpi-body">
            <div class="kpi-value">${d.today_completed ?? 0}</div>
            <div class="kpi-label">Completed today</div>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon kpi-icon-orange"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg></div>
          <div class="kpi-body">
            <div class="kpi-value">${ov.total_waiting ?? 0}</div>
            <div class="kpi-label">Waiting now</div>
          </div>
        </div>
        <div class="kpi-card">
          <div class="kpi-icon kpi-icon-purple"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M9 2h6"/></svg></div>
          <div class="kpi-body">
            <div class="kpi-value">${ov.avg_service_display || "—"}</div>
            <div class="kpi-label">Avg. service time</div>
          </div>
        </div>`;
    }

    const chart = $("#mgrPeakChart");
    const badge = $("#mgrPeakBadge");
    if (badge) {
      badge.textContent =
        peakHour != null && hourly[peakHour] > 0
          ? `Busiest: ${fmtHour(peakHour)}`
          : "No data yet";
    }
    if (chart) {
      const max = Math.max(1, ...hourly);
      chart.innerHTML = hourly
        .map((v, h) => {
          const pct = Math.round((v / max) * 100);
          const isPeak = h === peakHour && v > 0;
          const label = h % 3 === 0 ? fmtHour(h) : "";
          return `<div class="peak-bar-col" title="${fmtHour(h)}: ${v} ticket${
            v === 1 ? "" : "s"
          }">
            <div class="peak-bar ${isPeak ? "peak" : ""}" style="height:${Math.max(
            pct,
            v > 0 ? 4 : 2
          )}%"></div>
            <div class="peak-bar-label">${label}</div>
          </div>`;
        })
        .join("");
    }

    const donutWrap = $("#mgrDonut");
    if (donutWrap) {
      const services = state.services || [];
      const nameFor = (id) =>
        services.find((s) => s.id === id)?.name || id || "Unassigned";
      const entries = Object.entries(d.services_7d || {}).sort((a, b) => b[1] - a[1]);
      const total = entries.reduce((sum, [, v]) => sum + v, 0);
      if (!total) {
        donutWrap.innerHTML = `<div class="muted empty-state">No tickets with a service yet</div>`;
      } else {
        let offset = 0;
        const circumference = 2 * Math.PI * 40;
        const segments = entries
          .map(([id, v], i) => {
            const frac = v / total;
            const dash = frac * circumference;
            const seg = `<circle cx="60" cy="60" r="40" fill="none" stroke="${
              DONUT_PALETTE[i % DONUT_PALETTE.length]
            }" stroke-width="18" stroke-dasharray="${dash} ${circumference - dash}" stroke-dashoffset="${-offset}" transform="rotate(-90 60 60)"></circle>`;
            offset += dash;
            return seg;
          })
          .join("");
        const legend = entries
          .map(
            ([id, v], i) => `<div class="donut-legend-item">
              <span class="donut-swatch" style="background:${
                DONUT_PALETTE[i % DONUT_PALETTE.length]
              }"></span>
              <span class="dl-name">${escapeAttr(nameFor(id))}</span>
              <span class="dl-pct muted">${Math.round((v / total) * 100)}%</span>
            </div>`
          )
          .join("");
        donutWrap.innerHTML = `
          <svg viewBox="0 0 120 120" class="donut-svg">${segments}</svg>
          <div class="donut-legend">${legend}</div>`;
      }
    }
  }

  function renderManager() {
    renderDashboard();
    const ov = state.overview || {};
    setText("mWaiting", ov.total_waiting ?? 0);
    setText("mServing", ov.total_serving ?? 0);
    setText("mIdle", (ov.cashiers_idle || []).length);
    setText("mBreak", (ov.cashiers_break || []).length);
    setText("mAvg", ov.avg_service_display || "—");
    const clock = $("#mgrClock");
    if (clock) clock.textContent = "Updated " + new Date().toLocaleTimeString();

    const busy = $("#mgrBusy");
    if (busy) {
      const rows = ov.cashiers_busy || [];
      busy.innerHTML = rows.length
        ? rows
            .map((c) => {
              const ago = c.last_call_at
                ? Math.max(
                    0,
                    Math.round((Date.now() - new Date(c.last_call_at).getTime()) / 60000)
                  )
                : null;
              return `<div class="mgr-cashier busy">
                <div class="mc-name">${c.name}</div>
                <div class="mc-ticket">${c.ticket || "—"}</div>
                <div class="mc-meta">Served: ${c.served_count || 0}${
                ago != null ? ` · ${ago} min` : ""
              }</div>
              </div>`;
            })
            .join("")
        : `<div class="muted empty-state">No cashiers serving</div>`;
    }

    const idle = $("#mgrIdle");
    if (idle) {
      const rows = ov.cashiers_idle || [];
      idle.innerHTML = rows.length
        ? rows
            .map(
              (c) =>
                `<div class="mgr-cashier idle"><div class="mc-name">${c.name}</div><div class="mc-ticket muted">Idle</div><div class="mc-meta">Ready</div></div>`
            )
            .join("")
        : `<div class="muted empty-state">None idle</div>`;
    }

    const br = $("#mgrBreak");
    if (br) {
      const rows = ov.cashiers_break || [];
      br.innerHTML = rows.length
        ? rows
            .map(
              (c) =>
                `<div class="mgr-cashier break"><div class="mc-name">${c.name}</div><div class="mc-ticket muted">Break</div></div>`
            )
            .join("")
        : `<div class="muted empty-state">Nobody on break</div>`;
    }

    const queues = $("#mgrQueues");
    if (queues) {
      queues.innerHTML = (ov.queues || [])
        .map((qq) => {
          const waitClass = qq.waiting > 5 ? "hot" : qq.waiting > 0 ? "warm" : "cool";
          return `<div class="queue-card ${waitClass}">
            <div class="qc-top"><strong>${qq.name}</strong><span class="badge">${qq.status}</span></div>
            <div class="qc-metrics">
              <div><span class="qc-num">${qq.waiting}</span><span class="qc-lab">waiting</span></div>
              <div><span class="qc-num">${qq.eta || "—"}</span><span class="qc-lab">eta</span></div>
              <div><span class="qc-num">${qq.current_display || "—"}</span><span class="qc-lab">serving</span></div>
              <div><span class="qc-num">${qq.current_cashier_name || "—"}</span><span class="qc-lab">cashier</span></div>
            </div>
          </div>`;
        })
        .join("");
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
              ? `Issued ${h.ticket_display || ""}${h.eta ? " (" + h.eta + ")" : ""}`
              : h.type === "called"
              ? `Called ${h.ticket_display || ""}${who}`
              : h.type === "completed"
              ? `Completed ${h.ticket_display || ""}${who}`
              : h.type === "reset"
              ? `Reset ${h.queue_name || ""}`
              : h.type || "";
          return `<div class="history-item type-${h.type || ""}"><span><span class="type">${
            h.type || ""
          }</span> ${label}</span><span>${time}</span></div>`;
        })
        .join("") || "<div class='muted'>No activity yet</div>";
    }
  }

  function waitedLabel(display) {
    const h = (state.history || []).slice().reverse().find((x) => x.type === "issued" && x.ticket_display === display && x.timestamp);
    if (!h) return "";
    const m = Math.max(0, Math.round((Date.now() - new Date(h.timestamp).getTime()) / 60000));
    return m < 1 ? "just now" : m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
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

    renderServiceButtons();
    renderCashierSelect();
    const queue = q();

    setText("rWaiting", queue.waiting_count ?? 0);
    setText("rEta", queue.eta || "—");
    setText("rCurrent", queue.current_display || "—");
    setText("cCurrent", queue.current_display || "—");
    setText("cCashierLine", queue.current_cashier_name ? `at ${queue.current_cashier_name}` : "");
    setText("cWaiting", queue.waiting_count ?? 0);
    setText("cEta", queue.eta || "—");
    setText("cStatus", queue.status || "idle");

    const ul = $("#waitingList");
    if (ul) {
      ul.innerHTML = "";
      const displays = queue.waiting_display || [];
      if (!displays.length) ul.innerHTML = "<li class='muted'>No one waiting</li>";
      else
        displays.forEach((t, idx) => {
          const li = document.createElement("li");
          li.innerHTML = `<span class="pos">${idx + 1}</span><span class="tk">${escapeAttr(t)}</span><span class="wt">${waitedLabel(t)}</span><span class="call">Call</span>`;
          li.onclick = () =>
            doAction("call_ticket", {
              ticket: queue.waiting[idx],
              cashier_id: selectedCashierId || undefined,
            })
              .then((r) => {
                playCallSound();
                toast(
                  `Called ${t}${
                    r?.result?.cashier_name ? " → " + r.result.cashier_name : ""
                  }`
                );
              })
              .catch((e) => toast(e.message, true));
          ul.appendChild(li);
        });
    }

    setText("dCurrent", queue.current_display || "—");
    setText(
      "dCashier",
      queue.current_cashier_name ? `Please go to ${queue.current_cashier_name}` : ""
    );
    setText("dWaiting", queue.waiting_count ?? 0);
    setText("dEta", queue.eta || "—");
    const dNext = $("#dNext");
    if (dNext) {
      const next = (queue.waiting_display || []).slice(0, 5);
      dNext.innerHTML = next.length
        ? next.map((t, i) => `<li>${escapeAttr(t)}${i === 0 ? "<span>Next</span>" : ""}</li>`).join("")
        : `<li class="muted">No one waiting</li>`;
    }

    renderManager();
    renderCashierAdmin();
    renderServiceAdmin();
    fillPrintForm();
    fillSecurityForm();
  }

  // ---- events ----
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

  let issuing = false, ticketTimer = null;
  async function takeTicket() {
    if (issuing) return;
    issuing = true;
    try {
      const extra = {};
      if (selectedServiceId) extra.service_id = selectedServiceId;
      const res = await doAction("take_ticket", extra);
      if (res?.result) {
        setText("ticketNumber", res.result.ticket_display);
        setText("ticketEta", res.result.eta && res.result.eta !== "—" ? `Estimated wait: ${res.result.eta}` : "");
        const box = $("#ticketResult");
        if (box) {
          box.hidden = false;
          box.scrollIntoView({ behavior: "smooth", block: "nearest" });
          clearTimeout(ticketTimer);
          ticketTimer = setTimeout(() => (box.hidden = true), 15000);
        }
        playCallSound((state.security && state.security.new_ticket_sound) || "beep");
        toast(`Ticket ${res.result.ticket_display} issued`);
      }
    } catch (e) {
      toast(e.message, true);
    } finally {
      setTimeout(() => (issuing = false), 1500);
    }
  }
  $("#btnTake")?.addEventListener("click", takeTicket);

  $("#btnCallNext")?.addEventListener("click", async () => {
    try {
      if (!selectedCashierId) return toast("Select a cashier first", true);
      const res = await doAction("call_next", { cashier_id: selectedCashierId });
      if (res?.result) {
        playCallSound();
        toast(
          `Now serving ${res.result.ticket_display}${
            res.result.cashier_name ? " at " + res.result.cashier_name : ""
          }`
        );
      } else toast("No tickets waiting", true);
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

  $("#btnBreak")?.addEventListener("click", async () => {
    try {
      if (!selectedCashierId) return toast("Select a cashier", true);
      await doAction("set_cashier_status", {
        cashier_id: selectedCashierId,
        status: "break",
      });
      toast("On break");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnResume")?.addEventListener("click", async () => {
    try {
      if (!selectedCashierId) return toast("Select a cashier", true);
      await doAction("set_cashier_status", {
        cashier_id: selectedCashierId,
        status: "idle",
      });
      toast("Ready");
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
      adminDirty = false;
      toast(`Queue "${name}" created`);
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnAddCashier")?.addEventListener("click", () => {
    const n = (state.cashiers || []).length + 1;
    state.cashiers = state.cashiers || [];
    state.cashiers.push({ id: `cashier_${n}`, name: `Cashier ${n}`, enabled: true });
    adminDirty = false;
    renderCashierAdmin();
    adminDirty = true;
  });

  $("#btnSaveCashiers")?.addEventListener("click", async () => {
    try {
      const rows = [...document.querySelectorAll("#cashierAdminList .admin-row")];
      const cashiers = rows.map((row) => ({
        id: (row.querySelector(".c-id")?.value || "").trim(),
        name: (row.querySelector(".c-name")?.value || "").trim(),
        enabled: !!row.querySelector(".c-en")?.checked,
      }));
      await doAction("save_cashiers", { cashiers });
      adminDirty = false;
      toast("Cashiers saved");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnAddService")?.addEventListener("click", () => {
    const n = (state.services || []).length + 1;
    state.services = state.services || [];
    state.services.push({
      id: `service_${n}`,
      name: `Service ${n}`,
      queue_id: "main",
      enabled: true,
      icon: "🎫",
    });
    adminDirty = false;
    renderServiceAdmin();
    adminDirty = true;
  });

  $("#btnSaveServices")?.addEventListener("click", async () => {
    try {
      const rows = [...document.querySelectorAll("#serviceAdminList .admin-row")];
      const services = rows.map((row) => ({
        id: (row.querySelector(".s-id")?.value || "").trim(),
        name: (row.querySelector(".s-name")?.value || "").trim(),
        icon: (row.querySelector(".s-icon")?.value || "🎫").trim(),
        queue_id: row.querySelector(".s-queue")?.value || "main",
        enabled: !!row.querySelector(".s-en")?.checked,
      }));
      await doAction("save_services", { services });
      adminDirty = false;
      toast("Services saved");
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
      adminDirty = false;
      toast("Theme saved");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnResetTheme")?.addEventListener("click", async () => {
    try {
      await doAction("save_theme", {
        theme: DEFAULT_THEME,
      });
      adminDirty = false;
      toast("Theme reset");
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
          show_eta: !!$("#pt_show_eta")?.checked,
          logo_url: ($("#pt_logo")?.value || "").trim(),
          social_line: ($("#pt_social")?.value || "").trim(),
        },
      });
      printDirty = false;
      toast("Print layout saved");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnTestSound")?.addEventListener("click", () => {
    playCallSound($("#callSound")?.value || "chime");
    toast("Playing call sound");
  });

  $("#btnTestAnnounce")?.addEventListener("click", async () => {
    try {
      const entity = ($("#announceEntity")?.value || "").trim();
      if (!entity) return toast("Select a speaker first", true);
      // Save current announce settings then trigger a test call message via action
      await doAction("save_security", {
        admin_pin: ($("#adminPin")?.value || "").trim(),
        announce_enabled: true,
        announce_entity: entity,
        announce_tts_entity: ($("#announceTtsEntity")?.value || "").trim(),
        announce_templates: {
          with_cashier: ($("#announceWithCashier")?.value || "").trim(),
          without_cashier: ($("#announceWithoutCashier")?.value || "").trim(),
        },
        call_sound: $("#callSound")?.value || "chime",
        new_ticket_sound: $("#newTicketSound")?.value || "beep",
        ui_logo_url: ($("#uiLogoUrl")?.value || "").trim(),
      });
      adminDirty = false;
      await doAction("test_announce", {});
      toast("Test announcement sent");
    } catch (e) {
      toast(e.message, true);
    }
  });

  $("#btnSaveSecurity")?.addEventListener("click", async () => {
    try {
      await doAction("save_security", {
        admin_pin: ($("#adminPin")?.value || "").trim(),
        announce_enabled: !!$("#announceEnabled")?.checked,
        announce_entity: ($("#announceEntity")?.value || "").trim(),
        announce_tts_entity: ($("#announceTtsEntity")?.value || "").trim(),
        announce_templates: {
          with_cashier: ($("#announceWithCashier")?.value || "").trim(),
          without_cashier: ($("#announceWithoutCashier")?.value || "").trim(),
        },
        call_sound: $("#callSound")?.value || "chime",
        new_ticket_sound: $("#newTicketSound")?.value || "beep",
        ui_logo_url: ($("#uiLogoUrl")?.value || "").trim(),
      });
      adminDirty = false;
      unlocked = true;
      sessionStorage.setItem("qm_unlocked", "1");
      toast("Security saved");
    } catch (e) {
      toast(e.message, true);
    }
  });

  document.querySelectorAll("[data-print]").forEach((el) => {
    el.addEventListener("input", () => {
      printDirty = true;
      updatePrintPreview();
    });
    el.addEventListener("change", () => {
      printDirty = true;
      updatePrintPreview();
    });
  });
  document.querySelectorAll("[data-admin],[data-theme]").forEach((el) => {
    el.addEventListener("input", () => {
      adminDirty = true;
    });
    el.addEventListener("change", () => {
      adminDirty = true;
    });
  });

  $("#pinOk")?.addEventListener("click", async () => {
    try {
      const pin = $("#pinInput")?.value || "";
      const res = await doAction("verify_pin", { pin });
      if (res.ok) {
        unlocked = true;
        sessionStorage.setItem("qm_unlocked", "1");
        const mode = pendingMode || "admin";
        closePinModal();
        setMode(mode);
      } else {
        const err = $("#pinError");
        if (err) err.hidden = false;
      }
    } catch (e) {
      toast(e.message, true);
    }
  });
  $("#pinCancel")?.addEventListener("click", closePinModal);
  $("#pinInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#pinOk")?.click();
  });

  // Browsers require a user gesture before audio
  document.addEventListener(
    "click",
    () => {
      soundArmed = true;
      try {
        audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === "suspended") audioCtx.resume();
      } catch (_) {}
    },
    { once: false }
  );

  function setAdminTab(tab) {
    localStorage.setItem("qm_admin_tab", tab);
    $$("#adminNav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    $$("#mode-admin .admin-pane > [data-tab]").forEach((c) => c.classList.toggle("tab-active", c.dataset.tab === tab));
  }
  $$("#adminNav button").forEach((b) => b.addEventListener("click", () => setAdminTab(b.dataset.tab)));
  setAdminTab(localStorage.getItem("qm_admin_tab") || "counters");

  setMode("reception");
  loadState();
  setInterval(loadState, 3000);
})();
