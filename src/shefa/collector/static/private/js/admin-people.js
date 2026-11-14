// Campaigns tab (invite links) and Team tab (reviewers, tokens).
import { api } from "./api.js";
import { $, clear, copyButton, el, toast } from "./dom.js";
import { ask } from "./dialog.js";
import { dateTime, num, t } from "./i18n.js";
import { campaignLink, cerState, normalisePublicAddress, whatsappLink } from "./admin-model.js";

const PUB_KEY = "shefa_public_address";
let campaigns = [];
let highlight = "";
let tokenShown = null; // {name, token}: the one-time token box
let reloadStats = async () => {};

// ---- public address (the admin runs on the private port, contributors use the public one) ---
function savedAddress() { try { return localStorage.getItem(PUB_KEY) || ""; } catch { return ""; } }
function currentBase() { return normalisePublicAddress($("#pub-input").value); }

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
function renderToken() {
  const slot = $("#token-slot");
  clear(slot);
  if (!tokenShown) return;
  slot.append(el("section", { class: "token-box", role: "alert" }, [
    el("strong", { text: t("token_once", { name: tokenShown.name }) }),
    el("code", { text: tokenShown.token }),
    el("div", { class: "row" }, [
      copyButton(t, () => tokenShown.token),
      el("button", { type: "button", onclick: () => { tokenShown = null; renderToken(); } }, t("token_dismiss")),
    ]),
    el("p", { class: "hint", text: t("token_warn") }),
  ]));
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
    await reloadStats();
  } catch (error) {
    toast(t("err_generic"));
  }
}

export function renderTeam(stats) {
  renderToken();
  const table = $("#team-table");
  clear(table);
  const head = el("tr", {}, ["col_name", "col_role", "col_reviews", "col_seed", ""].map((key) => el("th", { scope: "col", text: key ? t(key) : "" })));
  table.append(el("thead", {}, [head]));
  const body = el("tbody");
  for (const person of stats.reviewers || []) {
    const state = cerState(person.seed_cer);
    const seedCell = el("td", { "data-label": t("col_seed") }, [
      state === "none" ? "—" : num(person.seed_cer, 2),
      state === "none" ? "" : ` (${t("seeds_n", { n: num(person.seeds) })}) `,
      state === "high" ? el("span", { class: "chip bad", text: t("cer_high") }) : null,
    ]);
    body.append(el("tr", { class: person.active ? "" : "inactive" }, [
      el("td", { "data-label": t("col_name"), text: person.name }),
      el("td", { "data-label": t("col_role"), text: t(`role_${person.role}`) }),
      el("td", { "data-label": t("col_reviews"), text: num(person.reviews) }),
      seedCell,
      el("td", { "data-label": t("col_action") }, [
        person.active
          ? el("button", { type: "button", class: "small-btn danger-outline", onclick: () => deactivate(person) }, t("deact_btn"))
          : el("span", { class: "chip", text: t("inactive") }),
      ]),
    ]));
  }
  table.append(body);
}

function initTeam() {
  $("#staff-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("#staff-name").value.trim();
    if (!name) { $("#staff-name").focus(); return; }
    try {
      const made = await api("/api/admin/staff", { method: "POST", body: { name, role: $("#staff-role").value } });
      tokenShown = { name, token: made.token };
      $("#staff-name").value = "";
      await reloadStats();
      $("#token-slot").scrollIntoView({ block: "nearest" });
    } catch (error) {
      toast(t("err_generic"));
    }
  });
}

export function initPeople(reload) {
  reloadStats = reload;
  initCampaigns();
  initTeam();
}
