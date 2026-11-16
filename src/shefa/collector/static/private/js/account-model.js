// Sign-in and password rules, kept free of the DOM so they can be checked in Node.
// The server is the judge (store.py: _hash, sign_in, change_password); these only mirror its rules
// so a person sees what is missing while typing, and turn its replies into string keys.

export const MIN_PASSWORD = 10;

/** The live hints under the "new password" boxes. Each value is true when that rule is met. */
export function passwordRules(password, again, username) {
  const value = String(password || "").normalize("NFC");
  const name = String(username || "").trim().toLowerCase();
  return {
    length: value.length >= MIN_PASSWORD,
    digits: value.length > 0 && !/^\p{Nd}+$/u.test(value), // Bangla digits count as digits too
    username: value.length > 0 && (!name || value.toLowerCase() !== name),
    match: value.length > 0 && value === String(again || "").normalize("NFC"),
  };
}

export function rulesMet(rules) {
  return rules.length && rules.digits && rules.username && rules.match;
}

/** Which message to show after a failed sign-in. Wrong name and wrong password look the same. */
export function loginErrorKey(error) {
  const code = error && error.code;
  if (code === "bad_login" || (error && error.status === 401)) return "si_bad";
  if (code === "locked") return "si_locked";
  if (code === "slow_down" || (error && error.status === 429)) return "si_slow";
  if (code === "invalid") return "si_bad"; // an over-long name or password cannot be right either
  if (code === "network") return "err_network";
  return "err_generic";
}

/** The server explains a refused password in English; known sentences get a translated key. */
const WEAK = {
  "the password must not be the username": "pw_weak_username",
  "use some letters too, not only digits": "pw_weak_digits",
  "a password needs at least 10 characters": "pw_weak_length",
  "that password is too easy to guess": "pw_weak_common",
  "choose a new password, not the same one": "pw_weak_same",
};

/**
 * Which message to show after a failed password change: {key} for a translated string, or
 * {text} when the server said something we have no translation for (shown as sent).
 */
export function passwordError(error) {
  const code = error && error.code;
  if (code === "weak_password") {
    const key = WEAK[error.message];
    return key ? { key } : { key: "pw_weak_other", text: error.message };
  }
  if (code === "bad_login") return { key: "pw_bad_old" };
  if (code === "slow_down" || code === "locked") return { key: "si_slow" };
  if (code === "invalid") return { key: "pw_weak_other", text: "" };
  if (code === "network") return { key: "err_network" };
  return { key: "err_generic" };
}

/** Where a signed-in person works. Relative, so it also works under /review/. */
export function homeFor(role) {
  return role === "admin" ? "admin.html" : "review.html";
}

// ---- usernames (store.py: USERNAME and create_staff) ----------------------------------------
/** The server's rule: 3 to 30 characters, a-z 0-9 . _ -, starting with a letter or a digit. */
export const USERNAME_RE = /^[a-z0-9][a-z0-9._-]{2,29}$/;

/**
 * A username suggested from a name, the way the server makes one ("Rina Akter" -> "rina.akter").
 * A name in Bangla letters gives "" (nothing to suggest): the admin types a username then.
 */
export function suggestUsername(name) {
  const slug = String(name || "").trim().toLowerCase()
    .replace(/[^a-z0-9._-]+/g, ".")
    .replace(/\.{2,}/g, ".")
    .replace(/^[._-]+/, "")
    .replace(/\.+$/, "")
    .slice(0, 30)
    .replace(/[._-]+$/, "");
  return USERNAME_RE.test(slug) ? slug : "";
}

export function usernameOk(username) {
  return USERNAME_RE.test(String(username || "").trim().toLowerCase());
}

/** Which message to show when adding a person or resetting a password fails. */
export function staffErrorKey(error) {
  const code = error && error.code;
  if (code === "taken" || (error && error.status === 409 && code !== "last_admin")) return "staff_err_taken";
  if (code === "bad_username") return "staff_err_username";
  if (code === "weak_password") return "staff_err_weak";
  if (code === "bad_role") return "staff_err_role";
  if (code === "last_admin") return "deact_last_admin";
  if (code === "no_staff") return "staff_err_gone";
  if (code === "invalid") return "staff_err_invalid";
  if (code === "network") return "err_network";
  return "err_generic";
}
