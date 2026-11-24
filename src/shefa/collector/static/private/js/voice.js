// "ডেস্কের কণ্ঠ দিন": a staff member records the front desk's lines in their own voice, so that
// contributors hear a person instead of the synthetic voice. Consent first, then one line at a
// time: record (tap start, tap stop), listen back, re-record or delete. The recorder is the same
// one the contributor page uses (16 kHz WAV, the browser's voice processing switched off).
import { api, ApiError, signOut } from "./api.js";
import { $, clear, clock, el, toast } from "./dom.js";
import { ask } from "./dialog.js";
import { setMeter } from "./charts.js";
import { applyI18n, initLangToggle, labelFor, num, onLangChange, t } from "./i18n.js";
import { homeFor } from "./account-model.js";
import { micErrorKey, record, releaseMic } from "./recorder.js";
import { orbs } from "./orbs.js";
import { COUNTDOWN_S, MAX_LINE_S, groupLines, progressOf, takeProblem, uploadErrorKey } from "./voice-model.js";

const ui = {
  loading: $("#loading"), error: $("#error"), errorText: $("#error-text"), consent: $("#consent"),
  consentTick: $("#consent-tick"), consentMsg: $("#consent-msg"), consentGo: $("#consent-go"),
  work: $("#work"), packState: $("#pack-state"), progressCount: $("#progress-count"),
  progressMeter: $("#progress-meter"), progressOpenings: $("#progress-openings"),
  player: $("#player"), groups: $("#groups"), wipe: $("#wipe"), who: $("#who"),
};

let me = null;
let data = null;          // {consented, enabled, lines:[{name, text, group, recorded}]}
const said = new Map();   // line name -> {key, vars, kind}: the message under that line
const urls = new Map();   // line name -> blob URL of the person's own recording
const refs = new Map();   // line name -> the elements of that line's card
let active = null;        // the take being recorded: {name, handle, startedAt, timer}
let busyName = "";        // a line being uploaded or deleted
let playing = "";         // the line whose recording is playing
let consentKey = "";      // what the consent form is saying

// ---- helpers -------------------------------------------------------------------------------
function lineByName(name) { return data && data.lines.find((line) => line.name === name); }
function say(name, key, vars, kind = "info") {
  if (key) said.set(name, { key, vars, kind }); else said.delete(name);
  paintLine(name);
}
function forgetAudio(name) {
  const url = urls.get(name);
  if (url) URL.revokeObjectURL(url);
  urls.delete(name);
  if (playing === name) stopPlayback();
}
function forgetAllAudio() { for (const name of [...urls.keys()]) forgetAudio(name); }

function showOnly(name) {
  ui.loading.hidden = name !== "loading";
  ui.error.hidden = name !== "error";
  ui.consent.hidden = name !== "consent";
  ui.work.hidden = name !== "work";
}

function showError(error) {
  ui.errorText.textContent = t(error && error.code === "network" ? "err_network" : "err_generic");
  showOnly("error");
}

// ---- drawing -------------------------------------------------------------------------------
function paintState() {
  if (!data) return;
  ui.packState.textContent = t(data.enabled ? "vr_state_on" : "vr_state_off");
  ui.packState.className = `banner ${data.enabled ? "ok" : "info"}`;
  const p = progressOf(data.lines);
  ui.progressCount.textContent = `${num(p.done)} / ${num(p.total)}`;
  setMeter(ui.progressMeter, p.pct, p.done && p.done === p.total ? "ok" : "");
  ui.progressMeter.setAttribute("aria-valuenow", String(Math.round(p.pct)));
  ui.progressMeter.setAttribute("aria-valuetext", `${num(p.done)} / ${num(p.total)}`);
  ui.progressOpenings.textContent = t("vr_openings_note", { done: num(p.openingsDone), total: num(p.openingsTotal) });
}

