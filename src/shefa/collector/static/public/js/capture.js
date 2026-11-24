// The record / listen back / accept widget, shared by the card loop, the mic check and the
// friend call. Push-to-talk on purpose: the person taps to start and taps to stop, so the
// assistant's voice is never recorded and nobody has to guess when the mic is open.
import { h, icon, add, clear, fill } from "./dom.js";
import { T, setT, t } from "./i18n.js";
import { record, micErrorKey } from "./recorder.js";
import { orbs } from "./orbs.js";

/**
 * opts.maxS     longest clip in seconds (we stop a little before the server's limit)
 * opts.minS     shortest clip the server will take
 * opts.review   false = no accept step (mic check): onDone gets the result straight away
 * opts.onAccept async (result) => ({ redo: "message" } | undefined)
 * opts.onDone   (result) => void, used when review is false
 * opts.onLevel  (0..1) => void, optional: the meter's level, for a voice ring that follows it
 * opts.onPhase  (phase) => void, optional: idle, rec, sending or review, as it changes
 * opts.ring     true: SHEFA's voice ring stands behind the record button and becomes it (the button
 *               turns into a clear circle over the ring once it has drawn); the returned voice(state)
 *               shows 'speaking' while the other side's line plays
 */
export function createCapture(opts) {
  const limit = Math.max(2, opts.maxS - 0.5);
  let phase = "idle", enabled = true, handle = null, tick = null, url = "", last = null, cut = false;

  const bar = h("i");
  const meter = h("div", { class: "meter", "aria-hidden": "true" }, bar);
  const btn = h("button", { type: "button", class: "recbtn", "aria-pressed": "false" });
  const label = h("p", { class: "reclabel" });
  const err = h("p", { class: "warn", role: "alert", hidden: true });
  const review = h("div", { class: "review", hidden: true });
  const el = h("div", { class: "capture" }, meter, btn, label, err, review);

  // ---- the ring (opts.ring): decoration over the real button. If the orbs module never loads,
  // the button, meter and everything else are exactly as without it.
  let ring = null, ringState = "idle", voiceState = null, micLevel = 0;
  const presence = h("div", { class: "live-ring", "aria-hidden": "true" });
  const ringLevel = () => {
    if (!el.isConnected) { queueMicrotask(dropRing); return 0; } // the card moved on: let it go
    if (ringState === "listening") return micLevel;
    if (ringState === "speaking") { const n = performance.now(); return 0.3 + 0.2 * Math.abs(Math.sin(n / 160) * Math.sin(n / 410)); }
    return 0;
  };
  function ringTo(state) { if (state === ringState) return; ringState = state; try { if (ring) ring.set({ state }); } catch { /* decoration */ } }
  function dropRing() { try { if (ring) ring.destroy(); } catch { /* gone */ } ring = null; presence.classList.remove("on"); }
  if (opts.ring) {
    const wrap = h("div", { class: "ring-wrap" });
    btn.before(wrap);
    wrap.append(presence, btn);
    orbs().then((m) => {
      if (!m || !el.isConnected) return;
      try { ring = m.mountRing(presence, { size: 168, state: ringState, level: ringLevel, hoverBend: true }); presence.classList.add("on"); } catch { ring = null; }
    });
  }
  const ringFromPhase = () => ringTo(phase === "rec" ? "listening" : phase === "sending" ? "processing" : voiceState || "idle");
  const level = (v) => { bar.style.transform = `scaleX(${v.toFixed(2)})`; micLevel = v; if (opts.onLevel) opts.onLevel(v); };

  function paint() {
    btn.disabled = !enabled || phase === "sending" || phase === "review";
    btn.classList.toggle("on", phase === "rec");
    btn.setAttribute("aria-pressed", String(phase === "rec"));
    fill(btn, icon(phase === "rec" ? "stop" : "mic", "big"));
    btn.setAttribute("aria-label", t(phase === "rec" ? "rec_stop" : "rec_tap"));
    review.hidden = phase !== "review";
    btn.hidden = phase === "review" || phase === "sending";
    meter.hidden = phase === "review" || phase === "sending";
    setT(label, phase === "sending" ? "rec_sending" : phase === "rec" ? "rec_stop" : enabled ? "rec_tap" : "rec_wait");
    label.hidden = phase === "review";
    el.dataset.phase = phase;
    if (opts.ring) ringFromPhase();
    if (opts.onPhase) opts.onPhase(phase);
  }

  function showError(key, params) {
    err.hidden = !key;
    if (key) { fill(err, T(key, params)); }
  }

  async function start() {
    showError("");
    try {
      handle = await record(level);
    } catch (e) {
      handle = null;
      showError(micErrorKey(e));
      return;
    }
    phase = "rec"; cut = false; paint();
    const t0 = performance.now();
    const left = h("span", { class: "count", "aria-hidden": "true" });
    label.after(left);
    tick = setInterval(() => {
      const remain = limit - (performance.now() - t0) / 1000;
      // A countdown only near the end: a clock running from the start makes people rush.
      left.hidden = remain > 5;
      fill(left, T("rec_left", { s: Math.max(0, Math.ceil(remain)) }));
      if (remain <= 0) { cut = true; stop(); }
    }, 100);
    el._left = left;
  }

  async function stop() {
    if (phase !== "rec" || !handle) return;
    clearInterval(tick);
    if (el._left) el._left.remove();
    const h0 = handle; handle = null;
    phase = "sending"; paint();
    level(0);
    const res = await h0.stop();
    level(0); // the recorder can report one last level after the reset above: the meter rests at zero
    res.cut = cut;
    if (res.dur < opts.minS + 0.1) { phase = "idle"; paint(); showError("rec_short"); return; }
    last = res;
    if (opts.review === false) { phase = "idle"; paint(); opts.onDone(res); return; }
    showReview(res);
  }

  function showReview(res) {
    phase = "review";
    url = URL.createObjectURL(res.blob);
    const audio = h("audio", { src: url, preload: "auto" });
    const play = h("button", { type: "button", class: "btn alt big-play", "aria-label": t("rec_hear") }, icon("play"), T("rec_hear"));
    play.onclick = () => { if (audio.paused) audio.play().catch(() => {}); else audio.pause(); };
    audio.onplay = () => fill(play, icon("pause"), T("rec_hear"));
    audio.onpause = audio.onended = () => fill(play, icon("play"), T("rec_hear"));
    const ok = h("button", { type: "button", class: "btn primary" }, icon("check"), T("rec_ok"));
    const again = h("button", { type: "button", class: "btn alt" }, icon("redo"), T("rec_again"));
    ok.onclick = accept;
    again.onclick = () => { reset(); };
    const quiet = res.peak < 0.02;
    // Cut off by the time limit: the end of what they said is missing, so ask for a shorter take.
    // Keeping it is allowed (the server marks it), but "again" is the first choice offered.
    if (res.cut) fill(ok, icon("check"), T("rec_keep_cut"));
    fill(review, audio, play, quiet && h("p", { class: "warn", role: "alert" }, T("rec_quiet")),
      res.cut && h("p", { class: "warn", role: "alert" }, T("rec_cut")),
      h("div", { class: "row" }, res.cut ? again : ok, res.cut ? ok : again));
    paint();
    (res.cut ? again : ok).focus();
  }

  async function accept() {
    phase = "sending"; paint();
    const out = await opts.onAccept(last);
    if (out && out.redo) { reset(); if (out.redoText) { err.hidden = false; err.textContent = out.redoText; } else showError("rec_redo"); return; }
    reset();
  }

  function reset() {
    clearInterval(tick);
    if (el._left) el._left.remove();
    if (handle) { handle.cancel(); handle = null; }
    if (url) { URL.revokeObjectURL(url); url = ""; }
    clear(review);
    phase = "idle"; last = null; level(0); paint();
    showError("");
  }

  btn.onclick = () => (phase === "rec" ? stop() : phase === "idle" ? start() : null);
  paint();

  return {
    el,
    enable(on) { enabled = on; paint(); },
    reset,
    error: (key, params) => showError(key, params),
    text: (msg) => { err.hidden = false; err.textContent = msg; },
    busy: () => phase !== "idle",
    voice(state) { voiceState = state || null; if (opts.ring) ringFromPhase(); },
    destroy() { reset(); dropRing(); },
  };
}
