// SHEFA Voice Commons, contributor page. This file is the router and the simple screens
// (landing, mic check, pass-the-phone, thank-you, delete); the heavy parts live in card.js,
// room.js, capture.js, queue.js and recorder.js.
import { $, h, icon, clear, fill } from "./dom.js";
import { T, setT, t, n, setLang, getLang, onLang } from "./i18n.js";
import { api } from "./api.js";
import { S, load, save, newSession, endSession, me, addPerson, totals } from "./session.js";
import * as Q from "./queue.js";
import { createCapture } from "./capture.js";
import { runCards } from "./card.js";
import { runRoom } from "./room.js";
import { releaseMic, micErrorKey } from "./recorder.js";
import { copyText, makeCard, pageLink, sharePicture, waLink } from "./share.js";
import { toast } from "./ui.js";

const app = $("#app");
const params = new URLSearchParams(location.search);
const IN_APP = /FBAN|FBAV|FB_IAB|FBIOS|FB4A|Instagram|Messenger|\bLine\//i.test(navigator.userAgent);
const ANDROID = /Android/i.test(navigator.userAgent);
const ROOM_CODE = (params.get("room") || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);
const FROM = (params.get("from") || "").slice(0, 40);

let cleanup = null; // what to tear down when the screen changes

// Show a screen. build(view) fills the container and may return a cleanup function.
function go(build) {
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  clear(app);
  const c = build(app);
  cleanup = typeof c === "function" ? c : null;
  const focus = app.querySelector("h1") || app;
  focus.setAttribute("tabindex", "-1");
  focus.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

// ---------------------------------------------------------------- landing
function landing() {
  go((view) => {
    const cfg = S.cfg;
    const have = !!(S.session && S.session.consent === cfg.consent_version);
    const from = cfg.from_name || FROM;
    const tick = h("input", { type: "checkbox", id: "tick" });
    const warn = h("p", { class: "warn", role: "alert", hidden: true }, T("err_consent"));
    const tsBox = h("div", { class: "ts" });
    const state = { token: () => "" };
    if (!have && cfg.turnstile_site_key) loadTurnstile(cfg.turnstile_site_key, tsBox).then((g) => { if (g) state.token = g; });

    const go2 = async (kind) => {
      warn.hidden = true;
      if (!have && !tick.checked) { warn.hidden = false; tick.focus(); return; }
      const btns = view.querySelectorAll(".btn");
      btns.forEach((b) => (b.disabled = true));
      if (!have) {
        let token = state.token();
        if (cfg.turnstile_site_key && !token) for (let k = 0; k < 40 && !token; k++) { await new Promise((r) => setTimeout(r, 250)); token = state.token(); }
        const r = await api("/api/c/start", { method: "POST", auth: false, body: {
          consent: true, consent_version: cfg.consent_version, campaign: cfg.campaign || params.get("c") || "",
          from_name: from, device: navigator.userAgent.slice(0, 120), turnstile: token || "" } });
        btns.forEach((b) => (b.disabled = false));
        if (!r.ok) {
          warn.hidden = false; fill(warn, T(r.status === 0 ? "server_down" : r.error.code === "slow_down" ? "err_slow_down" : r.error.code === "challenge" ? "err_challenge" : "err_generic"));
          return;
        }
        newSession(r.data);
        if (r.data.maintenance) cfg.maintenance = r.data.maintenance;
      }
      btns.forEach((b) => (b.disabled = false));
      afterStart(kind);
    };

    const consentLines = [["shield", "c1"], ["user", "c2"], ["trash", "c3"]].map(([ic, k]) =>
      h("li", null, icon(ic, "lead"), T(k)));
    const note = h("audio", { controls: true, preload: "none", src: (window.SHEFA_API || "") + "/voice-note", "aria-label": t(from ? "voice_note_from" : "voice_note", { name: from }) });

    return fill(view, h("div", { class: "stack" },
      cfg.maintenance ? h("p", { class: "banner", role: "status" }, T("maint")) : null,
      from ? h("p", { class: "from" }, T("sent_by", { name: from })) : null,
      ROOM_CODE ? h("p", { class: "from" }, T("invited", { code: ROOM_CODE })) : null,
      h("h1", null, T("hero_title")), h("p", { class: "lead-text" }, T("hero_sub")),
      cfg.voice_note ? h("div", { class: "box" }, h("p", { class: "q" }, icon("sound"), T(from ? "voice_note_from" : "voice_note", { name: from })), note) : null,
      h("ul", { class: "consent" }, consentLines),
      h("details", { class: "more" }, h("summary", null, T("more")),
        h("p", { lang: "bn", class: "bn-only" }, cfg.consent_bn), h("p", { lang: "en", class: "en-only" }, cfg.consent_en)),
      have ? h("p", { class: "muted" }, icon("check"), T("tick_back"))
        : h("label", { class: "tick", for: "tick" }, tick, T("tick")),
      warn, tsBox,
      h("button", { type: "button", class: "btn primary big", onclick: () => go2(ROOM_CODE ? "room" : "cards") }, T("start")),
      ROOM_CODE ? null : h("button", { type: "button", class: "btn alt", onclick: () => go2("room") }, icon("phone"), T("friend")),
      h("button", { type: "button", class: "linkbtn", onclick: () => { location.hash = "#delete"; } }, T("delete_link"))));
  });
}

function loadTurnstile(key, box) {
  // Cloudflare's script is only fetched when the server asks for it (a site key is set).
  return new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onerror = () => resolve(null);
    s.onload = () => {
      let token = "";
      try {
        window.turnstile.render(box, { sitekey: key, callback: (v) => { token = v; }, "expired-callback": () => { token = ""; } });
        resolve(() => token);
      } catch { resolve(null); }
    };
    document.head.append(s);
  });
}

