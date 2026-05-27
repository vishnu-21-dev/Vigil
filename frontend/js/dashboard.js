/**
 * Dashboard page logic - fetches live data from the API
 * and populates the Stitch-designed HTML.
 */

async function init() {
  try {
    await loadDashboard();
    startPolling();
  } catch (err) {
    console.error("Dashboard load failed:", err);
    showToast("Failed to load dashboard data", "error");
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
  pollInterval = setInterval(loadDashboard, 5000);
}

// ---- main loader ----

async function loadDashboard() {
  const [devices, alerts, quarantine, zones] = await Promise.all([
    API.devices.list(),
    API.alerts.list(),
    API.quarantine.list(),
    API.zones.list(),
  ]);

  renderStats(devices, alerts, quarantine);
  renderNetworkTopology(devices);
  renderAlertFeed(alerts, devices);
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
    
    let createdTimeStr = createdStr;
    if (!createdTimeStr.endsWith('Z') && !createdTimeStr.includes('+')) {
      createdTimeStr += 'Z';
    }
    const createdTime = new Date(createdTimeStr).getTime();
    const elapsed = Math.floor((Date.now() - createdTime) / 1000);
    const remaining = Math.max(0, timeout - elapsed);
    
    if (remaining > 0) {
      el.innerHTML = `Timer: ${remaining}s remaining`;
      el.className = 'failsafe-countdown text-on-surface bg-error/20 border border-error/30 px-2 py-0.5 rounded font-data-sm text-[10px] animate-pulse';
    } else {
      el.innerHTML = 'FAILSAFE TRIGGERED';
      el.className = 'failsafe-countdown text-on-error-container bg-error-container px-2 py-0.5 rounded font-label-caps text-[10px]';
    }
  });
}

// ---- stats cards ----

function renderStats(devices, alerts, quarantine) {
  const totalDevices = devices.length;
  const anomalyCount = devices.filter(d => d.status === "anomaly").length;
  const quarantineCount = devices.filter(d => d.status === "quarantined").length;
  const normalCount = devices.filter(d => d.status === "normal").length;
  const healthPct = totalDevices > 0
    ? ((normalCount / totalDevices) * 100).toFixed(1)
    : "0.0";

  const activeAlerts = alerts.filter(a => a.status === "active").length;

  setText("stat-total-devices", totalDevices.toLocaleString());
  setText("stat-anomalies", anomalyCount);
  setText("stat-quarantined", quarantineCount);
  setText("stat-health", healthPct + "%");

  // Show notification dot if there are active alerts
  const dot = document.getElementById("notification-dot");
  if (dot) {
    dot.classList.toggle("hidden", activeAlerts === 0);
  }
}

// ---- network topology ----

function renderNetworkTopology(devices) {
  const container = document.getElementById("network-topology");
  if (!container) return;

  // Clear existing dynamic content (keep the grid background)
  const existingNodes = container.querySelectorAll(".topo-node, .topo-line");
  existingNodes.forEach(el => el.remove());

  if (devices.length === 0) {
    container.innerHTML += `
      <div class="absolute inset-0 flex items-center justify-center">
        <p class="font-body-sm text-body-sm text-on-surface-variant">No devices detected</p>
      </div>`;
    return;
  }

  // Predefined positions for a nice network layout
  const positions = [
    { top: "18%", left: "22%" },
    { top: "35%", left: "48%" },
    { top: "25%", left: "72%" },
    { top: "58%", left: "35%" },
    { top: "68%", left: "18%" },
    { top: "12%", left: "55%" },
    { top: "50%", left: "70%" },
    { top: "78%", left: "55%" },
    { top: "42%", left: "15%" },
    { top: "65%", left: "82%" },
    { top: "30%", left: "35%" },
    { top: "80%", left: "30%" },
  ];

  // Draw connection lines between nearby nodes
  const usedPositions = [];
  devices.forEach((d, i) => {
    const pos = positions[i % positions.length];
    usedPositions.push({ ...pos, index: i });
  });

  // Simple connections: connect each node to the next
  for (let i = 0; i < usedPositions.length - 1; i++) {
    const from = usedPositions[i];
    const to = usedPositions[i + 1];
    const line = document.createElement("div");
    line.className = "topo-line absolute bg-outline-variant/30";

    const x1 = parseFloat(from.left);
    const y1 = parseFloat(from.top);
    const x2 = parseFloat(to.left);
    const y2 = parseFloat(to.top);

    const length = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    const angle = Math.atan2(y2 - y1, x2 - x1) * (180 / Math.PI);

    line.style.cssText = `
      top: ${y1}%;
      left: ${x1}%;
      width: ${length}%;
      height: 1px;
      transform-origin: 0 0;
      transform: rotate(${angle}deg);
    `;
    container.appendChild(line);
  }

  // Draw device nodes
  devices.forEach((device, i) => {
    const pos = positions[i % positions.length];
    const statusConfig = getNodeStyle(device.status);

    const node = document.createElement("div");
    node.className = "topo-node absolute group cursor-pointer z-10";
    node.style.cssText = `top: ${pos.top}; left: ${pos.left}; transform: translate(-50%, -50%);`;

    node.innerHTML = `
      <!-- Pulse ring for anomalies -->
      ${device.status === "anomaly" ? `<div class="absolute inset-0 -m-2 rounded-full bg-error/20 animate-ping"></div>` : ""}
      ${device.status === "quarantined" ? `<div class="absolute inset-0 -m-1 rounded-full border border-tertiary/40"></div>` : ""}

      <!-- Node dot -->
      <div class="${statusConfig.size} rounded-full ${statusConfig.bg} ${device.status === "anomaly" ? "animate-pulse" : ""} ring-2 ${statusConfig.ring}"></div>

      <!-- Tooltip -->
      <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 bg-surface-container-highest border border-outline-variant px-sm py-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20">
        <div class="font-data-sm text-data-sm text-on-surface">${esc(device.name)}</div>
        <div class="font-body-sm text-body-sm text-on-surface-variant">${esc(device.ip_address)}</div>
        <div class="font-body-sm text-body-sm ${statusConfig.textColor}">${device.status} - ${(device.anomaly_score * 100).toFixed(0)}%</div>
      </div>
    `;
    container.appendChild(node);
  });
}

