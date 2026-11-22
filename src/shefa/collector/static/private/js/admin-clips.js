// Clips tab (browse, listen, remove), the audit log, and the CLI help card.
import { api, audioSrc } from "./api.js";
import { $, clear, copyButton, el, toast } from "./dom.js";
import { ask } from "./dialog.js";
import { dateTime, labelFor, num, t } from "./i18n.js";
import { COMMANDS, STATUS_ORDER } from "./admin-model.js";

const PAGE = 25;
let rows = [];
let offset = 0;
let status = "";
let loaded = false;
let events = [];

// ---- clips -----------------------------------------------------------------------------
export async function loadClips() {
  try {
    const query = `status=${encodeURIComponent(status)}&limit=${PAGE}&offset=${offset}`;
    const data = await api(`/api/admin/clips?${query}`);
    rows = Array.isArray(data.clips) ? data.clips : [];
    loaded = true;
    renderClips();
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
}

function textCell(clip) {
  const final = clip.final_text;
  const draft = clip.draft_text;
  return el("td", { "data-label": t("col_text"), lang: "bn" }, [
    final ? el("div", {}, [el("span", { class: "chip good", text: t("text_final") }), ` ${final}`]) : null,
    draft ? el("div", { class: "muted" }, [el("span", { class: "chip", text: t("text_draft") }), ` ${draft}`]) : null,
    !final && !draft ? "-" : null,
  ]);
}

async function removeClip(clip) {
  const { ok, value } = await ask({
    title: t("rm_title"),
    body: [t("rm_body")],
    confirmKey: "rm_btn",
    danger: true,
    input: { label: t("rm_reason"), value: t("rm_reason_default"), maxlength: 120 },
  });
  if (!ok) return;
  try {
    const reply = await api(`/api/admin/clips/${encodeURIComponent(clip.id)}/remove`, { method: "POST", body: { reason: value || "removed by admin" } });
    toast(t(reply.ok ? "rm_done" : "rm_gone"));
    await loadClips();
  } catch (error) {
    toast(t("err_generic"));
  }
}

/** Undo a rejection: one reviewer's reject flag is enough to set a clip aside, so it can be wrong. */
async function restoreClip(clip) {
  const { ok } = await ask({
    title: t("restore_title"),
    body: [t("restore_body")],
    confirmKey: "restore_btn",
  });
  if (!ok) return;
  try {
    const reply = await api(`/api/admin/clips/${encodeURIComponent(clip.id)}/restore`, { method: "POST" });
    toast(t(reply && reply.ok ? "restore_done" : "restore_not_rejected"));
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
  await loadClips();
}

export function renderClips() {
  const select = $("#clip-status");
  if (select.options.length !== STATUS_ORDER.length + 1) {
    clear(select);
    select.append(el("option", { value: "" }, t("all")));
    for (const key of STATUS_ORDER) select.append(el("option", { value: key }, labelFor("status", key)));
  } else {
    select.options[0].textContent = t("all");
    STATUS_ORDER.forEach((key, index) => { select.options[index + 1].textContent = labelFor("status", key); });
  }
  select.value = status;
  $("#clip-prev").disabled = offset === 0;
  $("#clip-next").disabled = rows.length < PAGE;
  $("#clip-page").textContent = t("page_range", { from: num(offset + (rows.length ? 1 : 0)), to: num(offset + rows.length) });

  const table = $("#clip-table");
  clear(table);
  table.append(el("thead", {}, [el("tr", {}, ["col_when", "col_status", "col_slot", "col_split", "col_len", "col_audio", "col_text", ""].map((k) => el("th", { scope: "col", text: k ? t(k) : "" })))]));
  const body = el("tbody");
  if (!rows.length) body.append(el("tr", {}, [el("td", { colspan: 8, text: t("no_data") })]));
  for (const clip of rows) {
    body.append(el("tr", {}, [
      el("td", { "data-label": t("col_when"), text: dateTime(clip.created_at) }),
      el("td", { "data-label": t("col_status") }, [el("span", { class: `chip ${clip.status === "rejected" ? "bad" : ""}`, text: labelFor("status", clip.status) })]),
      el("td", { "data-label": t("col_slot") }, [
        clip.slot ? labelFor("slot", clip.slot) : "-",
        clip.kind ? el("div", { class: "muted small", text: labelFor("kind", clip.kind) }) : null,
      ]),
      el("td", { "data-label": t("col_split"), text: labelFor("split", clip.split) }),
      el("td", { "data-label": t("col_len"), text: `${num(clip.duration_s, 1)} s` }),
      el("td", { "data-label": t("col_audio") }, [
        el("audio", { controls: true, preload: "none", src: audioSrc(clip.audio_url), "aria-label": t("col_audio") }),
      ]),
      textCell(clip),
      el("td", { "data-label": t("col_action") }, [el("div", { class: "row" }, [
        clip.status === "rejected"
          ? el("button", { type: "button", class: "small-btn", onclick: () => restoreClip(clip) }, t("restore_btn"))
          : null,
        clip.status === "removed" || clip.status === "withdrawn"
          ? null
          : el("button", { type: "button", class: "small-btn danger-outline", onclick: () => removeClip(clip) }, t("rm_btn")),
      ])]),
    ]));
  }
  table.append(body);
}

function initClips() {
  $("#clip-status").addEventListener("change", (event) => { status = event.target.value; offset = 0; loadClips(); });
  $("#clip-prev").addEventListener("click", () => { offset = Math.max(0, offset - PAGE); loadClips(); });
  $("#clip-next").addEventListener("click", () => { offset += PAGE; loadClips(); });
}

export function clipsLoaded() { return loaded; }

// ---- audit log and help ----------------------------------------------------------------
export async function loadAudit() {
  try {
    const data = await api("/api/admin/audit?limit=100");
    events = Array.isArray(data.events) ? data.events : [];
    renderAudit();
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
}

export function renderAudit() {
  const list = $("#cmd-list");
  clear(list);
  for (const command of COMMANDS) {
    list.append(el("div", { class: "cmd" }, [el("code", { text: command }), copyButton(t, () => command)]));
  }
  const table = $("#audit-table");
  clear(table);
  table.append(el("thead", {}, [el("tr", {}, ["col_when", "col_actor", "col_action", "col_detail"].map((k) => el("th", { scope: "col", text: t(k) })))]));
  const body = el("tbody");
  if (!events.length) body.append(el("tr", {}, [el("td", { colspan: 4, text: t("no_data") })]));
  for (const event of events) {
    body.append(el("tr", {}, [
      el("td", { "data-label": t("col_when"), text: dateTime(event.at) }),
      el("td", { "data-label": t("col_actor"), text: event.actor }),
      el("td", { "data-label": t("col_action"), text: event.action }),
      el("td", { "data-label": t("col_detail"), text: event.detail }),
    ]));
  }
  table.append(body);
}

export function initClipsTab() { initClips(); }
