/**
 * config.js — where the backend is, and whether to use it.
 *
 * MOCK decides where data comes from:
 *   'auto'  (default) sample data only on GitHub Pages (*.github.io), the frontend-only demo,
 *           with a "Demo mode" banner. Everywhere else the real FastAPI backend is used.
 *   true    always use sample data (handy for working on the design without the backend).
 *   false   always use the backend.
 *
 * Where the backend is: FastAPI serves the site itself (http://localhost:8000/app/ locally,
 * or the Vercel deployment), so the API is on the same address. The one exception is
 * VS Code Live Server on this computer (another port), which points at localhost:8000.
 */
const MOCK = 'auto';

const LOCAL_HOSTS = ['localhost', '127.0.0.1', '[::1]'];
const onGitHubPages = location.hostname.endsWith('.github.io');
const LIVE_SERVER_PORTS = ['5500', '5501'];   // VS Code Live Server serves the files without the API
const onLiveServer = LOCAL_HOSTS.includes(location.hostname) && LIVE_SERVER_PORTS.includes(location.port);

export const CONFIG = Object.freeze({
  APP_NAME: 'Planora',
  API_BASE_URL: onLiveServer ? 'http://localhost:8000' : location.origin,
  USE_MOCK: MOCK === 'auto' ? onGitHubPages : MOCK,
  NOTIFICATION_POLL_SECONDS: 60,
});
