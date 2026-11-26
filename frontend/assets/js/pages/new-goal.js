/* New goal — 1) four inputs  2) AI breakdown + validation  3) create the schedule. */
import { api } from '../services/api.js';
import { startPage, flash } from '../components/page.js';
import { icon } from '../core/icons.js';
import { esc, toast, renderInto } from '../core/dom.js';
import { toKey, addDays, dayOfWeek, hrs, DAY_NAMES } from '../core/dates.js';
import { taskTable } from '../components/taskList.js';

const STEPS = ['Your goal', 'AI breakdown', 'Schedule'];
const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
const today = toKey(new Date());
const form = { title: '', deadline: addDays(today, 28), daily_available_hours: 2, available_days: [1, 2, 3, 4, 5, 6] };
let step = 1, loading = false, draftGoal = null, breakdown = null, excluded = new Set(), error = '';
let main, usedByOthers = {}; // hours per weekday (0=Sun … 6=Sat) already taken by the user's active goals
const MAX_DAY = 24;            // all goals together can't plan more than 24h on one day

startPage('new-goal', async m => {
  main = m;
  (await api.getActiveGoals()).forEach(g => g.available_days.forEach(d => (usedByOthers[d] = (usedByOthers[d] || 0) + g.daily_available_hours)));
  bind();
  render();
});

/** First chosen day where this goal's hours would push the day past 24h, or null. */
function overFullDay() {
  const d = DAY_ORDER.find(d => form.available_days.includes(d) && (usedByOthers[d] || 0) + form.daily_available_hours > MAX_DAY);
  return d === undefined ? null : d;
}

function capacity() {
  let hours = 0, days = 0;
  for (let d = today; d <= form.deadline; d = addDays(d, 1)) {
    if (form.available_days.includes(dayOfWeek(d))) { hours += form.daily_available_hours; days++; }
  }
  return { hours, days };
}

const stepper = () => `<ol class="steps" aria-label="Steps">${STEPS.map((s, i) => `<li${step === i + 1 ? ' class="on" aria-current="step"' : ''}><i>${i + 1}</i>${s}</li>`).join('')}</ol>`;

function render() {
  if (step === 1) return renderInto(main, `<div class="wrap narrow">${stepper()}${goalForm()}</div>`);
  if (loading) return renderInto(main, `<div class="wrap narrow">${stepper()}${loadingCard()}</div>`);
  renderInto(main, `<div class="wrap">${stepper()}${breakdownView()}</div>`);
}

function goalForm() {
  const cap = capacity();
  return `<div class="intro"><h1 tabindex="-1">What do you want to achieve?</h1><p class="muted">Four inputs. Planora handles the rest.</p></div>
    <div class="card"><form class="form" id="goal-form" novalidate>
      <label class="fld">Goal<textarea id="f-title" rows="2" placeholder="e.g. Learn JavaScript and build a small project"${error && !form.title ? ' aria-invalid="true"' : ''}>${esc(form.title)}</textarea></label>
      <div class="row">
        <label class="fld">Deadline<input id="f-deadline" type="date" value="${form.deadline}" min="${addDays(today, 1)}"></label>
        <label class="fld">Hours per working day<input id="f-hours" type="number" inputmode="decimal" min="0.5" max="12" step="0.5" value="${form.daily_available_hours}"></label>
      </div>
      <fieldset class="fld"><legend>Working days</legend><div class="daychips">${DAY_ORDER.map(d =>
        `<button type="button" data-day="${d}" aria-pressed="${form.available_days.includes(d)}">${DAY_NAMES[d]}</button>`).join('')}</div></fieldset>
      <p class="note" aria-live="polite">${icon('clock', 13)}Total time available: <b>${hrs(cap.hours)}</b> across ${cap.days} working days</p>
      ${othersNote()}
      <p class="err" role="alert">${esc(error)}</p>
      <div><button class="btn primary" type="submit">${icon('spark', 15)} Break it down</button></div>
    </form></div>`;
}

/** With other goals: how many hours a day are still free (only the busiest chosen day matters). */
function othersNote() {
  const chosen = form.available_days.filter(d => usedByOthers[d]);
  if (!chosen.length) return '';
  const busiest = chosen.reduce((a, d) => (usedByOthers[d] > usedByOthers[a] ? d : a));
  const free = Math.max(0, MAX_DAY - usedByOthers[busiest]);
  return `<p class="note">${icon('calendar', 13)}Your other goals already use ${hrs(usedByOthers[busiest])} on ${DAY_NAMES[busiest]}, so this goal can have up to <b>${hrs(free)}</b> a day on the days you picked.</p>`;
}

const loadingCard = () => `<div class="card loading-card" role="status">
    <p class="loading-t">${icon('spark', 18)} Breaking your goal into milestones and tasks…</p>
    ${'<div class="shimmer" aria-hidden="true"></div>'.repeat(6)}
    <p class="muted small">The AI returns structured data, which is checked before anything is scheduled.</p></div>`;

