// Overview and Coverage tabs: the numbers that answer "how are we doing and is it safe to go on?".
import { api } from "./api.js";
import { $, clear, el, toast } from "./dom.js";
import { ask } from "./dialog.js";
import { drawBars, setMeter } from "./charts.js";
import { labelFor, num, t } from "./i18n.js";
import { DISK, GATE, IMPACT_MAX, SPLIT_ORDER, STATUS_ORDER, diskLevel, gate, inOrder, parseGoal, pct, sortedEntries } from "./admin-model.js";

let reloadStats = async () => {};
let goalDirty = false;
let impactDirty = false;

export function initOverview(reload) {
  reloadStats = reload;
  $("#goal-input").addEventListener("input", () => { goalDirty = true; });
  $("#impact-input").addEventListener("input", () => {
    impactDirty = true;
    paintImpactCount();
  });

  $("#goal-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const goal = parseGoal($("#goal-input").value);
    if (goal === null) { toast(t("goal_bad")); $("#goal-input").focus(); return; }
    await saveSettings({ goal_minutes: goal }, () => { goalDirty = false; });
  });
  $("#impact-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveSettings({ impact_note: $("#impact-input").value.trim().slice(0, IMPACT_MAX) }, () => { impactDirty = false; });
  });
}

async function saveSettings(body, done) {
  try {
    await api("/api/admin/settings", { method: "POST", body });
    done();
    toast(t("saved"));
    await reloadStats();
  } catch (error) {
    toast(t(error.code === "network" ? "err_network" : "err_generic"));
  }
}

function paintImpactCount() {
  const length = $("#impact-input").value.length;
  $("#impact-count").textContent = `${num(length)}/${num(IMPACT_MAX)}`;
}

/** The switch that stops uploads. A confirm dialog guards both directions. */
async function togglePause(paused) {
  const { ok } = await ask({
    title: t(paused ? "resume_confirm_title" : "pause_confirm_title"),
    body: t(paused ? "resume_confirm_body" : "pause_confirm_body"),
    confirmKey: paused ? "resume_btn" : "pause_btn",
    danger: !paused,
  });
  if (!ok) return;
  try {
    await api("/api/admin/settings", { method: "POST", body: { kill_switch: !paused } });
    toast(t(paused ? "resumed_done" : "paused_done"));
    await reloadStats();
  } catch (error) {
    toast(t("err_generic"));
  }
}

function statCard(value, labelKey) {
  return el("div", { class: "stat" }, [el("div", { class: "num", text: value }), el("div", { class: "label", text: t(labelKey) })]);
}

export function renderOverview(stats) {
  const progress = stats.progress || {};
  const backlog = stats.backlog || {};
  const status = stats.status || {};

  // Pause / resume.
  const paused = !!stats.kill_switch;
  const state = $("#pause-state");
  state.textContent = t(paused ? "pause_is_off" : "pause_is_on");
  $("#pause-card").classList.toggle("banner", paused);
  $("#pause-card").classList.toggle("warn", paused);
  const button = $("#pause-btn");
  button.textContent = t(paused ? "resume_btn" : "pause_btn");
  button.className = paused ? "big primary" : "big danger-outline";
  button.onclick = () => togglePause(paused);

  // Cards.
  const grid = $("#stat-grid");
  clear(grid);
  grid.append(
    statCard(num(stats.contributors), "st_contributors"),
    statCard(num(stats.speakers_with_clips), "st_speakers"),
    statCard(num(Math.round((Number(stats.top_speaker_share) || 0) * 100)) + "%", "st_top_speaker"),
    statCard(num((stats.minutes_by_domain && stats.minutes_by_domain.isp) || 0, 1), "st_isp_minutes"),
    statCard(num((stats.minutes_by_domain && stats.minutes_by_domain.shop) || 0, 1), "st_shop_minutes"),
    statCard(num(stats.shareable_speakers || 0), "st_shareable"),
    statCard(num(progress.clips), "st_clips"),
    statCard(num(progress.minutes, 1), "st_minutes"),
    statCard(num(backlog.to_review), "st_to_review"),
    statCard(num(backlog.disputed), "st_disputed"),
  );

  // Goal.
  const goal = Number(progress.goal_minutes) || 0;
  const goalPct = pct(progress.minutes, goal);
  const meter = $("#goal-meter");
  setMeter(meter, goalPct, goalPct >= 100 ? "ok" : "");
  meter.setAttribute("aria-valuenow", String(Math.round(goalPct)));
  meter.setAttribute("aria-valuetext", t("goal_text", { have: num(progress.minutes, 1), goal: num(goal), pct: num(goalPct) }));
  $("#goal-text").textContent = t("goal_text", { have: num(progress.minutes, 1), goal: num(goal), pct: num(goalPct) });
  if (!goalDirty) $("#goal-input").value = goal ? String(goal) : "";
  if (!impactDirty) $("#impact-input").value = typeof stats.impact_note === "string" ? stats.impact_note : "";
  paintImpactCount();

  // Disk.
  const free = Number(stats.disk_free_mb);
  const disk = diskLevel(free);
  const diskMeter = $("#disk-meter");
  setMeter(diskMeter, disk.pct, disk.level);
  diskMeter.setAttribute("aria-valuemax", String(DISK.fullScaleMb));
  diskMeter.setAttribute("aria-valuenow", String(Math.round(free)));
  diskMeter.setAttribute("aria-valuetext", t("disk_text", { gb: num(free / 1000, 1) }));
  $("#disk-text").textContent = `${t("disk_text", { gb: num(free / 1000, 1) })} ${t(`disk_${disk.level}`, { stop: num(DISK.stopMb) })}`;

  drawBars($("#bars-status"), inOrder(status, STATUS_ORDER).map(([key, value]) => [labelFor("status", key), value]));
  drawBars($("#bars-split"), inOrder(stats.split, SPLIT_ORDER).map(([key, value]) => [labelFor("split", key), value]));
}

export function renderCoverage(stats) {
  const g = gate(stats);
  setMeter($("#gate-speakers"), g.speakersPct, g.speakers >= GATE.speakers ? "ok" : "");
  setMeter($("#gate-hours"), g.hoursPct, g.hours >= GATE.hoursMin ? "ok" : "");
  $("#gate-speakers-label").textContent = t("gate_speakers", { have: num(g.speakers), need: num(GATE.speakers) });
  $("#gate-hours-label").textContent = t("gate_hours", { have: num(g.hours, 1), need: num(GATE.hoursMin), target: num(GATE.hoursTarget) });
  const verdict = $("#gate-verdict");
  verdict.className = `banner ${g.met ? "ok" : "warn"}`;
  verdict.textContent = g.met
    ? t("gate_met")
    : t("gate_not_yet", { speakers: num(g.needSpeakers), hours: num(g.needHours, 1) });

  drawBars($("#bars-slot"), sortedEntries(stats.minutes_by_slot).map(([k, v]) => [labelFor("slot", k), v]), { digits: 1 });
  drawBars($("#bars-setting"), sortedEntries(stats.minutes_by_setting).map(([k, v]) => [labelFor("setting", k), v]), { digits: 1 });
  drawBars($("#bars-division"), sortedEntries(stats.by_division).map(([k, v]) => [labelFor("div", k), v]));
  drawBars($("#bars-age"), sortedEntries(stats.by_age).map(([k, v]) => [k === "unknown" ? t("unknown") : k, v]));
  drawBars($("#bars-gender"), sortedEntries(stats.by_gender).map(([k, v]) => [labelFor("gender", k), v]));
}
