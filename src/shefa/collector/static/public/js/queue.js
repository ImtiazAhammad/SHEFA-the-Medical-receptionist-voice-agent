// Offline-first upload queue. A clip is written to the phone FIRST (IndexedDB, or memory if the
// browser refuses), then sent one at a time with growing, jittered waits. The clip id is made
// on the phone, so a retry after a dropped connection can never create a second copy.
// Audio is stored as an ArrayBuffer plus its type: older iOS Safari cannot keep Blobs in IndexedDB.
import { api } from "./api.js";

const DB = "shefa-clips";
let db = null; // IndexedDB handle, or null when we fall back to memory
const mem = new Map();
const results = new Map(); // clip id -> last outcome, for waitFor()
const subs = new Set(); // () => void, called when the waiting count changes
const outcomeSubs = new Set(); // (outcome) => void
let items = []; // cached view of everything waiting, oldest first
let running = false;
let timer = null;
let state = { paused: "", auth: false }; // why we are holding back, for the status line

const idb = (mode, fn) => new Promise((resolve, reject) => {
  const tx = db.transaction("clips", mode);
  const r = fn(tx.objectStore("clips"));
  tx.oncomplete = () => resolve(r && r.result);
  tx.onerror = tx.onabort = () => reject(tx.error);
});

export async function init() {
  try {
    db = await new Promise((resolve, reject) => {
      const open = indexedDB.open(DB, 1);
      open.onupgradeneeded = () => open.result.createObjectStore("clips", { keyPath: "id" });
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
    items = (await idb("readonly", (s) => s.getAll())) || [];
  } catch { db = null; items = [...mem.values()]; }
  items.sort((a, b) => a.created - b.created);
  try { navigator.storage && navigator.storage.persist && navigator.storage.persist(); } catch { /* optional */ }
  window.addEventListener("online", () => { items.forEach((i) => (i.nextAt = 0)); kick(); });
  window.addEventListener("beforeunload", (e) => {
    if (items.length) { e.preventDefault(); e.returnValue = ""; }
  });
  changed();
  kick();
}

export const pending = () => items.length;
export const list = () => items.slice();
export const status = () => state;
export const onChange = (fn) => { subs.add(fn); return () => subs.delete(fn); };
export const onOutcome = (fn) => { outcomeSubs.add(fn); return () => outcomeSubs.delete(fn); };
const changed = () => subs.forEach((fn) => fn());

async function persist(rec) {
  if (db) { try { await idb("readwrite", (s) => s.put(rec)); return; } catch { db = null; } }
  mem.set(rec.id, rec);
}
async function unpersist(id) {
  mem.delete(id);
  if (db) { try { await idb("readwrite", (s) => s.delete(id)); } catch { /* ignore */ } }
}

export async function hexSha(buf) {
  try {
    if (!(crypto.subtle && crypto.subtle.digest)) return "";
    const d = new Uint8Array(await crypto.subtle.digest("SHA-256", buf));
    return [...d].map((b) => b.toString(16).padStart(2, "0")).join("");
  } catch { return ""; }
}

export function newClipId() {
  const b = crypto.getRandomValues(new Uint8Array(16));
  return [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

// Save a clip locally and start sending. Resolves as soon as it is safe on the phone.
export async function add({ blob, speaker, meta, dur }) {
  const buf = await blob.arrayBuffer();
  const rec = { id: newClipId(), speaker, buf, mime: blob.type || "audio/wav", sha: await hexSha(buf), meta, dur, created: Date.now(), tries: 0, nextAt: 0 };
  await persist(rec);
  items.push(rec);
  changed();
  kick();
  return rec.id;
}

// Wait up to `ms` for the server's verdict on one clip (so a rejection shows on the same step).
export function waitFor(id, ms) {
  if (results.has(id)) return Promise.resolve(results.get(id));
  return new Promise((resolve) => {
    const off = onOutcome((o) => { if (o.id === id) { off(); clearTimeout(t); resolve(o); } });
    const t = setTimeout(() => { off(); resolve({ id, outcome: "pending" }); }, ms);
  });
}

export async function clearAll() {
  for (const i of items) await unpersist(i.id);
  items = [];
  changed();
}

// Forget the waiting clips of one person (they deleted their recordings).
export async function clearSpeaker(speaker) {
  for (const i of items.filter((x) => x.speaker === speaker)) await unpersist(i.id);
  items = items.filter((x) => x.speaker !== speaker);
  changed();
}

function finish(rec, outcome, extra = {}) {
  const o = { id: rec.id, outcome, meta: rec.meta, speaker: rec.speaker, dur: rec.dur, ...extra };
  results.set(rec.id, o);
  items = items.filter((i) => i.id !== rec.id);
  unpersist(rec.id);
  changed();
  outcomeSubs.forEach((fn) => fn(o));
}

// How long to wait before the next try: 1.5 s doubling up to a minute, with random jitter so
// a whole village coming back online does not hit the server in the same second.
const backoff = (tries) => Math.min(60000, 1500 * 2 ** Math.min(tries, 6)) * (0.6 + Math.random() * 0.4);

export function kick() {
  if (running) return;
  running = true;
  loop().finally(() => { running = false; });
}

async function loop() {
  for (;;) {
    clearTimeout(timer);
    const due = items.find((i) => i.nextAt <= Date.now());
    if (!due) {
      if (items.length) {
        const next = Math.min(...items.map((i) => i.nextAt));
        timer = setTimeout(kick, Math.max(500, next - Date.now()));
      }
      return;
    }
    if (navigator.onLine === false) { // do not burn tries while we know there is no network
      timer = setTimeout(kick, 4000);
      return;
    }
    await sendOne(due);
  }
}

async function sendOne(rec) {
  const m = rec.meta || {};
  const headers = { "X-Card": m.card || "", "X-Step": m.step || "", "X-Setting": m.setting || "" };
  if (rec.sha) headers["X-Sha256"] = rec.sha;
  if (m.slot) headers["X-Slot"] = m.slot;
  if (m.choice) headers["X-Choice"] = m.choice;
  if (m.persona) headers["X-Persona"] = m.persona;
  if (m.autostop) headers["X-Autostop"] = "1";
  if (m.free) headers["X-Free"] = "1";
  if (m.room) { headers["X-Room"] = m.room; headers["X-Role"] = m.role || ""; headers["X-Turn"] = String(m.turn || 0); }
  const res = await api("/api/c/clip/" + rec.id, { method: "PUT", body: new Blob([rec.buf], { type: rec.mime }), headers, speaker: rec.speaker, timeout: 60000 });
  const hold = (ms, why = "") => {
    rec.tries++; rec.nextAt = Date.now() + ms; state = { ...state, paused: why }; changed();
    outcomeSubs.forEach((fn) => fn({ id: rec.id, outcome: "held" })); // lets a waiting screen stop waiting
  };
  if (res.ok) { state = { paused: "", auth: false }; return finish(rec, res.data && res.data.duplicate ? "dropped" : "sent", { duration_s: res.data && res.data.duration_s }); }
  const { code, message, reason } = res.error;
  if (res.status === 409 || res.status === 410) return finish(rec, "dropped", { code }); // duplicate or withdrawn: quietly forget it
  if (res.status === 422 && code !== "corrupt") return finish(rec, "rejected", { code, reason, message });
  if (res.status === 413) return finish(rec, "rejected", { code, reason: "too_big", message });
  if (res.status === 401) { state = { ...state, auth: true }; return hold(60000); }
  if (res.status === 503) return hold(60000, reason || "paused");
  if (res.status === 429) {
    if (code === "daily_cap") { state = { ...state, paused: "daily_cap" }; return hold(30 * 60000, "daily_cap"); }
    return hold(Math.max(15000, backoff(rec.tries)));
  }
  return hold(backoff(rec.tries)); // network error, 5xx, damaged in transit
}