function breakdownView() {
  const { tasks, milestones, checks, used_fallback: usedFallback } = breakdown;
  const byId = Object.fromEntries(tasks.map(t => [t.id, t]));
  const cap = capacity();
  const total = tasks.filter(t => !excluded.has(t.id)).reduce((a, t) => a + t.initial_estimated_hours, 0);
  const allOk = checks.every(c => c.ok);
  const fits = total <= cap.hours;

  const fallbackNotice = usedFallback ? `<div class="result warn" role="status"><span class="ic">${icon('alert', 18)}</span>
      <div><b>The AI couldn’t be reached</b><p class="small">So this is a generic starter plan. You can use it as it is, or try the AI again.</p></div>
      <button class="btn" type="button" id="retry-ai">${icon('refresh', 14)} Try AI again</button></div>` : '';

  const sections = milestones.map(m => `<section class="bd-ms" aria-labelledby="ms-${esc(m.id)}">
      <h2 class="ms-h" id="ms-${esc(m.id)}" style="--c:${esc(m.color)}"><i></i>${esc(m.name)}</h2>
      ${taskTable({
        caption: `${m.name} tasks`,
        interactive: false,
        showHeader: false,
        columns: ['Depends on', 'Estimate', 'Optional'],
        rows: tasks.filter(t => t.milestone_id === m.id).map(t => ({
          task: t,
          muted: excluded.has(t.id),
          title: t.optional ? '<span class="pill line">optional</span>' : '',
          cells: [
            t.dependencies.length ? `<span class="muted small">after ${t.dependencies.map(d => esc(byId[d]?.title || d)).join(', ')}</span>` : '<span class="muted none">—</span>',
            hrs(t.initial_estimated_hours),
            t.optional ? `<button class="link" type="button" data-toggle="${esc(t.id)}" aria-label="${excluded.has(t.id) ? 'Add back' : 'Remove'} ${esc(t.title)}">${excluded.has(t.id) ? 'Add back' : 'Remove'}</button>` : '<span class="none"></span>',
          ],
        })),
      })}</section>`).join('');

  return `<div class="page-h"><div><h1 tabindex="-1">Here’s the breakdown</h1><p>“${esc(form.title)}”</p></div></div>
    ${fallbackNotice}
    <div class="card">
      <ul class="checks" aria-label="Checks on the AI’s plan">${checks.map(c => `<li${c.ok ? '' : ' class="fail"'}>${icon(c.ok ? 'check' : 'alert', 15, 2.4)}${esc(c.label)}</li>`).join('')}</ul>
      ${sections}
      <div class="foot"><span>Estimated <b>${hrs(total)}</b> · available <b>${hrs(cap.hours)}</b></span>
        <span class="pill ${fits ? 'ok' : 'bad'}">${fits ? 'Fits' : 'Doesn’t fit'}</span>
        <span class="btn-row end"><button class="btn" type="button" id="back">Back</button>
          <button class="btn primary" type="button" id="create"${allOk ? '' : ' disabled'}>Create my schedule ${icon('arrowRight', 14)}</button></span></div>
    </div>
    <p class="hint">Durations are AI estimates, so treat them as a starting point.</p>`;
}

function readForm() {
  const t = main.querySelector('#f-title');
  if (!t) return;
  form.title = t.value.trim();
  form.deadline = main.querySelector('#f-deadline').value || form.deadline;
  form.daily_available_hours = +main.querySelector('#f-hours').value || form.daily_available_hours;
}

/** After moving to another step, put focus on its heading so screen readers announce it. */
const focusHeading = () => main.querySelector('h1')?.focus();

async function breakDown() {
  step = 2; loading = true; render();
  try {
    draftGoal = await api.createGoal({ ...form });
    breakdown = await api.decomposeGoal(draftGoal.id);
    excluded = new Set();
  } catch (err) { step = 1; error = err.message; }
  loading = false; render(); focusHeading();
}

async function retryAi() {
  loading = true; render();
  let msg = '';
  try {
    breakdown = await api.decomposeGoal(draftGoal.id);  // same draft goal; the server replaces its earlier breakdown
    excluded = new Set();
    if (breakdown.used_fallback) msg = 'The AI is still unavailable. You can keep the starter plan.';
  } catch (err) { msg = err.message; }
  loading = false; render(); focusHeading();
  if (msg) toast(msg);
}

async function createSchedule(button) {
  button.disabled = true;
  try {
    const res = await api.createSchedule(draftGoal.id, { excluded_task_ids: [...excluded] });
    flash(res.status.feasible ? 'Your schedule is ready.' : 'Your plan doesn’t fit before the deadline. See Goal health for options.');
    location.href = 'home.html';
  } catch (err) { button.disabled = false; toast(err.message); }
}

function bind() {
  main.addEventListener('click', e => {
    const day = e.target.closest('[data-day]');
    if (day) {
      readForm();
      const d = +day.dataset.day;
      form.available_days = form.available_days.includes(d) ? form.available_days.filter(x => x !== d) : [...form.available_days, d];
      return render();
    }
    const tog = e.target.closest('[data-toggle]');
    if (tog) { const id = tog.dataset.toggle; excluded.has(id) ? excluded.delete(id) : excluded.add(id); return render(); }
    if (e.target.closest('#back')) { step = 1; render(); return focusHeading(); }
    if (e.target.closest('#retry-ai')) return retryAi();
    const create = e.target.closest('#create');
    if (create) createSchedule(create);
  });
  main.addEventListener('submit', e => {
    e.preventDefault();
    readForm();
    error = !form.title ? 'Describe your goal.'
      : !form.available_days.length ? 'Pick at least one working day.'
      : form.deadline <= today ? 'The deadline must be after today.'
      : overFullDay() !== null ? `${DAY_NAMES[overFullDay()]} would add up to more than 24h with your other goals. Lower the hours or pick other days.` : '';
    if (error) { render(); return main.querySelector(form.title ? '#f-deadline' : '#f-title').focus(); }
    breakDown();
  });
  main.addEventListener('change', e => { if (['f-deadline', 'f-hours'].includes(e.target.id)) { readForm(); render(); } });
}