function afterStart(kind) {
  showQbar();
  if (S.session.micOk) return enter(kind);
  micCheck(() => enter(kind));
}

function enter(kind) {
  if (kind === "room") return roomScreen(ROOM_CODE);
  cards();
}

// ---------------------------------------------------------------- in-app browser wall
function inAppWall() {
  go((view) => {
    const link = location.href;
    const intent = `intent://${location.host}${location.pathname}${location.search}#Intent;scheme=${location.protocol.slice(0, -1)};package=com.android.chrome;end`;
    const copy = h("button", { type: "button", class: "btn alt big", onclick: async () => { toast(t((await copyText(link)) ? "copied" : "copy_failed")); } }, icon("copy"), T("inapp_copy"));
    fill(view, h("div", { class: "stack center wall" },
      h("h1", null, T("inapp_title")), h("p", null, T("inapp_body")),
      ANDROID ? h("a", { class: "btn primary big", href: intent }, T("inapp_title")) : null,
      copy,
      h("button", { type: "button", class: "linkbtn", onclick: () => { start(true); } }, T("inapp_go"))));
  });
}

// ---------------------------------------------------------------- mic check (local only)
function micCheck(next) {
  go((view) => {
    const result = h("p", { class: "result", role: "status" });
    const go3 = h("button", { type: "button", class: "btn primary big", hidden: true, onclick: next }, icon("check"), T("mc_next"));
    const cap = createCapture({
      review: false, maxS: 8, minS: 0.4,
      onDone: (r) => {
        const loud = r.peak >= 0.03;
        const noisy = loud && r.floor > 0.04; // only truly loud surroundings: pauses are the only place noise can be measured
        fill(result, T(!loud ? "mc_quiet" : noisy ? "mc_noisy" : "mc_good"));
        result.className = "result " + (!loud ? "bad" : noisy ? "meh" : "good");
        if (loud) { S.session.micOk = true; save(); }
        go3.hidden = !loud;
        if (loud) go3.focus();
      },
    });
    fill(view, h("div", { class: "stack" },
      h("h1", null, T("mc_title")), h("p", null, T("mc_sub")), h("p", { class: "tip" }, icon("shield"), T("mc_tip")),
      cap.el, result, go3,
      h("button", { type: "button", class: "linkbtn", onclick: next }, T("skip_step"))));
    return () => { cap.destroy(); };
  });
}

