/* End-of-day review — report each of the day's tasks, then the backend replans. */
import { api } from '../services/api.js';
import { loadPlan } from '../services/planData.js';
import { startPage, noGoal } from '../components/page.js';
import { icon } from '../core/icons.js';
import { esc, toast, renderInto } from '../core/dom.js';
import { fmt, hrs, quarter } from '../core/dates.js';
import { openFixModal } from '../components/fixModal.js';

const OPTIONS = [['completed', 'Completed'], ['partial', 'Partly'], ['not_completed', 'Not done']];
const LONG_DATE = { weekday: 'long', month: 'long', day: 'numeric' };
let main, plan, reviews, pending = [], selected = null, draft = {}, lastResult = null;

startPage('review', async m => { main = m; bind(); await refresh(); });

async function refresh() {
  plan = await loadPlan();
  if (!plan.goal) { main.innerHTML = noGoal(); return; }
  [reviews, { dates: pending }] = await Promise.all([api.getReviews(plan.goal.id), api.getPendingReviews(plan.goal.id)]);
  if (!pending.includes(selected)) { selected = pending[0] || null; draft = {}; } // oldest pending day first
  render();
}

function render() {
  const { goal, today } = plan;
  const day = selected;
  const head = `<div class="page-h"><div><h1>End-of-day review</h1><p>${fmt(day || today, LONG_DATE)} · reminder at ${esc(goal.reminder_time)}</p></div></div>`;

  if (!day) {
    const doneToday = reviews.some(r => r.date === today);
    renderInto(main, `<div class="wrap">${resultBanner()}${head}<div class="card"><p class="empty">${doneToday
      ? 'Today’s review is saved. Nothing else is waiting.' : 'Nothing to review right now.'}</p></div></div>`);
    return;
  }

  const items = plan.byDate[day] || [];
  const dayTabs = pending.length > 1 || day !== today
    ? `<div class="pending" role="group" aria-label="Days waiting for a review"><span class="muted small">Waiting for a review:</span>
        ${pending.map(d => `<button type="button" data-date="${d}" aria-pressed="${d === day}">${d === today ? 'Today' : fmt(d, { weekday: 'short', day: 'numeric' })}</button>`).join('')}</div>`
    : '';
  const lateNote = day !== today
    ? `<p class="note late">${icon('clock', 13)}This is a missed review from ${fmt(day, { weekday: 'long' })}. You can fill it in for 3 days; after that its work counts as not done.</p>` : '';

  renderInto(main, `<div class="wrap">${resultBanner()}${head}${dayTabs}${lateNote}
    <div class="layout-r">
      <section class="card" aria-label="Tasks planned for ${fmt(day, LONG_DATE)}">${items.map(a => taskItem(a, day === today)).join('')}</section>
      ${summary(items)}
    </div></div>`);
}

function taskItem(a, isToday) {
  const t = plan.task(a.task_id);
  const x = draft[t.id] || {};
  const num = (field, label, min, value) => `<label class="fld">${label}
    <input class="num" type="number" inputmode="decimal" min="${min}" step="0.25" value="${esc(value)}" data-task="${t.id}" data-field="${field}"></label>`;
  let details = '';
  if (x.status === 'completed') details = `<div class="fields">${num('actual_hours_spent', 'Time spent (hours)', 0, x.actual_hours_spent)}<p class="note">Marks the whole task complete.</p></div>`;
  if (x.status === 'partial') details = `<div class="fields">${num('actual_hours_spent', 'Time spent today (hours)', 0, x.actual_hours_spent)}
      ${num('remaining_hours', 'Still needed (hours)', 0.25, x.remaining_hours)}<p class="note">Time spent and time remaining are recorded separately.</p></div>`;
  if (x.status === 'not_completed') details = `<div class="fields"><p class="note">No time logged. The ${hrs(a.planned_hours)} planned that day will be spread across the coming days.</p></div>`;

  return `<div class="rv" style="--c:${esc(plan.milestone(t.milestone_id)?.color || 'var(--line-2)')}">
    <div class="rv-top"><span class="bar" aria-hidden="true"></span>
      <div class="rv-name"><p class="t" id="rv-${t.id}">${esc(t.title)}</p>
        <p class="muted small">Planned ${hrs(a.planned_hours)}${isToday ? ' today' : ''} · ${hrs(t.remaining_hours)} left on this task</p></div>
      <fieldset class="choices" aria-labelledby="rv-${t.id}">
        <legend class="sr-only">How did it go?</legend>
        ${OPTIONS.map(([v, l]) => `<label class="choice"><input type="radio" name="st-${t.id}" value="${v}" data-task="${t.id}"${x.status === v ? ' checked' : ''}><span class="${v}">${l}</span></label>`).join('')}
      </fieldset></div>
    ${details}
  </div>`;
}

