// Tiny DOM helpers. No framework: pages are built with h() and updated in place.
// Everything is created with createElement/textContent, never innerHTML, so text that comes
// from a link (?from=) or from the server can never inject markup.

export const $ = (sel, root = document) => root.querySelector(sel);

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  add(el, kids);
  return el;
}

export function add(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

// Replace the contents of el with kids (null/false are skipped, unlike the native append).
export const fill = (el, ...kids) => add(clear(el), kids);

export function clear(el) {
  el.replaceChildren();
  return el;
}

// An inline SVG that points at a symbol defined once in index.html.
export function icon(name, cls = "") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ic " + cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

// Small helper so every await-able wait can be written in one line.
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