/** One line's card. Built once per load; paintLine() updates it in place. */
function buildLine(line, index) {
  const meter = el("div", { class: "meter level", "aria-hidden": "true" }, [el("i")]);
  const time = el("span", { class: "rec-time", role: "timer" });
  const r = {
    card: el("article", { class: "card line-card", tabindex: "-1", "aria-labelledby": `line-${index}` }),
    text: el("p", { class: "line-text", id: `line-${index}`, lang: "bn", text: line.text }),
    status: el("span", { class: "chip" }),
    record: el("button", { type: "button", class: "primary", onclick: () => toggleRecord(line.name) }),
    play: el("button", { type: "button", onclick: () => togglePlay(line.name) }),
    remove: el("button", { type: "button", class: "danger-outline", onclick: () => removeLine(line.name) }),
    live: el("div", { class: "rec-live" }, [meter, time]),
    meter, time,
    msg: el("p", { class: "line-msg", role: "status" }),
  };
  r.card.append(
    el("div", { class: "line-head" }, [el("span", { class: "muted small", text: num(index + 1) }), r.status]),
    r.text,
    r.live,
    el("div", { class: "row line-actions" }, [r.record, r.play, r.remove]),
    r.msg,
  );
  refs.set(line.name, r);
  paintLine(line.name);
  return r.card;
}

function paintLine(name) {
  const line = lineByName(name);
  const r = refs.get(name);
  if (!line || !r) return;
  const recording = active && active.name === name;
  const busy = busyName === name;
  const locked = (!!active && !recording) || (!!busyName && !busy) || busy;
  r.card.classList.toggle("is-recording", !!recording);
  r.card.classList.toggle("is-done", !!line.recorded);
  r.status.textContent = t(recording ? "vr_status_recording" : line.recorded ? "vr_status_done" : "vr_status_todo");
  r.status.className = `chip ${recording ? "bad" : line.recorded ? "good" : ""}`;
  r.record.textContent = t(recording ? "vr_stop" : line.recorded ? "vr_rerecord" : "vr_record");
  r.record.className = recording ? "danger" : line.recorded ? "" : "primary";
  r.record.disabled = locked;
  r.play.textContent = t(playing === name ? "vr_pause" : "vr_play");
  r.play.hidden = !line.recorded;
  r.play.disabled = !!active || busy;
  r.remove.textContent = t("vr_delete");
  r.remove.hidden = !line.recorded;
  r.remove.disabled = !!active || busy;
  r.live.hidden = !recording;
  listeningOrb(r, !!recording);
  const message = said.get(name);
  r.msg.textContent = message ? t(message.key, message.vars) : busy ? t("vr_working") : "";
  r.msg.className = `line-msg ${message ? message.kind : ""}`;
  r.msg.hidden = !r.msg.textContent;
}

function paintAllLines() { for (const name of refs.keys()) paintLine(name); }

// A small listening orb beside the "recording" chip while that line records (Libraries.dev
// thinking-orbs, loaded on first use). Decoration: the chip says it in words, and if the orb
// module cannot load nothing else changes.
function listeningOrb(r, on) {
  if (on && !r.orbEl) {
    r.orbEl = document.createElement("span");
    r.orbEl.className = "orb-mini";
    r.orbEl.setAttribute("aria-hidden", "true");
    r.status.before(r.orbEl);
    const el = r.orbEl;
    orbs().then((m) => {
      if (!m || r.orbEl !== el) return;
      try { r.orb = m.mountOrb(el, { state: "listening", size: 20 }); } catch { r.orb = null; }
    });
  } else if (!on && r.orbEl) {
    try { if (r.orb) r.orb.destroy(); } catch { /* gone */ }
    r.orbEl.remove();
    r.orbEl = null; r.orb = null;
  }
}

function render() {
  if (!data) return;
  if (active) return; // never tear down the card that is recording; afterTake() redraws
  paintState();
  clear(ui.groups);
  refs.clear();
  let index = 0;
  for (const [group, lines] of groupLines(data.lines)) {
    const done = lines.filter((line) => line.recorded).length;
    const section = el("section", { class: "stack", "aria-labelledby": `group-${group}` }, [
      el("h2", { id: `group-${group}`, class: "group-head" }, [
        labelFor("group", group),
        el("span", { class: "muted small", text: ` ${num(done)} / ${num(lines.length)}` }),
      ]),
      group === "opening" ? el("p", { class: "hint", text: t("vr_group_opening_hint") }) : null,
    ]);
    for (const line of lines) section.append(buildLine(line, index++));
    ui.groups.append(section);
  }
}

