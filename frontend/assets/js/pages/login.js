/* Login / sign up (index.html). The form is drawn once per mode; errors update in place,
   so what the user typed (including the password) is never wiped. */
import { api } from '../services/api.js';
import { setToken, clearToken } from '../services/session.js';
import { icon } from '../core/icons.js';
import { esc } from '../core/dom.js';
import { addDemoBanner } from '../components/demoBanner.js';

clearToken(); // the login screen always shows; opening it logs out any earlier session in this tab

const root = document.getElementById('main');
let mode = 'login';
let expired = false;
// Set by services/http.js when a saved login stopped working.
try { expired = sessionStorage.getItem('planora.expired') === '1'; sessionStorage.removeItem('planora.expired'); } catch { /* ignore */ }

const validEmail = e => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);

function render() {
  const signup = mode === 'signup';
  root.innerHTML = `<div class="auth"><div class="card">
    <p class="logo"><i>${icon('target', 16, 2.2)}</i>Planora</p>
    <h1>${signup ? 'Create your account' : 'Welcome back'}</h1>
    <p class="muted">${signup ? 'Start turning goals into plans.' : 'Log in to see today’s plan.'}</p>
    ${expired && !signup ? `<p class="note gap-top" role="status">${icon('lock', 13)}Your session expired. Please log in again.</p>` : ''}
    <form class="form" id="auth" novalidate>
      ${signup ? '<label class="fld">Name<input id="name" name="name" autocomplete="name" required></label>' : ''}
      <label class="fld">Email<input id="email" name="email" type="email" autocomplete="email" inputmode="email" required></label>
      <label class="fld">Password<input id="password" name="password" type="password" required
        autocomplete="${signup ? 'new-password' : 'current-password'}"${signup ? ' minlength="8" aria-describedby="pw-hint"' : ''}></label>
      ${signup ? '<p class="fld-hint" id="pw-hint">At least 8 characters</p>' : ''}
      <p class="err" id="auth-error" role="alert"></p>
      <button class="btn primary block" type="submit">${signup ? 'Sign up' : 'Log in'}</button>
    </form>
    <p class="switch">${signup ? 'Already have an account?' : 'Don’t have an account?'}
      <button type="button" data-mode="${signup ? 'login' : 'signup'}">${signup ? 'Log in' : 'Sign up'}</button></p>
  </div></div>`;
}

/** Show an error under the form and mark/focus the field it's about (if any). */
function showError(message, fieldId) {
  root.querySelectorAll('[aria-invalid]').forEach(el => el.removeAttribute('aria-invalid'));
  root.querySelector('#auth-error').textContent = message;
  const field = fieldId && root.querySelector(`#${fieldId}`);
  if (field) { field.setAttribute('aria-invalid', 'true'); field.focus(); }
}

root.addEventListener('click', e => {
  const b = e.target.closest('[data-mode]');
  if (!b) return;
  mode = b.dataset.mode;
  expired = false;
  render();
  root.querySelector('input').focus();
});

root.addEventListener('submit', async e => {
  e.preventDefault();
  const signup = mode === 'signup';
  const form = e.target;
  const name = signup ? form.name.value.trim() : '';
  const email = form.email.value.trim();
  const password = form.password.value;

  if (signup && !name) return showError('Enter your name.', 'name');
  if (!validEmail(email)) return showError('Enter a valid email address.', 'email');
  if (!password) return showError('Enter your password.', 'password');
  if (signup && password.length < 8) return showError('Password must be at least 8 characters.', 'password');

  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  button.textContent = signup ? 'Creating account…' : 'Logging in…';
  showError('');
  try {
    const res = signup ? await api.signup({ name, email, password }) : await api.login({ email, password });
    setToken(res.token);
    location.href = 'pages/home.html';
  } catch (err) {
    button.disabled = false;
    button.textContent = signup ? 'Sign up' : 'Log in';
    showError(err.message);
  }
});

addDemoBanner();
render();