function summary(items) {
  const t = id => plan.task(id);
  let backlog = 0;
  items.forEach(a => {
    const x = draft[a.task_id];
    if (x?.status === 'not_completed') backlog += a.planned_hours;
    if (x?.status === 'partial') backlog += Math.max(0, (+x.remaining_hours || 0) - (t(a.task_id).remaining_hours - a.planned_hours));
  });
  const done = items.filter(a => draft[a.task_id]?.status).length;
  const allSet = done === items.length;
  return `<aside class="card sum" aria-labelledby="sum-h">
    <h2 class="sum-h" id="sum-h">After this review</h2>
    <dl>
      <div class="line"><dt class="muted">Tasks reviewed</dt><dd>${done}/${items.length}</dd></div>
      <div class="line"><dt class="muted">Backlog created</dt><dd>${hrs(quarter(backlog))}</dd></div>
      <div class="line"><dt class="muted">Working days left</dt><dd>${Math.max(0, plan.status.capacity_days - 1)}</dd></div>
    </dl>
    <p class="muted small">Backlog isn’t all dumped on tomorrow. It’s spread across the remaining days, within your daily hours.</p>
    <button class="btn primary block" type="button" id="submit"${allSet ? '' : ' disabled aria-describedby="submit-hint"'}>Submit review & replan</button>
    ${allSet ? '' : '<p class="muted small center" id="submit-hint">Pick a status for every task</p>'}
  </aside>`;
}

function resultBanner() {
  if (!lastResult) return '';
  const ok = lastResult.status.feasible;
  return `<div class="result ${ok ? 'ok' : 'bad'}" role="status"><span class="ic">${icon(ok ? 'check' : 'alert', 20)}</span>
    <div><b>${ok ? `Review saved. Schedule v${lastResult.version} is ready.` : `Review saved, but the plan no longer fits before ${fmt(plan.goal.deadline, { month: 'short', day: 'numeric' })}.`}</b>
    <p class="small">${esc(lastResult.summary)}</p></div>
    ${ok ? '<a class="btn sm" href="schedule.html">View schedule</a>' : '<button class="btn sm" type="button" id="fix">See options</button>'}</div>`;
}

/** Sensible starting numbers when a status is picked (the user can change them). */
function startDraft(taskId, status) {
  const a = plan.byDate[selected].find(x => x.task_id === taskId);
  const t = plan.task(taskId);
  draft[taskId] = {
    status,
    actual_hours_spent: status === 'completed' ? a.planned_hours : status === 'partial' ? quarter(a.planned_hours / 2) : 0,
    remaining_hours: status === 'partial' ? Math.max(0.25, quarter(t.remaining_hours - a.planned_hours / 2)) : 0,
  };
}

async function submit(button) {
  button.disabled = true;
  const items = plan.byDate[selected].map(a => ({
    task_id: a.task_id, status: draft[a.task_id].status,
    actual_hours_spent: +draft[a.task_id].actual_hours_spent || 0, remaining_hours: +draft[a.task_id].remaining_hours || 0,
  }));
  try {
    lastResult = await api.submitDailyReview(plan.goal.id, { date: selected, items });
  } catch (err) {
    toast(err.message);
    button.disabled = false;
    return;
  }
  draft = {};
  await refresh();
  main.focus();  // the page changed under the button; move focus to the top so the result banner is next
  if (!lastResult.status.feasible) openFixModal(plan.goal.id, afterFix);
  else toast(`Schedule v${lastResult.version} saved.`);
}

const afterFix = async () => { lastResult = null; await refresh(); };

function bind() {
  main.addEventListener('change', e => {
    const el = e.target;
    if (el.type === 'radio' && el.dataset.task) { startDraft(el.dataset.task, el.value); lastResult = null; render(); return; }
    if (el.dataset.field) render(); // update the backlog numbers once the user leaves a field
  });
  main.addEventListener('input', e => {
    const { task, field } = e.target.dataset;
    if (field) draft[task][field] = e.target.value;
  });
  main.addEventListener('click', e => {
    const submitBtn = e.target.closest('#submit');
    if (submitBtn) return submit(submitBtn);
    const tab = e.target.closest('[data-date]');
    if (tab) { selected = tab.dataset.date; draft = {}; lastResult = null; return render(); }
    if (e.target.closest('#fix')) openFixModal(plan.goal.id, afterFix);
  });
}
