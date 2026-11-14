// Reviewer page. One clip at a time: listen, write what was said, submit, next.
// Quality matters more than speed here, because these transcripts become training data.
import { api, ApiError, audioSrc, signOutTo } from "./api.js";
import { $, clear, el, toast } from "./dom.js";
import { applyI18n, initLangToggle, num, onLangChange, t } from "./i18n.js";
import { createPlayer } from "./player.js";
import {
  buildSubmission, heardEnough, isRejecting, noteKey, secondsSpent,
  skipsToNext, submitErrorKey, viewFor,
} from "./review-model.js";

const COUNT_KEY = "shefa_review_count";
const PREF_KEY = "shefa_review_prefs";

const ui = {
  loading: $("#loading"), error: $("#error"), errorText: $("#error-text"), empty: $("#empty"),
  emptyCount: $("#empty-count"), work: $("#work"), question: $("#question"), chips: $("#chips"),
  audioMsg: $("#audio-msg"), draftWarn: $("#draft-warn"), noDraft: $("#no-draft"),
  verifyBox: $("#verify-box"), expected: $("#expected"), adjBox: $("#adj-box"), candidates: $("#candidates"),
  textBox: $("#text-box"), text: $("#text"), msg: $("#msg"), rejectNote: $("#reject-note"),
  submit: $("#submit"), yes: $("#yes"), fix: $("#fix"), done: $("#done"), doneText: $("#done-text"),
  doneNotes: $("#done-notes"), counter: $("#counter"), who: $("#who"), answer: $("#answer"),
  guide: $("#guide"), autoplay: $("#autoplay"),
};

let item = null;        // the clip on screen
let view = null;        // what viewFor() decided
let startedAt = 0;      // when it appeared, for "seconds"
let busy = false;       // true while submitting or showing the result
let fixing = false;     // verify mode: the person chose "ঠিক করি"
let sessionCount = 0;
let nextTimer = 0;
let firstClip = true;
let refreshingAudio = false;

try { sessionCount = Number(sessionStorage.getItem(COUNT_KEY)) || 0; } catch { /* optional */ }

// ---- small preferences kept per browser (convenience only) --------------------------------
function loadPrefs() {
  try {
    const prefs = JSON.parse(localStorage.getItem(PREF_KEY) || "{}");
    if (prefs.autoplay === false) ui.autoplay.checked = false;
    if (prefs.guide === false) ui.guide.open = false;
    else if (prefs.guide === undefined && window.matchMedia("(max-width: 899px)").matches) ui.guide.open = false;
  } catch { /* defaults are fine */ }
}
function savePrefs() {
  try { localStorage.setItem(PREF_KEY, JSON.stringify({ autoplay: ui.autoplay.checked, guide: ui.guide.open })); } catch { /* optional */ }
}
ui.autoplay.addEventListener("change", savePrefs);
ui.guide.addEventListener("toggle", savePrefs);

// ---- player -------------------------------------------------------------------------------
const player = createPlayer(
  {
    audio: $("#audio"), seek: $("#seek"), time: $("#time"),
    speedButtons: [...document.querySelectorAll(".speeds button[data-speed]")],
  },
  {
    onAudioError: refreshAudio,
    onBlocked: () => { ui.audioMsg.textContent = t("rv_err_autoplay"); },
    onState: (state) => {
      const playing = state === "playing";
      $("#play").textContent = playing ? t("rv_pause") : t("rv_play");
      if (playing) ui.audioMsg.textContent = "";
    },
  },
);

/**
 * A signed audio link lasts 10 minutes. When the audio fails, ask the queue again: if it is the
 * same clip we only swap the link (the typed text stays), otherwise a new clip is shown.
 */
async function refreshAudio() {
  if (refreshingAudio || !item) return;
  refreshingAudio = true;
  try {
    const data = await api("/api/review/next");
    if (data.item && data.item.clip_id === item.clip_id) {
      item.audio_url = data.item.audio_url;
      player.reload(audioSrc(item.audio_url));
      ui.audioMsg.textContent = t("rv_audio_renewed");
    } else {
      toast(t("rv_audio_changed"), 6000);
      show(data.item);
    }
  } catch (error) {
    ui.audioMsg.textContent = t("rv_err_audio");
  } finally {
    refreshingAudio = false;
  }
}

// ---- screens ------------------------------------------------------------------------------
function showOnly(name) {
  ui.loading.hidden = name !== "loading";
  ui.error.hidden = name !== "error";
  ui.empty.hidden = name !== "empty";
  ui.work.hidden = name !== "work";
}

function paintCounter() {
  const text = t("rv_counter", { n: num(sessionCount) });
  ui.counter.textContent = text;
  ui.emptyCount.textContent = text;
}

