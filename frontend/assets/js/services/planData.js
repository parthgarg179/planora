/**
 * planData.js — loads everything a page usually needs about the active goal
 * in one go and adds a few lookups. Pages call loadPlan() and re-call it after
 * anything changes.
 */
import { api } from './api.js';

export async function loadPlan() {
  const goal = await api.getActiveGoal();
  if (!goal) return { goal: null };
  const [tasks, schedule, status] = await Promise.all([api.getTasks(goal.id), api.getSchedule(goal.id), api.getStatus(goal.id)]);

  const taskById = Object.fromEntries(tasks.map(t => [t.id, t]));
  const milestoneById = Object.fromEntries((goal.milestones || []).map(m => [m.id, m]));
  const byDate = {};
  schedule.assignments.forEach(a => (byDate[a.date] ??= []).push(a));

  return {
    goal, tasks, status,
    version: schedule.version,
    today: schedule.today,
    byDate,                                  // { 'YYYY-MM-DD': [{task_id, planned_hours}] }
    task: id => taskById[id],
    milestone: id => milestoneById[id],
  };
}
