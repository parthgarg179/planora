/* Home — dashboard: greeting, today's plan, schedule, review prompt, goal health,
   progress snapshot and plan updates.
   Wide screens (>= 1100px): main column (plan, schedule) + side column (review, health,
   progress, updates); from 1500px plan and schedule sit side by side. Smaller screens: one column. */
import { api } from '../services/api.js';
import { loadPlan } from '../services/planData.js';
import { startPage, noGoal } from '../components/page.js';
import { icon, priorityFlag } from '../core/icons.js';
import { esc, renderInto } from '../core/dom.js';
import { fmt, hrs, addDays, weekStart, parse, dayOfWeek, diffDays, timeBlocks, greeting, DAY_NAMES, isWorkingDay } from '../core/dates.js';
import { taskPill, deadlinePill, reviewPill, milestoneTag } from '../components/pills.js';
import { taskTable, taskButton } from '../components/taskList.js';
import { openTaskDrawer } from '../components/taskDrawer.js';
import { openFixModal } from '../components/fixModal.js';

const view = { range: 'today', day: null };
let main, plan, user, updates, reviews, pending = [];

startPage('home', async m => { main = m; bind(); await refresh(); });

async function refresh() {
  plan = await loadPlan();
  if (!plan.goal) { main.innerHTML = noGoal(); return; }
  let p;
  [user, updates, reviews, p] = await Promise.all([api.getMe(), api.getUpdates(plan.goal.id), api.getReviews(plan.goal.id), api.getPendingReviews(plan.goal.id)]);
  pending = p.dates;
  render();
}

function render() {
  const { goal, today } = plan;
  renderInto(main, `<div class="wrap"><div class="dash">
    ${hero(goal, today)}
    ${planCard(today)}
    ${scheduleCard(goal, today)}
    <div class="side-col">${reviewCta(today)}${healthCard(goal, today)}${snapshotCard()}${updatesCard()}</div>
  </div></div>`);
}

function hero(goal, today) {
  const live = plan.tasks.filter(t => t.status !== 'dropped');
  const done = live.filter(t => t.status === 'done').length;
  const st = plan.status;
  return `<header class="hero a-hero">
    <p class="date">${fmt(today, { weekday: 'long', month: 'long', day: 'numeric' })}</p>
    <h1>${greeting()}, ${esc(user.name.split(' ')[0])}</h1>
    <ul class="chips">
      <li class="chip"><span class="ci ok">${icon('check', 12, 3)}</span><b>${done}/${live.length}</b> tasks completed</li>
      <li class="chip"><span class="ci">${icon('clock', 12, 2.4)}</span><b>${hrs(st.remaining_hours)}</b> left of ${hrs(st.capacity_hours)} available</li>
      <li class="chip">${deadlinePill(st)} <span class="muted">due ${fmt(goal.deadline, { month: 'short', day: 'numeric' })}</span></li>
    </ul>
  </header>`;
}

/** Today's (or this week's) planned tasks. */
function planCard(today) {
  const week = view.range === 'week';
  const rows = [];
  if (!week) (plan.byDate[today] || []).forEach(a => rows.push({ ...a, date: today }));
  else {
    const ws = weekStart(today);
    for (let i = 0; i < 7; i++) {
      const d = addDays(ws, i);
      if (d >= today) (plan.byDate[d] || []).forEach(a => rows.push({ ...a, date: d }));
    }
  }
  const columns = [...(week ? ['Day'] : []), 'Planned', 'Priority', 'Milestone', 'Status'];
  const table = rows.length ? taskTable({
    caption: week ? 'Tasks planned for the rest of this week' : 'Tasks planned for today',
    columns,
    rows: rows.map(a => {
      const t = plan.task(a.task_id);
      return { task: t, cells: [...(week ? [fmt(a.date, { weekday: 'short', day: 'numeric' })] : []),
        hrs(a.planned_hours), priorityFlag(t.priority), milestoneTag(plan.milestone(t.milestone_id)), taskPill(t)] };
    }),
  }) : `<p class="empty">Nothing scheduled ${week ? 'for the rest of this week' : 'today'}.</p>`;

  return `<section class="card a-plan" aria-labelledby="plan-h">
    <div class="card-h"><h2 id="plan-h">${icon('list', 18)} ${week ? 'This week' : 'Today’s plan'}</h2>
      <label class="sr-only" for="range">Show</label>
      <select class="sel" id="range"><option value="today"${week ? '' : ' selected'}>Today</option><option value="week"${week ? ' selected' : ''}>This week</option></select>
      <div class="r"><a class="link" href="tasks.html">See all</a></div></div>
    ${table}
  </section>`;
}

