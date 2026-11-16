// Sign-in with a username and a password, and the "choose your own password" screen.
// The password travels in the request body and the session token in a header: nothing secret is
// ever put in the address bar. The same page is opened as index.html#password from the other
// pages ("পাসওয়ার্ড বদলান"), and by itself when a one-time password must be replaced.
import { api, clearToken, getToken, setToken, signOut, signOutTo, takeFlash } from "./api.js";
import { $ } from "./dom.js";
import { applyI18n, initLangToggle, onLangChange, t } from "./i18n.js";
import { homeFor, loginErrorKey, passwordError, passwordRules, rulesMet } from "./account-model.js";

const ui = {
  checking: $("#checking"), form: $("#form"), flash: $("#flash"), username: $("#username"),
  password: $("#password"), loginMsg: $("#login-msg"), go: $("#go"),
  pwForm: $("#pw-form"), pwTitle: $("#pw-title"), pwIntro: $("#pw-intro"), pwUsername: $("#pw-username"),
  pwOld: $("#pw-old"), pwOldLabel: $("#pw-old-label"), pwNew: $("#pw-new"), pwAgain: $("#pw-again"),
  pwRules: $("#pw-rules"), pwMsg: $("#pw-msg"), pwGo: $("#pw-go"), pwBack: $("#pw-back"),
};

let me = null;        // {name, username, role, must_change} once signed in
let forced = false;   // true when a one-time password must be replaced before anything else
let flashKey = "";    // one-shot message carried over from another page
let loginKey = "";    // what the sign-in form is saying (kept as a key so the language can change)
let pwSaid = null;    // what the password form is saying: {key, text}

// ---- screens ------------------------------------------------------------------------------
function show(screen) {
  ui.checking.hidden = screen !== "checking";
  ui.form.hidden = screen !== "signin";
  ui.pwForm.hidden = screen !== "password";
  document.documentElement.dataset.titleKey = screen === "password" ? "pw_page_title" : "si_page_title";
  document.title = t(document.documentElement.dataset.titleKey);
}

function paintMessages() {
  ui.flash.textContent = flashKey ? t(flashKey) : "";
  ui.flash.hidden = !flashKey;
  ui.loginMsg.textContent = loginKey ? t(loginKey) : "";
  ui.loginMsg.hidden = !loginKey;
  const text = pwSaid ? [t(pwSaid.key), pwSaid.text].filter(Boolean).join(" ") : "";
  ui.pwMsg.textContent = text;
  ui.pwMsg.hidden = !text;
}
function sayLogin(key) { loginKey = key; paintMessages(); }
function sayPassword(said) { pwSaid = said; paintMessages(); }

function paintRules() {
  const rules = passwordRules(ui.pwNew.value, ui.pwAgain.value, me && me.username);
  for (const row of ui.pwRules.querySelectorAll("li[data-rule]")) {
    const ok = !!rules[row.dataset.rule];
    row.dataset.state = ok ? "ok" : "todo";
    row.firstElementChild.textContent = ok ? "✓" : "•"; // a sign as well as a colour
  }
  return rules;
}

function paintPassword() {
  ui.pwTitle.textContent = t(forced ? "pw_title" : "pw_title_change");
  ui.pwIntro.textContent = t(forced ? "pw_intro_first" : "pw_intro_change");
  ui.pwOldLabel.textContent = t(forced ? "pw_old_first" : "pw_old");
  ui.pwBack.hidden = forced;
  if (me) {
    ui.pwBack.setAttribute("href", homeFor(me.role));
    ui.pwUsername.value = me.username || "";
  }
  paintRules();
}

function showSignIn() {
  show("signin");
  paintMessages();
  ui.username.focus();
}

/** oneTime: the password just typed at sign-in, so the person need not type it a second time. */
function showPassword(mustChange, oneTime = "") {
  forced = mustChange;
  ui.pwOld.value = oneTime;
  ui.pwNew.value = "";
  ui.pwAgain.value = "";
  sayPassword(null);
  paintPassword();
  show("password");
  (oneTime ? ui.pwNew : ui.pwOld).focus();
}

function goHome() {
  // Relative links so this also works when the pages are mounted under /review/.
  location.replace(homeFor(me.role));
}

