---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/patient/PatientApp.tsx","frontend/src/demo/DemoApp.tsx","src/shefa/collector/static/public/index.html","src/shefa/collector/static/private/admin.html"]
---

# SHEFA UI (all surfaces)

Scope: every SHEFA screen. Staff app (Live, Calls, Appointments, Doctors, Setup, Report, Staff, My Day, Overview, Sign-in), patient booking page, demo console, voice-collection public site and its private admin/review/voice/sign-in pages, legacy static pages. Mode: Operate (the collector's public page leans Persuade inside the same world).

Audience/job: front desk under pressure (two taps while a phone rings), owner checking the agent pays, doctor between patients, patient booking on a slow phone, volunteer recording their voice. Constraints: Bangla first, WCAG 2.2 AA, bright reception room, low bandwidth, no invented data.

## Direction contract

THESIS: Load and conflict are drawn, not coloured. A busy chamber session hatches denser as its serials fill; two bookings on one serial, or two schedule sessions that overlap, cross-hatch at ninety degrees. Refuses the category default: white cards, slate sidebar, one teal accent, KPI tiles.

OWN-WORLD: An eleven-step neutral zone ramp (Z0 near-black to Z10 near-white, faintly cool, never cream) is the only tonal token set. One dichroic magenta marks SHEFA's own voice and actions only (live call, booked by SHEFA, needs-a-person flag). Type: Anek Bangla/Anek Latin, condensed width for display, tracked caps legends; Martian Mono for quantities (serials, times, counts). Every rule one device pixel, zero radius, no shadows except the sheet. State vocabulary: selected = deepest zone fill; held back = dotted outline; disabled/cancelled = struck rule; load = hatch density; conflict = crossed hatch. Raises: one-device-pixel rules (centre-rail); block length is real duration (labanotation); destructive actions isolated by empty space (graphite console).

STORY: The desk sees at a glance which sessions are filling, which call needs a person, and where SHEFA acted; opens any call or booking as a sheet over the list without losing place; acts in two taps.

FIRST VIEWPORT: Staff app shell: a Z1 left rail (brand, Bangla nav, who/language/sign-out), main field on Z10. Live/Today leads: a top strip of doctors' sessions as hatch-density bars (serials booked / capacity, real numbers), below it the calls-in-progress table with magenta live marks and the needs-a-person rows first; any row opens a translucent sheet sliding from the right, the list beneath still visible.

FORM: Exposure Record (darkroom printer's exposure card), dealt as the bolder-register lead, chosen by the user; seed key f7d0721e.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
