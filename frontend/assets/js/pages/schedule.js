/* Schedule — week grid with daily capacity, plus a day view.
   Phones open on today's day view; the week view becomes a list of days. */
import { api } from '../services/api.js';
import { loadPlan } from '../services/planData.js';
import { startPage, noGoal } from '../components/page.js';
import { icon, priorityFlag } from '../core/icons.js';
import { esc, renderInto } from '../core/dom.js';
import { fmt, hrs, addDays, weekStart, parse, dayOfWeek, timeBlocks, DAY_NAMES, isWorkingDay } from '../core/dates.js';
import { taskButton } from '../components/taskList.js';
import { openTaskDrawer } from '../components/taskDrawer.js';
import { openFixModal } from '../components/fixModal.js';

const PHONE = window.matchMedia('(max-width: 767.98px)').matches;
const view = { mode: PHONE ? 'day' : 'week', weekOf: null, day: null };
let main, plan, reviews;

const REVIEW_WORD = { completed: 'done', partial: 'partly', not_completed: 'missed' };

startPage('schedule', async m => {
  main = m;
  bind();
  await refresh();
});

async function refresh() {
  plan = await loadPlan();
  if (!plan.goal) { main.innerHTML = noGoal(); return; }
  reviews = await api.getReviews(plan.goal.id);
  render();
}

function render() {
  const ws = view.weekOf || weekStart(plan.today);
  const days = [0, 1, 2, 3, 4, 5, 6].map(i => addDays(ws, i));
  const body = view.mode === 'day' ? dayView(days) : weekView(days);
  renderInto(main, `<div class="wrap">${header(days)}${body}</div>`);
}

function header(days) {
  const { goal, status: st } = plan;
  const workDays = goal.available_days.slice().sort((a, b) => (a || 7) - (b || 7)).map(d => DAY_NAMES[d]).join(', ');
  const range = `${fmt(days[0], { month: 'short', day: 'numeric' })} – ${fmt(days[6], { month: 'short', day: 'numeric' })}`;
  return `<div class="page-h">
      <div><h1>Schedule</h1><p>Version ${plan.version} · ${hrs(goal.daily_available_hours)} a day · ${workDays}</p></div>
      <div class="tools">
        <div class="seg" role="group" aria-label="View">
          <button type="button" data-mode="week" aria-pressed="${view.mode === 'week'}">Week</button>
          <button type="button" data-mode="day" aria-pressed="${view.mode === 'day'}">Day</button>
        </div>
        <div class="weeknav">
          <button class="iconbtn" type="button" data-week="-7" aria-label="Previous week">${icon('chevronLeft', 18)}</button>
          <button class="btn sm" type="button" data-week="0">Today</button>
          <button class="iconbtn" type="button" data-week="7" aria-label="Next week">${icon('chevronRight', 18)}</button>
        </div>
        <p class="range" aria-live="polite">${range}</p>
      </div></div>
    ${st.feasible ? '' : `<div class="result bad"><span class="ic">${icon('alert', 20)}</span>
      <div><b>This plan runs past your deadline.</b> <span class="muted">Work after ${fmt(goal.deadline)} is shaded red. It isn’t squeezed into extra hours.</span></div>
      <button class="btn sm" type="button" id="fix">See options</button></div>`}`;
}

function dayView(days) {
  const { goal, today } = plan;
  const d = view.day && days.includes(view.day) ? view.day : (days.includes(today) ? today : days[0]);
  const blocks = timeBlocks(plan.byDate[d] || [], goal.start_time);
  const strip = days.map(k => `<button type="button" data-day="${k}" aria-pressed="${k === d}"${isWorkingDay(goal, k) ? '' : ' class="off"'}
      aria-label="${fmt(k, { weekday: 'long', month: 'long', day: 'numeric' })}">${DAY_NAMES[dayOfWeek(k)]} ${parse(k).getDate()}</button>`).join('');
  const list = blocks.length ? `<ul class="blocks">${blocks.map(b => {
    const t = plan.task(b.task_id);
    const ms = plan.milestone(t.milestone_id);
    const after = t.dependencies.length ? ` · after ${t.dependencies.map(x => esc(plan.task(x).title)).join(', ')}` : '';
    return `<li class="blk click" data-task="${t.id}" style="--c:${esc(ms?.color || 'var(--line-2)')}"><span class="bar"></span>
      <div>${taskButton(t)}<p class="s">${b.from} to ${b.to} · ${esc(ms?.name || '')}${after}</p></div>
      <span class="h">${priorityFlag(t.priority)}</span></li>`;
  }).join('')}</ul>` : `<p class="empty">${isWorkingDay(goal, d) ? 'Nothing scheduled.' : 'Not a working day.'}</p>`;
  return `<section class="card" aria-label="${fmt(d, { weekday: 'long', month: 'long', day: 'numeric' })}">
    <div class="week" role="group" aria-label="Pick a day">${strip}</div>${list}</section>`;
}

function weekView(days) {
  const { goal, today } = plan;
  return `<ol class="wgrid">${days.map(k => {
    const items = plan.byDate[k] || [];
    const used = items.reduce((a, b) => a + b.planned_hours, 0);
    const rv = reviews.find(r => r.date === k);
    const working = isWorkingDay(goal, k);
    const cls = ['wcol', k === today && 'today', !working && 'offday', k > goal.deadline && items.length && 'beyond'].filter(Boolean).join(' ');
    return `<li class="${cls}"${k === today ? ' aria-current="date"' : ''}>
      <h2 class="wh"><span>${DAY_NAMES[dayOfWeek(k)]}</span><b>${parse(k).getDate()}</b><span class="sr-only">${fmt(k, { month: 'long' })}</span></h2>
      ${k === goal.deadline ? '<p class="dlmark">● Deadline</p>' : ''}
      ${working
        ? `<div class="meter cap" role="img" aria-label="${hrs(used)} of ${hrs(goal.daily_available_hours)} planned"><i style="--w:${Math.min(100, used / goal.daily_available_hours * 100)}%"></i></div>
           <p class="cap-t">${hrs(used)} / ${hrs(goal.daily_available_hours)}</p>`
        : '<p class="cap-t">Day off</p>'}
      ${items.map(a => {
        const t = plan.task(a.task_id);
        const ri = rv?.items.find(x => x.task_id === a.task_id);
        return `<button type="button" class="wb${ri?.status === 'completed' ? ' done' : ''}" data-task="${t.id}" style="--c:${esc(plan.milestone(t.milestone_id)?.color || 'var(--line-2)')}">
          <span class="tt">${esc(t.title)}</span>
          <span class="h">${icon('clock', 11)}${hrs(a.planned_hours)}${ri ? ` · ${REVIEW_WORD[ri.status]}` : ''}</span></button>`;
      }).join('')}
    </li>`;
  }).join('')}</ol>`;
}

function bind() {
  main.addEventListener('click', e => {
    const t = e.target.closest('[data-task]');
    if (t) return openTaskDrawer(plan, t.dataset.task, refresh);
    const mode = e.target.closest('[data-mode]');
    if (mode) { view.mode = mode.dataset.mode; return render(); }
    const nav = e.target.closest('[data-week]');
    if (nav) {
      const n = +nav.dataset.week;
      view.weekOf = n === 0 ? weekStart(plan.today) : addDays(view.weekOf || weekStart(plan.today), n);
      view.day = n === 0 ? plan.today : view.weekOf;
      return render();
    }
    const d = e.target.closest('[data-day]');
    if (d) { view.day = d.dataset.day; return render(); }
    if (e.target.closest('#fix')) openFixModal(plan.goal.id, refresh);
  });
}
