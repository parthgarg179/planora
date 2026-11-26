/**
 * taskDrawer.js — side panel (full screen on phones) with a task's estimates, subtasks,
 * dependencies, scheduled days and a quick progress update.
 * openTaskDrawer(plan, taskId, onChanged)
 */
import { api } from '../services/api.js';
import { icon, priorityFlag } from '../core/icons.js';
import { esc, openOverlay, closeOverlay, toast } from '../core/dom.js';
import { fmt, hrs } from '../core/dates.js';
import { taskPill, milestoneTag } from './pills.js';
import { openFixModal } from './fixModal.js';

export function openTaskDrawer(plan, taskId, onChanged) {
  const t = plan.task(taskId);
  const days = Object.keys(plan.byDate).filter(d => d >= plan.today && plan.byDate[d].some(a => a.task_id === taskId)).sort();
  const unlocks = plan.tasks.filter(x => x.dependencies.includes(taskId));
  const editable = t.status !== 'done' && t.status !== 'dropped';
  const noPrediction = t.predicted_hours == null;

  const scrim = openOverlay(`<div class="scrim"><div class="drawer" role="dialog" aria-labelledby="drawer-title">
    <div class="dh"><div>
        <p class="kicker">${milestoneTag(plan.milestone(t.milestone_id))} · ${esc(t.category)}</p>
        <h2 id="drawer-title">${esc(t.title)}</h2>
        <p class="tags">${taskPill(t)} ${priorityFlag(t.priority)} ${t.optional ? '<span class="pill line">optional</span>' : ''}</p>
      </div><button class="iconbtn x" type="button" data-close aria-label="Close">${icon('x', 18)}</button></div>

    <section class="dsec"><h3>Estimates</h3><dl class="est">
      <div><dt>Initial estimate (AI)</dt><dd>${hrs(t.initial_estimated_hours)}</dd></div>
      <div><dt>Personalised estimate${noPrediction ? ' · not enough history' : ''}</dt><dd${noPrediction ? ' class="na"' : ''}>${noPrediction ? '—' : hrs(t.predicted_hours)}</dd></div>
      <div><dt>Remaining</dt><dd>${hrs(t.remaining_hours)}</dd></div>
      <div><dt>Actual time spent</dt><dd>${hrs(t.actual_hours)}</dd></div>
    </dl></section>

    <section class="dsec"><h3>Subtasks</h3>${t.subtasks.length
      ? `<ul class="plain-list">${t.subtasks.map((s, i) => `<li><label class="sub"><input type="checkbox" data-sub="${i}"${s.done ? ' checked' : ''}>${esc(s.title)}</label></li>`).join('')}</ul>`
      : '<p class="muted small">No subtasks.</p>'}</section>

    <section class="dsec"><h3>Dependencies</h3>
      ${t.dependencies.length ? `<ul class="plain-list">${t.dependencies.map(d => `<li class="dep">${icon('link', 13)}Needs <b>${esc(plan.task(d).title)}</b> ${taskPill(plan.task(d))}</li>`).join('')}</ul>`
        : '<p class="muted small">None. This can start anytime.</p>'}
      ${unlocks.length ? `<p class="muted small gap-top">Unlocks: ${unlocks.map(u => esc(u.title)).join(', ')}</p>` : ''}
    </section>

    <section class="dsec"><h3>Scheduled</h3>${days.length
      ? `<ul class="plain-list">${days.map(d => `<li class="dep">${icon('calendar', 13)}${fmt(d)} · ${hrs(plan.byDate[d].find(a => a.task_id === taskId).planned_hours)} ${d > plan.goal.deadline ? '<span class="dlmark">after deadline</span>' : ''}</li>`).join('')}</ul>`
      : `<p class="muted small">${t.status === 'done' ? 'Finished.' : 'Not scheduled.'}</p>`}</section>

    ${editable ? `<section class="dsec"><h3>Update now</h3>
      <div class="fields">
        <label class="fld">Time spent (hours)<input class="num" type="number" inputmode="decimal" id="dq-spent" min="0" step="0.25" value="${t.remaining_hours}"></label>
        <label class="fld">Still needed (hours)<input class="num" type="number" inputmode="decimal" id="dq-left" min="0" step="0.25" value="0"></label>
      </div>
      <div class="btn-row gap-top">
        <button class="btn primary sm" type="button" id="dq-done">Mark complete</button>
        <button class="btn sm" type="button" id="dq-partial">Save as partly done</button>
      </div></section>` : ''}
  </div></div>`);

  scrim.querySelectorAll('[data-sub]').forEach(cb => cb.addEventListener('change', async () => {
    t.subtasks[+cb.dataset.sub].done = cb.checked;
    try { await api.updateTask(t.id, { subtasks: t.subtasks }); }
    catch (err) { cb.checked = !cb.checked; t.subtasks[+cb.dataset.sub].done = cb.checked; toast(err.message); }
  }));

  const save = async (complete, button) => {
    const spent = +scrim.querySelector('#dq-spent').value || 0;
    const left = complete ? 0 : +scrim.querySelector('#dq-left').value || 0;
    button.disabled = true;
    let res;
    try { res = await api.recordProgress(t.id, { actual_hours_spent: spent, remaining_hours: left }); }
    catch (err) { button.disabled = false; toast(err.message); return; }
    closeOverlay();
    await onChanged?.();
    if (!res.status.feasible) openFixModal(plan.goal.id, onChanged);
    else toast(`${t.title} updated. Schedule v${res.version}.`);
  };
  scrim.querySelector('#dq-done')?.addEventListener('click', e => save(true, e.currentTarget));
  scrim.querySelector('#dq-partial')?.addEventListener('click', e => save(false, e.currentTarget));
}
