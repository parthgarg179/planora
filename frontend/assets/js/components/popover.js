/**
 * popover.js — a small pop-up anchored to a button (profile menu, notifications panel).
 *
 *   openPopover(button, element, { menu: true, onClose })
 *
 * Phones: drops down below the top bar, right-aligned. Bigger screens: opens to the
 * right of the sidebar button. Closes on Escape (focus goes back to the button), a click
 * outside, or a window resize. With `menu: true`, arrow keys move between menu items.
 */
import { focusables } from '../core/dom.js';

const PHONE = window.matchMedia('(max-width: 767.98px)');
const GAP = 8;
let current = null; // { el, button, menu, onClose }

export const isPopoverOpen = el => current?.el === el;

export function openPopover(button, el, { menu = false, onClose } = {}) {
  closePopover({ restoreFocus: false });
  document.body.appendChild(el);
  place(el, button);
  button.setAttribute('aria-expanded', 'true');
  current = { el, button, menu, onClose };
  // Tabbing out of the pop-up closes it.
  el.addEventListener('focusout', e => {
    if (e.relatedTarget && !el.contains(e.relatedTarget) && e.relatedTarget !== button) closePopover({ restoreFocus: false });
  });
  const first = menu ? el.querySelector('[role="menuitem"]') : focusables(el)[0];
  (first || el).focus({ preventScroll: true });
}

export function closePopover({ restoreFocus = true } = {}) {
  if (!current) return;
  const { el, button, onClose } = current;
  current = null;
  el.remove();
  button.setAttribute('aria-expanded', 'false');
  onClose?.();
  if (restoreFocus) button.focus();
}

/** Re-position after the content changed size (e.g. notifications loaded). */
export function repositionPopover() { if (current) place(current.el, current.button); }

function place(el, button) {
  const r = button.getBoundingClientRect();
  Object.assign(el.style, { left: '', right: '', top: '', maxWidth: `calc(100vw - ${GAP * 2}px)` });
  if (PHONE.matches) {
    el.style.right = `${GAP}px`;
    el.style.top = `${r.bottom + GAP}px`;
    el.style.maxHeight = `calc(100dvh - ${r.bottom + GAP * 2}px - var(--tabbar-h))`;
  } else {
    el.style.left = `${r.right + 12}px`;
    el.style.top = `${Math.max(12, Math.min(r.top, window.innerHeight - el.offsetHeight - 12))}px`;
  }
}

/* One set of listeners for whichever pop-up is open. */
document.addEventListener('pointerdown', e => {
  if (current && !current.el.contains(e.target) && !current.button.contains(e.target)) closePopover({ restoreFocus: false });
});
document.addEventListener('keydown', e => {
  if (!current) return;
  if (e.key === 'Escape') { e.preventDefault(); closePopover(); return; }
  if (current.menu && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
    const items = [...current.el.querySelectorAll('[role="menuitem"]')];
    const i = items.indexOf(document.activeElement);
    const next = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: items.length - 1 }[e.key];
    items[(next + items.length) % items.length]?.focus();
    e.preventDefault();
  }
});
// Close when the window width changes (phones fire height-only resizes while scrolling).
let lastWidth = window.innerWidth;
window.addEventListener('resize', () => {
  if (window.innerWidth !== lastWidth) closePopover({ restoreFocus: false });
  lastWidth = window.innerWidth;
});
