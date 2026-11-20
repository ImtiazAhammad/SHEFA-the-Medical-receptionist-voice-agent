// SHEFA calls tab: live calls volunteers made with the real booking agent. Each call shows, turn
// by turn, what was said (once a reviewer typed it), what SHEFA heard, what it answered and how
// long each step took, so the founder can see where the agent goes wrong.
import { api } from "./api.js";
import { $, clear, el, toast } from "./dom.js";
import { num, t } from "./i18n.js";

let data = null;
let problemsOnly = true;

export function liveLoaded() { return data !== null; }

export async function loadLive() {
  try {
    data = await api(`/api/admin/live?problems=${problemsOnly ? 1 : 0}&limit=60`);
    renderLive();
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
}

export function initLive() {
  $("#live-problems").addEventListener("change", (e) => { problemsOnly = e.target.checked; loadLive(); });
  $("#live-refresh").addEventListener("click", loadLive);
}

const secs = (ms) => (ms === undefined ? "" : num(Math.round(ms / 100) / 10, 1) + "s");

export function renderLive() {
  if (!data) return;
  const s = data.status || {};
  $("#live-status").textContent = !s.enabled ? t("lv_status_off") : s.ready ? t("lv_status_ready") : t("lv_status_waiting");
  const box = $("#live-calls");
  clear(box);
  if (!data.calls.length) { box.append(el("p", { class: "hint", text: t("lv_none") })); return; }
  for (const c of data.calls) {
    const head = [
      new Date(c.started_at * 1000).toLocaleString(),
      t("lv_turns_n", { n: num(c.turns) }),
      c.end_reason ? t("lv_reason", { r: c.end_reason }) : t("lv_running"),
      c.verdict ? t("lv_verdict", { v: c.verdict }) : "",
      c.errors ? t("lv_errors", { n: num(c.errors) }) : "",
    ].filter(Boolean).join(" · ");
    const rows = c.turns_detail.map((turn) => el("tr", {}, [
      el("td", { text: turn.said || "—" }),
      el("td", { text: turn.heard || t("lv_heard_nothing") }),
      el("td", { text: turn.reply + (turn.language && turn.language !== "bn" ? ` [${turn.language}]` : "") }),
      el("td", { text: [secs(turn.ms.stt_ms), secs(turn.ms.agent_ms), secs(turn.ms.voice_ms)].join(" / ") + (turn.error ? ` (${turn.error})` : "") }),
    ]));
    const table = el("table", { class: "data-table stackable" }, [
      el("thead", {}, el("tr", {}, [t("lv_col_said"), t("lv_col_heard"), t("lv_col_reply"), t("lv_col_time")].map((x) => el("th", { text: x })))),
      el("tbody", {}, rows),
    ]);
    const sit = c.situation || {};
    box.append(el("details", { class: "card" }, [
      el("summary", { text: head }),
      el("p", { class: "hint", text: [sit.who_bn, sit.problem_bn, sit.twist_bn].filter(Boolean).join(" · ") }),
      c.note ? el("p", { text: t("lv_note", { note: c.note }) }) : null,
      el("div", { class: "table-wrap" }, table),
    ]));
  }
}
