// Microphone and recording. Preferred path: an AudioWorklet builds a 16 kHz 16-bit WAV (what the
// server likes best, no codec in the way). Fallback for older phones: MediaRecorder.
// The browser's "helpful" voice processing is switched OFF on purpose: echo cancellation, noise
// suppression and auto gain change the sound the speech model must learn to hear.

const DEV = new URLSearchParams(location.search).get("devmic") === "1"; // test hook, inert otherwise

let mic = null; // { stream, ctx, dev }
let wake = null;

const Ctx = window.AudioContext || window.webkitAudioContext;

// A fake microphone for testing without hardware: a buzzy "voice" switched on and off in bursts.
function synthStream() {
  const ctx = new Ctx();
  const dest = ctx.createMediaStreamDestination();
  const amp = ctx.createGain();
  amp.gain.value = 0;
  const bands = [[700, 4], [1200, 4], [2600, 3]].map(([f, q]) => {
    const b = ctx.createBiquadFilter();
    b.type = "bandpass"; b.frequency.value = f; b.Q.value = q;
    b.connect(amp);
    return b;
  });
  const osc = ctx.createOscillator();
  osc.type = "sawtooth"; osc.frequency.value = 130;
  bands.forEach((b) => osc.connect(b));
  amp.connect(dest);
  osc.start();
  // A fixed on/off pattern (not random) so every clip has real pauses: the server judges "speech"
  // against the quietest frames, so non-stop sound would be rejected as silence.
  const pattern = [0, 1, 1, 1, 0, 1, 1, 0];
  let tick = 0;
  const timer = setInterval(() => {
    const talking = pattern[tick++ % pattern.length] === 1;
    amp.gain.setTargetAtTime(talking ? 0.7 : 0.0, ctx.currentTime, 0.02);
    osc.frequency.setTargetAtTime(110 + Math.random() * 60, ctx.currentTime, 0.03);
  }, 180);
  return { stream: dest.stream, ctx, stop: () => { clearInterval(timer); osc.stop(); } };
}

export function micErrorKey(err) {
  const name = err && err.name;
  if (!window.isSecureContext || !navigator.mediaDevices) return "mic_insecure";
  if (name === "NotAllowedError" || name === "SecurityError") return "mic_denied";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "mic_none";
  if (name === "NotReadableError" || name === "AbortError") return "mic_busy";
  return "mic_generic";
}

// Open the microphone once and keep it for the whole card session, so the phone does not ask
// again for every clip. release() hands it back when the person leaves the recording screens.
export async function openMic() {
  if (mic && mic.stream.getAudioTracks().some((t) => t.readyState === "live")) {
    if (mic.ctx && mic.ctx.state === "suspended") await mic.ctx.resume();
    return mic;
  }
  mic = null;
  if (DEV) {
    const d = synthStream();
    mic = { stream: d.stream, ctx: d.ctx, dev: d };
  } else {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw Object.assign(new Error("no mediaDevices"), { name: "SecurityError" });
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
    mic = { stream, ctx: Ctx ? new Ctx() : null, dev: null };
  }
  if (mic.ctx && mic.ctx.state === "suspended") await mic.ctx.resume();
  return mic;
}

export function releaseMic() {
  if (!mic) return;
  try { mic.stream.getTracks().forEach((t) => t.stop()); } catch { /* ignore */ }
  try { if (mic.dev) mic.dev.stop(); } catch { /* ignore */ }
  try { if (mic.ctx) mic.ctx.close(); } catch { /* ignore */ }
  mic = null;
}

// Keep the screen on while someone is talking (phones dim and may suspend the page otherwise).
async function holdScreen() {
  try { wake = navigator.wakeLock ? await navigator.wakeLock.request("screen") : null; } catch { wake = null; }
}
function dropScreen() {
  try { if (wake) wake.release(); } catch { /* ignore */ }
  wake = null;
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") releaseMic(); // do not hold the mic while in the background
});

function wav(chunks, total) {
  const buf = new ArrayBuffer(44 + total * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, "RIFF"); v.setUint32(4, 36 + total * 2, true); str(8, "WAVE"); str(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 16000, true); v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, "data"); v.setUint32(40, total * 2, true);
  let at = 44;
  for (const c of chunks) { new Int16Array(buf, at, c.length).set(c); at += c.length * 2; }
  return new Blob([buf], { type: "audio/wav" });
}

