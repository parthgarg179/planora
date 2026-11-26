/**
 * Mock scheduler — a JavaScript copy of the logic your FastAPI scheduler will own.
 * Used only while CONFIG.USE_MOCK is true, so the UI can be tested without a backend.
 *
 * Rules: prerequisites first, then priority, never above the daily hours,
 * keep going on a task that is already started, and keep projecting past the
 * deadline (so the UI can show the shortfall instead of hiding it).
 */
import { addDays, quarter, isWorkingDay } from '../../core/dates.js';

const PRIORITY = { High: 0, Normal: 1, Low: 2 };
const open = t => t.status !== 'done' && t.status !== 'dropped';

export function schedule(goal, tasks, from) {
  const live = tasks.filter(t => t.status !== 'dropped');
  const finished = new Set(tasks.filter(t => !open(t)).map(t => t.id));
  const known = new Set(tasks.map(t => t.id));
  const left = {};
  live.forEach(t => { if (open(t) && t.remaining_hours > 1e-9) left[t.id] = t.remaining_hours; });

  const plan = {};
  let day = from, started = null, last = null;
  const limit = addDays(goal.deadline, 500);
  const anyLeft = () => Object.values(left).some(v => v > 1e-9);

  while (anyLeft() && day <= limit) {
    if (isWorkingDay(goal, day)) {
      let cap = goal.daily_available_hours;
      while (cap > 1e-9) {
        const ready = live.filter(t => left[t.id] > 1e-9 && t.dependencies.every(d => finished.has(d) || !known.has(d)));
        if (!ready.length) break;
        ready.sort((a, b) => ((b.id === started) - (a.id === started)) || PRIORITY[a.priority] - PRIORITY[b.priority] || a.order - b.order);
        const t = ready[0];
        const h = Math.min(cap, left[t.id]);
        (plan[day] ??= []).push({ task_id: t.id, planned_hours: quarter(h) });
        left[t.id] -= h; cap -= h; last = day;
        if (left[t.id] <= 1e-9) { finished.add(t.id); started = null; } else started = t.id;
      }
    }
    day = addDays(day, 1);
  }
  return { plan, last };
}

export function capacity(goal, from) {
  let hours = 0, days = 0;
  for (let d = from; d <= goal.deadline; d = addDays(d, 1)) if (isWorkingDay(goal, d)) { hours += goal.daily_available_hours; days++; }
  return { hours, days };
}

export function status(goal, tasks, from) {
  const { last } = schedule(goal, tasks, from);
  const remaining = tasks.filter(open).reduce((a, t) => a + t.remaining_hours, 0);
  const cap = capacity(goal, from);
  const feasible = !last || last <= goal.deadline;
  const slack = cap.hours - remaining;
  return {
    deadline: goal.deadline,
    remaining_hours: remaining,
    capacity_hours: cap.hours,
    capacity_days: cap.days,
    feasible,
    shortfall_hours: Math.max(0, remaining - cap.hours),
    slack_hours: slack,
    projected_finish: last,
    at_risk: feasible && slack < goal.daily_available_hours * 1.5,
  };
}

