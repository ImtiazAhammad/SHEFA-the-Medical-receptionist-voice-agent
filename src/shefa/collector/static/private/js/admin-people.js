// Campaigns tab (invite links) and Team tab (accounts: username, one-time password, reset).
import { api } from "./api.js";
import { $, clear, copyButton, el, toast } from "./dom.js";
import { ask } from "./dialog.js";
import { dateTime, num, t } from "./i18n.js";
import { campaignLink, cerState, normalisePublicAddress, whatsappLink } from "./admin-model.js";
import { staffErrorKey, suggestUsername, usernameOk } from "./account-model.js";

const PUB_KEY = "shefa_public_address";
let campaigns = [];
let highlight = "";
let reloadStats = async () => {};
let people = [];           // GET /api/admin/staff rows
let report = [];           // stats.reviewers: reviews and seed error per person
let myUsername = "";       // the signed-in admin (no reset button on their own row)
// The one-time password box: {kind:"new"|"reset", name, username, password}. Kept in memory only,
// shown once, gone when dismissed or when the page is closed.
let secret = null;
let staffMsg = "";         // the add-person form's message key
let usernameTouched = false;

// ---- public address (the admin runs on the private port, contributors use the public one) ---
function savedAddress() { try { return localStorage.getItem(PUB_KEY) || ""; } catch { return ""; } }
function currentBase() { return normalisePublicAddress($("#pub-input").value); }

/** The fixed public link, once known: fills the address when it is empty or a temporary
 * trycloudflare one (those change on every restart). An address typed on purpose is kept. */
export function offerPublicAddress(url) {
  const input = $("#pub-input");
  const base = normalisePublicAddress(url || "");
  if (!input || !base) return;
  const now = input.value.trim();
  if (now && !/trycloudflare\.com/i.test(now)) return;
  if (currentBase() === base) return;
  input.value = base;
  try { localStorage.setItem(PUB_KEY, base); } catch { /* a convenience only */ }
  paintPubMessage();
  renderCampaigns();
}

function paintPubMessage() {
  const raw = $("#pub-input").value.trim();
  const message = $("#pub-msg");
  if (!raw) message.textContent = t("pub_empty");
  else message.textContent = currentBase() ? t("pub_ok") : t("pub_bad");
}

// ---- campaigns -------------------------------------------------------------------------
export async function loadCampaigns() {
  try {
    const data = await api("/api/admin/campaigns");
    campaigns = Array.isArray(data.campaigns) ? data.campaigns : [];
    renderCampaigns();
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
}

export function renderCampaigns() {
  const list = $("#camp-list");
  clear(list);
  paintPubMessage();
  if (!campaigns.length) { list.append(el("p", { class: "muted", text: t("camp_none") })); return; }
  const base = currentBase();
  for (const campaign of campaigns) {
    const link = base ? campaignLink(base, campaign.code) : "";
    const message = t("wa_message", { link, from: campaign.from_name || "" }).trim();
    const linkInput = el("input", { type: "text", readonly: true, value: link, "aria-label": t("camp_link"), placeholder: t("camp_need_address") });
    list.append(el("section", { class: `card${campaign.code === highlight ? " banner ok" : ""}`, "aria-label": campaign.name }, [
      el("h3", { text: campaign.name }),
      el("p", { class: "muted small" }, [
        campaign.from_name ? `${t("camp_from_short")}: ${campaign.from_name} · ` : "",
        `${t("camp_people")}: ${num(campaign.people)} · ${t("camp_clips")}: ${num(campaign.clips)} · ${dateTime(campaign.created_at)}`,
      ]),
      el("div", { class: "link-box" }, [
        linkInput,
        copyButton(t, () => linkInput.value),
        base ? el("a", { class: "btn small-btn", href: whatsappLink(message), target: "_blank", rel: "noopener noreferrer" }, t("camp_whatsapp")) : null,
      ]),
    ]));
  }
}

function initCampaigns() {
  const input = $("#pub-input");
  input.value = savedAddress();
  input.addEventListener("input", () => {
    const base = currentBase();
    try { localStorage.setItem(PUB_KEY, base || ""); } catch { /* a convenience only */ }
    renderCampaigns();
  });
  $("#camp-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("#camp-name").value.trim();
    if (!name) { $("#camp-name").focus(); return; }
    try {
      const made = await api("/api/admin/campaigns", { method: "POST", body: { name, from_name: $("#camp-from").value.trim() } });
      highlight = made.code;
      $("#camp-name").value = "";
      $("#camp-from").value = "";
      toast(t("camp_created"));
      await loadCampaigns();
    } catch (error) {
      toast(t("err_generic"));
    }
  });
}