// ---- recording -----------------------------------------------------------------------------
async function toggleRecord(name) {
  if (active && active.name === name) { await finishTake(false); return; }
  if (active || busyName) return;
  stopPlayback();
  busyName = name; // asking for the microphone can take a moment: no second tap meanwhile
  say(name, "");
  paintAllLines();
  let handle;
  const r = refs.get(name);
  try {
    handle = await record((level) => { if (r) setMeter(r.meter, level * 100, level > 0.97 ? "bad" : ""); });
  } catch (error) {
    busyName = "";
    say(name, micErrorKey(error), null, "bad"); // said next to the button the person tapped
    paintAllLines();
    return;
  }
  busyName = "";
  active = { name, handle, startedAt: performance.now(), timer: 0 };
  active.timer = setInterval(tick, 200);
  tick();
  paintAllLines();
  if (r) r.record.focus();
}

function tick() {
  if (!active) return;
  const r = refs.get(active.name);
  const seconds = (performance.now() - active.startedAt) / 1000;
  const left = Math.max(0, Math.ceil(MAX_LINE_S - seconds));
  if (r) {
    r.time.textContent = left <= COUNTDOWN_S
      ? `${clock(seconds)} · ${t("vr_seconds_left", { n: num(left) })}`
      : `${clock(seconds)} / ${clock(30)}`;
    r.time.classList.toggle("ending", left <= COUNTDOWN_S);
  }
  if (seconds >= MAX_LINE_S) finishTake(true);
}

/** Stop the take and upload it. auto = the 30 second cap stopped it. */
async function finishTake(auto) {
  if (!active) return;
  const { name, handle, timer } = active;
  clearInterval(timer);
  active = null;
  busyName = name;
  say(name, "");
  let take;
  try {
    take = await handle.stop();
  } catch {
    take = null;
  }
  const problem = takeProblem(take);
  if (problem) { busyName = ""; say(name, problem, null, "bad"); afterTake(name); return; }
  paintLine(name);
  try {
    const reply = await api(`/api/voice/line/${encodeURIComponent(name)}`, { method: "PUT", raw: take.blob, contentType: take.mime });
    const line = lineByName(name);
    if (line) line.recorded = true;
    forgetAudio(name); // the old take is gone on the server too
    busyName = "";
    say(name, auto ? "vr_saved_auto" : "vr_saved", { s: num(reply && reply.duration_s, 1) }, auto ? "warn" : "ok");
  } catch (error) {
    busyName = "";
    say(name, uploadErrorKey(error), null, "bad");
    if (error instanceof ApiError && error.code === "consent") { await load(); return; }
  }
  afterTake(name);
}

/** Redraw after a take or a delete (group counts change) and keep the focus on that line. */
function afterTake(name) {
  render();
  const r = name && refs.get(name);
  if (r) (r.record.disabled ? r.card : r.record).focus({ preventScroll: true });
}

/** The page went to the background mid-take: the recorder lets go of the mic, so drop the take. */
function cancelTake(key) {
  if (!active) return;
  const { name, handle, timer } = active;
  clearInterval(timer);
  active = null;
  try { handle.cancel(); } catch { /* already stopped */ }
  if (key) said.set(name, { key, kind: "warn" });
  afterTake(name);
}

// ---- listening back ------------------------------------------------------------------------
function stopPlayback() {
  const was = playing;
  playing = "";
  ui.player.pause();
  if (was) paintLine(was);
}

async function togglePlay(name) {
  if (playing === name) { stopPlayback(); return; }
  stopPlayback();
  try {
    let url = urls.get(name);
    if (!url) {
      const blob = await api(`/api/voice/line/${encodeURIComponent(name)}`, { as: "blob" });
      url = URL.createObjectURL(blob);
      urls.set(name, url);
    }
    ui.player.src = url;
    playing = name;
    paintLine(name);
    await ui.player.play();
  } catch (error) {
    playing = "";
    if (error instanceof ApiError && error.status === 404) {
      const line = lineByName(name);
      if (line) line.recorded = false;
      say(name, "vr_gone", null, "warn");
      paintState();
    } else if (error && error.name === "NotAllowedError") {
      say(name, "vr_play_blocked", null, "warn");
    } else {
      say(name, error instanceof ApiError ? uploadErrorKey(error) : "vr_play_failed", null, "bad");
    }
  }
}

