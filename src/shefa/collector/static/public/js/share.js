// Sharing: WhatsApp message, copy link, and a picture drawn on a canvas.
// The picture and message carry no personal data: no name, no code, no clip details.
import { t } from "./i18n.js";

// The page link we are happy to pass on: our own address, nothing from the query string
// (no ?from, no ?devmic, no room code).
export function pageLink() {
  return location.origin + location.pathname.replace(/index\.html$/, "");
}

export const waLink = (text) => "https://wa.me/?text=" + encodeURIComponent(text);

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch { /* older browsers and insecure pages: fall back below */ }
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.className = "offscreen";
  document.body.append(box);
  box.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  box.remove();
  return ok;
}

function wrap(ctx, text, maxWidth) {
  const words = text.split(" ");
  const lines = [];
  let line = "";
  for (const w of words) {
    const test = line ? line + " " + w : w;
    if (ctx.measureText(test).width > maxWidth && line) { lines.push(line); line = w; } else line = test;
  }
  if (line) lines.push(line);
  return lines;
}

// 1080x1350 (a good shape for WhatsApp status and Facebook) with the clip count in big type.
export function makeCard(count) {
  const W = 1080, H = 1350;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d");
  const grad = g.createLinearGradient(0, 0, W, H);
  grad.addColorStop(0, "#0f766e"); grad.addColorStop(1, "#134e4a");
  g.fillStyle = grad; g.fillRect(0, 0, W, H);
  g.fillStyle = "rgba(255,255,255,0.08)";
  for (let i = 0; i < 7; i++) { g.beginPath(); g.arc(W - 120 + i * 0, 240 + i * 150, 60 + i * 14, 0, Math.PI * 2); g.fill(); }
  const font = '"Noto Sans Bengali","Kalpurush","Siyam Rupali",system-ui,sans-serif';
  g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "alphabetic";
  g.font = `600 52px ${font}`;
  g.fillText("SHEFA", W / 2, 170);
  g.font = `700 78px ${font}`;
  const lines = wrap(g, t("img_main", { n: count }), W - 200);
  lines.forEach((l, i) => g.fillText(l, W / 2, 560 + i * 110));
  g.font = `500 46px ${font}`;
  g.fillStyle = "rgba(255,255,255,0.85)";
  g.fillText(t("img_sub"), W / 2, 560 + lines.length * 110 + 60);
  g.font = `500 38px ${font}`;
  g.fillText(location.host, W / 2, H - 110);
  return new Promise((resolve) => c.toBlob(resolve, "image/png"));
}

// Share the picture with the phone's own share sheet when it can take files, else give a download.
export async function sharePicture(blob) {
  const file = new File([blob], "shefa.png", { type: "image/png" });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], text: t("wa_text", { url: pageLink() }) }); return "shared"; } catch (e) { if (e && e.name === "AbortError") return "cancelled"; }
  }
  return "download";
}