// ---------------------------------------------------------------- cards, rooms
function cards(first) {
  go((view) => {
    const flow = runCards(view, { first, onFinish: thanks, onPass: pass });
    return () => flow.destroy();
  });
}

function roomScreen(code) {
  go((view) => {
    const room = runRoom(view, { code, onFinish: thanks, onSolo: (card) => cards(card) });
    return () => room.destroy();
  });
}

// ---------------------------------------------------------------- pass the phone
function pass() {
  go((view) => {
    const tick = h("input", { type: "checkbox", id: "ptick" });
    const warn = h("p", { class: "warn", role: "alert", hidden: true }, T("err_consent"));
    const btn = h("button", { type: "button", class: "btn primary big", onclick: async () => {
      if (!tick.checked) { warn.hidden = false; tick.focus(); return; }
      btn.disabled = true;
      const r = await api("/api/c/speaker", { method: "POST" });
      btn.disabled = false;
      if (!r.ok) { warn.hidden = false; fill(warn, T(r.status === 0 ? "server_down" : "err_signed_out")); return; }
      addPerson(r.data.speaker_id, r.data.delete_code);
      showQbar();
      cards();
    } }, T("start"));
    fill(view, h("div", { class: "stack" }, h("h1", null, T("pass_title")), h("p", null, T("pass_sub")),
      h("ul", { class: "consent" }, [["shield", "c1"], ["user", "c2"], ["trash", "c3"]].map(([ic, k]) => h("li", null, icon(ic, "lead"), T(k)))),
      h("label", { class: "tick", for: "ptick" }, tick, T("tick")), warn, btn));
  });
}

