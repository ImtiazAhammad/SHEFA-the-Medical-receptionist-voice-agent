// Admin page shell: tabs, loading the stats, and telling each part to draw itself.
// Each tab loads its own data the first time it is opened. A language change redraws from the
// data already in memory, so nothing is fetched again.
import { ApiError, api, signOutTo } from "./api.js";
import { $ } from "./dom.js";
import { applyI18n, initLangToggle, onLangChange, t } from "./i18n.js";
import { initOverview, renderCoverage, renderOverview } from "./admin-overview.js";
import { initPeople, loadCampaigns, renderCampaigns, renderTeam } from "./admin-people.js";
import { clipsLoaded, initClipsTab, loadAudit, loadClips, renderAudit, renderClips } from "./admin-clips.js";

const TABS = ["overview", "coverage", "campaigns", "team", "clips", "audit"];
let stats = null;
let current = "overview";
const opened = new Set();

function showTab(name, { focus = false } = {}) {
  if (!TABS.includes(name)) name = "overview";
  current = name;
  for (const tab of TABS) {
    const button = $(`#tab-${tab}`);
    const selected = tab === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(`#panel-${tab}`).hidden = !selected || !stats;
    if (selected && focus) button.focus();
  }
  try { history.replaceState(null, "", `#${name}`); } catch { /* not important */ }
  if (!opened.has(name)) {
    opened.add(name);
    if (name === "campaigns") loadCampaigns();
    if (name === "clips") loadClips();
    if (name === "audit") loadAudit();
  }
}

function renderAll() {
  if (!stats) return;
  renderOverview(stats);
  renderCoverage(stats);
  renderTeam(stats);
  if (opened.has("campaigns")) renderCampaigns();
  if (clipsLoaded()) renderClips();
  renderAudit();
}

async function reload() {
  $("#error").hidden = true;
  try {
    stats = await api("/api/admin/stats");
    $("#loading").hidden = true;
    renderAll();
    showTab(current);
  } catch (error) {
    $("#loading").hidden = true;
    if (error instanceof ApiError && error.status === 0) {
      $("#error-text").textContent = t("err_network");
      $("#error").hidden = false;
    } else if (!(error instanceof ApiError && (error.status === 401 || error.status === 403))) {
      $("#error-text").textContent = t("err_generic");
      $("#error").hidden = false;
    }
  }
}

function initTabs() {
  const tabs = $("#tabs");
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (button) showTab(button.dataset.tab);
  });
  // Arrow keys move between tabs, as people expect from a tab bar.
  tabs.addEventListener("keydown", (event) => {
    const index = TABS.indexOf(current);
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      showTab(TABS[event.key === "Home" ? 0 : TABS.length - 1], { focus: true });
    } else if (step) {
      event.preventDefault();
      showTab(TABS[(index + step + TABS.length) % TABS.length], { focus: true });
    }
  });
}

async function start() {
  applyI18n();
  initLangToggle($("#lang"));
  onLangChange(renderAll);
  initTabs();
  initOverview(reload);
  initPeople(reload);
  initClipsTab();
  $("#refresh").addEventListener("click", () => { reload(); if (opened.has("clips")) loadClips(); if (opened.has("audit")) loadAudit(); if (opened.has("campaigns")) loadCampaigns(); });
  $("#error-retry").addEventListener("click", reload);
  $("#signout").addEventListener("click", () => signOutTo(""));
  const wanted = location.hash.slice(1);
  if (TABS.includes(wanted)) current = wanted;
  api("/api/review/me").then((me) => { $("#who").textContent = me.name; }).catch(() => {});
  await reload();
  // Numbers drift while uploads come in; refresh the overview now and then while it is on screen.
  setInterval(() => { if (!document.hidden && (current === "overview" || current === "coverage")) reload(); }, 60000);
}

start();