function currentFlags() {
  return [...document.querySelectorAll('input[name="flag"]:checked')].map((box) => box.value);
}
function setFlags(flags) {
  for (const box of document.querySelectorAll('input[name="flag"]')) box.checked = flags.includes(box.value);
}

function paintChips() {
  clear(ui.chips);
  if (!item) return;
  const parts = [];
  if (item.slot) parts.push(t(`slot_${item.slot}`));
  if (item.kind) parts.push(t(`kind_${item.kind}`));
  if (item.duration_s) parts.push(t("rv_seconds", { n: num(item.duration_s, 1) }));
  for (const part of parts) ui.chips.append(el("span", { class: "chip", text: part }));
}

/** Mode-specific parts. `view.ui` decides everything; blind and seed arrive here as "type". */
function paintMode() {
  const rejecting = isRejecting(currentFlags());
  ui.draftWarn.hidden = view.ui !== "draft";
  ui.noDraft.hidden = !(view.ui === "draft" && view.noDraft);
  ui.verifyBox.hidden = view.ui !== "verify" || fixing;
  ui.adjBox.hidden = view.ui !== "adjudicate";
  ui.textBox.hidden = view.ui === "verify" && !fixing;
  // In plain "yes" state of verify the Yes button is the submit; the common button returns when
  // fixing, or when a rejecting flag means there is nothing to confirm.
  ui.submit.hidden = view.ui === "verify" && !fixing && !currentFlags().length;
  ui.rejectNote.hidden = !rejecting;
  ui.yes.textContent = t("rv_yes");
}

function renderCandidates() {
  clear(ui.candidates);
  view.candidates.forEach((candidate, index) => {
    const flags = candidate.flags.map((flag) => el("span", { class: "chip warn", text: t(`flag_${flag}`) }));
    ui.candidates.append(el("div", { class: "candidate" }, [
      el("strong", { text: t("rv_adj_candidate", { n: num(index + 1) }) }),
      el("div", { class: "text", lang: "bn", text: candidate.text || "—" }),
      flags.length ? el("div", { class: "meta-chips" }, flags) : null,
      el("button", {
        type: "button", class: "primary",
        onclick: () => { ui.text.value = candidate.text; ui.text.focus(); },
      }, t("rv_use_this")),
    ]));
  });
}

function showMessage(text) {
  ui.msg.textContent = text;
  ui.msg.hidden = !text;
}

/** Put a clip (or the empty state) on screen. */
function show(next) {
  clearTimeout(nextTimer);
  busy = false;
  ui.done.hidden = true;
  ui.answer.hidden = false;
  showMessage("");
  ui.audioMsg.textContent = "";
  if (!next) {
    item = null;
    player.stop();
    paintCounter();
    showOnly("empty");
    $("#empty-refresh").focus();
    return;
  }
  item = next;
  view = viewFor(next);
  fixing = false;
  startedAt = Date.now();
  setFlags([]);
  ui.question.textContent = next.question_bn || t("rv_no_question");
  ui.expected.textContent = view.expected;
  ui.text.value = view.prefill;
  paintChips();
  renderCandidates();
  paintMode();
  paintCounter();
  showOnly("work");
  player.load(audioSrc(next.audio_url), next.duration_s);
  if (ui.autoplay.checked && !firstClip) player.autoplay();
  firstClip = false;
  focusInput();
  window.scrollTo({ top: 0 });
}

function focusInput() {
  if (view.ui === "verify" && !fixing) { ui.yes.focus({ preventScroll: true }); return; }
  ui.text.focus({ preventScroll: true });
  const end = ui.text.value.length;
  ui.text.setSelectionRange(end, end);
}

// ---- loading and submitting ---------------------------------------------------------------
async function loadNext() {
  showOnly("loading");
  try {
    const data = await api("/api/review/next");
    show(data.item);
  } catch (error) {
    ui.errorText.textContent = errorText(error);
    showOnly("error");
  }
}

function errorText(error) {
  if (error instanceof ApiError) return t(submitErrorKey(error));
  return t("err_generic");
}

async function submit({ yes = false } = {}) {
  if (!item || busy) return;
  const flags = currentFlags();
  const rejecting = isRejecting(flags);
  const text = yes ? view.expected : ui.text.value;
  if (!rejecting) {
    if (!heardEnough(player.heardSeconds(), player.duration())) {
      showMessage(t("rv_err_listen"));
      return;
    }
    if (!text.trim()) { showMessage(t("rv_err_empty")); ui.text.focus(); return; }
  }
  busy = true;
  ui.submit.disabled = ui.yes.disabled = true;
  showMessage("");
  try {
    const body = buildSubmission({ clipId: item.clip_id, text, flags, seconds: secondsSpent(startedAt, Date.now()) });
    const reply = await api("/api/review/submit", { method: "POST", body });
    // Count it, then show the cleaned text for a moment. We never show reply.status: for a
    // known-answer clip it would give the clip away.
    sessionCount += 1;
    try { sessionStorage.setItem(COUNT_KEY, String(sessionCount)); } catch { /* optional */ }
    showResult(reply, rejecting);
  } catch (error) {
    busy = false;
    if (skipsToNext(error)) {
      toast(t("rv_err_already"));
      await loadNext();
      return;
    }
    showMessage(errorText(error));
    if (error.code === "no_bangla" || error.code === "empty") { fixing = true; paintMode(); ui.text.focus(); }
  } finally {
    ui.submit.disabled = ui.yes.disabled = false;
  }
}

