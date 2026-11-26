/**
 * mockApi.js — fake backend used while CONFIG.USE_MOCK is true.
 * Same function names and response shapes as services/api.js expects from FastAPI.
 * Data lives in localStorage ("planora.mockdb"). Reset it from the browser console
 * with:  planoraResetMock()
 *
 * One deliberate difference: after an end-of-day review the mock moves "today"
 * to the next working day, so you can test several days in a row. The real
 * backend should just use the server's date.
 */
import { addDays, fmt, hrs, quarter, isWorkingDay } from '../../core/dates.js';
import { schedule, status } from './scheduler.js';
import { seedDatabase, sampleTasks, MILESTONES } from './seed.js';

const KEY = 'planora.mockdb';
let memory = null; // fallback when localStorage is unavailable

function load() {
  try { const raw = localStorage.getItem(KEY); if (raw) return JSON.parse(raw); } catch { /* ignore */ }
  if (!memory) { memory = seedDatabase(); replan(memory); save(memory); }
  return memory;
}
function save(db) { memory = db; try { localStorage.setItem(KEY, JSON.stringify(db)); } catch { /* ignore */ } }
const clone = x => JSON.parse(JSON.stringify(x));
const delay = (v, ms = 120) => new Promise(r => setTimeout(() => r(clone(v)), ms));
const fail = msg => new Promise((_, rej) => setTimeout(() => rej(Object.assign(new Error(msg), { status: 400 })), 120));

export function resetMock() { try { localStorage.removeItem(KEY); } catch { /* ignore */ } memory = null; }
window.planoraResetMock = () => { resetMock(); location.reload(); };

function replan(db) {
  Object.keys(db.assignments).forEach(k => { if (k >= db.today) delete db.assignments[k]; });
  Object.assign(db.assignments, schedule(db.goal, db.tasks, db.today).plan);
}
const nextWorkingDay = (goal, k) => { let d = addDays(k, 1); for (let i = 0; i < 14 && !isWorkingDay(goal, d); i++) d = addDays(d, 1); return d; };
const flatAssignments = db => Object.entries(db.assignments).sort(([a], [b]) => a.localeCompare(b))
  .flatMap(([date, items]) => items.map(i => ({ date, ...i })));
function logUpdate(db, title, text) {
  const st = status(db.goal, db.tasks, db.today);
  db.updates.unshift({ version: db.version, date: db.today, title, text: text + (st.feasible ? '' : ' Doesn’t fit before the deadline.'), bad: !st.feasible });
  return st;
}

/* ---------------- auth & account ---------------- */
// Mock accepts any email + password. The real backend must check them.
export function login({ email }) { const db = load(); db.user.email = email; save(db); return delay({ token: 'mock-token', user: db.user }); }
export function signup({ name, email }) { const db = load(); db.user.name = name; db.user.email = email; save(db); return delay({ token: 'mock-token', user: db.user }); }
export const logout = () => delay(null);
export const getMe = () => delay(load().user);
export function updateMe(patch) { const db = load(); Object.assign(db.user, patch); save(db); return delay(db.user); }
// Mock: counts finished sample tasks in this one goal (the real backend counts across all goals).
export function getEstimates() {
  const finished = load().tasks.filter(t => t.status === 'done' && t.actual_hours > 0).length;
  return delay({ finished_tasks: finished, threshold: 20, model_ready: true, model_synthetic: true });
}
export function changePassword({ current_password, new_password }) {
  if (!current_password) return fail('Enter your current password.');
  if (!new_password || new_password.length < 8) return fail('New password must be at least 8 characters.');
  return delay(null);
}

/* ---------------- goals ---------------- */
// Mock keeps a single goal (a new goal replaces it). The real backend supports several active goals.
export const getActiveGoals = () => delay([load().goal]);

