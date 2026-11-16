// The core loop: a small made-up phone call to one fictional clinic. The front desk says a line
// (always shown as text, and spoken), then it is the person's turn. At a few points the person
// picks what to say (a doctor, "who is best?", the fee...) and the desk's next line follows that
// choice, so calls differ and can run long. The phone only sends ids (card, node, choice, patient):
// the server works out what each clip answers.
import { h, icon, clear, fill } from "./dom.js";
import { T, t, rejectionText } from "./i18n.js";
import { api, url } from "./api.js";
import { S, me, save, markSeen } from "./session.js";
import { createCapture } from "./capture.js";
import * as Q from "./queue.js";
import { releaseMic } from "./recorder.js";
import { toast } from "./ui.js";

// The "where are you" chips. Asked once per person, shown as a small chip afterwards.
export function settingBlock(onPick) {
  const wrap = h("div", { class: "setting" });
  let open = !me().setting;
  const label = (s) => (t("set_" + s.id) !== "set_" + s.id ? T("set_" + s.id) : s.bn);
  function draw() {
    clear(wrap);
    const cur = (S.cfg.settings || []).find((s) => s.id === me().setting);
    if (!open && cur) {
      wrap.append(h("div", { class: "setting-cur" }, icon("check"), label(cur),
        h("button", { type: "button", class: "chip", onclick: () => { open = true; draw(); } }, T("set_change"))));
      return;
    }
    wrap.append(h("p", { class: "q" }, T("set_ask")),
      h("div", { class: "chips" }, (S.cfg.settings || []).map((s) =>
        h("button", { type: "button", class: "chip pick", "aria-pressed": String(me().setting === s.id), onclick: () => {
          me().setting = s.id; save(); open = false; draw(); onPick && onPick();
        } }, label(s)))));
  }
  draw();
  return wrap;
}

/** Fill {name}, {age}, {relation_bn}... in a hint from the patient the person chose. */
export function resolve(text, persona) {
  if (!text) return "";
  const p = persona || {};
  return String(text)
    .replaceAll("{name}", p.name || "")
    .replaceAll("{age_words}", p.age_words || "")
    .replaceAll("{age_bn}", p.age_bn || "")
    .replaceAll("{age}", p.age_bn || "")
    .replaceAll("{relation_bn}", p.relation_bn || "");
}

/** Where the desk's line is spoken from: the staff voice for this call if it has the line, else
 *  the synthetic voice. Returns a list to try in order (an empty list means text only). */
