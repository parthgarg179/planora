/**
 * planData.js — loads every active goal in one go and merges them into one plan,
 * so pages can show all goals together (tasks for a day from every goal, one review, …).
 * Pages call loadPlan() and re-call it after anything changes.
 *
 * Task and milestone ids are unique across goals, so one lookup works for all of them.
 * Each goal keeps its own status (feasibility), version, deadline and daily hours.
 */
import { api } from './api.js';
import { timeBlocks, dayOfWeek } from '../core/dates.js';
import { esc } from '../core/dom.js';

// One colour per goal (used for the small goal tag when there is more than one goal).
const GOAL_COLORS = ['#4f6bed', '#e0a100', '#1fa971', '#d9578f', '#7a5cf0', '#2aa6c4'];

export async function loadPlan() {
  const goals = (await api.getActiveGoals()).sort((a, b) => a.deadline.localeCompare(b.deadline) || a.id - b.id);
  if (!goals.length) return { goals: [], empty: true };

  const parts = await Promise.all(goals.map(g => Promise.all([api.getTasks(g.id), api.getSchedule(g.id), api.getStatus(g.id)])));

  const tasks = [], byDate = {}, statusById = {}, versionById = {};
  goals.forEach((g, i) => {
    const [goalTasks, schedule, status] = parts[i];
    g.color = GOAL_COLORS[i % GOAL_COLORS.length];
    goalTasks.forEach(t => tasks.push({ ...t, goal_id: g.id }));
    schedule.assignments.forEach(a => (byDate[a.date] ??= []).push({ ...a, goal_id: g.id }));
    statusById[g.id] = status;
    versionById[g.id] = schedule.version;
  });

  const goalById = Object.fromEntries(goals.map(g => [g.id, g]));
  const taskById = Object.fromEntries(tasks.map(t => [t.id, t]));
  const milestoneById = Object.fromEntries(goals.flatMap(g => g.milestones || []).map(m => [m.id, m]));
  const statuses = goals.map(g => statusById[g.id]);
  const worksOn = (g, date) => g.available_days.includes(dayOfWeek(date));

  return {
    goals, tasks, byDate,                     // byDate: { 'YYYY-MM-DD': [{task_id, planned_hours, goal_id}] }
    multi: goals.length > 1,
    today: parts[0][1].today,
    goal: id => goalById[id],
    goalOf: t => goalById[t.goal_id],
    status: id => statusById[id],
    version: id => versionById[id],
    task: id => taskById[id],
    milestone: id => milestoneById[id],
    /** Colour of a task's bar: its goal's colour when there are several goals, else its milestone's. */
    barColor: t => (goals.length > 1 ? goalById[t.goal_id].color : milestoneById[t.milestone_id]?.color) || 'var(--line-2)',
    /** All goals added together (hours summed, "feasible" only if every goal fits). */
    total: {
      remaining_hours: statuses.reduce((a, s) => a + s.remaining_hours, 0),
      capacity_hours: statuses.reduce((a, s) => a + s.capacity_hours, 0),
      feasible: statuses.every(s => s.feasible),
      at_risk: statuses.some(s => s.at_risk),
    },
    /** true if any goal works on this date */
    isWorking: date => goals.some(g => worksOn(g, date)),
    /** hours available on this date, added up over the goals that work that day */
    capacityOn: date => goals.filter(g => worksOn(g, date)).reduce((a, g) => a + g.daily_available_hours, 0),
    /** goals whose deadline is this date */
    deadlinesOn: date => goals.filter(g => g.deadline === date),
    /** The day's time blocks from every goal. Each goal starts at its own start time, but never
        before the previous goal's work ends, so blocks don't overlap (e.g. two goals both at 7 pm). */
    dayBlocks: date => {
      let free = 0; // first minute not yet taken
      return [...goals].sort((a, b) => a.start_time.localeCompare(b.start_time)).flatMap(g => {
        const items = (byDate[date] || []).filter(a => a.goal_id === g.id);
        if (!items.length) return [];
        const [h, m] = g.start_time.split(':').map(Number);
        const from = Math.max(h * 60 + m, free);
        free = from + items.reduce((a, x) => a + Math.round(x.planned_hours * 60), 0);
        return timeBlocks(items, `${Math.floor(from / 60)}:${from % 60}`);
      });
    },
  };
}

/** Call an API function once per goal → { goalId: result }. */
export async function perGoal(plan, fn) {
  const results = await Promise.all(plan.goals.map(g => fn(g.id)));
  return Object.fromEntries(plan.goals.map((g, i) => [g.id, results[i]]));
}

/** Every goal's daily reviews merged by date: [{date, items}] oldest first (task ids are unique, so items just join). */
export async function loadReviews(plan) {
  const byGoal = await perGoal(plan, api.getReviews);
  const byDate = {};
  Object.values(byGoal).flat().forEach(r => (byDate[r.date] ??= { date: r.date, items: [] }).items.push(...r.items));
  return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));
}

/** Days waiting for a review → { dates: [...] (all goals, oldest first), byGoal: { goalId: [...] } }. */
export async function loadPending(plan) {
  const res = await perGoal(plan, api.getPendingReviews);
  const byGoal = Object.fromEntries(Object.entries(res).map(([id, r]) => [id, r.dates]));
  return { dates: [...new Set(Object.values(byGoal).flat())].sort(), byGoal };
}

/** Small coloured label with a goal's name, shown next to tasks when there is more than one goal. */
export const goalTag = (plan, goalId) => {
  if (!plan.multi) return '';
  const g = plan.goal(goalId);
  return `<span class="mtag gtag" style="--c:${esc(g.color)}"><i></i>${esc(g.title)}</span>`;
};
