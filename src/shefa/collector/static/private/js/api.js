// Talking to the server, and keeping the staff token.
// Token rules (from the design): typed once, kept in sessionStorage only (gone when the tab closes),
// never in a URL, never in localStorage. A 401 or 403 sends the person back to sign-in.

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
  constructor(status, code, message) {
    super(message || code);
    this.status = status;
    this.code = code;
  }
}

/** Server errors come in two shapes: {error:{code,message}} and FastAPI's 422 {detail:[...]}. */
export function parseError(status, body) {
  if (body && body.error && typeof body.error === "object") {
    return new ApiError(status, String(body.error.code || "error"), String(body.error.message || ""));
  }
  if (body && Array.isArray(body.detail)) return new ApiError(status, "invalid", "invalid input");
  return new ApiError(status, status ? `http_${status}` : "network", "");
}

/** Pages go to sign-in on 401/403. Relative URL so this also works when mounted under /review/. */
export function signOutTo(flash) {
  clearToken();
  if (flash) setFlash(flash);
  location.href = "index.html";
}

/**
 * Call the API as the signed-in person. Returns parsed JSON; throws ApiError otherwise.
 * auth:false lets the sign-in page test a token before storing it (pass token explicitly).
 */
export async function api(path, { method = "GET", body, token, redirectOnAuth = true } = {}) {
  const headers = { Authorization: `Bearer ${token ?? getToken()}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(base() + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store" });
  } catch {
    throw new ApiError(0, "network", "");
  }
  let data = null;
  try { data = await response.json(); } catch { /* empty or non-JSON body */ }
  if (!response.ok) {
    const error = parseError(response.status, data);
    if (redirectOnAuth && (response.status === 401 || response.status === 403) && error.code !== "expired") {
      signOutTo(response.status === 401 ? "expired" : "forbidden");
    }
    throw error;
  }
  return data;
}

/** Audio links are signed and absolute (/api/...); prefix the API base when the shell is elsewhere. */
export function audioSrc(url) {
  return /^https?:/.test(url) ? url : base() + url;
}
