/**
 * shell.js — the app chrome shared by every logged-in page:
 *   - main navigation (bottom tab bar on phones, blue sidebar from 768px; same links, CSS decides)
 *   - phone top bar (logo, "New goal" button)
 *   - bell + profile button: in the top bar on phones, at the bottom of the sidebar on bigger screens
 *   - profile menu, and the "Demo mode" banner when running on sample data
 * Usage: const user = await mountShell('home')   (the key of the current page)
 */
import { api } from '../services/api.js';
import { clearToken } from '../services/session.js';
import { icon } from '../core/icons.js';
import { esc } from '../core/dom.js';
import { mountNotifications } from './notifications.js';
import { openPopover, closePopover, isPopoverOpen } from './popover.js';
import { addDemoBanner } from './demoBanner.js';

const NAV = [
  { key: 'home', href: 'home.html', icon: 'home', label: 'Home' },
  { key: 'tasks', href: 'tasks.html', icon: 'list', label: 'Tasks' },
  { key: 'schedule', href: 'schedule.html', icon: 'calendar', label: 'Schedule' },
  { key: 'review', href: 'review.html', icon: 'review', label: 'Review' },
  { key: 'progress', href: 'progress.html', icon: 'chart', label: 'Progress' },
  { key: 'new-goal', href: 'new-goal.html', icon: 'plus', label: 'New goal', desktopOnly: true },
];
const MENU_PAGES = ['profile', 'preferences'];
const PHONE = window.matchMedia('(max-width: 767.98px)');

let user = null;
let menuEl = null;

export const avatarInner = u => u?.photo_url
  ? `<img src="${esc(u.photo_url)}" alt="">`
  : esc((u?.name || '?').trim()[0]?.toUpperCase() || '?');

const current = (key, active) => (key === active ? ' aria-current="page"' : '');

export async function mountShell(active) {
  user = await api.getMe();
  addDemoBanner();

  document.getElementById('topbar').innerHTML = `
    <a class="logo" href="home.html"><i>${icon('target', 16, 2.2)}</i>Planora</a>
    <div class="topbar-actions" id="topbar-actions">
      <a class="iconbtn" href="new-goal.html" aria-label="New goal"${current('new-goal', active)}>${icon('plus', 20)}</a>
    </div>`;

  const side = document.getElementById('sidebar');
  side.innerHTML = `
    <ul class="nav-list">${NAV.map(n => `<li${n.desktopOnly ? ' class="nav-new"' : ''}>
      <a href="${n.href}"${current(n.key, active)}><span class="ic">${icon(n.icon, 18)}</span>${n.label}</a></li>`).join('')}
    </ul>
    <div class="grow"></div>
    <div class="side-tools" id="side-tools">
      <button class="bell" id="bell-btn" type="button" aria-label="Notifications" aria-haspopup="dialog" aria-expanded="false">${icon('bell', 19)}<span class="dot" hidden></span></button>
      <hr>
      <button class="me${MENU_PAGES.includes(active) ? ' on' : ''}" id="profile-btn" type="button" aria-haspopup="menu" aria-expanded="false"></button>
    </div>`;
  refreshAvatar(user);

  // Bell + profile live in the top bar on phones and in the sidebar otherwise.
  const tools = document.getElementById('side-tools');
  const placeTools = () => (PHONE.matches ? document.getElementById('topbar-actions') : side).append(tools);
  placeTools();
  PHONE.addEventListener('change', placeTools);

  const btn = document.getElementById('profile-btn');
  btn.addEventListener('click', () => (isPopoverOpen(menuEl) ? closePopover() : openMenu(btn, active)));
  mountNotifications(document.getElementById('bell-btn'));
  return user;
}

/** Call after the user's name or photo changes so the profile button updates. */
export function refreshAvatar(u) {
  user = u;
  const btn = document.getElementById('profile-btn');
  if (!btn) return;
  btn.innerHTML = avatarInner(u);
  btn.setAttribute('aria-label', `Account menu for ${u.name}`);
}

function openMenu(btn, active) {
  menuEl = document.createElement('div');
  menuEl.className = 'menu';
  menuEl.innerHTML = `
    <div class="who"><div class="av">${avatarInner(user)}</div><div><b>${esc(user.name)}</b><span>${esc(user.email)}</span></div></div>
    <div role="menu" aria-label="Account">
      <a href="profile.html" role="menuitem"${current('profile', active)}>${icon('user', 16)}Personal details</a>
      <a href="preferences.html" role="menuitem"${current('preferences', active)}>${icon('gear', 16)}Preferences</a>
      <hr>
      <button class="out" type="button" role="menuitem" data-logout>${icon('logout', 16)}Log out</button>
    </div>`;
  menuEl.querySelector('[data-logout]').addEventListener('click', logout);
  openPopover(btn, menuEl, { menu: true });
}

async function logout() {
  try { await api.logout(); } catch { /* log out locally anyway */ }
  clearToken();
  location.href = '../index.html';
}
