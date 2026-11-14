// A promise-based confirm built on the native <dialog>: it traps focus, closes on Esc, and is
// announced by screen readers without any extra code. Resolves to {ok, value}.
import { el } from "./dom.js";
import { t } from "./i18n.js";

/**
 * ask({title, body, confirmKey, danger, input:{label, value, maxlength}})
 * body may be a string or an array of strings (one paragraph each).
 */
export function ask({ title, body = [], confirmKey = "confirm", danger = false, input = null }) {
  return new Promise((resolve) => {
    const dialog = el("dialog", { "aria-labelledby": "dlg-title" });
    const field = input
      ? el("input", { type: "text", id: "dlg-input", maxlength: input.maxlength || 120, value: input.value || "" })
      : null;
    const form = el("form", { method: "dialog" }, [
      el("h2", { id: "dlg-title", text: title }),
      ...[].concat(body).map((paragraph) => el("p", { text: paragraph })),
      input ? el("div", { class: "field" }, [el("label", { for: "dlg-input", text: input.label }), field]) : null,
      el("div", { class: "actions" }, [
        el("button", { type: "button", value: "cancel", id: "dlg-cancel" }, t("cancel")),
        el("button", { type: "submit", value: "ok", class: danger ? "danger" : "primary" }, t(confirmKey)),
      ]),
    ]);
    dialog.append(form);
    const finish = (ok) => {
      const value = field ? field.value.trim() : "";
      dialog.close();
      dialog.remove();
      resolve({ ok, value });
    };
    form.addEventListener("submit", (event) => { event.preventDefault(); finish(true); });
    form.querySelector("#dlg-cancel").addEventListener("click", () => finish(false));
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); finish(false); });
    document.body.append(dialog);
    dialog.showModal();
    (field || form.querySelector("#dlg-cancel")).focus(); // default focus on the safe choice
  });
}
