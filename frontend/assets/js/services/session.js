/* session.js — stores the login token and guards pages.
   The token is kept in sessionStorage, so it lasts for this tab only: opening the site in a new
   tab or window always starts at the login screen (Parth's choice, for demoing the login flow). */
const TOKEN_KEY = 'planora.token';

export const getToken = () => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const setToken = t => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* storage unavailable */ } };
export const clearToken = () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ } };
export const isLoggedIn = () => !!getToken();

/** Call at the top of every app page. Sends logged-out users to the login screen. */
export function requireLogin() {
  if (!isLoggedIn()) { location.replace('../index.html'); return false; }
  return true;
}