export function lineSources(card, node) {
  const out = [];
  const v = card.voice;
  if (v && v.pack && Array.isArray(v.names) && v.names.includes(node.audio_name)) {
    out.push(url(`/hv/${v.pack}/${node.audio_name}.m4a`));
  }
  if (node.audio) out.push(url("/" + String(node.audio).replace(/^\//, "")));
  return out;
}

/** The patient chooser: two big buttons (ছেলে / মেয়ে, স্বামী / স্ত্রী...). */
export function personaPicker(personas, onPick) {
  return h("section", { class: "box persona-pick" },
    h("h2", null, T("pick_patient")),
    h("p", { class: "muted" }, T("pick_patient_sub")),
    h("div", { class: "persona-btns" }, personas.map((p) =>
      h("button", { type: "button", class: "btn alt persona-btn", onclick: () => onPick(p) },
        h("strong", null, p.label_bn),
        h("span", null, p.name),
        h("span", { class: "muted" }, T("age_years", { age: p.age_bn }))))));
}

export function patientLine(p) {
  return p ? h("p", { class: "persona" }, icon("user"), T("patient_line", { rel: p.relation_bn, name: p.name, age: p.age_bn })) : null;
}

export function runCards(view, { first, onFinish }) {
  let buffer = first ? [first] : [];
  let card = null, nid = "", persona = null, choice = null, turns = 0, recorded = 0;
  let history = [], cap = null, audio = null, heard = false, unlock = null, awaiting = new Set(), dead = false;
  const counter = h("span", { class: "chip count-chip" });
  const paintCounter = () => fill(counter, icon("check"), T("counter", { n: me().n }));

  const offLate = Q.onOutcome((o) => {
    // A clip the server turned down after the person already moved on: say so, and offer a redo.
    if (o.outcome !== "rejected" || awaiting.has(o.id) || !o.meta || !o.meta.card) return;
    const p = S.session && S.session.people[o.speaker];
    if (p) { p.n = Math.max(0, p.n - 1); save(); }
    paintCounter();
    const back = card && card.id === o.meta.card && card.nodes && card.nodes[o.meta.step] ? o.meta.step : "";
    toast(t("rec_late", { msg: rejectionText(o.reason, o.message) }), back ? "rec_redo_btn" : "", () => { showNode(back); });
  });

  function stopSound() {
    clearTimeout(unlock);
    if (audio) { audio.onended = audio.onerror = null; audio.pause(); audio = null; }
    try { window.speechSynthesis && speechSynthesis.cancel(); } catch { /* optional */ }
  }

  async function fetchCards() {
    const seen = (S.session.seen || []).slice(-60).join(",");
    return api(`/api/c/cards?n=3&seen=${encodeURIComponent(seen)}`);
  }

  async function nextCard() {
    stopSound();
    if (cap) cap.destroy();
    if (!buffer.length) {
      fill(view, h("p", { class: "center" }, T("loading")));
      const r = await fetchCards();
      if (dead) return;
      if (r.status === 401) return fill(view, h("p", { class: "warn center" }, T("err_signed_out")));
      if (!r.ok || !r.data.cards.length) {
        fill(view, h("div", { class: "stack center" }, h("p", { class: "warn" }, T("cards_fail")),
          h("button", { type: "button", class: "btn primary", onclick: nextCard }, T("retry")),
          h("button", { type: "button", class: "btn alt", onclick: finish }, T("finish"))));
        return;
      }
      buffer = r.data.cards.filter((c) => c.nodes);
    }
    card = buffer.shift();
    persona = null; turns = 0; recorded = 0; history = [];
    markSeen(card.id);
    if (buffer.length < 1) prefetch();
    const people = card.personas || [];
    if (people.length > 1) {
      fill(view, h("div", { class: "stack" },
        h("div", { class: "row between" }, counter),
        h("section", { class: "box" }, h("h2", { class: "small" }, T("sit_title")), h("p", { class: "situation" }, card.situation_bn)),
        personaPicker(people, (p) => { persona = p; showNode(card.start); })));
      paintCounter();
      window.scrollTo(0, 0);
      return;
    }
    persona = people[0] || null;
    showNode(card.start);
  }

  async function prefetch() {
    const r = await fetchCards();
    if (r.ok && !dead) buffer.push(...r.data.cards.filter((c) => c.nodes && c.id !== (card && card.id)));
  }

  function historyBox() {
    if (!history.length) return null;
    return h("section", { class: "history", "aria-label": t("history") },
      history.slice(-4).map((x) => h("div", { class: "hist" },
        h("p", { class: "hist-desk" }, h("b", null, T("desk_label")), " ", x.desk),
        h("p", { class: "hist-you" }, x.done ? T("you_done") : T("you_skipped")))));
  }

  function showNode(id) {
    stopSound();
    if (cap) cap.destroy();
    nid = id;
    const node = card.nodes[nid];
    if (!node) return callDone();
    const choices = node.choices || [];
    choice = choices.length === 1 ? choices[0] : null;
    heard = false;
    const final = choices.length === 0;
    let sync = () => {}; // set below once the record button exists; ready() may run before that

    // ---- the desk's line: always on screen, spoken once, replay any time --------------------
    const cue = h("p", { class: "turncue", role: "status" });
    const replay = h("button", { type: "button", class: "btn alt small" }, icon("sound"), T("agent_replay"));
    const bubble = h("section", { class: "bubble" },
      h("p", { class: "bubble-who" }, T("desk_label")),
      h("p", { class: "bubble-text", lang: "bn" }, node.line_bn), replay);

    const setCue = (state) => {
      bubble.classList.toggle("speaking", state === "speaking");
      cue.className = "turncue " + state;
      fill(cue, state === "speaking" ? T("desk_speaking") : state === "tap" ? T("desk_tap") : final ? T("call_ending") : T("your_turn"));
    };
    const ready = () => { if (heard) return; heard = true; setCue("turn"); sync(); if (final) setTimeout(() => !dead && nid === id && callDone(), 1200); };

    function play() {
      stopSound();
      const sources = lineSources(card, node);
      const tryNext = () => {
        const src = sources.shift();
        if (!src) { speakText(); return; }
        audio = new Audio(src);
        const a = audio;
        a.onended = () => { if (audio === a) ready(); };
        // Some phones never report "ended": unlock a little after the line's own length anyway.
        a.onloadedmetadata = () => {
          if (audio !== a) return;
          clearTimeout(unlock);
          const secs = Number.isFinite(a.duration) && a.duration > 0 ? a.duration : 25;
          unlock = setTimeout(() => audio === a && ready(), (secs + 3) * 1000);
        };
        a.onerror = () => { if (audio === a) tryNext(); };
        setCue("speaking");
        a.play().catch((e) => {
          if (audio !== a) return;
          if (e && e.name === "NotAllowedError") { setCue("tap"); unlock = setTimeout(ready, 2000); } // never stay locked
          else tryNext();
        });
      };
      tryNext();
    }
    function speakText() {
      // No recording could play: the words are on screen; try the phone's own Bangla voice too.
      ready();
      try {
        if (window.speechSynthesis) {
          const u = new SpeechSynthesisUtterance(node.line_bn);
          u.lang = "bn-BD";
          speechSynthesis.speak(u);
        }
      } catch { /* optional */ }
    }
    replay.onclick = play;

    if (final) {
      fill(view, h("div", { class: "stack" }, h("div", { class: "row between" }, counter, h("span", { class: "muted" }, T("turn_n", { n: turns }))),
        patientLine(persona), historyBox(), bubble, cue));
      paintCounter();
      play();
      return;
    }

    // ---- the person's part --------------------------------------------------------------------
    const settingReady = () => !!me().setting;
    sync = () => cap && cap.enable(heard && settingReady() && !!choice);
    const hintText = h("p", { class: "hint-text" });
    const hintBox = h("section", { class: "box hint" }, h("h2", { class: "small" }, T("hint_title2")), hintText, h("p", { class: "nudge" }, T("nudge")));
    const paintHint = () => { hintBox.hidden = !choice; if (choice) fill(hintText, resolve(choice.hint_bn, persona)); };
    let fork = null;
    if (choices.length > 1) {
      const chips = choices.map((c) => h("button", { type: "button", class: "chip pick", "aria-pressed": "false", onclick: () => {
        choice = c;
        chips.forEach((b) => b.setAttribute("aria-pressed", String(b === chipFor(c))));
        paintHint(); sync();
      } }, c.label_bn || c.id));
      const chipFor = (c) => chips[choices.indexOf(c)];
      fork = h("section", { class: "box fork" }, h("h2", { class: "small" }, T("fork_ask")), h("div", { class: "chips" }, chips));
    }
    paintHint();

    cap = createCapture({
      maxS: (node.cap_s || S.cfg.max_clip_s) + 0.4, minS: S.cfg.min_clip_s,
      onAccept: async (res) => {
        stopSound();
        const who = me();
        const meta = { card: card.id, step: nid, choice: choice.id, persona: persona ? persona.id : "", slot: node.slot,
          setting: who.setting, autostop: res.cut ? "1" : "" };
        const id = await Q.add({ blob: res.blob, speaker: S.session.speaker, dur: res.dur, meta });
        who.n++; who.sec += res.dur; save(); paintCounter();
        awaiting.add(id);
        const out = navigator.onLine === false ? { outcome: "pending" } : await Q.waitFor(id, 2500);
        awaiting.delete(id);
        if (out.outcome === "rejected") {
          who.n = Math.max(0, who.n - 1); who.sec = Math.max(0, who.sec - res.dur); save(); paintCounter();
          return { redo: true, redoText: rejectionText(out.reason, out.message) };
        }
        recorded++;
        go(true);
        return undefined;
      },
    });

    function go(done) {
      turns++;
      history.push({ desk: node.line_bn, done });
      const nextId = (choice || choices[0]).next;
      if (nextId) showNode(nextId); else callDone();
    }

    const skips = h("div", { class: "row links" },
      h("button", { type: "button", class: "linkbtn", onclick: () => { if (!choice) choice = choices[0]; go(false); } }, T("skip_step")),
      h("button", { type: "button", class: "linkbtn", onclick: () => nextCard() }, T("skip_call")));

    fill(view, h("div", { class: "stack" },
      h("div", { class: "row between" }, counter, h("span", { class: "muted" }, T("turn_n", { n: turns + 1 }))),
      settingBlock(sync), turns === 0 && h("section", { class: "box" }, h("h2", { class: "small" }, T("sit_title")), h("p", { class: "situation" }, card.situation_bn)),
      patientLine(persona), historyBox(), bubble, cue, fork, hintBox, cap.el, skips));
    paintCounter();
    sync();
    play();
    window.scrollTo(0, 0);
  }

  function callDone() {
    stopSound();
    if (cap) cap.destroy();
    fill(view, h("div", { class: "stack center" },
      h("h1", { tabindex: "-1" }, T("call_done")),
      h("p", null, T("call_done_n", { n: recorded })),
      h("p", { class: "muted" }, T("card_more")),
      h("button", { type: "button", class: "btn primary big", onclick: nextCard }, T("more_call")),
      h("button", { type: "button", class: "btn alt", onclick: finish }, T("finish"))));
    const hd = view.querySelector("h1"); hd && hd.focus();
  }

  function finish() {
    destroy();
    onFinish();
  }

  function destroy() {
    dead = true;
    stopSound();
    if (cap) cap.destroy();
    offLate();
    releaseMic();
  }

  nextCard();
  return { destroy };
}