ui.player.addEventListener("ended", () => stopPlayback());
ui.player.addEventListener("error", () => { if (playing) { const name = playing; stopPlayback(); say(name, "vr_play_failed", null, "bad"); } });

// ---- deleting ------------------------------------------------------------------------------
async function removeLine(name) {
  const line = lineByName(name);
  if (!line || active || busyName) return;
  const { ok } = await ask({ title: t("vr_delete_title"), body: [line.text, t("vr_delete_body")], confirmKey: "vr_delete", danger: true });
  if (!ok) return;
  busyName = name;
  paintAllLines();
  try {
    await api(`/api/voice/line/${encodeURIComponent(name)}`, { method: "DELETE" });
    line.recorded = false;
    forgetAudio(name);
    busyName = "";
    said.set(name, { key: "vr_deleted", kind: "info" });
  } catch (error) {
    busyName = "";
    said.set(name, { key: uploadErrorKey(error), kind: "bad" });
  }
  afterTake(name);
}

async function wipeAll() {
  if (active || busyName) return;
  const { ok } = await ask({ title: t("vr_wipe_confirm_title"), body: [t("vr_wipe_confirm_body")], confirmKey: "vr_wipe_btn", danger: true });
  if (!ok) return;
  ui.wipe.disabled = true;
  try {
    const reply = await api("/api/voice", { method: "DELETE" });
    forgetAllAudio();
    said.clear();
    toast(t("vr_wiped", { n: num(reply && reply.deleted) }));
    await load();
  } catch (error) {
    toast(t(error && error.code === "network" ? "err_network" : "err_generic"));
  } finally {
    ui.wipe.disabled = false;
  }
}

// ---- consent and loading -------------------------------------------------------------------
function sayConsent(key) {
  consentKey = key;
  ui.consentMsg.textContent = key ? t(key) : "";
  ui.consentMsg.hidden = !key;
}

async function giveConsent() {
  sayConsent("");
  if (!ui.consentTick.checked) {
    sayConsent("vr_consent_need_tick");
    ui.consentTick.focus();
    return;
  }
  ui.consentGo.disabled = true;
  try {
    await api("/api/voice/consent", { method: "POST" });
    await load();
  } catch (error) {
    sayConsent(error && error.code === "network" ? "err_network" : "err_generic");
  } finally {
    ui.consentGo.disabled = false;
  }
}

async function load() {
  try {
    const reply = await api("/api/voice/lines");
    data = {
      consented: !!reply.consented,
      enabled: !!reply.enabled,
      lines: (Array.isArray(reply.lines) ? reply.lines : []).map((line) => ({
        name: String(line.name), text: String(line.text || ""), group: String(line.group || ""), recorded: !!line.recorded,
      })),
    };
    if (!data.consented) {
      showOnly("consent");
      return;
    }
    showOnly("work");
    render();
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || (error.status === 403 && error.code !== "consent"))) return; // redirected
    showError(error);
  }
}

// ---- events and startup --------------------------------------------------------------------
ui.consentGo.addEventListener("click", giveConsent);
ui.consentTick.addEventListener("change", () => sayConsent(""));
ui.wipe.addEventListener("click", wipeAll);
$("#error-retry").addEventListener("click", () => { showOnly("loading"); load(); });
$("#signout").addEventListener("click", () => { cancelTake(""); releaseMic(); signOut(); });
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") { cancelTake("vr_cancelled_hidden"); stopPlayback(); }
});
window.addEventListener("pagehide", () => { cancelTake(""); releaseMic(); forgetAllAudio(); });

function paintWho() {
  if (!me) return;
  ui.who.textContent = `${me.name} (${t(`role_${me.role}`)})`;
  const home = $("#home-link");
  home.setAttribute("href", homeFor(me.role));
  home.textContent = t(me.role === "admin" ? "to_admin" : "to_review");
}

async function start() {
  applyI18n();
  initLangToggle($("#lang"));
  onLangChange(() => { paintWho(); render(); sayConsent(consentKey); });
  try {
    me = await api("/api/review/me");
    paintWho();
  } catch (error) {
    if (error instanceof ApiError && error.code === "network") showError(error);
    return; // auth problems already went to the sign-in page
  }
  await load();
}

start();