let draft = null; // goal being created in the New goal flow
export function createGoal(input) { draft = { ...input, id: 'draft' }; return delay(draft); }
export function decomposeGoal() {
  const tasks = sampleTasks(1);
  return delay({
    milestones: MILESTONES, tasks,
    checks: [
      { ok: true, label: 'Valid JSON matching the schema' },
      { ok: true, label: `${tasks.length} tasks across ${MILESTONES.length} milestones` },
      { ok: true, label: 'Every dependency exists' },
      { ok: true, label: 'No dependency cycles' },
      { ok: true, label: 'All durations are positive' },
    ],
    used_fallback: false,
  }, 1400);
}
export function createSchedule(_id, { excluded_task_ids = [] }) {
  const db = load();
  db.goal = { ...db.goal, id: 1, title: draft.title, deadline: draft.deadline, daily_available_hours: draft.daily_available_hours, available_days: draft.available_days, start_date: db.today, milestones: MILESTONES };
  db.tasks = sampleTasks(1).map(t => excluded_task_ids.includes(t.id) ? { ...t, status: 'dropped' } : t);
  db.assignments = {}; db.reviews = []; db.updates = []; db.version = 1;
  replan(db);
  const st = status(db.goal, db.tasks, db.today);
  db.updates = [{ version: 1, date: db.today, title: 'Plan created', text: `${db.tasks.filter(t => t.status !== 'dropped').length} tasks · ${hrs(st.remaining_hours)} estimated · ${hrs(st.capacity_hours)} available across ${st.capacity_days} working days.`, bad: !st.feasible }];
  save(db);
  return delay({ goal: db.goal, status: st });
}
export function updatePreferences(_id, prefs) {
  const db = load();
  Object.assign(db.goal, prefs);
  replan(db); db.version++;
  const g = db.goal;
  const st = logUpdate(db, `Schedule v${db.version} · preferences changed`, `${hrs(g.daily_available_hours)}/day, due ${fmt(g.deadline)}.`);
  save(db);
  return delay({ goal: g, status: st, version: db.version });
}

/* ---------------- plan ---------------- */
export const getTasks = () => delay(load().tasks);
export function getSchedule() { const db = load(); return delay({ version: db.version, today: db.today, assignments: flatAssignments(db) }); }
export function getStatus() { const db = load(); return delay(status(db.goal, db.tasks, db.today)); }
export const getUpdates = () => delay(load().updates);
export const getReviews = () => delay(load().reviews);

export function getFixOptions() {
  const db = load(); const g = db.goal;
  const st = status(g, db.tasks, db.today);
  const tryGoal = mod => { const g2 = { ...g, available_days: [...g.available_days] }; mod(g2); return status(g2, db.tasks, db.today); };
  const result = s => ({ feasible: s.feasible, finish: s.projected_finish, shortfall_hours: Math.max(s.shortfall_hours, s.feasible ? 0 : 0.25) });
  const options = [];
  if (st.projected_finish) options.push({ kind: 'extend_deadline', value: st.projected_finish, title: `Extend the deadline to ${fmt(st.projected_finish, { month: 'short', day: 'numeric' })}`, detail: 'Keeps your hours and scope as they are', result: { feasible: true, finish: st.projected_finish }, needs_consent: false });
  for (let h = g.daily_available_hours + 0.5; h <= Math.min(12, g.daily_available_hours + 4); h += 0.5) {
    const s = tryGoal(x => (x.daily_available_hours = h));
    if (s.feasible) { options.push({ kind: 'increase_hours', value: h, title: `Work ${hrs(h)} a day instead of ${hrs(g.daily_available_hours)}`, detail: '', result: result(s), needs_consent: true }); break; }
  }
  const missing = [0, 1, 2, 3, 4, 5, 6].filter(d => !g.available_days.includes(d));
  if (missing.length) {
    const d = missing[0];
    options.push({ kind: 'add_day', value: d, title: `Add ${['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][d]} as a working day`, detail: '', result: result(tryGoal(x => x.available_days.push(d))), needs_consent: false });
  }
  const optional = db.tasks.filter(t => t.optional && t.status !== 'done' && t.status !== 'dropped');
  if (optional.length) {
    const s = status(g, db.tasks.map(t => optional.includes(t) ? { ...t, status: 'dropped' } : t), db.today);
    options.push({ kind: 'drop_optional', value: optional.map(t => t.id), title: 'Drop optional tasks', detail: optional.map(t => `${t.title} (${hrs(t.remaining_hours)})`).join(', '), result: result(s), needs_consent: false });
  }
  return delay({ status: st, options });
}

export function applyFix(_id, { kind, value, consent }) {
  const db = load(); const g = db.goal; let msg = '';
  if (kind === 'increase_hours' && !consent) return fail('Consent is required before raising your daily hours.');
  if (kind === 'extend_deadline') { g.deadline = value; msg = `Deadline moved to ${fmt(value, { month: 'short', day: 'numeric' })}`; }
  if (kind === 'increase_hours') { g.daily_available_hours = value; msg = `Daily time raised to ${hrs(value)}`; }
  if (kind === 'add_day') { g.available_days = [...g.available_days, value]; msg = 'Working day added'; }
  if (kind === 'drop_optional') { db.tasks.forEach(t => { if (value.includes(t.id)) t.status = 'dropped'; }); msg = 'Optional tasks dropped'; }
  replan(db); db.version++;
  const st = logUpdate(db, `Schedule v${db.version} · plan adjusted`, msg + '.');
  save(db);
  return delay({ message: msg, status: st, version: db.version });
}