/** Week strip + the chosen day's time blocks. */
function scheduleCard(goal, today) {
  const selDay = view.day || today;
  const ws = weekStart(selDay);
  const review = reviews.find(r => r.date === selDay);
  const blocks = timeBlocks(plan.byDate[selDay] || [], goal.start_time);
  const strip = [0, 1, 2, 3, 4, 5, 6].map(i => {
    const d = addDays(ws, i);
    const cls = [!isWorkingDay(goal, d) && 'off', d === goal.deadline && 'dl'].filter(Boolean).join(' ');
    return `<button type="button" data-day="${d}" aria-pressed="${d === selDay}"${cls ? ` class="${cls}"` : ''}
      aria-label="${fmt(d, { weekday: 'long', month: 'long', day: 'numeric' })}${d === goal.deadline ? ', deadline' : ''}">${DAY_NAMES[dayOfWeek(d)]} ${parse(d).getDate()}</button>`;
  }).join('');
  const list = blocks.length ? `<ul class="blocks">${blocks.map(b => {
    const t = plan.task(b.task_id);
    const ri = review?.items.find(x => x.task_id === b.task_id);
    return `<li class="blk click" data-task="${t.id}" style="--c:${esc(plan.milestone(t.milestone_id)?.color || 'var(--line-2)')}"><span class="bar"></span>
      <div>${taskButton(t)}<p class="s">${b.from} to ${b.to}${selDay > goal.deadline ? ' · <span class="dlmark">after deadline</span>' : ''}</p></div>
      <span class="h">${ri ? reviewPill(ri.status) : `<span class="pill brand">${hrs(b.planned_hours)}</span>`}</span></li>`;
  }).join('')}</ul>` : `<p class="empty">${isWorkingDay(goal, selDay) ? 'Nothing scheduled.' : 'Not a working day.'}</p>`;

  return `<section class="card a-sched" aria-labelledby="sched-h">
    <div class="card-h"><h2 id="sched-h">${icon('calendar', 18)} Schedule</h2><div class="r"><a class="link" href="schedule.html">Open</a></div></div>
    <div class="week" role="group" aria-label="Pick a day">${strip}</div>
    ${list}
  </section>`;
}

function healthCard(goal, today) {
  const st = plan.status;
  const pct = Math.min(100, st.remaining_hours / Math.max(st.capacity_hours, 0.01) * 100);
  return `<section class="card a-health" aria-labelledby="health-h">
    <div class="card-h"><h2 id="health-h">${icon('target', 18)} Goal health</h2><div class="r">${deadlinePill(st)}</div></div>
    <div class="health">
      <p class="muted hrow">${esc(goal.title)}</p>
      <p class="hrow"><span>Remaining work <b>${hrs(st.remaining_hours)}</b></span><span class="muted">Available ${hrs(st.capacity_hours)}</span></p>
      <div class="meter" role="img" aria-label="${hrs(st.remaining_hours)} of work for ${hrs(st.capacity_hours)} available"><i class="${st.feasible ? '' : 'over'}" style="--w:${pct}%"></i></div>
      <dl class="kpis">
        <div class="kpi"><dt class="l">days left (${st.capacity_days} working)</dt><dd class="v">${diffDays(today, goal.deadline)}</dd></div>
        <div class="kpi"><dt class="l">${st.slack_hours >= 0 ? 'buffer' : 'shortfall'}</dt><dd class="v${st.slack_hours < 0 ? ' neg' : ''}">${st.slack_hours >= 0 ? '+' : ''}${hrs(st.slack_hours)}</dd></div>
        <div class="kpi"><dt class="l">projected finish</dt><dd class="v">${st.projected_finish ? fmt(st.projected_finish, { month: 'short', day: 'numeric' }) : '—'}</dd></div>
      </dl>
      ${st.feasible ? '' : `<button class="btn sm danger gap-top" type="button" id="fix">${icon('alert', 14)} See options to fix the plan</button>`}
    </div>
  </section>`;
}

