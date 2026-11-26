/* Tasks — every task of every active goal, grouped by goal, then by milestone. */
import { loadPlan, goalTag } from '../services/planData.js';
import { startPage, noGoal } from '../components/page.js';
import { icon, priorityFlag } from '../core/icons.js';
import { esc } from '../core/dom.js';
import { hrs, fmt } from '../core/dates.js';
import { taskPill } from '../components/pills.js';
import { taskTable } from '../components/taskList.js';
import { openTaskDrawer } from '../components/taskDrawer.js';

let main, plan;

startPage('tasks', async m => {
  main = m;
  main.addEventListener('click', e => {
    const r = e.target.closest('[data-task]');
    if (r) openTaskDrawer(plan, r.dataset.task, refresh);
  });
  await refresh();
});

async function refresh() {
  plan = await loadPlan();
  if (plan.empty) { main.innerHTML = noGoal(); return; }
  const goal = plan.goals[0];
  const sub = plan.multi ? `${plan.goals.length} goals` : `${esc(goal.title)} · ${goal.milestones.length} milestones`;
  main.innerHTML = `<div class="wrap">
    <div class="page-h"><div><h1>Tasks</h1><p>${sub}</p></div></div>
    ${plan.goals.map(goalCard).join('')}
    <p class="hint">Select any task for details, subtasks and estimates.</p></div>`;
}

/** One card per goal (with the goal's name as its heading when there are several). */
function goalCard(g, i) {
  const head = plan.multi ? `<div class="card-h"><h2 id="goal-${g.id}">${goalTag(plan, g.id)}</h2>
      <div class="r muted small">due ${fmt(g.deadline, { month: 'short', day: 'numeric' })}</div></div>` : '';
  return `<div class="card${i ? ' gap-top' : ''}"${plan.multi ? ` role="region" aria-labelledby="goal-${g.id}"` : ''}>${head}${g.milestones.map(milestoneSection).join('')}</div>`;
}

function milestoneSection(m) {
  const tasks = plan.tasks.filter(t => t.milestone_id === m.id);
  const total = tasks.filter(t => t.status !== 'dropped').reduce((a, t) => a + t.initial_estimated_hours, 0);
  return `<section aria-labelledby="ms-${esc(m.id)}">
    <h2 class="ms-h" id="ms-${esc(m.id)}" style="--c:${esc(m.color)}"><i></i>${esc(m.name)}<span class="muted">${hrs(total)} estimated</span></h2>
    ${taskTable({
      caption: `${m.name} tasks`,
      showHeader: false,
      columns: ['Depends on', 'Time', 'Priority', 'Status'],
      rows: tasks.map(t => ({
        task: t,
        muted: t.status === 'dropped',
        title: t.optional ? '<span class="pill line">optional</span>' : '',
        cells: [
          t.dependencies.length ? `<span class="muted small">${icon('link', 12)} after ${t.dependencies.map(d => esc(plan.task(d).title)).join(', ')}</span>` : '<span class="muted none">—</span>',
          `<span class="small">${t.status === 'done' ? `${hrs(t.actual_hours)} spent` : `${hrs(t.remaining_hours)} left`}</span>`,
          priorityFlag(t.priority),
          taskPill(t),
        ],
      })),
    })}
  </section>`;
}
