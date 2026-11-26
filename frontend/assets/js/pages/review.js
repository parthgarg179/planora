/* End-of-day review — report each of the day's tasks from every goal in one form,
   then each goal's part is sent to the backend, which replans that goal. */
import { api } from '../services/api.js';
import { loadPlan, loadReviews, loadPending } from '../services/planData.js';
import { startPage, noGoal } from '../components/page.js';
import { icon } from '../core/icons.js';
import { esc, toast, renderInto } from '../core/dom.js';
import { fmt, hrs, quarter } from '../core/dates.js';
import { openFixModal } from '../components/fixModal.js';

const OPTIONS = [['completed', 'Completed'], ['partial', 'Partly'], ['not_completed', 'Not done']];
const LONG_DATE = { weekday: 'long', month: 'long', day: 'numeric' };
let main, plan, reviews, pending = [], pendingByGoal = {}, selected = null, draft = {}, lastResult = null;

startPage('review', async m => { main = m; bind(); await refresh(); });

async function refresh() {
  plan = await loadPlan();
  if (plan.empty) { main.innerHTML = noGoal(); return; }
  let p;
  [reviews, p] = await Promise.all([loadReviews(plan), loadPending(plan)]);
  pending = p.dates;
  pendingByGoal = p.byGoal;
  if (!pending.includes(selected)) { selected = pending[0] || null; draft = {}; } // oldest pending day first
  render();
}

/** The day's planned tasks from every goal that still needs a review for that day. */
const itemsFor = day => (plan.byDate[day] || []).filter(a => (pendingByGoal[a.goal_id] || []).includes(day));

function render() {
  const { today } = plan;
  const day = selected;
  const reminder = plan.goals.map(g => g.reminder_time).sort()[0]; // earliest reminder of all goals
  const head = `<div class="page-h"><div><h1>End-of-day review</h1><p>${fmt(day || today, LONG_DATE)} · reminder at ${esc(reminder)}</p></div></div>`;

  if (!day) {
    const doneToday = reviews.some(r => r.date === today);
    renderInto(main, `<div class="wrap">${resultBanner()}${head}<div class="card"><p class="empty">${doneToday
      ? 'Today’s review is saved. Nothing else is waiting.' : 'Nothing to review right now.'}</p></div></div>`);
    return;
  }

  const items = itemsFor(day);
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

  return `<div class="rv" style="--c:${esc(plan.barColor(t))}">
    <div class="rv-top"><span class="bar" aria-hidden="true"></span>
      <div class="rv-name"><p class="t" id="rv-${t.id}">${esc(t.title)}</p>
        <p class="muted small">${plan.multi ? `${esc(plan.goalOf(t).title)} · ` : ''}Planned ${hrs(a.planned_hours)}${isToday ? ' today' : ''} · ${hrs(t.remaining_hours)} left on this task</p></div>
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
  const daysLeft = Math.max(...plan.goals.map(g => plan.status(g.id).capacity_days)); // the goal with the most days left
  return `<aside class="card sum" aria-labelledby="sum-h">
    <h2 class="sum-h" id="sum-h">After this review</h2>
    <dl>
      <div class="line"><dt class="muted">Tasks reviewed</dt><dd>${done}/${items.length}</dd></div>
      <div class="line"><dt class="muted">Backlog created</dt><dd>${hrs(quarter(backlog))}</dd></div>
      <div class="line"><dt class="muted">Working days left</dt><dd>${Math.max(0, daysLeft - 1)}</dd></div>
    </dl>
    <p class="muted small">Backlog isn’t all dumped on tomorrow. It’s spread across the remaining days, within your daily hours.</p>
    <button class="btn primary block" type="button" id="submit"${allSet ? '' : ' disabled aria-describedby="submit-hint"'}>Submit review & replan</button>
    ${allSet ? '' : '<p class="muted small center" id="submit-hint">Pick a status for every task</p>'}
  </aside>`;
}

function resultBanner() {
  if (!lastResult) return '';
  const late = lastResult.filter(r => !r.res.status.feasible);
  const ok = !late.length;
  const name = r => (plan.multi || lastResult.length > 1 ? `“${esc(r.goal.title)}”` : 'the plan');
  const title = ok
    ? (lastResult.length > 1 ? 'Review saved. Your schedules are updated.' : `Review saved. Schedule v${lastResult[0].res.version} is ready.`)
    : `Review saved, but ${late.map(r => `${name(r)} no longer fits before ${fmt(r.goal.deadline, { month: 'short', day: 'numeric' })}`).join(', and ')}.`;
  const lines = lastResult.map(r => `<p class="small">${lastResult.length > 1 ? `<b>${esc(r.goal.title)}:</b> ` : ''}${esc(r.res.summary)}</p>`).join('');
  return `<div class="result ${ok ? 'ok' : 'bad'}" role="status"><span class="ic">${icon(ok ? 'check' : 'alert', 20)}</span>
    <div><b>${title}</b>${lines}</div>
    ${ok ? '<a class="btn sm" href="schedule.html">View schedule</a>'
      : late.map(r => `<button class="btn sm" type="button" data-fix="${r.goal.id}">See options${late.length > 1 ? ` · ${esc(r.goal.title)}` : ''}</button>`).join('')}</div>`;
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

/** Each goal's tasks are saved with that goal's review (the backend replans one goal at a time). */
async function submit(button) {
  button.disabled = true;
  const byGoal = {};
  itemsFor(selected).forEach(a => (byGoal[a.goal_id] ??= []).push({
    task_id: a.task_id, status: draft[a.task_id].status,
    actual_hours_spent: +draft[a.task_id].actual_hours_spent || 0, remaining_hours: +draft[a.task_id].remaining_hours || 0,
  }));
  const results = [];
  for (const [goalId, items] of Object.entries(byGoal)) {
    try {
      results.push({ goal: plan.goal(goalId), res: await api.submitDailyReview(+goalId, { date: selected, items }) });
    } catch (err) {
      // goals saved before the error stay saved; the page reloads so only the rest is still waiting
      toast(`${plan.multi ? `${plan.goal(goalId).title}: ` : ''}${err.message}`);
      break;
    }
  }
  lastResult = results.length ? results : null;
  draft = {};
  await refresh();
  main.focus();  // the page changed under the button; move focus to the top so the result banner is next
  const late = results.filter(r => !r.res.status.feasible);
  if (late.length === 1) openFixModal(late[0].goal.id, afterFix);
  else if (results.length && !late.length) toast(results.length > 1 ? 'Review saved for every goal.' : `Schedule v${results[0].res.version} saved.`);
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
    const fix = e.target.closest('[data-fix]');
    if (fix) openFixModal(+fix.dataset.fix, afterFix);
  });
}
