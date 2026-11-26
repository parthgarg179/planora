/**
 * notifications.js — the bell and its panel.
 * Checks the backend every CONFIG.NOTIFICATION_POLL_SECONDS (and when the tab becomes
 * visible again), so reminders appear while the site is open. Polling pauses while the
 * tab is hidden.
 */
import { api } from '../services/api.js';
import { CONFIG } from '../config.js';
import { icon } from '../core/icons.js';
import { esc } from '../core/dom.js';
import { timeAgo } from '../core/dates.js';
import { openPopover, closePopover, isPopoverOpen, repositionPopover } from './popover.js';

const KIND_ICON = { review_reminder: 'review', missed_review: 'clock', schedule_changed: 'refresh', deadline_risk: 'alert' };

let bell, panel = null, data = { unread: 0, items: [] };

export function mountNotifications(button) {
  bell = button;
  bell.addEventListener('click', () => (isPopoverOpen(panel) ? closePopover() : open()));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(() => { if (!document.hidden) refresh(); }, CONFIG.NOTIFICATION_POLL_SECONDS * 1000);
  refresh();
}

async function refresh() {
  let fresh;
  try { fresh = await api.getNotifications(); } catch { return; } // stay quiet if the server is briefly unreachable
  if (JSON.stringify(fresh) === JSON.stringify(data)) return;     // nothing new: leave the panel alone
  data = fresh;
  bell.querySelector('.dot').hidden = !data.unread;
  bell.setAttribute('aria-label', data.unread ? `Notifications, ${data.unread} unread` : 'Notifications');
  if (isPopoverOpen(panel)) render();
}

function open() {
  panel = document.createElement('section');
  panel.className = 'npanel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-labelledby', 'npanel-title');
  render();
  openPopover(bell, panel);
  refresh();
}

function render() {
  // Re-rendering replaces the buttons, so remember which one had focus and put it back.
  const had = panel.contains(document.activeElement) ? document.activeElement : null;
  const focusSel = had?.dataset.id ? `[data-id="${had.dataset.id}"]` : had?.hasAttribute('data-read-all') ? '[data-read-all]' : null;
  panel.innerHTML = `
    <div class="nhead"><h2 id="npanel-title">Notifications</h2>${data.unread ? '<button class="link" type="button" data-read-all>Mark all as read</button>' : ''}</div>
    ${data.items.length ? `<ul class="nlist">${data.items.map(n => `<li>
      <button class="nitem${n.read ? '' : ' unread'}" type="button" data-id="${n.id}" data-link="${esc(n.link)}">
        <span class="nic k-${esc(n.kind)}">${icon(KIND_ICON[n.kind] || 'bell', 16)}</span>
        <span class="ntext"><b>${esc(n.title)}</b>${n.body ? `<span>${esc(n.body)}</span>` : ''}<small>${timeAgo(n.created_at)}${n.read ? '' : '<span class="sr-only"> · unread</span>'}</small></span>
      </button></li>`).join('')}</ul>`
    : '<p class="empty">You’re all caught up.</p>'}`;

  panel.querySelector('[data-read-all]')?.addEventListener('click', async () => {
    await api.markAllNotificationsRead();
    data.items.forEach(n => { n.read = true; });
    data.unread = 0;
    bell.querySelector('.dot').hidden = true;
    bell.setAttribute('aria-label', 'Notifications');
    render();
    panel.querySelector('.nitem')?.focus();
  });
  panel.querySelectorAll('.nitem').forEach(el => el.addEventListener('click', async () => {
    try { await api.markNotificationRead(+el.dataset.id); } catch { /* still navigate */ }
    location.href = el.dataset.link; // links are page names inside pages/, e.g. "review.html"
  }));
  if (focusSel) (panel.querySelector(focusSel) || panel.querySelector('.nitem'))?.focus({ preventScroll: true });
  repositionPopover();
}
