/**
 * fixModal.js — shown when remaining work no longer fits before the deadline.
 * The backend works out the options; nothing changes until the user picks one.
 * Bottom sheet on phones, centred window from 768px.
 * openFixModal(goalId, onChanged)
 */
import { api } from '../services/api.js';
import { icon } from '../core/icons.js';
import { esc, openOverlay, closeOverlay, toast } from '../core/dom.js';
import { fmt, hrs } from '../core/dates.js';

export async function openFixModal(goalId, onChanged) {
  let data;
  try { data = await api.getFixOptions(goalId); } catch (err) { toast(err.message); return; }
  const { status: st, options } = data;
  const result = r => r.feasible
    ? `<span class="pill ok">Fits · done by ${fmt(r.finish, { month: 'short', day: 'numeric' })}</span>`
    : `<span class="pill bad">Still ${hrs(r.shortfall_hours)} short</span>`;

  const scrim = openOverlay(`<div class="scrim center"><div class="modal" role="dialog" aria-labelledby="fix-title" aria-describedby="fix-desc">
    <div class="dh"><span class="warn-ic">${icon('alert', 22)}</span>
      <div><h2 id="fix-title">Your remaining work doesn’t fit before ${fmt(st.deadline, { month: 'long', day: 'numeric' })}</h2>
      <p class="muted small gap-sm" id="fix-desc">Planora won’t quietly add hours or move your deadline. Pick what you’d like to change.</p></div>
      <button class="iconbtn x" type="button" data-close aria-label="Close">${icon('x', 18)}</button></div>
    <section class="dsec"><div class="warnbox">
      <div><p class="v">${hrs(st.remaining_hours)}</p><p class="l">remaining work</p></div>
      <div><p class="v">${hrs(st.capacity_hours)}</p><p class="l">time available</p></div>
      <div><p class="v">${st.shortfall_hours > 0 ? hrs(st.shortfall_hours) : 'order'}</p><p class="l">${st.shortfall_hours > 0 ? 'shortfall' : 'task order pushes it past the deadline'}</p></div>
    </div>
    ${st.projected_finish ? `<p class="muted small gap-top">At this pace you’d finish around <b>${fmt(st.projected_finish, { weekday: 'short', month: 'short', day: 'numeric' })}</b>.</p>` : ''}</section>
    <section class="dsec"><h3>Options</h3>
      <ul class="plain-list">${options.map((o, i) => `<li class="fix"><div>
          <p class="t">${esc(o.title)}</p>
          ${o.detail ? `<p class="s">${esc(o.detail)}</p>` : ''}
          ${o.kind !== 'extend_deadline' ? `<p class="s">${result(o.result)}</p>` : ''}
          ${o.needs_consent ? `<label class="consent"><input type="checkbox" data-consent="${i}"> I agree to the extra daily time</label>` : ''}
        </div><button class="btn sm" type="button" data-apply="${i}">Apply</button></li>`).join('')}
        <li class="fix"><div><p class="t">Keep the plan for now</p><p class="s">Work past the deadline stays visible, shaded red</p></div>
          <button class="btn sm ghost" type="button" data-close>Keep</button></li>
      </ul>
    </section></div></div>`);

  scrim.querySelectorAll('[data-apply]').forEach(b => b.addEventListener('click', async () => {
    const o = options[+b.dataset.apply];
    const consent = !!scrim.querySelector(`[data-consent="${b.dataset.apply}"]`)?.checked;
    if (o.needs_consent && !consent) {
      toast('Tick the consent box first. Planora won’t raise your hours without it.');
      scrim.querySelector(`[data-consent="${b.dataset.apply}"]`).focus();
      return;
    }
    b.disabled = true;
    let res;
    try { res = await api.applyFix(goalId, { kind: o.kind, value: o.value, consent }); }
    catch (err) { b.disabled = false; toast(err.message); return; }
    closeOverlay();
    await onChanged?.();
    toast(res.message + (res.status.feasible ? '. The plan fits again.' : '. Still short. Try another option.'));
  }));
}
