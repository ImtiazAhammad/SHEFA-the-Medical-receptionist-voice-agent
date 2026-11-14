// A simple clip player: big Play/Replay, three speeds, a plain progress bar (no waveform).
// It also measures how long the clip was really played, so the page can ask a reviewer to listen
// before submitting (drafts anchor people to the machine's mistakes otherwise).
import { clock } from "./dom.js";

const SPEEDS = [0.75, 1, 1.25];

export function createPlayer(els, { onAudioError, onBlocked, onState }) {
  const audio = els.audio;
  let heard = 0;
  let last = 0;
  let expected = 0;
  let raf = 0;
  let hasSource = false;

  const duration = () => (Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : expected);

  function paint() {
    const total = duration();
    const current = audio.currentTime || 0;
    els.seek.value = total ? String(Math.round((current / total) * 1000)) : "0";
    els.seek.setAttribute("aria-valuetext", `${clock(current)} / ${clock(total)}`);
    els.time.textContent = `${clock(current)} / ${clock(total)}`;
  }

  // While playing, count only small forward steps as listening (a jump is a seek, not listening).
  function account() {
    const current = audio.currentTime;
    const step = current - last;
    if (step > 0 && step < 1) heard += step;
    last = current;
  }
  function tick() {
    account();
    paint();
    if (!audio.paused && !audio.ended) raf = requestAnimationFrame(tick);
  }
  // A background tab pauses animation frames but still sends timeupdate, so count there too.
  audio.addEventListener("timeupdate", () => { if (!audio.paused) account(); });

  audio.addEventListener("play", () => { last = audio.currentTime; cancelAnimationFrame(raf); raf = requestAnimationFrame(tick); onState && onState("playing"); });
  audio.addEventListener("pause", () => { cancelAnimationFrame(raf); paint(); onState && onState("paused"); });
  audio.addEventListener("ended", () => { cancelAnimationFrame(raf); paint(); onState && onState("ended"); });
  audio.addEventListener("seeked", () => { last = audio.currentTime; paint(); });
  audio.addEventListener("loadedmetadata", paint);
  audio.addEventListener("error", () => { if (hasSource) onAudioError && onAudioError(); });
  els.seek.addEventListener("input", () => {
    const total = duration();
    if (total) audio.currentTime = (Number(els.seek.value) / 1000) * total;
  });

  function play() {
    const promise = audio.play();
    if (promise && promise.catch) {
      promise.catch((error) => {
        // Autoplay blocked before the first tap is normal; it is not a broken link.
        if (error && error.name === "NotAllowedError") onBlocked && onBlocked();
      });
    }
  }

  const api = {
    load(url, expectedSeconds) {
      heard = 0; last = 0; expected = Number(expectedSeconds) || 0;
      cancelAnimationFrame(raf);
      audio.pause();
      hasSource = true;
      audio.src = url;
      audio.load();
      audio.playbackRate = api.rate;
      paint();
      onState && onState("loaded");
    },
    /** Swap in a fresh signed link (the old one expired) and keep the listening already done. */
    reload(url) {
      const keepHeard = heard;
      api.load(url, expected);
      heard = keepHeard;
    },
    stop() {
      hasSource = false;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    },
    toggle() { if (audio.paused || audio.ended) { if (audio.ended) audio.currentTime = 0; play(); } else audio.pause(); },
    replay() { audio.currentTime = 0; last = 0; play(); },
    back(seconds = 3) { audio.currentTime = Math.max(0, audio.currentTime - seconds); last = audio.currentTime; paint(); },
    autoplay() { audio.currentTime = 0; play(); },
    heardSeconds: () => heard,
    duration,
    rate: 1,
    setRate(rate) {
      if (!SPEEDS.includes(rate)) return;
      api.rate = rate;
      audio.defaultPlaybackRate = rate;
      audio.playbackRate = rate;
      for (const button of els.speedButtons) button.setAttribute("aria-pressed", String(Number(button.dataset.speed) === rate));
    },
  };
  for (const button of els.speedButtons) button.addEventListener("click", () => api.setRate(Number(button.dataset.speed)));
  api.setRate(1);
  return api;
}
