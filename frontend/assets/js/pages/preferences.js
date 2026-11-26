/* Preferences — how the plan is built. Saving replans the unfinished work. */
import { api } from '../services/api.js';
import { startPage, noGoal } from '../components/page.js';
import { icon } from '../core/icons.js';
import { esc, toast } from '../core/dom.js';
import { toKey, DAY_NAMES } from '../core/dates.js';
import { openFixModal } from '../components/fixModal.js';
import { estimatesLine } from '../components/estimates.js';

const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
let main, goal, days, estimates = '';

startPage('preferences', async m => {
  main = m;
  goal = await api.getActiveGoal();
  if (!goal) { main.innerHTML = noGoal(); return; }
  const [est, tasks] = await Promise.all([api.getEstimates(), api.getTasks(goal.id)]);
  estimates = estimatesLine(est, tasks);
  days = [...goal.available_days];
  render();
  bind();
});

function render() {
  main.innerHTML = `<div class="wrap narrow">
    <div class="page-h"><div><h1>Preferences</h1><p>How your plan is built. Changing these replans the work you haven’t done yet. Finished work stays as it is.</p></div></div>
    <div class="card"><form class="form" id="prefs" novalidate>
      <div class="row">
        <label class="fld">Hours per working day<input id="p-hours" type="number" inputmode="decimal" min="0.5" max="12" step="0.5" value="${goal.daily_available_hours}"></label>
        <label class="fld">Deadline<input id="p-deadline" type="date" value="${goal.deadline}" min="${toKey(new Date())}"></label>
      </div>
      <fieldset class="fld"><legend>Working days</legend><div class="daychips">${DAY_ORDER.map(d =>
        `<button type="button" data-day="${d}" aria-pressed="${days.includes(d)}">${DAY_NAMES[d]}</button>`).join('')}</div></fieldset>
      <div class="row">
        <label class="fld">Preferred start time<input id="p-start" type="time" value="${esc(goal.start_time)}"></label>
        <label class="fld">Review reminder<input id="p-reminder" type="time" value="${esc(goal.reminder_time)}"></label>
      </div>
      <div class="fld"><span>Duration estimates</span><p class="note est-line">${icon('spark', 14)}<span>${esc(estimates)}</span></p></div>
      <p class="err msg" id="prefs-error" role="alert"></p>
      <div class="btn-row"><button class="btn primary" type="submit">Save & replan</button><a class="btn ghost" href="home.html">Cancel</a></div>
    </form></div></div>`;
}

function bind() {
  main.addEventListener('click', e => {
    const b = e.target.closest('[data-day]');
    if (!b) return;
    const d = +b.dataset.day;
    days = days.includes(d) ? days.filter(x => x !== d) : [...days, d];
    b.setAttribute('aria-pressed', days.includes(d));
  });
  main.addEventListener('submit', async e => {
    e.preventDefault();
    const errorBox = main.querySelector('#prefs-error');
    const hours = +main.querySelector('#p-hours').value;
    const problem = !days.length ? 'Pick at least one working day.' : !(hours > 0) ? 'Enter how many hours you can work each day.' : '';
    errorBox.textContent = problem;
    if (problem) return;

    const button = e.target.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      const res = await api.updatePreferences(goal.id, {
        daily_available_hours: hours,
        deadline: main.querySelector('#p-deadline').value || goal.deadline,
        available_days: days,
        start_time: main.querySelector('#p-start').value,
        reminder_time: main.querySelector('#p-reminder').value,
      });
      goal = res.goal;
      if (!res.status.feasible) openFixModal(goal.id, () => toast('Plan updated.'));
      else toast(`Saved. Schedule v${res.version} is ready.`);
    } catch (err) {
      errorBox.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  });
}
