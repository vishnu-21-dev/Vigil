/**
 * IoT Anomaly Detection - Frontend API Client
 * 
 * Wraps all FastAPI backend endpoints into clean async functions.
 * Import this file in every HTML page before page-specific scripts.
 * 
 * Usage:
 *   const devices = await API.devices.list();
 *   const alert  = await API.alerts.get("some-id");
 */

const API_BASE = window.location.port === "8000"
  ? ""                             // Served from FastAPI
  : "http://localhost:8000";       // Separate dev server

const API = (() => {
  // ---- helpers ----

  async function request(method, path, body = null) {
    const opts = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body !== null) opts.body = JSON.stringify(body);

    const res = await fetch(`${API_BASE}${path}`, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  const get    = (path) => request("GET", path);
  const post   = (path, body) => request("POST", path, body);
  const put    = (path, body) => request("PUT", path, body);
  const del_   = (path) => request("DELETE", path);

  // ---- health ----

  const health = {
    check: () => get("/health"),
  };

  // ---- devices ----

  const devices = {
    /** @param {string} [status] - "normal"|"anomaly"|"quarantined" */
    list: (status) => {
      const q = status ? `?status=${status}` : "";
      return get(`/devices/${q}`);
    },
    get: (id) => get(`/devices/${id}`),
    create: (data) => post("/devices/", data),
    delete: (id) => del_(`/devices/${id}`),
    importCSV: async (file) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/devices/import`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error((await res.json()).detail);
      return res.json();
    },
  };

  // ---- monitor ----

  const monitor = {
    status: () => get("/monitor/"),
    ingest: (deviceId, features) =>
      post("/monitor/ingest", { device_id: deviceId, features }),
  };

  // ---- demo ----

  const demo = {
    triggerAnomaly: () => post("/demo/trigger-anomaly"),
  };

  // ---- alerts ----

  const alerts = {
    /** @param {string} [status] - "active"|"resolved" */
    list: (status) => {
      const q = status ? `?status=${status}` : "";
      return get(`/alerts/${q}`);
    },
    get: (id) => get(`/alerts/${id}`),
    resolve: (id) => post(`/alerts/${id}/resolve`),
  };

  // ---- quarantine ----

  const quarantine = {
    /** @param {string} [status] - "pending"|"approved"|"dismissed"|"released"|"ai_contained" */
    list: (status) => {
      const q = status ? `?status=${status}` : "";
      return get(`/quarantine/${q}`);
    },
    get: (id) => get(`/quarantine/${id}`),
    request: (deviceId, reason) =>
      post("/quarantine/request", { device_id: deviceId, reason }),
    approve: (id, approvedBy, notes = null) =>
      post(`/quarantine/${id}/approve`, { approved_by: approvedBy, notes }),
    dismiss: (id) => post(`/quarantine/${id}/dismiss`),
    release: (id) => post(`/quarantine/${id}/release`),
  };

  // ---- reports ----

  const reports = {
    list: () => get("/reports/"),
    get: (id) => get(`/reports/${id}`),
    generate: (alertId, additionalContext = null) =>
      post("/reports/generate", {
        alert_id: alertId,
        additional_context: additionalContext,
      }),
  };

  // ---- zones ----

  const zones = {
    list: () => get("/zones/"),
    get: (id) => get(`/zones/${id}`),
    create: (data) => post("/zones/", data),
    update: (id, data) => put(`/zones/${id}`, data),
    delete: (id) => del_(`/zones/${id}`),
    lookupIP: (ip) => get(`/zones/lookup/${ip}`),
  };

  // ---- public API ----

  return { health, devices, monitor, alerts, quarantine, reports, zones, demo };
})();
