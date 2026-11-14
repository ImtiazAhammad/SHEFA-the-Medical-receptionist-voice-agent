// The core loop, "answer the agent": a made-up situation, the assistant's real question played
// aloud, then the person answers in their own words. Cards come three at a time. The phone only
// sends ids (card, step, setting): the server fills in what the clip answers.
import { h, icon, clear, fill } from "./dom.js";
import { T, setT, t, n, rejectionText } from "./i18n.js";
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

export function runCards(view, { first, onFinish }) {
  let buffer = first ? [first] : [];
  let card = null, i = 0, doneHere = 0, cap = null, audio = null, heard = false, awaiting = new Set(), dead = false;
  const counter = h("span", { class: "chip count-chip" });
  const paintCounter = () => fill(counter, icon("check"), T("counter", { n: me().n }));

  const offLate = Q.onOutcome((o) => {
    // A clip the server turned down after the person already moved on: say so, and offer a redo.
    if (o.outcome !== "rejected" || awaiting.has(o.id) || !o.meta || !o.meta.card) return;
    const p = S.session && S.session.people[o.speaker];
    if (p) { p.n = Math.max(0, p.n - 1); save(); }
    paintCounter();
    const idx = card && card.id === o.meta.card ? card.steps.findIndex((s) => s.id === o.meta.step) : -1;
    toast(t("rec_late", { msg: rejectionText(o.reason, o.message) }), idx >= 0 ? "rec_redo_btn" : "", () => { i = idx; showStep(); });
  });

  function stopSound() {
    if (audio) { audio.pause(); audio = null; }
    try { window.speechSynthesis && speechSynthesis.cancel(); } catch { /* optional */ }
  }

  async function nextCard() {
    stopSound();
    if (cap) cap.destroy();
    if (!buffer.length) {
      fill(view, h("p", { class: "center" }, T("loading")));
      const seen = (S.session.seen || []).slice(-40).join(",");
      const r = await api(`/api/c/cards?n=3&seen=${encodeURIComponent(seen)}`);
      if (dead) return;
      if (r.status === 401) return signedOut();
      if (!r.ok || !r.data.cards.length) {
        fill(view, h("div", { class: "stack center" }, h("p", { class: "warn" }, T("cards_fail")),
          h("button", { type: "button", class: "btn primary", onclick: nextCard }, T("retry")),
          h("button", { type: "button", class: "btn alt", onclick: finish }, T("finish"))));
        return;
      }
      buffer = r.data.cards;
    }
    card = buffer.shift(); i = 0; doneHere = 0;
    markSeen(card.id);
    if (buffer.length < 1) prefetch();
    showStep();
  }

  async function prefetch() {
    const seen = [...(S.session.seen || []).slice(-40)].join(",");
    const r = await api(`/api/c/cards?n=3&seen=${encodeURIComponent(seen)}`);
    if (r.ok && !dead) buffer.push(...r.data.cards.filter((c) => c.id !== (card && card.id)));
  }

  function signedOut() {
    fill(view, h("p", { class: "warn center" }, T("err_signed_out")));
  }

  function showStep() {
    stopSound();
    if (cap) cap.destroy();
    const step = card.steps[i];
    heard = false;
    const settingReady = () => !!me().setting;
    const sync = () => cap && cap.enable(heard && settingReady());

    cap = createCapture({
      maxS: S.cfg.max_clip_s, minS: S.cfg.min_clip_s,
      onAccept: async (res) => {
        stopSound();
        const person = me();
        const id = await Q.add({ blob: res.blob, speaker: S.session.speaker, dur: res.dur,
          meta: { card: card.id, step: step.id, slot: step.slot, setting: person.setting } });
        person.n++; person.sec += res.dur; save(); paintCounter();
        awaiting.add(id);
        const out = navigator.onLine === false ? { outcome: "pending" } : await Q.waitFor(id, 2500);
        awaiting.delete(id);
        if (out.outcome === "rejected") {
          person.n = Math.max(0, person.n - 1); person.sec = Math.max(0, person.sec - res.dur); save(); paintCounter();
          return { redo: true, redoText: rejectionText(out.reason, out.message) };
        }
        doneHere++;
        advance();
        return undefined;
      },
    });

    const dots = h("ol", { class: "dots", "aria-label": t("step_of", { i: i + 1, n: card.steps.length }) },
      card.steps.map((s, k) => h("li", { class: k < i ? "done" : k === i ? "now" : "" })));
    const stepOf = h("span", { class: "muted" }, T("step_of", { i: i + 1, n: card.steps.length }));
    paintCounter();

    const persona = card.persona && card.persona.patient ? h("p", { class: "persona" }, icon("user"), T("persona", { name: card.persona.patient })) : null;
    const situation = h("section", { class: "box" },
      h("h2", { class: "small" }, T("sit_title")),
      h("p", { class: "situation" }, card.situation_bn), persona);

    // The assistant's question: auto-played, and the record button waits for it to end.
    const playBtn = h("button", { type: "button", class: "btn alt", "aria-label": t("agent_replay") }, icon("sound"), T("agent_replay"));
    const text = h("details", { class: "qtext" }, h("summary", null, T("agent_text")), h("p", null, step.question_bn));
    if (!step.audio) text.open = true;
    const agent = h("section", { class: "box agent" }, h("h2", { class: "small" }, T("agent_says")), playBtn, text);

    function playQuestion() {
      stopSound();
      if (step.audio) {
        audio = new Audio(url("/" + step.audio.replace(/^\//, "")));
        const a = audio;
        a.onended = () => { heard = true; agent.classList.remove("speaking"); sync(); };
        a.onerror = () => { heard = true; agent.classList.remove("speaking"); text.open = true; sync(); };
        agent.classList.add("speaking");
        a.play().catch((e) => { agent.classList.remove("speaking"); if (e && e.name !== "NotAllowedError") { heard = true; text.open = true; sync(); } });
      } else {
        // No recorded voice: show the words and try the phone's own Bangla voice, never wait on it.
        heard = true; sync();
        try {
          if (window.speechSynthesis) {
            const u = new SpeechSynthesisUtterance(step.question_bn);
            u.lang = "bn-BD";
            speechSynthesis.speak(u);
          }
        } catch { /* optional */ }
      }
    }
    playBtn.onclick = playQuestion;

    const hint = h("section", { class: "box hint" }, h("h2", { class: "small" }, T("hint_title")),
      h("p", { class: "hint-text" }, step.hint_bn), h("p", { class: "nudge" }, T("nudge")));

    const skips = h("div", { class: "row links" },
      h("button", { type: "button", class: "linkbtn", onclick: () => advance() }, T("skip_step")),
      h("button", { type: "button", class: "linkbtn", onclick: () => nextCard() }, T("skip_card")));

    fill(view, h("div", { class: "stack" },
      h("div", { class: "row between" }, counter, stepOf), dots,
      settingBlock(sync), situation, agent, hint, cap.el, skips));
    sync();
    playQuestion();
    view.focus && window.scrollTo(0, 0);
  }

  function advance() {
    if (i + 1 < card.steps.length) { i++; showStep(); return; }
    cardDone();
  }

  function cardDone() {
    stopSound();
    if (cap) cap.destroy();
    fill(view, h("div", { class: "stack center" },
      h("h1", { tabindex: "-1" }, T("card_done")),
      h("p", null, T("card_done_n", { n: doneHere })),
      h("p", { class: "muted" }, T("card_more")),
      h("button", { type: "button", class: "btn primary big", onclick: nextCard }, T("more_card")),
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
