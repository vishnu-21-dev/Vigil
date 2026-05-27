/**
 * Reports page logic - fetches report data from the API
 * and populates the Stitch-designed HTML.
 */

async function init() {
  try {
    await loadReports();
    startPolling();
  } catch (err) {
    console.error("Reports load failed:", err);
    showToast("Failed to load reports", "error");
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
  pollInterval = setInterval(loadReports, 10000);
}

// ---- main loader ----

async function loadReports() {
  const [reports, alerts] = await Promise.all([
    API.reports.list(),
    API.alerts.list(),
  ]);

  // Notification dot
  const activeAlerts = alerts.filter(a => a.status === "active");
  const dot = document.getElementById("notification-dot");
  if (dot) {
    dot.classList.toggle("hidden", activeAlerts.length === 0);
  }

  renderStats(reports);
  renderReportsList(reports);
  renderGenerateSection(alerts);
}

// ---- stats ----

function renderStats(reports) {
  setText("stat-total-reports", reports.length);
  
  const severityCounts = { critical: 0, high: 0, medium: 0, low: 0 };
  reports.forEach(r => {
    const sev = (r.severity || "low").toLowerCase();
    if (severityCounts[sev] !== undefined) severityCounts[sev]++;
  });
  
  setText("stat-critical-reports", severityCounts.critical);
  setText("stat-high-reports", severityCounts.high);
  setText("stat-other-reports", severityCounts.medium + severityCounts.low);
}

// ---- reports list ----

function renderReportsList(reports) {
  const container = document.getElementById("reports-list");
  if (!container) return;

  if (reports.length === 0) {
    container.innerHTML = `
      <div class="bg-surface-container border border-outline-variant p-xl text-center">
        <span class="material-symbols-outlined text-primary mb-sm" style="font-size: 48px;">description</span>
        <p class="font-body-md text-body-md text-on-surface">No reports generated yet</p>
        <p class="font-body-sm text-body-sm text-on-surface-variant mt-xs">Generate a report from an active alert below</p>
      </div>`;
    return;
  }

  container.innerHTML = reports.map(r => {
    const severityConfig = getSeverityConfig(r.severity);
    return `
      <div class="bg-surface-container border border-outline-variant hover:border-outline transition-colors cursor-pointer" onclick="toggleReport('${r.id}')">
        <div class="p-md flex justify-between items-start">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-sm mb-xs">
              <span class="${severityConfig.badgeClass} font-label-caps text-label-caps px-2 py-0.5 rounded text-[10px]">${(r.severity || 'low').toUpperCase()}</span>
              <span class="font-data-sm text-data-sm text-on-surface-variant">${timeAgo(r.created_at)}</span>
            </div>
            <h3 class="font-data-md text-data-md text-on-surface truncate">${esc(r.title)}</h3>
            <p class="font-body-sm text-body-sm text-on-surface-variant mt-xs truncate">${esc(r.summary)}</p>
            <div class="flex items-center gap-md mt-sm">
              <span class="font-body-sm text-body-sm text-on-surface-variant">
                <span class="material-symbols-outlined text-sm align-middle mr-xs">developer_board</span>${esc(r.device_name)}
              </span>
              <span class="font-body-sm text-body-sm text-on-surface-variant">
                <span class="material-symbols-outlined text-sm align-middle mr-xs">location_on</span>${esc(r.zone)}
              </span>
            </div>
          </div>
          <span class="material-symbols-outlined text-on-surface-variant ml-sm transition-transform" id="chevron-${r.id}">expand_more</span>
        </div>
        <div id="detail-${r.id}" class="hidden border-t border-outline-variant p-md bg-surface-container-low">
          <pre class="font-data-sm text-data-sm text-on-surface whitespace-pre-wrap break-words leading-relaxed">${esc(r.full_report)}</pre>
          <div class="mt-md flex items-center gap-sm">
            <span class="font-label-caps text-label-caps text-on-surface-variant">AFFECTED:</span>
            ${(r.affected_devices || []).map(d => `<span class="bg-surface-container-highest border border-outline-variant px-2 py-0.5 rounded font-data-sm text-data-sm text-on-surface">${esc(d)}</span>`).join("")}
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function toggleReport(reportId) {
  const detail = document.getElementById(`detail-${reportId}`);
  const chevron = document.getElementById(`chevron-${reportId}`);
  if (!detail) return;
  
  const isHidden = detail.classList.contains("hidden");
  detail.classList.toggle("hidden");
  if (chevron) {
    chevron.style.transform = isHidden ? "rotate(180deg)" : "";
  }
}

// ---- generate section ----

function renderGenerateSection(alerts) {
  const container = document.getElementById("generate-section");
  if (!container) return;

  const activeAlerts = alerts.filter(a => a.status === "active");

  if (activeAlerts.length === 0) {
    container.innerHTML = `
      <p class="font-body-sm text-body-sm text-on-surface-variant text-center py-md">No active alerts to generate reports from.</p>
    `;
    return;
  }

  container.innerHTML = activeAlerts.map(a => `
    <div class="flex items-center justify-between py-sm px-md hover:bg-surface-container-highest transition-colors rounded">
      <div class="flex items-center gap-sm">
        <span class="w-2 h-2 rounded-full bg-error animate-pulse"></span>
        <span class="font-data-sm text-data-sm text-on-surface">${esc(a.device_name)}</span>
        <span class="font-body-sm text-body-sm text-on-surface-variant">- ${esc(a.alert_type)}</span>
        <span class="font-data-sm text-data-sm text-on-surface-variant">${(a.confidence * 100).toFixed(0)}%</span>
      </div>
      <button class="bg-primary-container/30 hover:bg-primary-container border border-primary text-primary font-label-caps text-label-caps px-md py-xs uppercase tracking-wider transition-colors text-[10px]"
              onclick="handleGenerateReport('${a.id}')">
        Generate
      </button>
    </div>
  `).join("");
}

async function handleGenerateReport(alertId) {
  try {
    showToast("Generating incident report...", "info");
    await API.reports.generate(alertId);
    showToast("Report generated successfully", "success");
    await loadReports();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ---- utilities ----

function getSeverityConfig(severity) {
  switch ((severity || "low").toLowerCase()) {
    case "critical": return { badgeClass: "bg-error/20 text-error border border-error/30" };
    case "high": return { badgeClass: "bg-tertiary/20 text-tertiary border border-tertiary/30" };
    case "medium": return { badgeClass: "bg-secondary/20 text-secondary border border-secondary/30" };
    default: return { badgeClass: "bg-surface-container-highest text-on-surface-variant border border-outline-variant" };
  }
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