function updatesCard() {
  return `<section class="card a-updates" aria-labelledby="upd-h">
    <div class="card-h"><h2 id="upd-h">${icon('note', 18)} Plan updates</h2></div>
    ${updates.length ? `<ul class="upd-list">${updates.slice(0, 4).map(u => `<li class="upd"><span class="o${u.bad ? ' bad' : ''}" aria-hidden="true"></span>
      <div><p class="t">${esc(u.title)}</p><p class="s">${esc(u.text)}</p></div></li>`).join('')}</ul>` : '<p class="empty">No updates yet.</p>'}
  </section>`;
}

/** Small completion ring + counts, linking to the Progress page. */
function snapshotCard() {
  const live = plan.tasks.filter(t => t.status !== 'dropped');
  const done = live.filter(t => t.status === 'done');
  const total = live.reduce((a, t) => a + t.initial_estimated_hours, 0);
  const pct = Math.round(done.reduce((a, t) => a + t.initial_estimated_hours, 0) / Math.max(total, 0.01) * 100);
  const spent = plan.tasks.reduce((a, t) => a + t.actual_hours, 0);
  const C = 2 * Math.PI * 30;
  return `<section class="card a-snap" aria-labelledby="snap-h">
    <div class="card-h"><h2 id="snap-h">${icon('chart', 18)} Progress</h2><div class="r"><a class="link" href="progress.html">Details</a></div></div>
    <div class="snap">
      <svg width="76" height="76" viewBox="0 0 76 76" role="img" aria-label="${pct}% complete">
        <circle cx="38" cy="38" r="30" class="ring-bg"/>
        <circle cx="38" cy="38" r="30" class="ring-fg" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct / 100)}" transform="rotate(-90 38 38)"/>
        <text x="38" y="44" text-anchor="middle" class="ring-t">${pct}%</text>
      </svg>
      <ul><li><b>${done.length}</b> of ${live.length} tasks done</li><li><b>${hrs(spent)}</b> spent so far</li><li class="muted small">by estimated hours</li></ul>
    </div>
  </section>`;
}

function reviewCta(today) {
  if (!pending.length) return '';
  const missed = pending.filter(d => d < today);
  const [title, text] = missed.length
    ? [`${missed.length} missed review${missed.length === 1 ? '' : 's'}`,
       `You haven’t reviewed ${missed.map(d => fmt(d, { weekday: 'long' })).join(' and ')} yet. Fill ${missed.length === 1 ? 'it' : 'them'} in so the plan stays accurate.`]
    : ['Done for the day?', 'Tell Planora what you finished. Anything left over gets spread across the remaining days.'];
  return `<aside class="cta a-review" aria-label="Review">${icon('review', 22)}<div><p class="cta-t">${title}</p><p>${text}</p></div>
    <a class="btn" href="review.html">${missed.length ? 'Review now' : 'Start end-of-day review'} ${icon('arrowRight', 14)}</a></aside>`;
}

function bind() {
  main.addEventListener('click', e => {
    if (e.target.closest('a, select')) return;
    const task = e.target.closest('[data-task]');
    if (task) return openTaskDrawer(plan, task.dataset.task, refresh);
    const day = e.target.closest('[data-day]');
    if (day) { view.day = day.dataset.day; return render(); }
    if (e.target.closest('#fix')) openFixModal(plan.goal.id, refresh);
  });
  main.addEventListener('change', e => { if (e.target.id === 'range') { view.range = e.target.value; render(); } });
}