const pickMime = () => ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/ogg"]
  .find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) || "";

// Summary of how loud the clip was; the review step and mic check use it to warn early.
function summarize(levels, peak) {
  const sorted = levels.slice().sort((a, b) => a - b);
  const q = (p) => (sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))] : 0);
  return { peak, floor: q(0.2), loud: q(0.9) };
}

/**
 * Start recording. onLevel(0..1) feeds the meter. Returns { stop(), cancel() };
 * stop() resolves { blob, mime, dur, peak, floor, loud }.
 */
export async function record(onLevel) {
  const m = await openMic();
  const levels = [];
  let peak = 0;
  const t0 = performance.now();
  const meter = (rms, pk) => {
    levels.push(rms);
    if (levels.length > 2000) levels.splice(0, 500);
    if (pk > peak) peak = pk;
    onLevel && onLevel(Math.max(0, Math.min(1, (20 * Math.log10(rms || 1e-5) + 60) / 45)));
  };
  holdScreen();

  // ---- AudioWorklet path
  if (m.ctx && m.ctx.audioWorklet && typeof AudioWorkletNode !== "undefined" && m.wk !== "no") {
    try {
      if (!m.wk) { await m.ctx.audioWorklet.addModule(new URL("./worklet.js", import.meta.url).href); m.wk = true; }
      const src = m.ctx.createMediaStreamSource(m.stream);
      const node = new AudioWorkletNode(m.ctx, "shefa-capture", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: "explicit" });
      const mute = m.ctx.createGain(); mute.gain.value = 0; // some browsers only run nodes that reach the speakers
      src.connect(node); node.connect(mute); mute.connect(m.ctx.destination);
      const chunks = []; let total = 0; let finish;
      const done = new Promise((r) => { finish = r; });
      node.port.onmessage = (e) => {
        if (e.data.pcm) { chunks.push(e.data.pcm); total += e.data.pcm.length; }
        else if (e.data.rms != null) meter(e.data.rms, e.data.peak);
        else if (e.data.done) finish();
      };
      const cleanup = () => { try { src.disconnect(); node.disconnect(); mute.disconnect(); } catch { /* ignore */ } dropScreen(); };
      return {
        async stop() {
          node.port.postMessage("stop");
          await Promise.race([done, new Promise((r) => setTimeout(r, 1500))]);
          cleanup();
          return { blob: wav(chunks, total), mime: "audio/wav", dur: total / 16000, ...summarize(levels, peak) };
        },
        cancel() { cleanup(); },
      };
    } catch { m.wk = "no"; /* fall through to MediaRecorder */ }
  }

  // ---- MediaRecorder fallback (the level meter comes from an analyser when we have an AudioContext)
  const mime = pickMime();
  const rec = new MediaRecorder(m.stream, mime ? { mimeType: mime } : undefined);
  const parts = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) parts.push(e.data); };
  let poll = null;
  if (m.ctx) {
    const an = m.ctx.createAnalyser(); an.fftSize = 1024;
    m.ctx.createMediaStreamSource(m.stream).connect(an);
    const buf = new Float32Array(an.fftSize);
    poll = setInterval(() => {
      an.getFloatTimeDomainData(buf);
      let sq = 0, pk = 0;
      for (const x of buf) { sq += x * x; pk = Math.max(pk, Math.abs(x)); }
      meter(Math.sqrt(sq / buf.length), pk);
    }, 50);
  }
  rec.start(250);
  const end = () => { clearInterval(poll); dropScreen(); };
  return {
    stop() {
      return new Promise((resolve) => {
        rec.onstop = () => {
          end();
          const type = rec.mimeType || mime || "audio/webm";
          resolve({ blob: new Blob(parts, { type }), mime: type, dur: (performance.now() - t0) / 1000, ...summarize(levels, m.ctx ? peak : 1) });
        };
        try { rec.stop(); } catch { end(); resolve({ blob: new Blob(parts), mime, dur: 0, peak: 0, floor: 0, loud: 0 }); }
      });
    },
    cancel() { end(); try { rec.stop(); } catch { /* ignore */ } },
  };
}
