// Phase 15 — centralized API service for the React frontend.
//
// The frontend talks to the REAL Python backend over HTTP/REST. The backend
// server (`python -m app.dashboard --port 8877`) exposes a read-only JSON API:
//
//   GET /api/health     -> backend status (no secrets)
//   GET /api/dashboard  -> full DashboardData (sections A-I), the SAME
//                          contract as the compiled `dashboard_data.json` file
//
// The backend base URL comes from the environment variable VITE_API_BASE_URL
// (see frontend/.env). It defaults to http://127.0.0.1:8877 so the built site
// works against the documented backend invocation.
//
// No secrets are ever placed here: the image is a read-only consumer of real
// backend data and the health payload deliberately excludes API keys.

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8877';

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL
).replace(/\/+$/, '');

export async function apiGet(path) {
  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: 'application/json' },
    });
  } catch (err) {
    throw new Error(`Cannot reach ${API_BASE_URL}${path} (${err.message})`);
  }
  if (!res.ok) {
    throw new Error(`${path} failed with HTTP ${res.status} (${res.statusText || 'error'})`);
  }
  return res.json();
}

export async function fetchDashboard() {
  return apiGet('/api/dashboard');
}

export async function fetchHealth() {
  return apiGet('/api/health');
}