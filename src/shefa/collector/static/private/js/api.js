// Talking to the server, and keeping the staff session.
// Session rules (from the design): a person signs in with a username and a password; the server
// answers with a session token that is kept in sessionStorage only (gone when the tab closes),
// never in a URL, never in localStorage. A 401 sends the person back to sign-in. A 403 with the
// code "must_change" sends them to the "choose your own password" screen.

const TOKEN_KEY = "shefa_staff_token";
const FLASH_KEY = "shefa_staff_flash";

function base() {
  return (typeof window !== "undefined" && window.SHEFA_API) || "";
}

export function getToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return memoryToken; }
}
let memoryToken = ""; // fallback if sessionStorage is blocked: lives until the page reloads
export function setToken(token) {
  memoryToken = token;
  try { sessionStorage.setItem(TOKEN_KEY, token); } catch { /* keep the in-memory copy */ }
}
export function clearToken() {
  memoryToken = "";
  try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* nothing to clear */ }
}

/** A one-shot message for the sign-in page ("session ended", "wrong role"). */
export function setFlash(code) { try { sessionStorage.setItem(FLASH_KEY, code); } catch { /* optional */ } }
export function takeFlash() {
  try {
    const code = sessionStorage.getItem(FLASH_KEY) || "";
    sessionStorage.removeItem(FLASH_KEY);
    return code;
  } catch { return ""; }
}

export class ApiError extends Error {
  constructor(status, code, message, reason = "") {
    super(message || code);
    this.status = status;
    this.code = code;
    this.reason = reason; // audio rejections say why: too_short, too_long, silent, clipped, unreadable
  }
}

/** Server errors come in two shapes: {error:{code,message}} and FastAPI's 422 {detail:[...]}. */
export function parseError(status, body) {
  if (body && body.error && typeof body.error === "object") {
    return new ApiError(status, String(body.error.code || "error"), String(body.error.message || ""), String(body.error.reason || ""));
  }
  if (body && Array.isArray(body.detail)) return new ApiError(status, "invalid", "invalid input");
  return new ApiError(status, status ? `http_${status}` : "network", "");
}

/**
 * What a failed call means for the session (kept apart from fetch so Node can check it):
 * "signin" = the session is gone, "forbidden" = this account may not open that page,
 * "password" = a one-time password must be replaced first, "" = an ordinary error for the page.
 * A 403 with any other code (consent, expired audio link, ...) is NOT a session problem.
 */
export function authAction(status, code) {
  if (status === 401) return "signin";
  if (status === 403 && code === "must_change") return "password";
  if (status === 403 && code === "forbidden") return "forbidden";
  return "";
}

/** Back to sign-in. Relative URL so this also works when the pages are mounted under /review/. */
export function signOutTo(flash) {
  clearToken();
  if (flash) setFlash(flash);
  location.href = "index.html";
}

/** The screen where a person chooses their own password (also used for "change password"). */
export const PASSWORD_PAGE = "index.html#password";

/** "বের হই": end the session on the server (best effort), forget it here, go to sign-in. */
export async function signOut() {
  if (getToken()) {
    try { await api("/api/staff/logout", { method: "POST", redirectOnAuth: false }); } catch { /* signing out anyway */ }
  }
  signOutTo("");
}

/**
 * Call the API as the signed-in person. Returns parsed JSON; throws ApiError otherwise.
 *   body        a value sent as JSON
 *   raw         a Blob sent as it is (a recording); `contentType` names it
 *   as: "blob"  return the reply as a Blob (audio that needs the Bearer header)
 *   token       use this token instead of the stored one ("" sends no Authorization header)
 *   redirectOnAuth:false  the page handles 401/403 itself (sign-in and password forms)
 */
export async function api(path, { method = "GET", body, raw, contentType, as = "json", token, redirectOnAuth = true } = {}) {
  const headers = {};
  const bearer = token ?? getToken();
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  let payload;
  if (raw !== undefined) {
    payload = raw;
    headers["Content-Type"] = contentType || raw.type || "application/octet-stream";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  let response;
  try {
    response = await fetch(base() + path, { method, headers, body: payload, cache: "no-store" });
  } catch {
    throw new ApiError(0, "network", "");
  }
  if (response.ok && as === "blob") {
    try { return await response.blob(); } catch { throw new ApiError(0, "network", ""); }
  }
  let data = null;
  try { data = await response.json(); } catch { /* empty or non-JSON body */ }
  if (!response.ok) {
    const error = parseError(response.status, data);
    if (redirectOnAuth) {
      const action = authAction(response.status, error.code);
      if (action === "signin") signOutTo("expired");
      else if (action === "forbidden") signOutTo("forbidden");
      else if (action === "password") location.href = PASSWORD_PAGE;
    }
    throw error;
  }
  return data;
}

/** Audio links are signed and absolute (/api/...); prefix the API base when the shell is elsewhere. */
export function audioSrc(url) {
  return /^https?:/.test(url) ? url : base() + url;
}
