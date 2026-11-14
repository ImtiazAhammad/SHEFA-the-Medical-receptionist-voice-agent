// Small DOM helpers. Rule for the whole app: server text only ever goes in through textContent,
// so a clip transcript, a person's name or an audit detail can never become markup.

/** el("button", {class:"primary", onclick: fn, "aria-label": "x"}, "text" | [children]) */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "value") node.value = value;
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export const $ = (selector, root = document) => root.querySelector(selector);

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

let toastTimer = 0;
/** A short message in the aria-live region (#toast must exist in the page). */
export function toast(message, ms = 3500) {
  const box = document.getElementById("toast");
  if (!box) return;
  box.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.textContent = ""; }, ms);
}

/** Copy text. Uses the Clipboard API when allowed, else a temporary field and execCommand. */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fall through to the old way */ }
  const field = el("textarea", { readonly: true, "aria-hidden": "true", class: "sr-only" });
  field.value = text;
  document.body.append(field);
  field.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  field.remove();
  return ok;
}

/** A button that copies `getText()` and says so. */
export function copyButton(t, getText, labelKey = "copy") {
  const button = el("button", { type: "button", class: "small-btn" }, t(labelKey));
  button.addEventListener("click", async () => {
    const ok = await copyText(getText());
    toast(ok ? t("copied") : t("copy_failed"));
  });
  return button;
}

/** Whole seconds as m:ss. */
export function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