// ---------------------------------------------------------------- thank you
const GENDERS = ["female", "male", "other", "skip"];
// Our own order (big divisions first, "prefer not to say" last) instead of the server's alphabetical one.
const DIVISIONS = ["dhaka", "chattogram", "rajshahi", "khulna", "barishal", "sylhet", "rangpur", "mymensingh", "abroad", "skip"];
function thanks() {
  releaseMic();
  go((view) => {
    const person = me();
    const waiting = h("p", { class: "queue-state", role: "status" });
    const paintQ = () => {
      const k = Q.pending();
      fill(waiting, k ? h("span", { class: "spin", "aria-hidden": "true" }) : icon("check"), T(k ? "th_wait" : "th_alldone", { n: k }));
      waiting.className = "queue-state " + (k ? "wait" : "ok");
    };
    paintQ();
    const off = Q.onChange(paintQ);

    const group = h("section", { class: "box" }, h("h2", { class: "small" }, T("group_title")));
    const impact = h("p", { class: "impact", hidden: true });
    // Group numbers and the admin's note: fetched now, and again once the phone is back online
    // (a person finishing on a bad connection should still see them).
    let loaded = false;
    const loadGroup = () => {
      if (loaded) return;
      Promise.all([api("/api/c/progress", { auth: false }), api("/api/c/config?c=" + encodeURIComponent((S.session && S.session.campaign) || params.get("c") || ""), { auth: false })]).then(([p, c]) => {
        if (loaded || !p.ok) return;
        loaded = true;
        if (c.ok && c.data.impact_note) { impact.textContent = c.data.impact_note; impact.hidden = false; }
        const { minutes, goal_minutes: goal, speakers } = p.data;
        const pct = Math.min(100, Math.round((minutes / Math.max(1, goal)) * 100));
        group.append(h("div", { class: "bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) }, fillBar(pct)),
          h("p", { class: "muted" }, T("group_line", { m: Math.round(minutes * 10) / 10, g: goal, s: speakers })));
      });
    };
    loadGroup();
    window.addEventListener("online", loadGroup);

    const code = person.deleteCode || S.session.deleteCode;
    const codeBox = h("section", { class: "box code" }, h("h2", { class: "small" }, T("code_title")),
      h("p", { class: "bigcode", dir: "ltr" }, code),
      h("button", { type: "button", class: "btn alt", onclick: async () => toast(t((await copyText(code)) ? "copied" : "copy_failed")) }, icon("copy"), T("copy")),
      h("p", { class: "muted" }, T("code_note")));

    const link = pageLink();
    const img = h("button", { type: "button", class: "btn alt", onclick: async () => {
      const blob = await makeCard(person.n);
      if (!blob) return;
      if ((await sharePicture(blob)) === "download") {
        const a = h("a", { href: URL.createObjectURL(blob), download: "shefa.png" });
        document.body.append(a); a.click(); a.remove();
      }
    } }, icon("share"), T(navigator.canShare ? "share_img" : "share_dl"));
    const shareBox = person.n > 0 ? h("section", { class: "box" }, h("h2", { class: "small" }, T("share_title")),
      h("div", { class: "stack" },
        h("a", { class: "btn wa", href: waLink(t("wa_text", { url: link })), target: "_blank", rel: "noopener" }, icon("wa"), T("share_wa")),
        h("button", { type: "button", class: "btn alt", onclick: async () => toast(t((await copyText(link)) ? "copied" : "copy_failed")) }, icon("copy"), T("share_link")),
        img)) : null;

    const first = !person.profileDone;
    fill(view, h("div", { class: "stack" },
      h("h1", null, T("th_title")),
      h("p", { class: "lead-text" }, person.n ? T("th_sum", { n: person.n, m: Math.round(person.sec / 6) / 10 }) : T("th_sum_none")),
      waiting, impact, group, codeBox, shareBox, first ? profileForm(person) : null,
      h("button", { type: "button", class: "btn primary big", onclick: () => cards() }, icon("mic"), T("more_rec")),
      h("div", { class: "row wrap" },
        h("button", { type: "button", class: "btn alt", onclick: pass }, icon("user"), T("next_person")),
        h("button", { type: "button", class: "btn alt", onclick: () => roomScreen("") }, icon("phone"), T("friend"))),
      h("button", { type: "button", class: "linkbtn", onclick: () => { location.hash = "#delete"; } }, T("delete_link"))));
    return () => { off(); window.removeEventListener("online", loadGroup); };
  });
}

function fillBar(pct) {
  const i = h("i");
  i.style.width = pct + "%"; // set through the DOM, so no inline style attribute is needed
  return i;
}

// Optional taps, asked only after the clips. Division only, never district.
function profileForm(person) {
  const pick = { age_band: "", gender: "", division: "" };
  const group = (field, title, values, label) => {
    const wrap = h("div", { class: "chips", role: "group", "aria-label": t(title) });
    values.forEach((v) => {
      const b = h("button", { type: "button", class: "chip pick", "aria-pressed": "false", onclick: () => {
        pick[field] = pick[field] === v ? "" : v;
        wrap.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b && !!pick[field])));
      } }, label(v));
      wrap.append(b);
    });
    return h("div", { class: "field" }, h("p", { class: "q" }, T(title)), wrap);
  };
  const nick = h("input", { type: "text", class: "input", maxlength: "30", id: "nick", autocomplete: "off" });
  const credit = h("input", { type: "checkbox", id: "credit" });
  const done = h("p", { class: "ok", role: "status", hidden: true }, T("opt_saved"));
  const save1 = h("button", { type: "button", class: "btn alt", onclick: async () => {
    const r = await api("/api/c/profile", { method: "POST", body: { ...pick, nickname: nick.value.trim(), credit_ok: credit.checked && !!nick.value.trim() } });
    if (r.ok) { done.hidden = false; person.profileDone = true; save(); save1.disabled = true; } else toast(t("err_generic"));
  } }, T("opt_save"));
  return h("section", { class: "box" }, h("h2", { class: "small" }, T("opt_title")),
    group("age_band", "opt_age", S.cfg.age_bands || [], (v) => n(v)),
    group("gender", "opt_gender", GENDERS, (v) => T("g_" + v)),
    group("division", "opt_div", DIVISIONS.filter((d) => (S.cfg.divisions || DIVISIONS).includes(d)), (v) => T("d_" + v)),
    h("div", { class: "field" }, h("label", { class: "q", for: "nick" }, T("opt_nick")), nick,
      h("label", { class: "tick", for: "credit" }, credit, T("opt_credit"))),
    save1, done);
}

