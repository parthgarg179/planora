/**
 * estimates.js — is this plan using the AI's estimates or the user's own pace?
 * `est` comes from GET /users/me/estimates. Predictions are made when a goal is scheduled,
 * so a user who passes the threshold mid-goal gets them from their next goal.
 */
import { icon } from '../core/icons.js';

/** 'learning' (not enough history) | 'no_model' | 'on' (this plan uses it) | 'next_goal' */
export function estimatesState(est, tasks) {
  if (est.finished_tasks < est.threshold) return 'learning';
  if (!est.model_ready) return 'no_model';
  return tasks.some(t => t.predicted_hours != null) ? 'on' : 'next_goal';
}

/** The Progress page card. */
export function estimatesCard(est, tasks) {
  const n = est.finished_tasks, need = est.threshold;
  const synthetic = est.model_synthetic ? '<p class="muted small gap-sm">Model trained on synthetic sample data for now.</p>' : '';
  const box = (ic, title, body) => `<div class="lock"><span class="ic">${icon(ic, 18)}</span><div><h2 class="lock-t">${title}</h2>
      <div class="muted small gap-sm">${body}</div></div></div>`;

  switch (estimatesState(est, tasks)) {
    case 'learning':
      return box('lock', 'Personalised estimates', `<p>Estimates come from the AI. Planora starts learning your pace after <b>${need} finished tasks with logged time</b>.</p>
        <div class="meter gap-md" role="img" aria-label="${n} of ${need} finished tasks"><i style="--w:${Math.min(100, n / need * 100)}%"></i></div>
        <p class="gap-sm">${n} / ${need} finished</p>`);
    case 'no_model':
      return box('lock', 'Personalised estimates', `<p>Estimates come from the AI. You have ${n} finished tasks, but no trained model is installed.</p>`);
    case 'on':
      return box('check', 'Personalised estimates · on', `<p>This plan uses your own pace (based on ${n} finished tasks).</p>${synthetic}`);
    default:
      return box('check', 'Personalised estimates · unlocked', `<p>Your next goal will use your own pace (based on ${n} finished tasks). This plan keeps its AI estimates.</p>${synthetic}`);
  }
}


/** One short line for the Preferences page. */
export function estimatesLine(est, tasks) {
  const n = est.finished_tasks, need = est.threshold;
  return {
    learning: `AI estimates. Personalised estimates start after ${need} finished tasks (${n} / ${need} so far).`,
    no_model: `AI estimates. You have ${n} finished tasks, but no trained model is installed.`,
    on: `Personalised: this plan uses your own pace, based on ${n} finished tasks.`,
    next_goal: `Personalised estimates are unlocked (${n} finished tasks). Your next goal will use them; this plan keeps its AI estimates.`,
  }[estimatesState(est, tasks)] + (est.model_synthetic && n >= need ? ' The model is trained on synthetic sample data for now.' : '');
}