/* ---------------- tasks & reviews ---------------- */
export function updateTask(taskId, patch) {
  const db = load(); const t = db.tasks.find(x => x.id === taskId);
  Object.assign(t, patch); save(db); return delay(t);
}

export function recordProgress(taskId, { actual_hours_spent = 0, remaining_hours = 0 }) {
  const db = load(); const t = db.tasks.find(x => x.id === taskId);
  t.actual_hours += actual_hours_spent;
  t.remaining_hours = Math.max(0, remaining_hours);
  t.status = t.remaining_hours > 0 ? 'in_progress' : 'done';
  if (t.status === 'done') t.subtasks.forEach(s => (s.done = true));
  replan(db); db.version++;
  const st = logUpdate(db, `Schedule v${db.version} · task updated`, `${t.title}: ${t.status === 'done' ? 'completed' : hrs(t.remaining_hours) + ' left'}.`);
  save(db);
  return delay({ task: t, status: st, version: db.version });
}

export function submitDailyReview(_id, { date, items }) {
  const db = load();
  const planned = db.assignments[date] || [];
  let backlog = 0; const counts = { completed: 0, partial: 0, not_completed: 0 }; const rec = [];
  items.forEach(it => {
    const t = db.tasks.find(x => x.id === it.task_id);
    const p = planned.find(x => x.task_id === it.task_id)?.planned_hours || 0;
    counts[it.status]++;
    if (it.status === 'completed') {
      t.actual_hours += it.actual_hours_spent || 0; t.remaining_hours = 0; t.status = 'done'; t.subtasks.forEach(s => (s.done = true));
    } else if (it.status === 'partial') {
      const rem = Math.max(0, it.remaining_hours || 0);
      t.actual_hours += it.actual_hours_spent || 0;
      backlog += Math.max(0, rem - (t.remaining_hours - p));
      t.remaining_hours = rem; t.status = rem > 0 ? 'in_progress' : 'done';
    } else backlog += p;
    rec.push({ task_id: t.id, planned_hours: p, status: it.status, actual_hours_spent: it.actual_hours_spent || 0, remaining_hours: t.remaining_hours });
  });
  db.reviews.push({ date, items: rec });

  const before = clone(db.assignments);
  db.today = nextWorkingDay(db.goal, date); // mock only: move to the next day
  replan(db); db.version++;
  const changed = [...new Set([...Object.keys(before), ...Object.keys(db.assignments)])].filter(k => k >= db.today).sort()
    .filter(k => JSON.stringify(before[k] || []) !== JSON.stringify(db.assignments[k] || []));
  const spread = changed.slice(0, 4).map(k => fmt(k, { weekday: 'short', day: 'numeric' })).join(', ') + (changed.length > 4 ? ` +${changed.length - 4} more` : '');
  const summary = `${counts.completed} done, ${counts.partial} partly done, ${counts.not_completed} not done. ` +
    (backlog > 0 ? `${hrs(quarter(backlog))} of backlog spread across ${spread || 'later days'}.` : 'No backlog.');
  const st = logUpdate(db, `Schedule v${db.version} · ${fmt(date, { weekday: 'short' })} review`, summary);
  save(db);
  return delay({ version: db.version, today: db.today, backlog_hours: quarter(backlog), changed_dates: changed, summary, status: st });
}

/* ---------------- added with the backend: pending reviews & notifications ---------------- */
export function getPendingReviews() {
  const db = load();
  const done = new Set(db.reviews.map(r => r.date));
  const dates = (db.assignments[db.today] || []).length && !done.has(db.today) ? [db.today] : [];
  return delay({ dates });
}
export function getNotifications() {
  const db = load();
  db.readNotes ??= [];
  const items = db.updates.slice(0, 10).map((u, i) => ({
    id: i + 1, kind: u.bad ? 'deadline_risk' : 'schedule_changed', title: u.title, body: u.text,
    link: u.bad ? 'home.html' : 'schedule.html', created_at: new Date().toISOString(), read: db.readNotes.includes(u.title),
  }));
  return delay({ unread: items.filter(n => !n.read).length, items });
}
export function markNotificationRead(id) {
  const db = load(); db.readNotes ??= [];
  const u = db.updates[id - 1]; if (u && !db.readNotes.includes(u.title)) db.readNotes.push(u.title);
  save(db); return delay(null);
}
export function markAllNotificationsRead() {
  const db = load(); db.readNotes = db.updates.map(u => u.title); save(db); return delay(null);
}
