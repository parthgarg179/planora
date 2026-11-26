/* Small DOM helpers shared by every page: escaping, selectors, dialogs, toasts. */

/** Escape text before putting it inside HTML strings. Use for anything a user (or the AI) wrote. */
export const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
/** Elements inside `root` that can receive keyboard focus, in tab order. */
export const focusables = root => $$(FOCUSABLE, root).filter(el => el.offsetParent !== null || el === document.activeElement);

/**
 * Replace `root`'s content and keep keyboard focus on the "same" control afterwards.
 * Pages re-render after every click; without this, a keyboard user would lose their place.
 * The control is found again by its id, or by its data-, name and value attributes.
 */
export function renderInto(root, html) {
  const key = focusKey(document.activeElement, root);
  root.innerHTML = html;
  if (key) root.querySelector(key)?.focus({ preventScroll: true });
}
function focusKey(el, root) {
  if (!el || el === root || !root.contains(el)) return null;
  if (el.id) return `#${CSS.escape(el.id)}`;
  const attrs = [...el.attributes].filter(a => a.name.startsWith('data-') || a.name === 'name' || (a.name === 'value' && el.type === 'radio'));
  return attrs.length ? el.tagName.toLowerCase() + attrs.map(a => `[${a.name}="${CSS.escape(a.value)}"]`).join('') : null;
}

/**
 * Click delegation: elements with data-action="name" call handlers[name](el, event).
 * Returns a function that removes the listener.
 */
export function onAction(root, handlers) {
  const fn = e => {
    const el = e.target.closest('[data-action]');
    if (!el || !root.contains(el)) return;
    handlers[el.dataset.action]?.(el, e);
  };
  root.addEventListener('click', fn);
  return () => root.removeEventListener('click', fn);
}

/* ---------- dialogs (drawer / modal) ----------
   openOverlay(html) shows `html` (a .scrim containing an element with role="dialog") and makes it
   behave like a real dialog: the page behind becomes inert, focus moves inside and can't leave with
   Tab, Escape or a click on the backdrop closes it, and focus returns to where it was. */
let current = null; // { scrim, returnTo }

const layer = () => document.getElementById('overlay')
  || document.body.appendChild(Object.assign(document.createElement('div'), { id: 'overlay' }));
const background = () => $$('body > :not(#overlay):not(.toast-region):not(script)');

export function openOverlay(html) {
  if (current) closeOverlay({ restoreFocus: false });
  const returnTo = document.activeElement;
  const root = layer();
  root.innerHTML = html;
  const scrim = root.firstElementChild;
  const dialog = $('[role="dialog"]', scrim) || scrim;
  dialog.setAttribute('aria-modal', 'true');
  if (!dialog.hasAttribute('tabindex')) dialog.tabIndex = -1;

  background().forEach(el => { el.inert = true; });
  document.documentElement.classList.add('no-scroll');
  current = { scrim, returnTo };

  scrim.addEventListener('click', e => { if (e.target === scrim || e.target.closest('[data-close]')) closeOverlay(); });
  scrim.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.stopPropagation(); closeOverlay(); }
    if (e.key === 'Tab') trapTab(e, dialog);
  });
  // Focus the dialog itself (not its first field, which would pop up a phone keyboard);
  // screen readers announce its label and Tab moves into it.
  dialog.focus();
  return scrim;
}

export function closeOverlay({ restoreFocus = true } = {}) {
  if (!current) return;
  const { returnTo } = current;
  current = null;
  layer().innerHTML = '';
  background().forEach(el => { el.inert = false; });
  document.documentElement.classList.remove('no-scroll');
  if (restoreFocus && returnTo?.isConnected) returnTo.focus();
}

/** Keep Tab / Shift+Tab inside `box`. */
export function trapTab(e, box) {
  const items = focusables(box);
  if (!items.length) { e.preventDefault(); return; }
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && (document.activeElement === first || !box.contains(document.activeElement))) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

/* ---------- toast ----------
   Messages go into one polite live region, so screen readers read them out. */
let toastTimer;
function region() {
  let box = $('.toast-region');
  if (!box) {
    box = document.createElement('div');
    box.className = 'toast-region';
    box.setAttribute('role', 'status');
    box.setAttribute('aria-live', 'polite');
    document.body.appendChild(box);
  }
  return box;
}

export function toast(message, actionLabel, action) {
  clearTimeout(toastTimer);
  const box = region();
  box.innerHTML = `<div class="toast">${esc(message)}${actionLabel ? ` <button type="button">${esc(actionLabel)}</button>` : ''}</div>`;
  if (action) $('button', box).addEventListener('click', () => { box.innerHTML = ''; action(); });
  toastTimer = setTimeout(() => { box.innerHTML = ''; }, 5200);
}
