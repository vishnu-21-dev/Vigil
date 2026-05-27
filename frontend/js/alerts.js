/**
 * Alerts page logic - fetches alert data from the API
 * and populates the Stitch-designed HTML.
 */

async function init() {
  try {
    await loadAlerts();
    startPolling();
  } catch (err) {
    console.error("Alerts load failed:", err);
    showToast("Failed to load alerts data", "error");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

let pollInterval;
let allAlerts = [];

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(loadAlerts, 5000);
}

// ---- main loader ----

async function loadAlerts() {
  const [alerts, activeAlertsList] = await Promise.all([
    API.alerts.list(),
    API.alerts.list("active"),
  ]);

  allAlerts = alerts;

  // Notification dot
  const dot = document.getElementById("notification-dot");
  if (dot) {
    dot.classList.toggle("hidden", activeAlertsList.length === 0);
  }

  renderStatsRibbon(alerts);
  renderAlertsTable(alerts);
  startCountdowns();
}

let countdownInterval;

function startCountdowns() {
  if (countdownInterval) clearInterval(countdownInterval);
  updateCountdowns();
  countdownInterval = setInterval(updateCountdowns, 1000);
}

function updateCountdowns() {
  const elements = document.querySelectorAll('.failsafe-countdown');
  elements.forEach(el => {
    const createdStr = el.getAttribute('data-created');
    const timeout = parseInt(el.getAttribute('data-timeout'), 10);
    if (!createdStr || isNaN(timeout)) return;
    
    // API returns trailing Z for UTC usually, or use directly
    let createdTimeStr = createdStr;
    if (!createdTimeStr.endsWith('Z') && !createdTimeStr.includes('+')) {
      createdTimeStr += 'Z';
    }
    const createdTime = new Date(createdTimeStr).getTime();
    const elapsed = Math.floor((Date.now() - createdTime) / 1000);
    const remaining = Math.max(0, timeout - elapsed);
    
    if (remaining > 0) {
      el.textContent = remaining + 's';
    } else {
      el.textContent = '0s';
    }
  });
}

// ---- stats ribbon ----

function renderStatsRibbon(alerts) {
  const critical = alerts.filter(a => a.status === "active" && a.confidence > 0.9).length;
  const high = alerts.filter(a => a.status === "active" && a.confidence > 0.75 && a.confidence <= 0.9).length;
  const medium = alerts.filter(a => a.status === "active" && a.confidence > 0.5 && a.confidence <= 0.75).length;
  const low = alerts.filter(a => a.status === "active" && a.confidence <= 0.5).length;

  setText("stat-critical", critical);
  setText("stat-high", high);
  setText("stat-medium", medium);
  setText("stat-low", low);
}

// ---- alerts table ----

function renderAlertsTable(alerts) {
  const tbody = document.getElementById("alerts-tbody");
  if (!tbody) return;

  // Sort by timestamp desc
  const sorted = [...alerts].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

  // Update pagination info
  const paginationInfo = document.getElementById("pagination-info");
  if (paginationInfo) {
    paginationInfo.textContent = `Showing 1-${sorted.length} of ${sorted.length}`;
  }

  if (sorted.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="p-lg text-center">
          <div class="flex flex-col items-center py-lg">
            <span class="material-symbols-outlined text-primary mb-sm" style="font-size: 36px;">verified_user</span>
            <p class="font-body-md text-body-md text-on-surface">No alerts</p>
            <p class="font-body-sm text-body-sm text-on-surface-variant mt-xs">All clear - no security events detected</p>
          </div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = sorted.map(a => {
    const severity = getSeverity(a.confidence);
    const isActive = a.status === "active";
    const rowOpacity = isActive ? "" : "opacity-60";

    return `
      <tr class="hover:bg-surface-container-highest transition-colors group ${rowOpacity}">
        <td class="p-md text-center">
          <span class="w-2 h-2 rounded-full ${severity.dotClass} inline-block ${isActive ? 'animate-pulse' : ''}"></span>
        </td>
        <td class="p-md font-data-sm text-data-sm text-on-surface-variant">${timeAgo(a.timestamp)}</td>
        <td class="p-md">
          <div class="font-body-md text-on-surface font-semibold">${esc(a.alert_type)}</div>
          <div class="text-on-surface-variant text-[11px] mt-xs">Zone: ${esc(a.zone)}</div>
        </td>
        <td class="p-md">
          <div class="flex items-center space-x-sm">
            <span class="material-symbols-outlined text-sm text-primary">developer_board</span>
            <span class="font-data-md text-data-md text-primary">${esc(a.device_name)}</span>
          </div>
        </td>
        <td class="p-md">
          <div class="flex items-center space-x-sm">
            <div class="w-16 h-1.5 bg-surface-container-high rounded-full overflow-hidden">
              <div class="h-full ${severity.barClass}" style="width: ${(a.confidence * 100).toFixed(0)}%"></div>
            </div>
            <span class="font-data-sm text-data-sm ${severity.textClass}">${(a.confidence * 100).toFixed(0)}</span>
          </div>
        </td>
        <td class="p-md">
          <span class="${isActive ? 'bg-error/10 text-error border border-error/20' : 'bg-surface-container-highest text-on-surface-variant border border-outline-variant'} px-2 py-0.5 rounded font-label-caps text-[10px]">
            ${isActive ? 'ACTIVE' : 'RESOLVED'}
          </span>
        </td>
        <td class="p-md font-data-md text-data-md">
          ${isActive ? `
            <span class="failsafe-countdown text-error font-bold" data-created="${a.created_at}" data-timeout="${a.failsafe_timeout || 120}">--</span>
          ` : `
            <span class="text-on-surface-variant">--</span>
          `}
        </td>
        <td class="p-md text-right space-x-sm">
          ${isActive ? `
            <button class="text-tertiary hover:bg-tertiary/10 p-xs rounded transition-colors" title="Quarantine"
                    onclick="quarantineFromAlert('${a.device_id}', '${esc(a.alert_type)}')">
              <span class="material-symbols-outlined text-sm">security</span>
            </button>
            <button class="text-primary hover:bg-primary/10 p-xs rounded transition-colors" title="Resolve"
                    onclick="resolveAlert('${a.id}')">
              <span class="material-symbols-outlined text-sm">check_circle</span>
            </button>
            <button class="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high p-xs rounded transition-colors" title="Generate Report"
                    onclick="generateReport('${a.id}')">
              <span class="material-symbols-outlined text-sm">description</span>
            </button>
          ` : `
            <button class="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high p-xs rounded transition-colors" title="View Details">
              <span class="material-symbols-outlined text-sm">visibility</span>
            </button>
          `}
        </td>
      </tr>
    `;
  }).join("");
}

function getSeverity(confidence) {
  if (confidence > 0.9) return { dotClass: "bg-error", barClass: "bg-error", textClass: "text-error", label: "CRITICAL" };
  if (confidence > 0.75) return { dotClass: "bg-tertiary", barClass: "bg-tertiary", textClass: "text-tertiary", label: "HIGH" };
  if (confidence > 0.5) return { dotClass: "bg-secondary", barClass: "bg-secondary", textClass: "text-secondary", label: "MEDIUM" };
  return { dotClass: "bg-on-surface-variant", barClass: "bg-on-surface-variant", textClass: "text-on-surface-variant", label: "LOW" };
}

// ---- actions ----

async function resolveAlert(alertId) {
  try {
    await API.alerts.resolve(alertId);
    showToast("Alert resolved", "success");
    await loadAlerts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function quarantineFromAlert(deviceId, reason) {
  try {
    await API.quarantine.request(deviceId, reason || "Flagged from alerts page");
    showToast("Quarantine request created - pending approval", "success");
    await loadAlerts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function generateReport(alertId) {
  try {
    showToast("Generating report...", "info");
    await API.reports.generate(alertId);
    showToast("Report generated - view in Reports", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- utilities ----

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
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
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
