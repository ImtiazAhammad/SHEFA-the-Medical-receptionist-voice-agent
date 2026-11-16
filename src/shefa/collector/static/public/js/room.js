// "Call a friend", voice-message style. Two people on two phones share a 6-letter code. They take
// turns: the desk speaks first, then the caller answers (one card step per round). Nothing is live:
// each person records their own side, it goes up through the same offline queue, and the other
// phone picks it up within a few seconds. Odd turns belong to the desk, even turns to the caller,
// so both phones can work out whose turn it is from the clip list alone.
import { h, icon, clear, fill } from "./dom.js";
import { T, setT, t, n } from "./i18n.js";
import { api } from "./api.js";
import { S, me } from "./session.js";
import { createCapture } from "./capture.js";
import { settingBlock, personaPicker, patientLine, resolve } from "./card.js";
import * as Q from "./queue.js";
import { copyText, pageLink, waLink } from "./share.js";
import { toast } from "./ui.js";
import { rejectionText } from "./i18n.js";
import { releaseMic } from "./recorder.js";

const WAIT_FOR_PARTNER_MS = 60000;
const MAX_TURNS = 30; // a long call is fine; this only stops a forgotten room from running forever

export function runRoom(view, { code, onFinish, onSolo }) {
  let room = null; // {code, role, card, sheet, partner_here, clips}
  let poll = null, cap = null, dead = false, startedAt = Date.now(), myLast = 0, partnerUrls = new Map(), busyPoll = false;

  function menu(error) {
    const input = h("input", { type: "text", class: "input code", maxlength: "6", autocapitalize: "characters", autocomplete: "off", spellcheck: "false", id: "rcode", "aria-label": t("rm_code_label"), placeholder: "ABC234" });
    input.dataset.ka = "aria-label:rm_code_label";
    const msg = h("p", { class: "warn", role: "alert", hidden: !error }, error ? T(error) : null);
    const go = h("button", { type: "button", class: "btn alt", onclick: () => join(input.value.trim().toUpperCase()) }, T("rm_go"));
    fill(view, h("div", { class: "stack" },
      h("h1", { tabindex: "-1" }, T("rm_title")), h("p", null, T("rm_sub")),
      h("button", { type: "button", class: "btn primary big", onclick: make }, icon("phone"), T("rm_make")),
      h("div", { class: "box" }, h("p", { class: "q" }, T("rm_join")), h("div", { class: "row" }, input, go), msg),
      h("button", { type: "button", class: "btn alt", onclick: () => { destroy(); onFinish(); } }, T("back"))));
  }

  async function make() {
    const r = await api("/api/c/room", { method: "POST", body: {} });
    if (!r.ok) return menu(r.status === 0 ? "server_down" : "err_generic");
    startedAt = Date.now();
    room = { code: r.data.code, role: "caller", card: r.data.card, sheet: null, partner_here: false, clips: [] };
    begin();
  }

  async function join(c) {
    if (!/^[A-Z0-9]{6}$/.test(c)) return menu("rm_no_room");
    const r = await api("/api/c/room/join", { method: "POST", body: { code: c } });
    if (!r.ok) return menu(r.status === 404 ? "rm_no_room" : r.status === 409 ? "rm_full" : r.status === 0 ? "server_down" : "err_generic");
    room = { code: r.data.code, role: r.data.role, card: r.data.card, sheet: r.data.sheet, partner_here: true, clips: [] };
    begin();
  }

  function begin() {
    refresh();
    clearInterval(poll);
    poll = setInterval(refresh, 3000);
  }

  async function refresh() {
    if (dead || busyPoll || document.hidden || !room) return;
    busyPoll = true;
    const r = await api("/api/c/room/" + room.code);
    busyPoll = false;
    if (dead) return;
    if (r.ok) {
      room = { ...room, ...r.data, code: room.code };
    } else if (r.status === 404 || r.status === 401) {
      clearInterval(poll); room = null; menu("rm_no_room"); return;
    }
    render();
  }

  // ---- turn bookkeeping
  function turns() {
    const nums = [myLast, ...room.clips.map((c) => parseInt(c.turn, 10) || 0),
      ...Q.list().filter((q) => q.meta && q.meta.room === room.code).map((q) => q.meta.turn || 0)];
    return Math.max(...nums);
  }

  async function prefetch(clip) {
    if (!clip || partnerUrls.has(clip.id)) return;
    partnerUrls.set(clip.id, "loading");
    const r = await api(`/api/c/room/${room.code}/clip/${clip.id}`, { blob: true });
    partnerUrls.set(clip.id, r.ok ? URL.createObjectURL(r.data) : "");
    if (!r.ok) partnerUrls.delete(clip.id);
    if (!dead) render();
  }

  function partnerBox(clip) {
    if (!clip) return null;
    prefetch(clip);
    const src = partnerUrls.get(clip.id);
    if (!src || src === "loading") return h("p", { class: "muted" }, T("rm_hear_loading"));
    const audio = h("audio", { src, preload: "auto" });
    const b = h("button", { type: "button", class: "btn alt", onclick: () => (audio.paused ? audio.play().catch(() => {}) : audio.pause()) }, icon("play"), T("rm_hear"));
    audio.onplay = () => fill(b, icon("pause"), T("rm_hear"));
    audio.onpause = audio.onended = () => fill(b, icon("play"), T("rm_hear"));
    return h("div", null, audio, b);
  }

  function sheetBox() {
    // 24 doctors is too long to scroll past on a phone: one fold per department.
    const sh = room.sheet;
    if (!sh) return null;
    const depts = [];
    for (const d of sh.doctors) {
      let g = depts.find((x) => x.name === d.dept_bn);
      if (!g) depts.push((g = { name: d.dept_bn, doctors: [] }));
      g.doctors.push(d);
    }
    return h("section", { class: "box" }, h("h2", { class: "small" }, sh.title_bn),
      h("p", { class: "muted" }, sh.tips_bn),
      sh.address_bn && h("p", null, icon("check"), " ", sh.address_bn),
      depts.map((g) => h("details", { class: "sheet-dept" }, h("summary", null, g.name),
        h("ul", { class: "sheet" }, g.doctors.map((d) => h("li", null,
          h("strong", null, d.name_bn),
          h("span", null, `${d.days_bn}, ${d.hours_bn}`),
          h("span", { class: "muted" }, T("rm_fee"), ` ${n(d.fee)} · `, T("rm_room"), ` ${d.room}`)))))));
  }

  function goalsBox(card) {
    const goals = (card.goals_bn || []).map((g) => resolve(g, room.persona)).filter(Boolean);
    if (!goals.length) return null;
    return h("section", { class: "box hint" }, h("h2", { class: "small" }, T("rm_goals")),
      h("ol", { class: "goals" }, goals.map((g) => h("li", null, g))), h("p", { class: "nudge" }, T("nudge")));
  }

  function renderWaiting() {
    const link = `${pageLink()}?room=${room.code}`;
    const msg = t("rm_invite", { code: room.code, url: link });
    const left = Math.max(0, WAIT_FOR_PARTNER_MS - (Date.now() - startedAt));
    const alone = h("div", { class: "stack", hidden: left > 0 },
      h("p", { class: "muted" }, T("rm_alone_hint")),
      h("button", { type: "button", class: "btn alt", onclick: () => { const c = room.card; destroy(); onSolo(c); } }, T("rm_alone")));
    if (left > 0) setTimeout(() => !dead && room && !room.partner_here && render(), left + 50);
    fill(view, h("div", { class: "stack center" },
      h("h1", { tabindex: "-1" }, T("rm_title")),
      h("p", null, T("rm_code_is")),
      h("p", { class: "bigcode", "aria-live": "off" }, room.code),
      h("p", { class: "muted" }, T("rm_wait")),
      h("div", { class: "stack wide" },
        h("a", { class: "btn wa", href: waLink(msg), target: "_blank", rel: "noopener" }, icon("wa"), T("share_wa")),
        h("button", { type: "button", class: "btn alt", onclick: async (e) => { await copyText(link); toast(t("copied")); } }, icon("copy"), T("share_link"))),
      alone));
  }

  function render() {
    if (dead || !room) return;
    if (room.role === "caller" && !room.partner_here) { if (cap) cap.destroy(); cap = null; return renderWaiting(); }
    const card = room.card;
    const max = turns();
    const next = max + 1;
    const finished = max >= MAX_TURNS || room.ended;
    const mine = room.role === "desk" ? next % 2 === 1 : next % 2 === 0;
    const people = card.personas || [];
    if (room.role === "caller" && people.length > 1 && !room.persona && !finished) {
      if (cap && cap.busy()) return;
      // Polling calls render() every few seconds: draw the chooser once, or a tap can land on a
      // button that was just replaced.
      if (view._rk === "persona" && view.firstChild) return;
      view._rk = "persona";
      if (cap) { cap.destroy(); cap = null; }
      fill(view, h("div", { class: "stack" },
        h("section", { class: "box" }, h("h2", { class: "small" }, T("sit_title")), h("p", { class: "situation" }, card.situation_bn)),
        personaPicker(people, (p) => { room.persona = p; view._rk = ""; render(); })));
      return;
    }
    if (room.role === "caller" && !room.persona && people.length === 1) room.persona = people[0];
    const last = room.clips.filter((c) => c.role !== room.role).sort((a, b) => (+b.turn) - (+a.turn))[0];
    const stateKey = [finished, mine, next, last && last.id, partnerUrls.get(last && last.id), room.role].join("|");
    if (view._rk === stateKey && view.firstChild) return; // nothing changed: do not disturb a recording in progress
    if (cap && cap.busy()) return;
    view._rk = stateKey;
    if (cap) { cap.destroy(); cap = null; }

    const head = h("div", { class: "row between" }, h("span", { class: "chip tag" }, room.code),
      h("strong", null, T(room.role === "caller" ? "rm_caller" : "rm_desk")));
    if (finished) {
      fill(view, h("div", { class: "stack center" }, head, h("h1", { tabindex: "-1" }, T("rm_done")),
        partnerBox(last), h("button", { type: "button", class: "btn primary big", onclick: () => { destroy(); onFinish(); } }, T("finish"))));
      return;
    }
    if (!mine) {
      fill(view, h("div", { class: "stack center" }, head,
        h("p", { class: "waiting" }, T(next === 1 ? "rm_turn_first" : "rm_turn_wait")), partnerBox(last)));
      return;
    }
    cap = createCapture({
      maxS: S.cfg.max_clip_s, minS: S.cfg.min_clip_s,
      onAccept: async (res) => {
        const person = me();
        const meta = { card: card.id, setting: person.setting, room: room.code, role: room.role, turn: next,
          persona: room.persona ? room.persona.id : "", autostop: res.cut ? "1" : "" };
        const id = await Q.add({ blob: res.blob, speaker: S.session.speaker, dur: res.dur, meta });
        myLast = next;
        person.n++; person.sec += res.dur;
        const out = navigator.onLine === false ? { outcome: "pending" } : await Q.waitFor(id, 2500);
        if (out.outcome === "rejected") {
          myLast = next - 1; person.n--; person.sec -= res.dur;
          return { redo: true, redoText: rejectionText(out.reason, out.message) };
        }
        view._rk = "";
        refresh();
        return undefined;
      },
    });
    const body = room.role === "caller"
      ? [h("section", { class: "box" }, h("h2", { class: "small" }, T("sit_title")), h("p", { class: "situation" }, card.situation_bn),
          patientLine(room.persona)), goalsBox(card), settingBlock()]
      : [h("p", { class: "q" }, T(next === 1 ? "rm_open" : "rm_ask")), sheetBox(), settingBlock()];
    const end = h("button", { type: "button", class: "linkbtn", onclick: () => { room.ended = true; view._rk = ""; render(); } }, T("rm_end"));
    fill(view, h("div", { class: "stack" }, head, h("p", { class: "turn" }, T("rm_turn_you"), " · ", T("turn_n", { n: next })),
      partnerBox(last), ...body, cap.el, h("div", { class: "row links" }, end)));
    cap.enable(true);
  }

  function destroy() {
    dead = true;
    clearInterval(poll);
    if (cap) cap.destroy();
    partnerUrls.forEach((u) => u && u !== "loading" && URL.revokeObjectURL(u));
    releaseMic();
  }

  if (code) join(code); else menu();
  return { destroy };
}
