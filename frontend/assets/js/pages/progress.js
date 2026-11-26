/* Progress — completion, personalised-estimate status, estimated vs actual time, review history. */
import { api } from '../services/api.js';
import { loadPlan, loadReviews } from '../services/planData.js';
import { startPage, noGoal } from '../components/page.js';
import { esc } from '../core/dom.js';
import { fmt, hrs } from '../core/dates.js';
import { estimatesCard } from '../components/estimates.js';

const STATUS_TEXT = { completed: 'done', partial: 'partly', not_completed: 'missed' };
const RING = 2 * Math.PI * 44; // circumference of the completion ring

startPage('progress', async main => {
  const plan = await loadPlan();
  if (plan.empty) { main.innerHTML = noGoal(); return; }
  const [reviews, est] = await Promise.all([loadReviews(plan), api.getEstimates()]);
  const sub = plan.multi ? `All ${plan.goals.length} goals: ${plan.goals.map(g => esc(g.title)).join(' · ')}` : esc(plan.goals[0].title);

  main.innerHTML = `<div class="wrap">
    <div class="page-h"><div><h1>Progress</h1><p>${sub}</p></div></div>
    <div class="grid2 first">
      ${completionCard(plan)}
      <section class="card" aria-label="Personalised estimates">${estimatesCard(est, plan.tasks)}</section>
    </div>
    ${timeCard(plan.tasks)}
    ${historyCard(plan, reviews)}
  </div>`;
});

function completionCard(plan) {
  const live = plan.tasks.filter(t => t.status !== 'dropped');
  const done = live.filter(t => t.status === 'done');
  const total = live.reduce((a, t) => a + t.initial_estimated_hours, 0);
  const pct = Math.round(done.reduce((a, t) => a + t.initial_estimated_hours, 0) / Math.max(total, 0.01) * 100);
  const spent = plan.tasks.reduce((a, t) => a + t.actual_hours, 0);
  return `<section class="card" aria-labelledby="comp-h">
    <div class="card-h"><h2 id="comp-h">Completion</h2></div>
    <div class="ring">
      <svg width="110" height="110" viewBox="0 0 110 110" role="img" aria-label="${pct}% complete">
        <circle cx="55" cy="55" r="44" class="ring-bg"/>
        <circle cx="55" cy="55" r="44" class="ring-fg" stroke-dasharray="${RING}" stroke-dashoffset="${RING * (1 - pct / 100)}" transform="rotate(-90 55 55)"/>
        <text x="55" y="61" text-anchor="middle" class="ring-t">${pct}%</text>
      </svg>
      <div><p class="muted small">by estimated hours</p>
        <ul class="ring-facts">
          <li><b>${done.length}</b> of ${live.length} tasks done</li>
          <li><b>${hrs(spent)}</b> spent so far</li>
          <li><b>${hrs(plan.total.remaining_hours)}</b> still to do</li>
        </ul></div>
    </div>
  </section>`;
}

function timeCard(tasks) {
  const touched = tasks.filter(t => t.actual_hours > 0);
  const max = Math.max(1, ...touched.map(t => Math.max(t.initial_estimated_hours, t.actual_hours)));
  const pct = h => `${h / max * 100}%`;
  return `<section class="card gap-top" aria-labelledby="time-h">
    <div class="card-h"><h2 id="time-h">Estimated vs. actual time</h2></div>
    <ul class="legend" aria-hidden="true"><li><i class="est"></i>Estimated</li><li><i class="act"></i>Actual so far</li><li><i class="over"></i>Over estimate</li></ul>
    ${touched.length ? `<ul class="bars">${touched.map(t => `<li class="brow">
        <span class="bt">${esc(t.title)}</span>
        <span class="bb" aria-hidden="true"><i class="est" style="--w:${pct(t.initial_estimated_hours)}"></i><i class="${t.actual_hours > t.initial_estimated_hours ? 'over' : 'act'}" style="--w:${pct(t.actual_hours)}"></i></span>
        <span class="muted small">${hrs(t.actual_hours)} / ${hrs(t.initial_estimated_hours)}<span class="sr-only"> (actual / estimated)</span></span></li>`).join('')}</ul>`
      : '<p class="empty">No time logged yet.</p>'}
  </section>`;
}

function historyCard(plan, reviews) {
  return `<section class="card gap-top" aria-labelledby="hist-h">
    <div class="card-h"><h2 id="hist-h">Review history</h2></div>
    ${reviews.length ? `<ul class="upd-list">${[...reviews].reverse().map(r => `<li class="upd"><span class="o" aria-hidden="true"></span><div>
      <p class="t">${fmt(r.date, { weekday: 'long', month: 'short', day: 'numeric' })}</p>
      <p class="s">${r.items.map(i => `${esc(plan.task(i.task_id).title)}: ${STATUS_TEXT[i.status]}${i.status === 'partial' ? ` (${hrs(i.actual_hours_spent)} spent, ${hrs(i.remaining_hours)} left)` : ''}`).join(' · ')}</p>
    </div></li>`).join('')}</ul>` : '<p class="empty">No reviews yet.</p>'}
  </section>`;
}