// ---- team ------------------------------------------------------------------------------
export function setMe(me) { myUsername = String((me && me.username) || "").toLowerCase(); }

export async function loadStaff() {
  try {
    const data = await api("/api/admin/staff");
    people = Array.isArray(data.staff) ? data.staff : [];
    paintTeam();
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
}

function renderSecret() {
  const slot = $("#secret-slot");
  clear(slot);
  if (!secret) return;
  const shown = secret;
  const both = () => `${t("secret_copy_text", { username: shown.username, password: shown.password })}`;
  slot.append(el("section", { class: "token-box stack", role: "alert", "aria-labelledby": "secret-h" }, [
    el("h2", { id: "secret-h", text: t(shown.kind === "reset" ? "secret_title_reset" : "secret_title_new", { name: shown.name }) }),
    el("dl", { class: "secret-list" }, [
      el("dt", { text: t("staff_username") }), el("dd", {}, [el("code", { text: shown.username })]),
      el("dt", { text: t("secret_password") }), el("dd", {}, [el("code", { class: "secret", text: shown.password })]),
    ]),
    el("p", { text: t("secret_rules") }),
    el("p", { class: "hint", text: t("secret_warn") }),
    el("div", { class: "row" }, [
      copyButton(t, () => shown.password, "secret_copy_pw"),
      copyButton(t, both, "secret_copy_both"),
      el("button", { type: "button", class: "primary", onclick: () => { secret = null; renderSecret(); $("#staff-name").focus(); } }, t("secret_dismiss")),
    ]),
  ]));
}

function showSecret(value) {
  secret = value;
  renderSecret();
  const box = $("#secret-slot");
  box.scrollIntoView({ block: "nearest" });
  const first = box.querySelector("button");
  if (first) first.focus({ preventScroll: true });
}

function paintStaffMsg() {
  const box = $("#staff-msg");
  box.textContent = staffMsg ? t(staffMsg) : "";
  box.hidden = !staffMsg;
}

async function deactivate(person) {
  const { ok } = await ask({
    title: t("deact_title", { name: person.name }),
    body: [t("deact_body"), t("deact_lockout")],
    confirmKey: "deact_btn",
    danger: true,
  });
  if (!ok) return;
  try {
    await api(`/api/admin/staff/${encodeURIComponent(person.id)}`, { method: "DELETE" });
    toast(t("deact_done"));
  } catch (error) {
    toast(t(staffErrorKey(error)), 6000);
  }
  await refreshTeam();
}

async function resetPassword(person) {
  const { ok } = await ask({
    title: t("reset_title", { name: person.name }),
    body: [t("reset_body"), person.has_password ? "" : t("reset_body_token")].filter(Boolean),
    confirmKey: "reset_btn",
    danger: true,
  });
  if (!ok) return;
  try {
    const made = await api(`/api/admin/staff/${encodeURIComponent(person.id)}/reset`, { method: "POST" });
    showSecret({ kind: "reset", name: person.name, username: String(made.username || person.username || ""), password: String(made.password || "") });
  } catch (error) {
    // A first-version account has no username; the server makes one from the name and refuses a
    // name it cannot turn into one (a Bangla name, a space). Tell the admin the terminal way.
    const key = error.code === "bad_username" || error.code === "taken" ? "reset_err_username" : staffErrorKey(error);
    toast(t(key, { name: person.name }), 9000);
  }
  await refreshTeam();
}

/** One person's account state, as chips (a word as well as a colour). */
function stateChips(person) {
  const chips = [];
  if (!person.active) chips.push(el("span", { class: "chip", text: t("inactive") }));
  else chips.push(el("span", { class: "chip good", text: t("active") }));
  if (!person.has_password) chips.push(el("span", { class: "chip warn", text: t("st_no_password") }));
  else if (person.must_change) chips.push(el("span", { class: "chip warn", text: t("st_must_change") }));
  return el("div", { class: "meta-chips" }, chips);
}

function paintTeam() {
  renderSecret();
  const table = $("#team-table");
  clear(table);
  const head = el("tr", {}, ["col_name", "col_username", "col_role", "col_state", "col_reviews", "col_seed", ""].map((key) => el("th", { scope: "col", text: key ? t(key) : "" })));
  table.append(el("thead", {}, [head]));
  const body = el("tbody");
  const byId = new Map(report.map((row) => [row.id, row]));
  // The account list is the source; before it arrives fall back to the stats report.
  const rows = people.length ? people : report.map((row) => ({ ...row, username: "", must_change: 0, has_password: true }));
  if (!rows.length) body.append(el("tr", {}, [el("td", { colspan: 7, text: t("no_data") })]));
  for (const person of rows) {
    const stats = byId.get(person.id) || {};
    const state = cerState(stats.seed_cer);
    const seedCell = el("td", { "data-label": t("col_seed") }, [
      state === "none" ? "-" : num(stats.seed_cer, 2),
      state === "none" ? "" : ` (${t("seeds_n", { n: num(stats.seeds) })}) `,
      state === "high" ? el("span", { class: "chip bad", text: t("cer_high") }) : null,
    ]);
    const mine = !!myUsername && String(person.username || "").toLowerCase() === myUsername;
    const actions = [];
    if (person.active && !mine) {
      actions.push(el("button", { type: "button", class: "small-btn", onclick: () => resetPassword(person) }, t("reset_btn")));
      actions.push(el("button", { type: "button", class: "small-btn danger-outline", onclick: () => deactivate(person) }, t("deact_btn")));
    }
    if (mine) actions.push(el("span", { class: "muted small", text: t("staff_is_you") }));
    body.append(el("tr", { class: person.active ? "" : "inactive" }, [
      el("td", { "data-label": t("col_name"), text: person.name }),
      el("td", { "data-label": t("col_username") }, [person.username ? el("code", { text: person.username }) : el("span", { class: "muted", text: "-" })]),
      el("td", { "data-label": t("col_role"), text: t(`role_${person.role}`) }),
      el("td", { "data-label": t("col_state") }, [stateChips(person)]),
      el("td", { "data-label": t("col_reviews"), text: num(stats.reviews) }),
      seedCell,
      el("td", { "data-label": t("col_action") }, [el("div", { class: "row" }, actions)]),
    ]));
  }
  table.append(body);
  paintStaffMsg();
}

export function renderTeam(stats) {
  report = Array.isArray(stats && stats.reviewers) ? stats.reviewers : [];
  paintTeam();
}

/** The stats reload also fetches the account list (admin.js reload). */
async function refreshTeam() {
  await reloadStats();
}

function initTeam() {
  const name = $("#staff-name");
  const username = $("#staff-username");
  name.addEventListener("input", () => {
    if (!usernameTouched) username.value = suggestUsername(name.value);
    if (staffMsg) { staffMsg = ""; paintStaffMsg(); }
  });
  username.addEventListener("input", () => {
    usernameTouched = username.value.trim() !== "";
    if (staffMsg) { staffMsg = ""; paintStaffMsg(); }
  });
  $("#staff-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const fullName = name.value.trim();
    const user = username.value.trim().toLowerCase();
    if (!fullName) { staffMsg = "staff_err_name"; paintStaffMsg(); name.focus(); return; }
    if (!user) { staffMsg = "staff_err_no_username"; paintStaffMsg(); username.focus(); return; }
    if (!usernameOk(user)) { staffMsg = "staff_err_username"; paintStaffMsg(); username.focus(); return; }
    const role = $("#staff-role").value;
    $("#staff-go").disabled = true;
    staffMsg = "";
    paintStaffMsg();
    try {
      const made = await api("/api/admin/staff", { method: "POST", body: { name: fullName, role, username: user } });
      name.value = "";
      username.value = "";
      usernameTouched = false;
      showSecret({ kind: "new", name: fullName, username: String(made.username || user), password: String(made.password || "") });
      await refreshTeam();
    } catch (error) {
      staffMsg = staffErrorKey(error);
      paintStaffMsg();
      (error.code === "taken" || error.code === "bad_username" ? username : name).focus();
    } finally {
      $("#staff-go").disabled = false;
    }
  });
}

export function initPeople(reload) {
  reloadStats = reload;
  initCampaigns();
  initTeam();
}
