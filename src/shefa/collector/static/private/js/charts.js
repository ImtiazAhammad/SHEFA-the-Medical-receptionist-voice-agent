// Plain CSS bar charts: a row is a label, a bar whose width is a CSS variable, and the number.
// No library, and the numbers are always printed so colour or width is never the only signal.
import { clear, el } from "./dom.js";
import { num, t } from "./i18n.js";

/** entries: [[label, value], ...]; digits: decimals to show. */
export function drawBars(container, entries, { digits = 0, emptyKey = "no_data" } = {}) {
  clear(container);
  if (!entries.length) {
    container.append(el("p", { class: "muted", text: t(emptyKey) }));
    return;
  }
  const max = Math.max(...entries.map(([, value]) => value), 0.0001);
  for (const [label, value] of entries) {
    const fill = el("i");
    fill.style.setProperty("--w", `${Math.max(2, (value / max) * 100)}%`);
    container.append(el("div", { class: "bar-row" }, [
      el("span", { class: "name", text: label }),
      el("div", { class: "track", "aria-hidden": "true" }, [fill]),
      el("span", { class: "val", text: num(value, digits) }),
    ]));
  }
}

/** Set a meter's fill (0..100) and its colour class (ok, warn, bad or none). */
export function setMeter(meter, percent, level = "") {
  meter.classList.remove("ok", "warn", "bad");
  if (level) meter.classList.add(level);
  meter.firstElementChild.style.setProperty("--w", `${Math.max(0, Math.min(100, percent))}%`);
}
