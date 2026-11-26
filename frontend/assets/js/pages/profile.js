/* Personal details — photo, name, email, password.
   Messages update in place, so a failed save never wipes what the user typed. */
import { api } from '../services/api.js';
import { startPage } from '../components/page.js';
import { refreshAvatar } from '../components/shell.js';
import { esc } from '../core/dom.js';

const MAX_PHOTO_MB = 2;
const validEmail = e => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);
let main, user;

startPage('profile', async m => { main = m; user = await api.getMe(); render(); bind(); });

function render() {
  main.innerHTML = `<div class="wrap narrow">
    <div class="page-h"><div><h1>Personal details</h1><p>Your account information.</p></div></div>
    <section class="card" aria-labelledby="details-h"><form class="form" id="details" novalidate>
      <h2 class="sr-only" id="details-h">Profile</h2>
      <div class="photo">
        <div><p class="form-title">Profile photo</p><p class="muted small">${user.photo_url ? 'Shown in the navigation and the profile menu.' : 'No photo yet. Your initial is shown instead.'}</p></div>
        <div class="btn-row">
          <label class="btn sm file-btn">Upload photo<input type="file" id="photo" class="sr-only" accept="image/*"></label>
          ${user.photo_url ? '<button type="button" class="btn sm ghost danger" id="rm-photo">Remove</button>' : ''}
        </div>
      </div>
      <p class="msg" id="msg-photo" aria-live="polite"></p>
      <div class="row">
        <label class="fld">Name<input id="name" value="${esc(user.name)}" autocomplete="name" required></label>
        <label class="fld">Email<input id="email" type="email" inputmode="email" value="${esc(user.email)}" autocomplete="email" required></label>
      </div>
      <p class="msg" id="msg-details" aria-live="polite"></p>
      <div><button class="btn primary" type="submit">Save changes</button></div>
    </form></section>

    <section class="card" aria-labelledby="pw-h"><form class="form" id="password" novalidate>
      <h2 class="form-title" id="pw-h">Change password</h2>
      <input type="text" name="username" autocomplete="username" value="${esc(user.email)}" hidden>
      <label class="fld">Current password<input id="pw-current" type="password" autocomplete="current-password" required></label>
      <div class="row">
        <label class="fld">New password<input id="pw-new" type="password" autocomplete="new-password" minlength="8" aria-describedby="pw-hint" required></label>
        <label class="fld">Confirm new password<input id="pw-confirm" type="password" autocomplete="new-password" required></label>
      </div>
      <p class="fld-hint" id="pw-hint">At least 8 characters</p>
      <p class="msg" id="msg-password" aria-live="polite"></p>
      <div><button class="btn" type="submit">Update password</button></div>
    </form></section></div>`;
}

/** Show a message under a form; mark and focus the field it's about, if any. */
function say(key, ok, text, fieldId) {
  const box = main.querySelector(`#msg-${key}`);
  box.className = `msg ${ok ? 'ok-msg' : 'err'}`;
  box.textContent = text;
  box.closest('form').querySelectorAll('[aria-invalid]').forEach(el => el.removeAttribute('aria-invalid'));
  const field = fieldId && main.querySelector(`#${fieldId}`);
  if (field) { field.setAttribute('aria-invalid', 'true'); field.focus(); }
}

async function saveUser(patch, key, okText, { rerender = false } = {}) {
  try {
    user = await api.updateMe(patch);
    refreshAvatar(user);
    if (rerender) render();
    say(key, true, okText);
  } catch (err) { say(key, false, err.message); }
}

function bind() {
  main.addEventListener('submit', async e => {
    e.preventDefault();
    if (e.target.id === 'details') {
      const name = main.querySelector('#name').value.trim();
      const email = main.querySelector('#email').value.trim();
      if (!name) return say('details', false, 'Name can’t be empty.', 'name');
      if (!validEmail(email)) return say('details', false, 'Enter a valid email address.', 'email');
      return saveUser({ name, email }, 'details', 'Saved.');
    }
    if (e.target.id === 'password') {
      const cur = main.querySelector('#pw-current').value;
      const nw = main.querySelector('#pw-new').value;
      const cf = main.querySelector('#pw-confirm').value;
      if (!cur) return say('password', false, 'Enter your current password.', 'pw-current');
      if (nw.length < 8) return say('password', false, 'New password must be at least 8 characters.', 'pw-new');
      if (nw !== cf) return say('password', false, 'The new passwords don’t match.', 'pw-confirm');
      try {
        await api.changePassword({ current_password: cur, new_password: nw });
        e.target.reset();
        say('password', true, 'Password updated.');
      } catch (err) { say('password', false, err.message, 'pw-current'); }
    }
  });
  main.addEventListener('click', e => {
    if (e.target.closest('#rm-photo')) saveUser({ photo_url: null }, 'photo', 'Photo removed.', { rerender: true });
  });
  main.addEventListener('change', e => {
    if (e.target.id !== 'photo') return;
    const file = e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) return say('photo', false, 'Choose an image file.');
    if (file.size > MAX_PHOTO_MB * 1024 * 1024) return say('photo', false, `Photo must be under ${MAX_PHOTO_MB} MB.`);
    // The image is sent as a data URL. A production backend would take a multipart upload instead.
    const reader = new FileReader();
    reader.onload = () => saveUser({ photo_url: reader.result }, 'photo', 'Photo updated.', { rerender: true });
    reader.readAsDataURL(file);
  });
}
