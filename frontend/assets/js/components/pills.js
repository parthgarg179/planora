/* pills.js — small status badges reused across pages. */
import { esc } from '../core/dom.js';

export function taskPill(t) {
  if (t.status === 'dropped') return '<span class="pill line">Dropped</span>';
  if (t.status === 'done') return '<span class="pill ok">Complete</span>';
  if (t.status === 'in_progress') return '<span class="pill warn">In progress</span>';
  return '<span class="pill todo">To do</span>';
}

export function deadlinePill(st) {
  if (!st.feasible) return '<span class="pill bad">Won’t fit by deadline</span>';
  if (st.at_risk) return '<span class="pill warn">Tight</span>';
  return '<span class="pill ok">On track</span>';
}

export function reviewPill(status) {
  return status === 'completed' ? '<span class="pill ok">Done</span>'
    : status === 'partial' ? '<span class="pill warn">Partly</span>'
    : '<span class="pill bad">Missed</span>';
}

/** Milestone name with its colour dot. The colour comes from the data, so it's passed as a CSS variable. */
export const milestoneTag = m => m ? `<span class="mtag" style="--c:${esc(m.color)}"><i></i>${esc(m.name)}</span>` : '';