function getNodeStyle(status) {
  switch (status) {
    case "anomaly":
      return {
        size: "w-5 h-5",
        bg: "bg-error",
        ring: "ring-error/30",
        textColor: "text-error",
      };
    case "quarantined":
      return {
        size: "w-4 h-4",
        bg: "bg-tertiary",
        ring: "ring-tertiary/30",
        textColor: "text-tertiary",
      };
    default:
      return {
        size: "w-3 h-3",
        bg: "bg-primary",
        ring: "ring-primary/30",
        textColor: "text-primary",
      };
  }
}

// ---- alert feed ----

function renderAlertFeed(alerts, devices) {
  const feed = document.getElementById("alert-feed");
  if (!feed) return;

  const badge = document.getElementById("alert-count-badge");

  const active = alerts
    .filter(a => a.status === "active")
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, 10);

  // Update badge
  if (badge) {
    if (active.length > 0) {
      badge.textContent = `${active.length} HIGH PRIORITY`;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }

  if (active.length === 0) {
    feed.innerHTML = `
      <div class="p-lg text-center flex flex-col items-center justify-center h-full">
        <span class="material-symbols-outlined text-primary mb-sm" style="font-size: 48px; font-variation-settings: 'FILL' 1;">verified_user</span>
        <p class="font-body-md text-body-md text-on-surface">All Clear</p>
        <p class="font-body-sm text-body-sm text-on-surface-variant mt-xs">No active alerts detected</p>
      </div>`;
    return;
  }

  feed.innerHTML = active.map(a => `
    <div class="p-md hover:bg-surface-container-highest transition-colors group cursor-pointer" onclick="viewAlert('${a.id}')">
      <div class="flex justify-between items-start mb-sm">
        <div class="font-data-md text-data-md text-error flex items-center">
          <span class="material-symbols-outlined text-sm mr-xs" style="font-variation-settings: 'FILL' 1;">warning</span>
          ${esc(a.device_name)}
        </div>
        <div class="font-data-sm text-data-sm text-on-surface-variant">${timeAgo(a.timestamp)}</div>
      </div>
      <div class="flex items-center space-x-sm mb-sm">
        <span class="font-body-sm text-body-sm text-on-surface-variant">Zone: ${esc(a.zone)}</span>
        <span class="font-body-sm text-body-sm text-on-surface-variant">-</span>
        <span class="font-body-sm text-body-sm text-on-surface-variant">${esc(a.alert_type)}</span>
      </div>
      <div class="flex items-center space-x-sm mb-md">
        <span class="font-body-sm text-body-sm text-on-surface-variant">Anomaly Confidence:</span>
        <span class="font-data-sm text-data-sm text-on-surface bg-surface-container border border-outline-variant px-1 rounded mr-md">${(a.confidence * 100).toFixed(0)}%</span>
        <span class="failsafe-countdown" data-created="${a.created_at}" data-timeout="${a.failsafe_timeout || 120}"></span>
      </div>
      <div class="flex justify-end space-x-sm">
        <button class="bg-tertiary-container/30 hover:bg-tertiary-container border border-tertiary text-tertiary font-label-caps text-label-caps px-md py-sm uppercase tracking-wider transition-colors"
                onclick="event.stopPropagation(); quarantineFromAlert('${a.device_id}', '${esc(a.alert_type)}')">
          Quarantine
        </button>
        <button class="bg-primary-container/30 hover:bg-primary-container border border-primary text-primary font-label-caps text-label-caps px-md py-sm uppercase tracking-wider transition-colors"
                onclick="event.stopPropagation(); resolveAlert('${a.id}')">
          Resolve
        </button>
      </div>
    </div>
  `).join("");
}

// ---- actions ----

async function resolveAlert(alertId) {
  try {
    await API.alerts.resolve(alertId);
    showToast("Alert resolved", "success");
    loadDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function triggerDemo() {
  try {
    await API.demo.triggerAnomaly();
    showToast("Demo anomaly injected", "success");
    loadDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function quarantineFromAlert(deviceId, reason) {
  try {
    await API.quarantine.request(deviceId, reason || "Flagged from dashboard alert");
    showToast("Quarantine request created - pending approval", "success");
    loadDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function viewAlert(alertId) {
  window.location.href = `alerts.html?id=${alertId}`;
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
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
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