// ---------------------------------------------------------------- delete my recordings
function deletePage() {
  go((view) => {
    const input = h("input", { type: "text", class: "input code", id: "dcode", autocomplete: "off", autocapitalize: "characters", spellcheck: "false", maxlength: "20", placeholder: "AB12-CD34-EF56" });
    const msg = h("p", { role: "alert", hidden: true });
    const btn = h("button", { type: "button", class: "btn danger big" }, icon("trash"), T("del_btn"));
    let armed = false;
    btn.onclick = async () => {
      const codeText = input.value.trim().toUpperCase();
      if (!codeText) { input.focus(); return; }
      if (!armed) { armed = true; fill(btn, icon("trash"), T("del_sure")); msg.hidden = false; msg.className = "warn"; fill(msg, T("del_warn")); return; }
      armed = false; btn.disabled = true;
      const r = await api("/api/c/delete", { method: "POST", auth: false, body: { delete_code: codeText } });
      btn.disabled = false; fill(btn, icon("trash"), T("del_btn"));
      msg.hidden = false;
      if (r.ok) {
        msg.className = "ok"; fill(msg, T("del_ok", { n: r.data.deleted }));
        if (S.session) {
          // Only the person who owns this code is removed; others on the same phone keep their clips.
          const sid = Object.keys(S.session.people).find((k) => (S.session.people[k].deleteCode || "").toUpperCase() === codeText);
          if (sid) {
            await Q.clearSpeaker(sid);
            delete S.session.people[sid];
            const rest = Object.keys(S.session.people);
            if (rest.length) { if (S.session.speaker === sid) S.session.speaker = rest[0]; save(); }
            else { endSession(); hideQbar(); }
          }
        }
      } else {
        msg.className = "warn"; fill(msg, T(r.status === 404 ? "del_nf" : r.status === 0 ? "server_down" : "err_generic"));
      }
    };
    fill(view, h("div", { class: "stack" }, h("h1", null, T("del_title")), h("p", null, T("del_sub")),
      h("label", { class: "q", for: "dcode" }, T("del_label")), input, btn, msg,
      h("button", { type: "button", class: "btn alt", onclick: () => { location.hash = ""; } }, T("back"))));
  });
}

// ---------------------------------------------------------------- the status line at the bottom
const qbar = $("#qbar");
function showQbar() { qbar.hidden = false; paintQbar(); }
function hideQbar() { qbar.hidden = true; }
function paintQbar() {
  if (qbar.hidden) return;
  const k = Q.pending();
  const st = Q.status();
  const why = st.auth ? "err_signed_out" : st.paused === "daily_cap" ? "err_daily_cap" : st.paused ? "err_paused" : k && navigator.onLine === false ? "err_net_wait" : "";
  fill(qbar, h("span", { class: "qmain" }, k ? icon("redo", "mini") : icon("check", "mini"), T(k ? "q_bar" : "q_bar_zero", { n: k })), why ? h("span", { class: "qwhy" }, T(why)) : null);
}
Q.onChange(paintQbar);
window.addEventListener("online", paintQbar);
window.addEventListener("offline", paintQbar);

// ---------------------------------------------------------------- boot
async function start(skipWall) {
  if (location.hash === "#delete") return deletePage();
  if (IN_APP && !skipWall) return inAppWall();
  if (!S.cfg) {
    go((view) => fill(view, h("p", { class: "center" }, T("loading"))));
    const c = new URLSearchParams(location.search).get("c") || "";
    const r = await api("/api/c/config?c=" + encodeURIComponent(c), { auth: false });
    if (!r.ok) {
      go((view) => fill(view, h("div", { class: "stack center" }, h("p", { class: "warn" }, T("server_down")),
        h("button", { type: "button", class: "btn primary", onclick: () => start(skipWall) }, T("retry")))));
      return;
    }
    S.cfg = r.data;
  }
  landing();
}

async function boot() {
  const lang = $("#lang");
  const paintLang = () => { fill(lang, T("other_lang")); };
  paintLang();
  lang.addEventListener("click", () => setLang(getLang() === "bn" ? "en" : "bn"));
  load();
  await Q.init();
  if (S.session) showQbar();
  window.addEventListener("hashchange", () => start());
  start();
}

boot();
