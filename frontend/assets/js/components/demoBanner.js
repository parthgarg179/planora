/* demoBanner.js — thin strip saying the site is running on sample data (mock mode only). */
import { CONFIG } from '../config.js';
import { icon } from '../core/icons.js';

export function addDemoBanner() {
  if (!CONFIG.USE_MOCK || document.querySelector('.demo-banner')) return;
  const bar = document.createElement('p');
  bar.className = 'demo-banner';
  bar.innerHTML = `${icon('spark', 13)} Demo mode · sample data stored in this browser, nothing is sent to a server`;
  document.querySelector('.frame').prepend(bar);
}
