// SHEFA's orbs (world/orbs/shefa-orbs.js: Libraries.dev voice-ring and thinking-orbs), fetched
// only when one is first shown, so the cost lands on the live-call screen and nowhere else.
// Decoration only: if the module cannot load (slow, offline, blocked), every caller goes on
// exactly as before, and nothing here ever throws.
let mod = null;
export function orbs() {
  if (!mod) mod = import("../world/orbs/shefa-orbs.js?v=2").catch(() => { mod = null; return null; });
  return mod;
}