// ---- sign in ------------------------------------------------------------------------------
async function signIn(event) {
  event.preventDefault();
  const username = ui.username.value.trim();
  const password = ui.password.value; // never trimmed: spaces may be part of a password
  if (!username) { sayLogin("si_empty_user"); ui.username.focus(); return; }
  if (!password) { sayLogin("si_empty_pass"); ui.password.focus(); return; }
  ui.go.disabled = true;
  flashKey = "";
  sayLogin("");
  try {
    const reply = await api("/api/staff/login", { method: "POST", body: { username, password }, token: "", redirectOnAuth: false });
    setToken(reply.token);
    me = { name: reply.name, role: reply.role, username: username.toLowerCase(), must_change: !!reply.must_change };
    ui.password.value = "";
    if (me.must_change) showPassword(true, password);
    else goHome();
  } catch (error) {
    clearToken();
    sayLogin(loginErrorKey(error));
    ui.password.focus();
    ui.password.select();
  } finally {
    ui.go.disabled = false;
  }
}

// ---- choose a password --------------------------------------------------------------------
async function changePassword(event) {
  event.preventDefault();
  const rules = paintRules();
  if (!ui.pwOld.value) { sayPassword({ key: "pw_empty_old" }); ui.pwOld.focus(); return; }
  if (!rulesMet(rules)) {
    const key = !rules.length ? "pw_weak_length" : !rules.digits ? "pw_weak_digits" : !rules.username ? "pw_weak_username" : "pw_mismatch";
    sayPassword({ key });
    (rules.length && rules.digits && rules.username ? ui.pwAgain : ui.pwNew).focus();
    return;
  }
  ui.pwGo.disabled = true;
  sayPassword(null);
  try {
    const reply = await api("/api/staff/password", { method: "POST", body: { old: ui.pwOld.value, new: ui.pwNew.value }, redirectOnAuth: false });
    setToken(reply.token); // the old session ended with the old password: use the new one
    ui.pwOld.value = ui.pwNew.value = ui.pwAgain.value = "";
    goHome();
  } catch (error) {
    // 401 bad_login = the old password is wrong (stay here); any other 401 = the session is gone.
    if (error.status === 401 && error.code !== "bad_login") { signOutTo("expired"); return; }
    if (error.status === 403) { signOutTo("forbidden"); return; }
    sayPassword(passwordError(error));
    if (error.code === "bad_login") { ui.pwOld.focus(); ui.pwOld.select(); } else ui.pwNew.focus();
  } finally {
    ui.pwGo.disabled = false;
  }
}

// ---- events and startup -------------------------------------------------------------------
ui.form.addEventListener("submit", signIn);
ui.pwForm.addEventListener("submit", changePassword);
$("#show").addEventListener("change", (event) => { ui.password.type = event.target.checked ? "text" : "password"; });
$("#pw-show").addEventListener("change", (event) => {
  for (const field of [ui.pwOld, ui.pwNew, ui.pwAgain]) field.type = event.target.checked ? "text" : "password";
});
for (const field of [ui.pwNew, ui.pwAgain]) field.addEventListener("input", () => { paintRules(); if (pwSaid) sayPassword(null); });
ui.pwOld.addEventListener("input", () => { if (pwSaid) sayPassword(null); });
for (const field of [ui.username, ui.password]) field.addEventListener("input", () => { if (loginKey) sayLogin(""); });
$("#pw-signout").addEventListener("click", () => signOut());

async function start() {
  applyI18n();
  initLangToggle($("#lang"));
  onLangChange(() => { paintMessages(); paintPassword(); show(ui.pwForm.hidden ? (ui.form.hidden ? "checking" : "signin") : "password"); });
  const flash = takeFlash();
  if (flash) {
    flashKey = flash === "forbidden" ? "si_forbidden" : "si_expired";
    clearToken();
    showSignIn();
    return;
  }
  if (!getToken()) { showSignIn(); return; }
  // Already signed in this tab: find out who, then go straight on (or to the password screen).
  show("checking");
  try {
    me = await api("/api/review/me", { redirectOnAuth: false });
    if (me.must_change) showPassword(true);
    else if (location.hash === "#password") showPassword(false);
    else goHome();
  } catch (error) {
    if (error.code === "network") loginKey = "err_network";
    else { clearToken(); if (location.hash === "#password") flashKey = "si_expired"; }
    showSignIn();
  }
}

start();