function showResult(reply, rejected) {
  player.stop();
  ui.answer.hidden = true;
  ui.done.hidden = false;
  ui.doneText.textContent = reply.text || (rejected ? t("rv_rejected_done") : "—");
  clear(ui.doneNotes);
  const notes = Array.isArray(reply.notes) ? reply.notes : [];
  for (const note of notes) {
    const key = noteKey(note);
    ui.doneNotes.append(el("li", { text: key ? t(key) : String(note) }));
  }
  paintCounter();
  $("#next-now").focus();
  // Long enough to read the cleaned text (longer when something was changed), short enough to keep flowing.
  nextTimer = setTimeout(loadNext, notes.length ? 3200 : 1400);
}

// ---- events -------------------------------------------------------------------------------
$("#play").addEventListener("click", () => player.toggle());
$("#replay").addEventListener("click", () => player.replay());
$("#cant-hear").addEventListener("click", () => {
  // Never rejects by itself: it ticks "unusable" and lets the person confirm with Submit.
  setFlags([...new Set([...currentFlags(), "unusable"])]);
  paintMode();
  showMessage("");
  ui.audioMsg.textContent = t("rv_cant_hear_note");
  ui.submit.hidden = false;
  ui.submit.focus();
});
ui.submit.addEventListener("click", () => submit());
ui.yes.addEventListener("click", () => submit({ yes: true }));
ui.fix.addEventListener("click", () => { fixing = true; paintMode(); ui.text.focus(); });
$("#next-now").addEventListener("click", () => { clearTimeout(nextTimer); loadNext(); });
$("#error-retry").addEventListener("click", loadNext);
$("#empty-refresh").addEventListener("click", loadNext);
$("#signout").addEventListener("click", () => signOutTo(""));
for (const box of document.querySelectorAll('input[name="flag"]')) box.addEventListener("change", paintMode);
ui.text.addEventListener("input", () => { if (ui.msg.textContent) showMessage(""); });

function primaryAction() {
  if (!item || ui.work.hidden) return;
  if (!ui.done.hidden) { clearTimeout(nextTimer); loadNext(); return; } // result on screen: go on
  if (busy) return;
  if (view.ui === "verify" && !fixing && !isRejecting(currentFlags())) submit({ yes: true });
  else submit();
}

document.addEventListener("keydown", (event) => {
  // Never act while an input method is composing Bangla letters.
  if (event.isComposing || event.keyCode === 229) return;
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); primaryAction(); return; }
  if (!item) return;
  // Ctrl+Space is often the Bangla keyboard switch, so F8 does the same thing.
  if ((event.ctrlKey && event.code === "Space") || event.key === "F8") { event.preventDefault(); player.replay(); return; }
  if (event.key === "F9") { event.preventDefault(); player.back(3); }
});

// ---- language and startup -----------------------------------------------------------------
function paintSpeeds() {
  for (const button of document.querySelectorAll(".speeds button[data-speed]")) {
    button.textContent = `${num(Number(button.dataset.speed), 2)}×`;
  }
}
function repaintAll() {
  paintSpeeds();
  paintCounter();
  $("#play").textContent = $("#audio").paused ? t("rv_play") : t("rv_pause");
  if (item && view) { paintChips(); renderCandidates(); paintMode(); if (!item.question_bn) ui.question.textContent = t("rv_no_question"); }
}

async function start() {
  applyI18n();
  initLangToggle($("#lang"));
  onLangChange(repaintAll);
  loadPrefs();
  paintSpeeds();
  try {
    const me = await api("/api/review/me");
    ui.who.textContent = `${me.name} (${t(`role_${me.role}`)})`;
    $("#admin-link").hidden = me.role !== "admin";
    onLangChange(() => { ui.who.textContent = `${me.name} (${t(`role_${me.role}`)})`; });
  } catch (error) {
    if (!(error instanceof ApiError) || error.code === "network") {
      ui.errorText.textContent = t("err_network");
      showOnly("error");
      return;
    }
    return; // auth errors already redirected to sign-in
  }
  await loadNext();
}

start();
