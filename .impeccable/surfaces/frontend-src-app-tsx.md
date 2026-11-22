---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/patient/PatientApp.tsx","frontend/src/demo/DemoApp.tsx","src/shefa/collector/static/public/index.html","src/shefa/collector/static/private/admin.html"]
---

# SHEFA UI (all surfaces)

Scope: every SHEFA screen. Staff app (Live, Calls, Appointments, Doctors, Setup, Report, Staff, My Day, Overview, Sign-in), patient booking page, demo, voice-collection public site and its private admin/review/voice/sign-in pages, legacy static pages, lab report. Mode: Operate (public pages lean warm and reassuring inside the same world).

Second pass (2026-11-22): the Exposure Record world was rejected by the user as too cold and clinical-tech, slow to read at a glance, not Bangladeshi, and too austere for patients. Lean: bold and distinctive. Nothing visual kept; all function kept.

## Direction contract

THESIS: Every doctor wears a box colour across the whole product, so the desk finds a doctor's sessions, list and patients by colour, the way a pharmacist reaches for the right box on the shelf. Status speaks in plain colour plus words, readable across the room. Refuses the category default (white cards, slate sidebar, one teal accent) and the grey austerity of the previous pass.

OWN-WORLD: Bangladeshi medicine packaging. Bright white box board on a warm shelf field; a deep pharma-green rail; solid colour label blocks with reversed bold type (a doctor's name block, a status pill); a printed batch/expiry stamp block (dashed frame, tabular digits) for serials and references. Type: Baloo Da 2 bold for names, headings and numbers that matter; Hind Siliguri for body and data. Small radius, box-on-shelf soft shadow. Raises: one colour one meaning everywhere with a printed legend (orienteering map); each app area owns a hue on the rail (tabbed manual); on a doctor's phone one patient fills the screen (vertical feed).

STORY: The desk sees each doctor's session filling in that doctor's colour, sees the red needs-a-person queue first, sees what SHEFA did in its blue, and acts in two taps; patients and volunteers feel a friendly, local, trustworthy place.

FIRST VIEWPORT: Deep green rail with Bangla nav (area hue squares) and a status legend at its foot; white work field. Live leads: the needs-a-person queue in a red-banded block at top when present; then "today's chambers": one row per doctor, a solid colour name block, sessions on a time axis as bars filling in the doctor's colour with "১৯/২৪" in a stamp; in-progress calls with blue live pills.

FORM: Medicine Shelf (Bangladeshi pharma packaging), grounded candidate 3 dealt by the roll and chosen by the user; seed key 5e2bc9d4.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
