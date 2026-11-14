// Bangla-first language switch. Every visible string lives in strings.js with a bn and an en form.
// Why this shape: static HTML marks its text with data-i18n attributes (no inline script needed),
// and code that builds elements later calls t("key") and re-renders when the language changes.
import { STRINGS } from "./strings.js";

const KEY = "shefa_staff_lang";
let lang = "bn";
const listeners = new Set();

try {
  const saved = typeof localStorage !== "undefined" ? localStorage.getItem(KEY) : "";
  if (saved === "en" || saved === "bn") lang = saved;
} catch { /* storage may be blocked; Bangla is the default anyway */ }

export function getLang() { return lang; }

/** Translate a key. {name} placeholders are filled from vars. A missing key shows itself, never crashes. */
export function t(key, vars) {
  const entry = STRINGS[key];
  let text = entry ? (entry[lang] ?? entry.bn) : key;
  if (vars) text = text.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m));
  return text;
}

/** Numbers in Bangla digits when the page is in Bangla (what the reviewers read naturally). */
export function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  try {
    return new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en", { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(Number(value));
  } catch {
    return String(value);
  }
}

export function dateTime(epochSeconds) {
  if (!epochSeconds) return "—";
  try {
    return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(epochSeconds * 1000));
  } catch {
    return new Date(epochSeconds * 1000).toISOString();
  }
}

/** Fill every [data-i18n*] element under root. Uses textContent/setAttribute only, never innerHTML. */
export function applyI18n(root = document) {
  document.documentElement.lang = lang;
  for (const node of root.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of root.querySelectorAll("[data-i18n-placeholder]")) node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  for (const node of root.querySelectorAll("[data-i18n-aria-label]")) node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  for (const node of root.querySelectorAll("[data-i18n-title]")) node.setAttribute("title", t(node.dataset.i18nTitle));
  const titleKey = document.documentElement.dataset.titleKey;
  if (titleKey) document.title = t(titleKey);
}

export function onLangChange(callback) { listeners.add(callback); }

export function setLang(next) {
  if (next !== "bn" && next !== "en") return;
  lang = next;
  try { localStorage.setItem(KEY, lang); } catch { /* a convenience only */ }
  applyI18n();
  for (const callback of listeners) callback(lang);
}

/** Wire the header button: it always offers the OTHER language. */
export function initLangToggle(button) {
  const paint = () => {
    button.textContent = lang === "bn" ? "English" : "বাংলা";
    button.setAttribute("lang", lang === "bn" ? "en" : "bn");
    button.setAttribute("aria-label", lang === "bn" ? "Switch to English" : "বাংলায় দেখুন");
  };
  button.addEventListener("click", () => setLang(lang === "bn" ? "en" : "bn"));
  onLangChange(paint);
  paint();
}

export function has(key) { return Object.prototype.hasOwnProperty.call(STRINGS, key); }

/** A label for a data key such as a division id: the translated word, or the raw key if unknown. */
export function labelFor(prefix, key) {
  if (key === "unknown") return t("unknown");
  const full = `${prefix}_${key}`;
  return has(full) ? t(full) : String(key);
}
