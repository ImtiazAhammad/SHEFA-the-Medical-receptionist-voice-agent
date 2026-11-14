// Sign-in: check the token with the server, keep it for this tab only, and go to the right page.
// The token travels in a header, never in the address bar.
import { ApiError, api, clearToken, getToken, setToken, takeFlash } from "./api.js";
import { $ } from "./dom.js";
import { applyI18n, initLangToggle, t } from "./i18n.js";

const form = $("#form");
const input = $("#token");
const message = $("#token-msg");
const go = $("#go");

function route(role) {
  // Relative links so this also works when the pages are mounted under /review/.
  location.replace(role === "admin" ? "admin.html" : "review.html");
}

function say(key) {
  message.textContent = key ? t(key) : "";
  message.hidden = !key;
}

async function tryToken(token, { quiet = false } = {}) {
  go.disabled = true;
  say("");
  try {
    const me = await api("/api/review/me", { token, redirectOnAuth: false });
    setToken(token);
    route(me.role);
  } catch (error) {
    clearToken();
    if (quiet) return;
    if (error instanceof ApiError && error.status === 401) say("si_bad");
    // 403 on /api/review/me: an admin token used on the public (tunnel) address.
    else if (error instanceof ApiError && error.status === 403) say("si_admin_public");
    else say("err_network");
    input.focus();
  } finally {
    go.disabled = false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const token = input.value.trim();
  if (!token) { say("si_empty"); input.focus(); return; }
  tryToken(token);
});
$("#show").addEventListener("change", (event) => { input.type = event.target.checked ? "text" : "password"; });

applyI18n();
initLangToggle($("#lang"));
const flash = takeFlash();
if (flash) {
  const flashBox = $("#flash");
  flashBox.textContent = t(flash === "forbidden" ? "si_forbidden" : "si_expired");
  flashBox.hidden = false;
  clearToken();
} else if (getToken()) {
  tryToken(getToken(), { quiet: true }); // already signed in this tab: go straight on
}
input.focus();
