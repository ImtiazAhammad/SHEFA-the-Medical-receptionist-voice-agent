// The person's session, kept in localStorage so a reload (or a dead battery) does not lose
// their place. Storage can be blocked (private mode, strict settings), so every access is in
// try/catch and the page keeps working from memory when it fails.

const KEY = "shefa.session.v1";

// cfg: the server's /api/c/config reply. session: who this phone is.
export const S = { cfg: null, session: null };

export function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "null");
    if (raw && raw.cid && raw.secret && raw.speaker) S.session = raw;
  } catch { /* memory only */ }
  return S.session;
}

export function save() {
  try {
    if (S.session) localStorage.setItem(KEY, JSON.stringify(S.session));
    else localStorage.removeItem(KEY);
  } catch { /* memory only */ }
}

export function newSession(made, extra = {}) {
  S.session = {
    cid: made.contributor_id, secret: made.secret, deleteCode: made.delete_code,
    speaker: made.speaker_id, people: { [made.speaker_id]: { n: 0, sec: 0, setting: "", deleteCode: made.delete_code, profileDone: false } },
    seen: [], micOk: false, profileDone: false, consent: S.cfg ? S.cfg.consent_version : "",
    ...extra,
  };
  save();
}

export function endSession() {
  S.session = null;
  save();
}

// The person currently holding the phone (pass-the-phone swaps this).
export function me() {
  const s = S.session;
  if (!s) return null;
  return s.people[s.speaker] || (s.people[s.speaker] = { n: 0, sec: 0, setting: "" });
}

// Every person on a shared phone has their own delete code and profile.
export function addPerson(speakerId, deleteCode) {
  S.session.speaker = speakerId;
  S.session.people[speakerId] = { n: 0, sec: 0, setting: "", deleteCode: deleteCode || "", profileDone: false };
  save();
}

export function totals() {
  const people = Object.values(S.session ? S.session.people : {});
  return { n: people.reduce((a, p) => a + p.n, 0), sec: people.reduce((a, p) => a + p.sec, 0) };
}

export function markSeen(id) {
  const seen = S.session.seen;
  if (!seen.includes(id)) seen.push(id);
  if (seen.length > 60) seen.splice(0, seen.length - 60);
  save();
}
