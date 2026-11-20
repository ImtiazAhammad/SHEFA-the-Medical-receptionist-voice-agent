// A live call with the real SHEFA agent. Each turn: tap to talk, tap to stop; the clip is sent
// at once (never queued offline: a late turn means nothing in a live call), SHEFA transcribes it,
// answers, and the answer is spoken. The volunteer sees what SHEFA heard, so its mistakes show.
import { h, icon, clear, fill } from "./dom.js";
import { T, t } from "./i18n.js";
import { api } from "./api.js";
import { S, me, save } from "./session.js";
import { createCapture } from "./capture.js";
import { settingBlock } from "./card.js";
import { newClipId } from "./queue.js";
import { rejectionText } from "./i18n.js";

const VERDICTS = [["ok", "lv_v_ok"], ["misheard", "lv_v_misheard"], ["odd", "lv_v_odd"], ["slow", "lv_v_slow"], ["other", "lv_v_other"]];

export async function liveStatus() {
  const r = await api("/api/c/live", { auth: false, timeout: 8000 });
  return r.ok ? r.data : { enabled: false, ready: false, busy: false };
}

export function runLive(view, { onFinish, onScripted }) {
  let dead = false, call = null, cap = null, audio = null, audioUrl = "", turns = 0, ended = false;
  const log = h("div", { class: "live-log", "aria-live": "polite" });
  const cue = h("p", { class: "cue", role: "status" });
  const warn = h("p", { class: "warn", role: "alert", hidden: true });
  const listenBtn = h("button", { type: "button", class: "btn alt", hidden: true }, icon("sound"), T("lv_tap_hear"));

  function say(key, params) { fill(cue, T(key, params)); }
  function showWarn(text) { warn.hidden = !text; warn.textContent = text || ""; }

  function stopAudio() {
    if (audio) { audio.onended = null; audio.pause(); audio = null; }
    if (audioUrl) { URL.revokeObjectURL(audioUrl); audioUrl = ""; }
  }

  // Play SHEFA's answer, then hand the turn back. A phone that blocks sound gets a tap button;
  // a phone that never reports "ended" is unlocked after the clip's own length.
  function speak(b64, then) {
    stopAudio();
    listenBtn.hidden = true;
    if (!b64) { then(); return; }
    let done = false;
    const finish = () => { if (done || dead) return; done = true; listenBtn.hidden = true; then(); };
    try {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      audioUrl = URL.createObjectURL(new Blob([bytes], { type: "audio/mp4" }));
    } catch { then(); return; }
    const a = new Audio(audioUrl);
    audio = a;
    a.onended = finish;
    a.onerror = finish;
    a.onloadedmetadata = () => {
      const secs = Number.isFinite(a.duration) && a.duration > 0 ? a.duration : 20;
      setTimeout(finish, (secs + 2) * 1000);
    };
    say("lv_speaking");
    a.play().catch(() => {
      say("lv_tap_needed");
      listenBtn.hidden = false;
      listenBtn.onclick = () => { a.play().catch(finish); listenBtn.hidden = true; };
      setTimeout(finish, 8000); // never stay locked
    });
  }

  function bubble(who, text, extra) {
    log.append(h("div", { class: "live-turn " + who },
      h("p", { class: "bubble-who" }, T(who === "shefa" ? "lv_shefa" : "lv_you")),
      h("p", { class: "bubble-text", lang: "bn" }, text), extra || null));
    log.lastChild.scrollIntoView({ block: "nearest" });
  }

  // ---------------------------------------------------------------- intro
  async function intro() {
    const status = await liveStatus();
    if (dead) return;
    const go = h("button", { type: "button", class: "btn primary big" }, icon("phone"), T("lv_start"));
    const note = h("p", { class: "warn", role: "status", hidden: true });
    if (!status.ready) { note.hidden = false; fill(note, T("lv_off")); go.disabled = true; }
    else if (status.busy) { note.hidden = false; fill(note, T("lv_busy")); }
    go.onclick = start;
    fill(view, h("div", { class: "stack" },
      h("h1", null, T("lv_title")),
      h("p", { class: "lead-text" }, T("lv_sub")),
      h("section", { class: "box" }, h("ul", { class: "consent" },
        h("li", null, T("lv_rule_test")), h("li", null, T("lv_rule_talk")), h("li", null, T("lv_rule_emergency")))),
      settingBlock(), note, go,
      h("button", { type: "button", class: "btn alt", onclick: () => { destroy(); onScripted(); } }, T("lv_scripted"))));
  }

  // ---------------------------------------------------------------- the call
  async function start() {
    showWarn("");
    fill(view, h("div", { class: "stack center" }, h("p", { class: "waiting" }, T("lv_connecting"))));
    const r = await api("/api/c/live/start", { method: "POST", timeout: 45000 });
    if (dead) return;
    if (!r.ok) {
      const code = r.error && r.error.code;
      return endScreen(code === "busy" ? "busy" : code === "agent_off" ? "agent_off" : r.status === 0 ? "offline" : "start_failed", false);
    }
    call = r.data;
    const sit = call.situation || {};
    const hideDept = /বিভাগের নাম না/.test(sit.twist_bn || "");
    const situation = h("section", { class: "box hint" },
      h("h2", { class: "small" }, T("lv_situation")),
      h("p", { class: "hint-text" }, T("lv_situation_line", { who: sit.who_bn, problem: sit.problem_bn })),
      hideDept ? null : h("p", { class: "muted" }, T("lv_dept_hint", { dept: sit.department_hint })),
      h("p", { class: "nudge" }, sit.twist_bn || ""));
    const hang = h("button", { type: "button", class: "btn alt", onclick: () => hangUp() }, icon("stop"), T("lv_hangup"));
    cap = createCapture({
      review: false, maxS: S.cfg.max_clip_s || 20, minS: S.cfg.min_clip_s || 0.6,
      onDone: (res) => send(res),
    });
    cap.enable(false);
    fill(view, h("div", { class: "stack" }, situation, log, cue, warn, listenBtn, cap.el, hang));
    bubble("shefa", call.greeting);
    speak(call.audio, yourTurn);
  }

  function yourTurn() {
    if (dead || ended) return;
    say("lv_your_turn");
    cap.enable(true);
  }

  async function send(res) {
    cap.enable(false);
    showWarn("");
    say("lv_sending");
    const id = newClipId();
    const person = me();
    const up = await api("/api/c/clip/" + id, {
      method: "PUT", body: res.blob, speaker: S.session.speaker, timeout: 30000,
      headers: { "X-Live": call.call_id, "X-Setting": person.setting || "" },
    });
    if (dead) return;
    if (!up.ok) {
      if (up.status === 410) return endScreen("ended_elsewhere", true);
      if (up.status === 422) { showWarn(rejectionText(up.error.reason, up.error.message)); return yourTurn(); }
      if (up.status === 503) return endScreen("paused", true);
      showWarn(t(up.status === 0 ? "lv_net" : "lv_send_failed"));
      return yourTurn();
    }
    person.n++; person.sec += res.dur; save();
    await askShefa(id, 0);
  }

  async function askShefa(clipId, tries) {
    say("lv_thinking");
    const r = await api(`/api/c/live/${call.call_id}/turn`, { method: "POST", body: { clip_id: clipId }, timeout: 70000 });
    if (dead) return;
    if (!r.ok) {
      // the server answers a repeated clip with the same answer, so retrying is safe
      if ((r.status === 0 || r.status === 409 || r.status >= 500) && tries < 2) {
        await new Promise((ok) => setTimeout(ok, 1500));
        return askShefa(clipId, tries + 1);
      }
      if (r.status === 404 || r.status === 410) return endScreen("ended_elsewhere", true);
      showWarn(t("lv_send_failed"));
      return yourTurn();
    }
    const out = r.data;
    turns = out.turn;
    bubble("you", out.heard || t("lv_heard_nothing"), h("p", { class: "muted small" }, T("lv_heard_label")));
    bubble("shefa", out.reply);
    if (out.ended) { ended = true; speak(out.audio, () => endScreen(out.end_reason, true)); return; }
    speak(out.audio, yourTurn);
  }

  async function hangUp() {
    ended = true;
    stopAudio();
    if (cap) cap.destroy();
    if (call) api(`/api/c/live/${call.call_id}/end`, { method: "POST", body: {} });
    endScreen("caller_hung_up", true);
  }

  // ---------------------------------------------------------------- end + feedback
  function endScreen(reason, askFeedback) {
    ended = true;
    stopAudio();
    if (cap) { cap.destroy(); cap = null; }
    const key = "lv_end_" + reason;
    const why = t(key) !== key ? T(key) : T("lv_end_other");
    let verdict = "";
    const noteBox = h("textarea", { rows: 2, maxlength: 300, placeholder: t("lv_note_ph") });
    const thanks = h("p", { class: "muted", role: "status" });
    const chips = h("div", { class: "chips", role: "group", "aria-label": t("lv_how") },
      VERDICTS.map(([v, k]) => h("button", { type: "button", class: "chip pick", "aria-pressed": "false", onclick: (e) => {
        verdict = v;
        chips.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
      } }, T(k))));
    const sendFb = h("button", { type: "button", class: "btn primary", onclick: async () => {
      if (!verdict) { fill(thanks, T("lv_pick_one")); return; }
      sendFb.disabled = true;
      const r = await api(`/api/c/live/${call.call_id}/end`, { method: "POST", body: { verdict, note: noteBox.value } });
      fill(thanks, T(r.ok ? "lv_fb_thanks" : "lv_send_failed"));
      if (!r.ok) sendFb.disabled = false;
    } }, T("lv_fb_send"));
    fill(view, h("div", { class: "stack" },
      h("h1", { tabindex: "-1" }, T("lv_ended")),
      h("p", null, why),
      turns ? h("p", { class: "muted" }, T("lv_turns", { n: turns })) : null,
      askFeedback && call ? h("section", { class: "box" }, h("p", { class: "q" }, T("lv_how")), chips, noteBox, sendFb, thanks) : null,
      log.childElementCount ? h("details", { class: "more" }, h("summary", null, T("lv_transcript")), log) : null,
      h("button", { type: "button", class: "btn primary big", onclick: () => { reset(); intro(); } }, icon("phone"), T("lv_again")),
      h("button", { type: "button", class: "btn alt", onclick: () => { destroy(); onScripted(); } }, T("lv_scripted")),
      h("button", { type: "button", class: "btn alt", onclick: () => { destroy(); onFinish(); } }, T("finish"))));
    const hd = view.querySelector("h1"); hd && hd.focus();
  }

  function reset() {
    stopAudio();
    if (cap) { cap.destroy(); cap = null; }
    call = null; turns = 0; ended = false;
    clear(log);
    showWarn("");
  }

  function destroy() {
    if (dead) return;
    if (call && !ended) api(`/api/c/live/${call.call_id}/end`, { method: "POST", body: {} });
    dead = true;
    stopAudio();
    if (cap) cap.destroy();
  }

  intro();
  return { destroy };
}
