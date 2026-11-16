// Voices tab: which staff members recorded the desk's lines, switching each voice pack on or off,
// listening to the lines, and how often contributors hear a human voice at all.
// Audio needs the Bearer header, so it is fetched into a blob URL and only when asked for.
import { ApiError, api } from "./api.js";
import { $, clear, el, toast } from "./dom.js";
import { ask } from "./dialog.js";
import { labelFor, num, t } from "./i18n.js";
import { groupLines, percentToShare, shareToPercent } from "./voice-model.js";

let voices = null;           // GET /api/admin/voices
let getStats = () => null;
let shareDirty = false;
const expanded = new Set();  // staff ids whose line list is open
const lineState = new Map(); // "id/name" -> "missing" | "error"
const urls = new Map();      // "id/name" -> blob URL
let playing = "";            // "id/name" now playing

const keyOf = (id, name) => `${id}/${name}`;

export function voicesLoaded() { return voices !== null; }

export async function loadVoices() {
  try {
    voices = await api("/api/admin/voices");
    renderVoices(getStats());
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
}

function currentShare(stats) {
  if (voices && Number.isFinite(Number(voices.share))) return Number(voices.share);
  if (stats && Number.isFinite(Number(stats.human_voice_share))) return Number(stats.human_voice_share);
  return 0;
}

function paintShare(stats) {
  const pct = shareToPercent(currentShare(stats));
  if (!shareDirty) $("#share-input").value = String(pct);
  $("#share-text").textContent = t(pct === 0 ? "vo_share_zero" : "vo_share_now", { pct: num(pct) });
}

// ---- playing -------------------------------------------------------------------------------
function player() { return $("#voice-player"); }

function stopPlayback() {
  playing = "";
  player().pause();
}

async function togglePlay(pack, line) {
  const key = keyOf(pack.staff_id, line.name);
  if (playing === key) { stopPlayback(); renderVoices(getStats()); return; }
  stopPlayback();
  try {
    let url = urls.get(key);
    if (!url) {
      const blob = await api(`/api/admin/voices/${encodeURIComponent(pack.staff_id)}/${encodeURIComponent(line.name)}`, { as: "blob" });
      url = URL.createObjectURL(blob);
      urls.set(key, url);
    }
    lineState.delete(key);
    player().src = url;
    playing = key;
    renderVoices(getStats());
    await player().play();
  } catch (error) {
    playing = "";
    lineState.set(key, error instanceof ApiError && error.status === 404 ? "missing" : "error");
    renderVoices(getStats());
  }
}

// ---- switching a pack on or off -------------------------------------------------------------
async function setEnabled(pack, enabled) {
  if (enabled) {
    const { ok } = await ask({
      title: t("vo_on_title", { name: pack.name }),
      body: [t("vo_on_body"), pack.lines ? "" : t("vo_on_empty")].filter(Boolean),
      confirmKey: "vo_turn_on",
    });
    if (!ok) return;
  }
  try {
    await api(`/api/admin/voices/${encodeURIComponent(pack.staff_id)}`, { method: "POST", body: { enabled } });
    toast(t(enabled ? "vo_turned_on" : "vo_turned_off", { name: pack.name }));
  } catch (error) {
    toast(t(error.code === "consent" ? "vo_err_consent" : error.code === "network" ? "err_network" : "err_generic"), 6000);
  }
  await loadVoices();
}

// ---- drawing -------------------------------------------------------------------------------
function yesNo(value) {
  return el("span", { class: `chip ${value ? "good" : ""}`, text: t(value ? "yes" : "no") });
}

function lineList(pack) {
  const list = el("ol", { class: "voice-lines" });
  for (const [group, lines] of groupLines(voices.lines)) {
    for (const line of lines) {
      const key = keyOf(pack.staff_id, line.name);
      const state = lineState.get(key);
      list.append(el("li", {}, [
        el("span", { class: "chip", text: labelFor("group", group) }),
        el("span", { class: "line-text small", lang: "bn", text: ` ${line.text}` }),
        el("div", { class: "row" }, [
          el("button", { type: "button", class: "small-btn", onclick: () => togglePlay(pack, line), "aria-label": `${t(playing === key ? "vr_pause" : "vr_play")}: ${line.text}` }, t(playing === key ? "vr_pause" : "vr_play")),
          state ? el("span", { class: "muted small", text: t(state === "missing" ? "vo_not_recorded" : "vr_play_failed") }) : null,
        ]),
      ]));
    }
  }
  return list;
}

export function renderVoices(stats) {
  if (!voices) return;
  paintShare(stats);
  const table = $("#voice-table");
  clear(table);
  const cols = ["col_name", "vo_col_lines", "vo_col_consent", "vo_col_active", "vo_col_pack", ""];
  table.append(el("thead", {}, [el("tr", {}, cols.map((k) => el("th", { scope: "col", text: k ? t(k) : "" })))]));
  const body = el("tbody");
  const packs = Array.isArray(voices.packs) ? voices.packs : [];
  const total = Number(voices.total_lines) || (Array.isArray(voices.lines) ? voices.lines.length : 0);
  if (!packs.length) body.append(el("tr", {}, [el("td", { colspan: cols.length, text: t("vo_none") })]));
  for (const pack of packs) {
    const open = expanded.has(pack.staff_id);
    const listId = `vo-lines-${pack.staff_id}`;
    const toggle = pack.enabled
      ? el("button", { type: "button", class: "small-btn danger-outline", onclick: () => setEnabled(pack, false) }, t("vo_turn_off"))
      : el("button", { type: "button", class: "small-btn primary", disabled: !pack.consented || !pack.active, onclick: () => setEnabled(pack, true) }, t("vo_turn_on"));
    body.append(el("tr", { class: pack.active ? "" : "inactive" }, [
      el("td", { "data-label": t("col_name"), text: pack.name }),
      el("td", { "data-label": t("vo_col_lines"), text: `${num(pack.lines)} / ${num(total)}` }),
      el("td", { "data-label": t("vo_col_consent") }, [yesNo(pack.consented)]),
      el("td", { "data-label": t("vo_col_active") }, [yesNo(pack.active)]),
      el("td", { "data-label": t("vo_col_pack") }, [el("span", { class: `chip ${pack.enabled ? "good" : ""}`, text: t(pack.enabled ? "vo_on" : "vo_off") })]),
      el("td", { "data-label": t("col_action") }, [el("div", { class: "row" }, [
        toggle,
        el("button", {
          type: "button", class: "small-btn", "aria-expanded": String(open), "aria-controls": listId,
          onclick: () => { if (open) expanded.delete(pack.staff_id); else expanded.add(pack.staff_id); renderVoices(getStats()); },
        }, t(open ? "vo_hide_lines" : "vo_show_lines")),
        !pack.consented ? el("span", { class: "muted small", text: t("vo_no_consent") }) : null,
      ])]),
    ]));
    if (open) {
      body.append(el("tr", { class: "detail-row", id: listId }, [
        el("td", { colspan: cols.length }, [
          el("p", { class: "hint", text: t("vo_lines_hint") }),
          lineList(pack),
        ]),
      ]));
    }
  }
  table.append(body);
}

export function initVoices(statsGetter) {
  getStats = statsGetter;
  $("#share-input").addEventListener("input", () => { shareDirty = true; });
  $("#share-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const share = percentToShare($("#share-input").value);
    if (share === null) { toast(t("vo_share_bad")); $("#share-input").focus(); return; }
    try {
      await api("/api/admin/settings", { method: "POST", body: { human_voice_share: share } });
      shareDirty = false;
      toast(t("saved"));
      await loadVoices();
    } catch (error) {
      toast(t(error.code === "network" ? "err_network" : "err_generic"));
    }
  });
  player().addEventListener("ended", () => { playing = ""; renderVoices(getStats()); });
  window.addEventListener("pagehide", () => { for (const url of urls.values()) URL.revokeObjectURL(url); urls.clear(); });
}
