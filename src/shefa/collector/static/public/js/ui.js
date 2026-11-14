// One small message bar for things that happen "in the background" (a clip the server turned down
// after the person had already moved on, a copied link). Never blocks the page.
import { h, clear, fill } from "./dom.js";
import { T } from "./i18n.js";

let timer = null;

export function toast(content, actionKey, onAction) {
  const el = document.getElementById("toast");
  fill(el, h("span", null, content));
  if (actionKey) {
    el.append(h("button", { type: "button", class: "chip", onclick: () => { hide(); onAction && onAction(); } }, T(actionKey)));
  }
  el.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(hide, actionKey ? 9000 : 3500);
}

export function hide() {
  document.getElementById("toast").hidden = true;
}
