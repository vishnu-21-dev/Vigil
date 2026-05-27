/**
 * Quarantine page logic - fetches quarantine data from the API
 * and populates the Stitch-designed HTML.
 */

async function init() {
  try {
    await loadQuarantine();
    startPolling();
  } catch (err) {
    console.error("Quarantine load failed:", err);
    showToast("Failed to load quarantine data", "error");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

let pollInterval;
function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(loadQuarantine, 5000);
}

// ---- main loader ----

async function loadQuarantine() {
  const [requests, devices] = await Promise.all([
    API.quarantine.list(),
    API.devices.list(),
  ]);

  const pending = requests.filter(r => r.status === "pending");
  const active = requests.filter(r => r.status === "approved" || r.status === "ai_contained");
  const released = requests.filter(r => r.status === "released" || r.status === "dismissed");
  const activeAlerts = (await API.alerts.list()).filter(a => a.status === "active");

  // Update badges
  setText("pending-badge", `${pending.length} PENDING`);
  setText("active-badge", `${active.length} ACTIVE`);
  setText("released-count", released.length);

  // Notification dot
  const dot = document.getElementById("notification-dot");
  if (dot) {
    dot.classList.toggle("hidden", pending.length === 0 && activeAlerts.length === 0);
  }

  renderPendingCards(pending, devices);
  renderActiveTable(active, devices);
  renderReleasedTable(released, devices);
}

// ---- pending approval cards ----

function renderPendingCards(pending, devices) {
  const grid = document.getElementById("pending-grid");
  if (!grid) return;

  if (pending.length === 0) {
    grid.innerHTML = `
      <div class="col-span-full bg-surface-container border border-outline-variant p-lg text-center">
        <span class="material-symbols-outlined text-primary mb-sm" style="font-size: 36px;">verified_user</span>
        <p class="font-body-md text-body-md text-on-surface">No pending requests</p>
        <p class="font-body-sm text-body-sm text-on-surface-variant mt-xs">All quarantine requests have been reviewed</p>
      </div>`;
    return;
  }

  grid.innerHTML = pending.map(req => {
    const severityLabel = req.confidence > 0.8 ? "CRITICAL" : req.confidence > 0.5 ? "HIGH" : "MEDIUM";
    const severityClass = req.confidence > 0.8
      ? "bg-error-container text-on-error-container"
      : req.confidence > 0.5
        ? "bg-tertiary-container text-on-tertiary-container"
        : "bg-surface-container-highest text-on-surface-variant";

    return `
      <div class="bg-surface-container border border-outline-variant rounded hover:border-outline transition-colors flex flex-col">
        <div class="p-md border-b border-outline-variant flex justify-between items-center">
          <div class="flex items-center gap-sm">
            <span class="material-symbols-outlined text-error">router</span>
            <span class="font-data-md text-data-md text-on-surface">${esc(req.device_name)}</span>
          </div>
          <span class="${severityClass} font-label-caps text-label-caps px-2 py-1 rounded">${severityLabel}</span>
        </div>
        <div class="p-md flex-1 flex flex-col gap-sm">
          <div class="flex justify-between">
            <span class="font-body-sm text-body-sm text-on-surface-variant">IP Address</span>
            <span class="font-data-sm text-data-sm text-on-surface">${findDeviceIP(req.device_id, devices)}</span>
          </div>
          <div class="flex justify-between">
            <span class="font-body-sm text-body-sm text-on-surface-variant">Zone</span>
            <span class="font-data-sm text-data-sm text-on-surface">${esc(req.zone)}</span>
          </div>
          <div class="flex justify-between">
            <span class="font-body-sm text-body-sm text-on-surface-variant">Confidence</span>
            <span class="font-data-sm text-data-sm text-error">${(req.confidence * 100).toFixed(0)}%</span>
          </div>
          <div class="flex justify-between">
            <span class="font-body-sm text-body-sm text-on-surface-variant">Flagged</span>
            <span class="font-data-sm text-data-sm text-on-surface-variant">${timeAgo(req.flagged_at)}</span>
          </div>
          <div class="mt-xs">
            <span class="font-body-sm text-body-sm text-on-surface-variant">Reason:</span>
            <p class="font-body-sm text-body-sm text-on-surface mt-xs">${esc(req.reason)}</p>
          </div>
        </div>
        <div class="p-md pt-0 flex gap-sm mt-auto">
          <button class="flex-1 bg-error text-on-error font-label-caps text-label-caps py-sm uppercase tracking-wider hover:bg-error/80 transition-colors active:opacity-80"
                  onclick="approveRequest('${req.id}')">
            <span class="material-symbols-outlined text-sm align-middle mr-xs">gavel</span>Approve
          </button>
          <button class="flex-1 border border-outline-variant text-on-surface-variant font-label-caps text-label-caps py-sm uppercase tracking-wider hover:bg-surface-container-highest transition-colors active:opacity-80"
                  onclick="dismissRequest('${req.id}')">
            Dismiss
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// ---- active quarantine table ----

function renderActiveTable(activeRequests, devices) {
  const tbody = document.getElementById("quarantine-tbody");
  if (!tbody) return;

  if (activeRequests.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="p-lg text-center text-on-surface-variant font-body-sm text-body-sm">
          No devices currently quarantined
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = activeRequests.map(req => {
    const isAiContained = req.status === "ai_contained" || req.triggered_by === "AI_FAILSAFE";
    const duration = getDuration(req.auto_contained_at || req.approved_at);
    const statusBadge = isAiContained
      ? `<span class="bg-error/20 text-error border border-error/30 font-label-caps text-label-caps px-2 py-1 rounded shadow-[0_0_10px_rgba(255,180,171,0.2)]">AI-CONTAINED</span>`
      : `<span class="bg-tertiary-container/40 text-tertiary font-label-caps text-label-caps px-2 py-1 rounded">APPROVED</span>`;
    return `
      <tr class="hover:bg-surface-container-highest transition-colors">
        <td class="p-md font-data-sm text-data-sm flex items-start gap-sm">
          <div class="w-2 h-2 rounded-full bg-error mt-2"></div>
          <div class="flex flex-col">
            <div class="flex items-center gap-sm">
              ${esc(req.device_name)}
              ${statusBadge}
            </div>
            ${isAiContained ? `<div class="font-body-sm text-[11px] text-on-surface-variant mt-1 max-w-xs whitespace-normal leading-tight">${esc(req.reason)}</div>` : ''}
          </div>
        </td>
        <td class="p-md font-data-sm text-data-sm text-on-surface-variant align-top pt-md">${findDeviceIP(req.device_id, devices)}</td>
        <td class="p-md align-top pt-md">${esc(req.zone)}</td>
        <td class="p-md text-on-surface-variant align-top pt-md">${esc(req.approved_by) || "System"}</td>
        <td class="p-md text-right font-data-sm text-data-sm align-top pt-md">${duration}</td>
        <td class="p-md text-right align-top pt-md">
          <button class="border border-outline-variant text-on-surface-variant font-label-caps text-label-caps px-md py-xs uppercase tracking-wider hover:bg-surface-container-highest hover:text-primary transition-colors"
                  onclick="releaseDevice('${req.id}')">
            Release
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// ---- released/dismissed history table ----

function renderReleasedTable(released, devices) {
  const tbody = document.getElementById("released-tbody");
  if (!tbody) return;

  if (released.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="p-lg text-center text-on-surface-variant font-body-sm text-body-sm">
          No history yet
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = released.map(req => {
    const statusClass = req.status === "released"
      ? "bg-primary-container/30 text-primary"
      : "bg-surface-container-highest text-on-surface-variant";
    const statusLabel = req.status === "released" ? "RELEASED" : "DISMISSED";

    return `
      <tr class="hover:bg-surface-container-highest transition-colors">
        <td class="p-md font-data-sm text-data-sm flex items-center gap-sm">
          <div class="w-2 h-2 rounded-full bg-primary"></div>
          ${esc(req.device_name)}
        </td>
        <td class="p-md font-data-sm text-data-sm text-on-surface-variant">${findDeviceIP(req.device_id, devices)}</td>
        <td class="p-md">${esc(req.zone)}</td>
        <td class="p-md text-on-surface-variant">${esc(req.approved_by) || "-"}</td>
        <td class="p-md text-right">
          <span class="${statusClass} font-label-caps text-label-caps px-2 py-1 rounded">${statusLabel}</span>
        </td>
      </tr>
    `;
  }).join("");
}

// ---- actions ----

async function approveRequest(requestId) {
  try {
    await API.quarantine.approve(requestId, "Security Analyst", "Approved via dashboard");
    showToast("Quarantine approved - device isolated", "success");
    await loadQuarantine();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function dismissRequest(requestId) {
  try {
    await API.quarantine.dismiss(requestId);
    showToast("Request dismissed - device cleared", "info");
    await loadQuarantine();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function releaseDevice(requestId) {
  try {
    await API.quarantine.release(requestId);
    showToast("Device released from quarantine", "success");
    await loadQuarantine();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- utilities ----

function findDeviceIP(deviceId, devices) {
  const device = devices.find(d => d.id === deviceId);
  return device ? device.ip_address : "-";
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function esc(str) {
  if (str == null) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function timeAgo(isoStr) {
  if (!isoStr) return "-";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function getDuration(isoStr) {
  if (!isoStr) return "-";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  const remainMins = mins % 60;
  if (hrs < 24) return `${hrs}h ${remainMins}m`;
  const days = Math.floor(hrs / 24);
  return `${days}d ${hrs % 24}h`;
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  const colors = {
    success: "bg-primary-container text-on-primary-container border-primary",
    error: "bg-error-container text-on-error-container border-error",
    info: "bg-surface-container-highest text-on-surface border-outline-variant",
  };
  toast.className = `fixed bottom-6 right-6 px-md py-sm rounded border font-data-sm text-data-sm shadow-2xl z-50 transition-opacity duration-300 ${colors[type] || colors.info}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
