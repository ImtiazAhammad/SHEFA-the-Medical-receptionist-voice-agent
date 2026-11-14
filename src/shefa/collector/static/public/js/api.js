// All talking to the server goes through here, so errors look the same everywhere:
// { ok, status, data, error: { code, message, reason } }. A dead network is status 0.
import { S } from "./session.js";

const base = () => window.SHEFA_API || "";

export function authHeaders(speaker) {
  const s = S.session;
  if (!s) return {};
  return { "X-Cid": s.cid, "X-Secret": s.secret, "X-Speaker": speaker || s.speaker };
}

export async function api(path, { method = "GET", body, headers = {}, auth = true, speaker, timeout = 20000, blob = false } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  const h = { ...(auth ? authHeaders(speaker) : {}), ...headers };
  let init = { method, headers: h, signal: ctl.signal, cache: "no-store" };
  if (body instanceof Blob) {
    init.body = body;
  } else if (body !== undefined) {
    h["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  try {
    const res = await fetch(base() + path, init);
    if (blob && res.ok) return { ok: true, status: res.status, data: await res.blob() };
    let data = null;
    try { data = await res.json(); } catch { /* not json */ }
    if (res.ok) return { ok: true, status: res.status, data };
    const e = (data && data.error) || {};
    return { ok: false, status: res.status, data, error: { code: e.code || "http_" + res.status, message: e.message || "", reason: e.reason || "" } };
  } catch {
    return { ok: false, status: 0, error: { code: "network", message: "", reason: "" } };
  } finally {
    clearTimeout(timer);
  }
}

export const url = (path) => base() + path;
