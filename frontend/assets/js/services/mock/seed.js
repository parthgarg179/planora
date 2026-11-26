/**
 * seed.js — sample data for mock mode only. Not real user history.
 * The goal is placed around today's real date so the dashboard looks current.
 */
import { toKey, addDays, dayOfWeek } from '../../core/dates.js';

export const MILESTONES = [
  { id: 'm1', name: 'Fundamentals', color: '#6b86e8' },
  { id: 'm2', name: 'The browser', color: '#f2c94c' },
  { id: 'm3', name: 'Project build', color: '#5ad19a' },
  { id: 'm4', name: 'Wrap up', color: '#e58bb6' },
];

// [id, title, milestone, category, hours, priority, dependencies, optional, subtasks]
const TASKS = [
  ['t1', 'Set up editor & tools', 'm1', 'setup', 1, 'High', [], false, ['Install VS Code + Live Server', 'Create a practice folder']],
  ['t2', 'Variables, types & operators', 'm1', 'learning', 2, 'High', ['t1'], false, ['let / const / var', 'Strings, numbers, booleans', 'Arithmetic & comparison']],
  ['t3', 'Conditionals & loops', 'm1', 'learning', 2.5, 'High', ['t2'], false, ['if / else, switch', 'for, while, for…of', '10 small exercises']],
  ['t4', 'Functions & scope', 'm1', 'learning', 3, 'High', ['t3'], false, ['Declarations vs arrows', 'Parameters & return', 'Closures (intro)']],
  ['t5', 'Arrays & objects', 'm1', 'learning', 3, 'High', ['t4'], false, ['map / filter / reduce', 'Object literals', 'Destructuring']],
  ['t6', 'Practice set: 20 exercises', 'm1', 'practice', 2.5, 'Normal', ['t5'], false, ['Exercises 1–10', 'Exercises 11–20']],
  ['t7', 'DOM selection & manipulation', 'm2', 'learning', 3, 'High', ['t5'], false, ['querySelector', 'Creating & removing nodes', 'classList & styles']],
  ['t8', 'Events & forms', 'm2', 'learning', 2.5, 'High', ['t7'], false, ['addEventListener', 'Form submit & validation']],
  ['t9', 'Fetch API & async/await', 'm2', 'learning', 4, 'High', ['t5'], false, ['Promises', 'async / await', 'Call a public API']],
  ['t10', 'LocalStorage', 'm2', 'learning', 1, 'Low', ['t7'], true, ['Save & load JSON']],
  ['t11', 'Plan the project & wireframe', 'm3', 'planning', 1.5, 'Normal', ['t8'], false, ['Pick the idea', 'Sketch 2–3 screens']],
  ['t12', 'Build HTML/CSS layout', 'm3', 'project', 3, 'High', ['t11'], false, ['Page structure', 'Responsive styles']],
  ['t13', 'Core JavaScript features', 'm3', 'project', 7, 'High', ['t12', 't9'], false, ['Data model', 'Render list', 'Add / edit / delete', 'API integration']],
  ['t14', 'Extra feature: dark mode', 'm3', 'project', 1.5, 'Low', ['t13'], true, ['Theme toggle', 'Persist choice']],
  ['t15', 'Testing & bug fixes', 'm4', 'testing', 4, 'Normal', ['t13'], false, ['Test main flows', 'Fix bugs', 'Check mobile']],
  ['t16', 'Deploy to GitHub Pages', 'm4', 'setup', 1, 'Normal', ['t15'], false, ['Push repo', 'Enable Pages']],
  ['t17', 'Revision quiz', 'm4', 'revision', 1.5, 'Low', ['t6'], true, ['Quiz', 'Review weak areas']],
];

export function sampleTasks(goalId = 1) {
  return TASKS.map(([id, title, milestone_id, category, h, priority, dependencies, optional, subs], order) => ({
    id, goal_id: goalId, order, title, description: '', milestone_id, category,
    complexity: h >= 4 ? 'High' : h >= 2.5 ? 'Medium' : 'Low',
    initial_estimated_hours: h, predicted_hours: null, remaining_hours: h, actual_hours: 0,
    priority, status: 'todo', optional, dependencies,
    subtasks: subs.map(title => ({ title, done: false })),
  }));
}

const WORKING_DAYS = [1, 2, 3, 4, 5, 6]; // Mon–Sat
const prevWorkingDay = (k) => { let d = addDays(k, -1); while (!WORKING_DAYS.includes(dayOfWeek(d))) d = addDays(d, -1); return d; };
const nthWorkingDay = (k, n) => { let d = k, c = WORKING_DAYS.includes(dayOfWeek(k)) ? 1 : 0; while (c < n) { d = addDays(d, 1); if (WORKING_DAYS.includes(dayOfWeek(d))) c++; } return d; };

export function seedDatabase() {
  let today = toKey(new Date());
  if (!WORKING_DAYS.includes(dayOfWeek(today))) today = addDays(today, 1); // start on a working day
  const d2 = prevWorkingDay(today), d1 = prevWorkingDay(d2);

  const tasks = sampleTasks(1);
  const t = id => tasks.find(x => x.id === id);
  Object.assign(t('t1'), { status: 'done', remaining_hours: 0, actual_hours: 1 }); t('t1').subtasks.forEach(s => (s.done = true));
  Object.assign(t('t2'), { status: 'done', remaining_hours: 0, actual_hours: 2.5 }); t('t2').subtasks.forEach(s => (s.done = true));
  Object.assign(t('t3'), { status: 'in_progress', remaining_hours: 2, actual_hours: 0.5 }); t('t3').subtasks[0].done = true;

  return {
    user: { id: 1, name: 'Alex', email: 'alex@example.com', photo_url: null }, // sample user; Sign up renames it
    goal: {
      id: 1, title: 'Learn JavaScript and build a project', status: 'active',
      start_date: d1, deadline: nthWorkingDay(today, 22),
      daily_available_hours: 2, available_days: WORKING_DAYS,
      start_time: '19:00', reminder_time: '21:30',
      milestones: MILESTONES,
    },
    tasks,
    today,
    version: 3,
    assignments: {
      [d1]: [{ task_id: 't1', planned_hours: 1 }, { task_id: 't2', planned_hours: 1 }],
      [d2]: [{ task_id: 't2', planned_hours: 1 }, { task_id: 't3', planned_hours: 1 }],
    },
    reviews: [
      { date: d1, items: [
        { task_id: 't1', planned_hours: 1, status: 'completed', actual_hours_spent: 1, remaining_hours: 0 },
        { task_id: 't2', planned_hours: 1, status: 'partial', actual_hours_spent: 1, remaining_hours: 1 }] },
      { date: d2, items: [
        { task_id: 't2', planned_hours: 1, status: 'completed', actual_hours_spent: 1.5, remaining_hours: 0 },
        { task_id: 't3', planned_hours: 1, status: 'partial', actual_hours_spent: 0.5, remaining_hours: 2 }] },
    ],
    updates: [
      { version: 3, date: d2, title: 'Schedule v3 · review saved', text: '1 done, 1 partly done. 1.5h left on Conditionals & loops was rescheduled.', bad: false },
      { version: 2, date: d1, title: 'Schedule v2 · review saved', text: '1 done, 1 partly done. 1h of backlog moved to the next day.', bad: false },
      { version: 1, date: d1, title: 'Plan created', text: '17 tasks · 44h estimated across 22+ working days.', bad: false },
    ],
  };
}
