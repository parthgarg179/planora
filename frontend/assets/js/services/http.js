/* http.js — thin wrapper around fetch() for the FastAPI backend. */
import { CONFIG } from '../config.js';
import { getToken, clearToken } from './session.js';

export class ApiError extends Error {
  constructor(status, message, detail) { super(message); this.status = status; this.detail = detail; }
}

export async function request(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(CONFIG.API_BASE_URL + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, 'Can’t reach the server. Is the backend running?');
  }

  if (res.status === 401) {
    clearToken();
    // Had a token that no longer works → tell the login page why the user landed there.
    if (token) { try { sessionStorage.setItem('planora.expired', '1'); } catch { /* ignore */ } }
    if (!location.pathname.endsWith('/index.html') && !location.pathname.endsWith('/')) location.replace('../index.html');
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    // FastAPI puts error messages in "detail"
    const msg = typeof data?.detail === 'string' ? data.detail : `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, data?.detail);
  }
  return data;
}
