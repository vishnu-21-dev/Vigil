/**
 * Devices page logic - fetches device data from the API
 * and populates the Stitch-designed HTML.
 */

async function init() {
  try {
    setupFilters();
    await loadDevices();
    startPolling();
  } catch (err) {
    console.error("Devices load failed:", err);
    showToast("Failed to load devices data", "error");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

let pollInterval;
let allDevices = [];

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(loadDevices, 5000);
}

function setupFilters() {
  const filterInput = document.getElementById("filter-input");
  const statusFilter = document.getElementById("status-filter");
  
  if (filterInput) {
    filterInput.addEventListener("input", renderDevicesTable);
  }
  if (statusFilter) {
    statusFilter.addEventListener("change", renderDevicesTable);
  }
}

async function loadDevices() {
  allDevices = await API.devices.list();
  
  // Notification dot checking via alerts
  const alerts = await API.alerts.list();
  const activeAlerts = alerts.filter(a => a.status === "active");
  const dot = document.getElementById("notification-dot");
  if (dot) {
    dot.classList.toggle("hidden", activeAlerts.length === 0);
  }

  renderDevicesTable();
}

function renderDevicesTable() {
  const tbody = document.getElementById("devices-tbody");
  if (!tbody) return;

  const filterText = (document.getElementById("filter-input")?.value || "").toLowerCase();
  const statusFilter = (document.getElementById("status-filter")?.value || "all").toLowerCase();

  let filtered = allDevices;

  // Apply filters
  if (filterText) {
    filtered = filtered.filter(d => 
      d.name.toLowerCase().includes(filterText) || 
      d.ip_address.toLowerCase().includes(filterText) ||
      (d.zone && d.zone.toLowerCase().includes(filterText))
    );
  }
  if (statusFilter !== "all") {
    filtered = filtered.filter(d => d.status.toLowerCase() === statusFilter);
  }

  // Update summary
  const summary = document.getElementById("devices-summary");
  if (summary) {
    summary.textContent = `${filtered.length} devices`;
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="p-lg text-center text-on-surface-variant font-body-sm text-body-sm">
          No devices found matching your filters.
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(d => {
    let statusClass = "";
    let statusLabel = "";
    let iconClass = "text-on-surface-variant";
    let iconName = "router";
    let scoreClass = "";

    switch (d.status) {
      case "normal":
        statusClass = "bg-surface-container border border-outline-variant text-primary";
        statusLabel = "Normal";
        scoreClass = "";
        break;
      case "anomaly":
        statusClass = "bg-error-container/20 border border-error/50 text-error";
        statusLabel = "Anomaly";
        iconClass = "text-error";
        iconName = "sensors";
        scoreClass = "text-error font-bold";
        break;
      case "quarantined":
        statusClass = "bg-tertiary-container/20 border border-tertiary/50 text-tertiary";
        statusLabel = "Quarantined";
        iconClass = "text-tertiary";
        iconName = "dns";
        scoreClass = "text-tertiary font-bold";
        break;
      default:
        statusClass = "bg-surface-container border border-outline-variant text-on-surface";
        statusLabel = d.status;
        scoreClass = "";
        break;
    }

    const isAnomaly = d.status === "anomaly";
    const rowClass = isAnomaly ? "bg-error-container/10" : "hover:bg-surface-container-highest transition-colors";
    
    return `
      <tr class="${rowClass}">
        <td class="py-sm px-md flex items-center gap-sm">
          <span class="material-symbols-outlined ${iconClass} text-lg">${iconName}</span>
          ${esc(d.name)}
        </td>
        <td class="py-sm px-md">${esc(d.ip_address)}</td>
        <td class="py-sm px-md text-on-surface-variant">${esc(d.zone)}</td>
        <td class="py-sm px-md">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full ${statusClass} text-[10px] uppercase font-bold">
            ${statusLabel}
          </span>
        </td>
        <td class="py-sm px-md text-on-surface-variant">${timeAgo(d.last_seen)}</td>
        <td class="py-sm px-md text-right ${scoreClass}">${(d.anomaly_score * 100).toFixed(0)}%</td>
        <td class="py-sm px-md text-right">
          <button class="px-sm py-1 bg-transparent border border-outline-variant text-on-surface font-label-caps text-[10px] uppercase rounded hover:border-error hover:text-error transition-colors disabled:opacity-50 disabled:pointer-events-none"
                  onclick="requestQuarantine('${d.id}')"
                  ${d.status === 'quarantined' ? 'disabled' : ''}>
            Quarantine
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

async function requestQuarantine(deviceId) {
  try {
    await API.quarantine.request(deviceId, "Manual quarantine request from Devices page");
    showToast("Quarantine requested for device", "success");
    await loadDevices(); // Reload immediately
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- utilities ----

function esc(str) {
  if (str == null) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function timeAgo(isoStr) {
  if (!isoStr) return "Never";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} mins ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  return `${Math.floor(hrs / 24)} days ago`;
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
