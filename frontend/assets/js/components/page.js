/* page.js — common start-up for every logged-in page. */
import { requireLogin } from '../services/session.js';
import { mountShell } from './shell.js';
import { esc, toast } from '../core/dom.js';
import { icon } from '../core/icons.js';

const FLASH_KEY = 'planora.flash';
/** Queue a message to show as a toast on the next page that loads. */
export function flash(msg) { try { sessionStorage.setItem(FLASH_KEY, msg); } catch { /* ignore */ } }
function showFlash() { try { const m = sessionStorage.getItem(FLASH_KEY); if (m) { sessionStorage.removeItem(FLASH_KEY); toast(m); } } catch { /* ignore */ } }

/**
 * startPage('home', render) → checks login, draws the shell (navigation, bell, profile), then calls render().
 * Any error from render is shown in the main area instead of failing silently.
 */
export async function startPage(key, render) {
  if (!requireLogin()) return;
  document.body.dataset.page = key;
  const main = document.getElementById('main');
  main.setAttribute('aria-busy', 'true');
  try {
    await mountShell(key);
    await render(main);
    showFlash();
  } catch (err) {
    console.error(err);
    if (err.status === 401) return; // session expired: http.js is already sending the user to the login page
    main.innerHTML = errorCard(err);
    main.querySelector('#retry').addEventListener('click', () => location.reload());
  } finally {
    main.removeAttribute('aria-busy');
  }
}

/** Calm "couldn't load" card with a Retry button, used when a page fails to load. */
function errorCard(err) {
  const offline = err.status === 0; // fetch itself failed (see http.js)
  const title = offline ? 'Planora can’t reach the server' : 'This page couldn’t load';
  const hint = offline
    ? 'Check your connection, or that the backend is running, then try again. Nothing you saved is lost.'
    : 'Something unexpected went wrong. Try again in a moment.';
  return `<div class="wrap narrow"><div class="result warn"><span class="ic">${icon('alert', 18)}</span>
    <div><b>${title}</b><p class="small">${hint}</p>
      ${offline ? '' : `<p class="small muted">${esc(err.message)}</p>`}</div>
    <button class="btn" type="button" id="retry">${icon('refresh', 14)} Retry</button></div></div>`;
}

/** Shown when the user has no active goal yet. */
export const noGoal = () => `<div class="wrap narrow"><div class="card"><div class="empty">
  <p>You don’t have a goal yet.</p><a class="btn primary" href="new-goal.html">Create your first goal</a></div></div></div>`;
