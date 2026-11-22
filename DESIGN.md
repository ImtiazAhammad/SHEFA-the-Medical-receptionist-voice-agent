---
name: SHEFA
description: A Bangla voice receptionist for small clinics, set on a Bangladeshi medicine shelf.
colors:
  shelf: "oklch(0.962 0.006 165)"
  box: "oklch(0.993 0.003 165)"
  box-2: "oklch(0.975 0.005 165)"
  ink: "oklch(0.23 0.012 165)"
  ink-2: "oklch(0.41 0.012 165)"
  ink-3: "oklch(0.5 0.01 165)"
  rule: "oklch(0.895 0.007 165)"
  rule-strong: "oklch(0.79 0.01 165)"
  rail: "oklch(0.35 0.075 162)"
  rail-hover: "oklch(0.4 0.08 162)"
  rail-rule: "oklch(0.43 0.07 162)"
  rail-ink: "oklch(0.99 0.005 160)"
  rail-ink-2: "oklch(0.87 0.035 160)"
  urgent: "oklch(0.55 0.2 27)"
  urgent-ink: "oklch(0.49 0.19 27)"
  urgent-wash: "oklch(0.955 0.03 27)"
  on-urgent: "oklch(0.99 0.01 27)"
  waiting: "oklch(0.82 0.15 82)"
  waiting-ink: "oklch(0.5 0.11 70)"
  waiting-wash: "oklch(0.965 0.05 88)"
  done: "oklch(0.5 0.12 158)"
  done-hover: "oklch(0.44 0.11 158)"
  done-ink: "oklch(0.45 0.11 158)"
  done-wash: "oklch(0.955 0.035 158)"
  on-done: "oklch(0.99 0.01 158)"
  shefa: "oklch(0.52 0.17 262)"
  shefa-ink: "oklch(0.47 0.17 262)"
  shefa-wash: "oklch(0.955 0.03 262)"
  on-shefa: "oklch(0.99 0.01 262)"
  focus: "oklch(0.52 0.17 262)"
  doc-0: "oklch(0.5 0.1 195)"
  doc-1: "oklch(0.5 0.12 345)"
  doc-2: "oklch(0.5 0.12 300)"
  doc-3: "oklch(0.5 0.1 50)"
  doc-4: "oklch(0.5 0.1 115)"
  doc-5: "oklch(0.44 0.025 250)"
typography:
  display:
    fontFamily: "'Baloo Da 2', 'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "'Baloo Da 2', 'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.4375rem"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "'Baloo Da 2', 'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 700
    lineHeight: 1.2
  figure:
    fontFamily: "'Baloo Da 2', 'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 800
    lineHeight: 1.1
    fontFeature: "tnum"
  body:
    fontFamily: "'Hind Siliguri', 'Baloo Da 2', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.65
  label:
    fontFamily: "'Hind Siliguri', 'Baloo Da 2', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.3
rounded:
  sm: "6px"
  md: "10px"
  pill: "999px"
spacing:
  "1": "0.25rem"
  "2": "0.5rem"
  "3": "0.75rem"
  "4": "1rem"
  "5": "1.5rem"
  "6": "2rem"
  "7": "3rem"
  tap: "44px"
components:
  button:
    backgroundColor: "{colors.box}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.05rem"
    height: "44px"
  button-primary:
    backgroundColor: "{colors.done}"
    textColor: "{colors.on-done}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.05rem"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.done-hover}"
    textColor: "{colors.on-done}"
  button-shefa:
    backgroundColor: "{colors.shefa}"
    textColor: "{colors.on-shefa}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.05rem"
    height: "44px"
  button-urgent:
    backgroundColor: "{colors.urgent}"
    textColor: "{colors.on-urgent}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.05rem"
    height: "44px"
  button-small:
    rounded: "{rounded.sm}"
    padding: "0.3rem 0.75rem"
    height: "36px"
  input:
    backgroundColor: "{colors.box}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.45rem 0.75rem"
    height: "44px"
  segmented:
    backgroundColor: "{colors.box-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "3px"
  mark-done:
    backgroundColor: "{colors.done-wash}"
    textColor: "{colors.done-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-waiting:
    backgroundColor: "{colors.waiting-wash}"
    textColor: "{colors.waiting-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-urgent:
    backgroundColor: "{colors.urgent}"
    textColor: "{colors.on-urgent}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-shefa:
    backgroundColor: "{colors.shefa-wash}"
    textColor: "{colors.shefa-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-live:
    backgroundColor: "{colors.shefa}"
    textColor: "{colors.on-shefa}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  box:
    backgroundColor: "{colors.box}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "1rem"
  doc-name:
    backgroundColor: "{colors.doc-0}"
    textColor: "oklch(0.985 0.004 165)"
    rounded: "{rounded.sm}"
    padding: "0.1rem 0.6rem"
  rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-ink}"
    width: "16rem"
  rail-item-active:
    backgroundColor: "{colors.box}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "44px"
---

# Design System: SHEFA

## Overview

**Creative North Star: "The Medicine Shelf"**

SHEFA looks like a Bangladeshi pharmacy shelf, read as a working screen. Off-white box board sits on a shelf with the faintest cast of the rail's pharma green, never cream. A deep pharma-green rail runs down the staff app and across the top of every public page. Solid colour label blocks carry reversed bold type, the way a medicine box prints its brand name. Serials and references are printed in a dashed batch stamp with tabular digits, like the MFG/EXP block on a carton. Every doctor wears their own box colour across the whole product, so the desk finds a doctor's sessions, list and patients by colour, the way a pharmacist reaches for the right box.

Status is a printed legend: one colour, one meaning, everywhere, and always with words beside the colour. Red means a caller needs a person, or there is a clash or an error. Amber means waiting. Green means done, and green is also the colour of going ahead. SHEFA blue means SHEFA itself: a live call, a booking it made, its side of a transcript. Gone is grey and struck through. The legend sits at the foot of the rail on desktop and repeats on the page on a phone.

The density is a working desk's, but friendly and local rather than austere. Bangla comes first. Type is round and bold for names and the numbers that matter (Baloo Da 2) and plain and readable for everything else (Hind Siliguri). Corners are small, and boxes sit on the shelf with a soft shadow. The world has a light shelf and an after-hours dark shelf, chosen by the device or by the viewer.

**Key Characteristics:**
- Off-white boxes on a faintly green-grey shelf; a pharma-green rail or top bar.
- One colour, one meaning: urgent red, waiting amber, done green, SHEFA blue, gone grey, always with words.
- Six doctor box colours that never collide with the legend hues.
- Reversed name blocks and dashed batch stamps borrowed from medicine packaging.
- Baloo Da 2 for names, headings and numbers that matter; Hind Siliguri for body and data.
- Light and dark shelves, with a three-way theme switch (follow device, light, dark).

## Colors

A near-neutral shelf and box board carrying a trace of the rail's green, a deep pharma-green structural rail, a five-meaning status legend, and six doctor box colours that each get a meaning of their own.

### Primary
- **Settled Green** (done): the legend's "done, confirmed, seen" and the colour of going ahead. Primary buttons, the selected time slot, the patient's current step, checkbox accents and the receipt's top band all use it. In the frontmatter it appears once, as `done`; the code aliases it as `--primary`.
- **Settled Green, deep** (done-hover): the hover state for primary actions.
- **Settled Green ink and wash** (done-ink, done-wash): green text on white, and the pale fill behind a done pill or a completed step.

### Secondary
- **SHEFA Blue** (shefa): only for what SHEFA itself is doing or did. The live-call pill, the live demo orb, the "now" line on the day axis, the in-progress count, the SHEFA bar in the source report, and the capsule half in the logo. Its ink is the link colour, and its wash is the background of SHEFA's transcript turns, text selection and the input focus halo.
- **Focus Blue** (focus): the 3px focus outline. It is the same hue as SHEFA blue and turns lighter on the dark shelf. On the green rail, focus turns warm yellow so it stays visible.

### Tertiary: the legend
- **Needs-a-Person Red** (urgent, urgent-ink, urgent-wash, on-urgent): a caller who needs a person, a clash in the week preview, an error, the emergency notice. A solid red fill is reserved for the loudest cases: the callbacks header band, the desk alert, the "needs a person" pill. Errors in a field use the wash with an urgent border.
- **Waiting Amber** (waiting, waiting-ink, waiting-wash): pending, unconfirmed, retrying. Mostly used as a wash for notes and sample banners, with amber ink on the pill.
- **Gone**: cancelled, off or disabled renders as ink-3 text, struck through, with no dot. The tokens.css file declares a `--gone` value, but the build never reads it.

### Doctor box colours
- **Teal, Rose, Violet, Copper, Olive, Graphite** (doc-0 to doc-5, in that order): each doctor's identity, all at one lightness and strength so no doctor shouts louder than another; Graphite replaced a sky blue that read too close to SHEFA blue. Each colour appears as a solid name block, a colour band on the doctor's box, a session bar on the day axis, and a chip square. White type on every one passes AA. In code, a `.doc-cN` class sets a local `--doc` that every doctor-coloured element reads.

### Neutral
- **Warm Shelf** (shelf): the page field behind every box.
- **Box Board** (box): every container, button and input face.
- **Box Board, shaded** (box-2): table heads, hover rows, the segmented-control well, editor panels, summary cards, user transcript turns.
- **Carton Ink** (ink, ink-2, ink-3): body text, secondary text, and hints, placeholders and disabled text.
- **Fold Lines** (rule, rule-strong): row dividers, and the stroke on controls and dashed empty states.
- **Pharma Green Rail** (rail, rail-hover, rail-rule, rail-ink, rail-ink-2): the staff rail, the sign-in field, the patient, demo and collector top bars, and the lab report's title band.

### Named Rules
**The One Colour, One Meaning Rule.** Each legend hue means one thing on every surface: red needs a person, amber waits, green is done or go, blue is SHEFA, grey struck through is gone. Never use a legend hue for decoration, and never let colour speak without a word beside it.

**The Box Colour Rule.** Doctors wear only the six doc colours, which sit clear of the legend hues. A doctor's colour appears wherever that doctor does (name block, session bar, box band, chip). A clash overrides the doctor's colour with urgent red.

**The Two Shelves Rule.** Every colour has a dark-shelf value (see the sidecar). The theme is chosen by `prefers-color-scheme`, unless `:root[data-theme]` forces light or dark. Surfaces read tokens and never hard-code a light value. On the dark shelf, text on a solid green, blue or red fill turns dark (the on-done, on-shefa and on-urgent values), so the fills keep their hue and stay legible.

## Typography

**Display Font:** Baloo Da 2 (variable 400 to 800), falling back to Hind Siliguri, Noto Sans Bengali and system-ui
**Body Font:** Hind Siliguri (400, 500, 600, 700), falling back to Baloo Da 2, Noto Sans Bengali and system-ui

**Character:** Baloo Da 2 is the round, bold voice of the label. It sets doctors' names, headings, buttons, stamps, phone numbers and the big figures. Hind Siliguri is the quiet, highly legible Bangla for body text and data. Both are self-hosted under SIL OFL. Public pages for patients and volunteers on slow phones load the light set (Baloo Da 2 only, about 120 KB), so their body text falls through to Baloo.

### Hierarchy
- **Display** (800, 2.5rem; sign-in up to clamp(2.4rem, 5.5vw, 4.75rem); line-height 1.1): page titles and the sign-in statement. On a phone, page titles step down to 1.875rem.
- **Headline** (700, 1.4375rem, 1.2): section heads such as "today's chambers" and "recent calls".
- **Title** (700, 1.1875rem, 1.2): box titles, empty-state titles, the doctor band, transcript text size.
- **Figure** (800, 1.875rem, 1.1, tabular): measures in the overview and report tables, and the big serial on a doctor's phone.
- **Body** (400, 1rem, 1.65; English 1.5): running text and data. Transcript lines hold to 62ch.
- **Label** (600, 0.875rem, 1.3): field labels, table heads, pills and hints. Axis hours and legend entries drop to 0.75rem.

The type steps are 0.75, 0.875, 1, 1.1875, 1.4375, 1.875 and 2.5rem.

### Named Rules
**The Label Voice Rule.** Baloo Da 2 is for what the box shouts (names, headings, numbers that matter, buttons, stamps). Never set paragraphs or table data in it on staff surfaces, where Hind Siliguri is loaded.

**The Tabular Digits Rule.** Times, serials, phone numbers, counts and tables always use tabular numerals.

## Layout

The staff app is a two-column grid: a sticky 16rem green rail, and a main work field with padding of clamp(1rem, 3.2vw, 3rem) and a maximum width of 86rem. Page heads put the title and tools on one line and wrap. Sections stack with 2rem gaps. Spacing runs 0.25, 0.5, 0.75, 1, 1.5, 2 and 3rem, and every tap target is at least 44px. Live leads with the needs-a-person box, then today's chambers (a 12rem name column beside a time axis), then two working boxes laid out in an auto-fit grid of columns at least 24rem wide.

At 52rem and below, the rail becomes a top bar and the nav moves to a fixed bottom tab bar with icons over labels. The legend repeats on the page, and day-axis rows stack the name block above the bar. At 40rem and below, tables become stacked records with each cell labelled, and a doctor's day becomes a feed: one patient fills most of the screen in its own box, with a green top band, and the page snaps from one patient to the next. Patient, demo and volunteer pages are single columns of 40rem (patient) or 560px (volunteer), with a sticky green top bar.

Detail opens in a sheet: a box pulled off the shelf that slides in from the right, up to 46rem wide, with a 16px leading radius. It slides in over 0.24s on the drawer curve `cubic-bezier(0.32, 0.72, 0, 1)` (no overshoot) and back out over 0.16s when closed with the pointer; Esc closes it at once. The backdrop fades with it.

## Elevation & Depth

Depth is a printed box resting on a shelf: a short contact shadow plus a soft drop. Boxes carry the resting shadow. Anything pulled forward (the sheet, the desk alert, the sign-in card, the receipt, the active needs-a-person box, a hovered patient card) carries the lifted shadow. On the dark shelf, both shadows become plain black at higher opacity. Empty states lift nothing: they are a dashed outline on the bare shelf.

### Shadow Vocabulary
- **Box on shelf** (`box-shadow: 0 1px 2px oklch(0.3 0.02 165 / 0.07), 0 6px 16px -8px oklch(0.3 0.02 165 / 0.18)`): every resting container, the active rail item, the pressed segment, button hover.
- **Pulled forward** (`box-shadow: 0 2px 4px oklch(0.3 0.02 165 / 0.08), 0 18px 40px -12px oklch(0.3 0.02 165 / 0.28)`): sheet, desk alert, sign-in card, receipt, active callbacks box, demo orb.

### Named Rules
**The Live Ring Rule.** A ring only pulses while a call or a recording is live (the blue live orb, the dot in a live pill). Static outlines that mark a state are fine, such as the 2px urgent outline on a callbacks box with people waiting or the 2px doctor-colour outline on a full session. Decorative halos at rest are not.

## Shapes

Small, honest corners, like card stock: 6px for controls, name blocks and session bars; 10px for boxes, notes and panels; full pills for marks, chips and patient choice chips. Status dots are circles. Doctor chips are 3px-rounded squares. Stamps are dashed 1.5px frames with tight 4px corners. Transcript turns are 14px bubbles with one 4px corner on the speaker's side. Dashed borders mean something printed or not yet there: the batch stamp, an empty state, the danger zone divider, the patient's callback divider. Off days and leave on the day axis use a diagonal stripe in two box tones inside a dashed frame, with the label struck through.

## Components

### Buttons
Square-shouldered and plainly labelled, set in Baloo Da 2 at 600.
- **Shape:** gently rounded (6px), at least 44px tall, padding 0.5rem 1.05rem; Lucide icons at 16px inline, with a 0.45rem gap.
- **Default:** box face, strong rule stroke, ink text. On hover (pointer devices only), the stroke darkens to ink-2 and the button gains the box shadow. When pressed, it drops to box-2 with no shadow and scales to 0.98, easing back over 0.16s. Every pressable control uses the same 0.98.
- **Primary:** settled green fill with on-done text; on hover, deep green. Used for going ahead (book, save, confirm).
- **SHEFA:** blue fill, for actions that hand work to SHEFA.
- **Urgent:** red fill, for the needs-a-person action. **Danger** is a default button with urgent ink that turns to an urgent wash on hover.
- **Quiet:** no stroke and no fill; hover shades to box-2. **Small:** 36px tall at 0.875rem.
- **Disabled:** box-2 face, rule stroke, ink-3 text, not-allowed cursor.
- **Focus:** 3px focus-blue outline offset 2px (warm yellow on the rail).

### Marks (status pills)
The legend in pill form: colour plus words.
- **Style:** pill, at least 1.65rem tall, 0.875rem at 600, with a 0.5rem dot in the current colour before the words.
- **Variants:** done (green wash, green ink), waiting (amber wash, amber ink), needs a person (solid red, white), SHEFA (blue wash, blue ink), live (solid blue, with the dot pulsing every 1.6s), quiet (outlined, hollow dot), gone (no fill, ink-3, struck through, no dot), selected (ink fill with a green dot).

### Doctor name block, band and chip
- **Name block:** a doctor's name reversed out of their box colour, white Baloo Da 2 at 700, 6px corners. It heads each row of the day axis and appears inline wherever a doctor is named.
- **Band:** on the Doctors page and the patient's doctor list, each doctor is a white box with a full-bleed colour band across its top that carries the name.
- **Chip:** a 0.75rem colour square before a doctor's name in dense lists.

### Batch stamp
The printed MFG/EXP block. A dashed 1.5px frame in the current colour with 4px corners, holding tabular Baloo Da 2 digits at 700 and a small Hind Siliguri unit. It carries serials such as "১৯/২৪" on a session bar (on a box face, framed in the doctor's colour) and references. The patient receipt prints its reference as a large stamp in green.

### Boxes / Containers
- **Corner Style:** 10px.
- **Background:** box on the shelf.
- **Shadow Strategy:** box-on-shelf at rest; pulled-forward when active (see Elevation).
- **Border:** none at rest. Rows inside a box are divided by 1px rule lines, and table heads shade to box-2.
- **Internal Padding:** 1rem to 1.5rem; ledger rows at least 54px tall.

### Inputs / Fields
- **Style:** box face, 1px strong rule stroke, 6px corners, at least 44px tall (50px on patient pages). Labels sit above in 0.875rem at 600, in ink-2. A unit field prints its unit in a box-2 cell beside the input.
- **Focus:** the border turns focus blue, with a 3px SHEFA-wash halo.
- **Error:** urgent border on an urgent wash; the message sits below in urgent ink at 600.
- **Select:** a drawn chevron, no native arrow. Checkboxes and radios are accent green.

### Segmented control
A box-2 well with a 3px inset. The chosen segment is a box face with the resting shadow. On the rail, the well darkens to translucent black and the chosen segment stays white. It is used for language (বাংলা / English) and the three-way theme switch (follow device, light, dark; Lucide Monitor, Sun and Moon at 16px). The theme choice is remembered per device under `shefa.theme` and applied before first paint.

### Navigation
- **Rail (desktop):** a 16rem pharma-green column. At the top is the capsule logo (a white and SHEFA-blue capsule tilted on a green tile) with SHEFA in Baloo Da 2 at 800 and শেফা beside it. Nav items are 44px rows, each with a 1.9rem translucent icon tile holding a Lucide icon. On hover the row turns rail-hover. The active item becomes a white box with ink text at 700 and a green icon tile. The legend sits at the rail's foot, then preferences, then the signed-in user.
- **Phone:** the rail collapses to a top bar holding the logo and preferences, and the nav becomes a fixed bottom tab bar on the rail green, with icons over 0.72rem labels.
- **Public pages:** a sticky green top bar with the logo, a pill language toggle and the theme switch.

### Today's chambers (signature)
One row per doctor: a name block, then a time axis with hourly ticks and a blue "now" line. Each session is a bar framed in the doctor's colour on a 14% tint. It fills in solid doctor colour as serials are booked, and a stamp shows booked over capacity. A full session gains a 2px outline in the doctor's colour and the word "full". Leave shows as the striped, dashed, struck-through block.

### Needs-a-person box (signature)
The first box on Live. When callers are waiting, its header becomes a solid red band with a white count badge, the box takes a 2px red outline and the lifted shadow, and each row sits on an urgent wash. When nobody waits, it shrinks to a quiet one-line box with an ink-2 heading.

### Week preview
In setup, each session is a 6px-rounded bar in the doctor's colour, as long as the session really is. Overlapping sessions turn urgent red, and a clash pill sits on top.

## Do's and Don'ts

### Do:
- **Do** put words beside every status colour; a mark is always a dot plus a label.
- **Do** give each doctor one of the six box colours and use it on every surface that names them.
- **Do** use settled green for the primary action and SHEFA blue only for what SHEFA is doing or did.
- **Do** print serials and references in the dashed batch stamp with tabular digits.
- **Do** keep corners on the scale: 6px controls, 10px boxes, pill for marks and chips.
- **Do** use Lucide icons (lucide-react in the app; Lucide paths copied into static sprites) at 16 to 20px with a 2px stroke.
- **Do** read every colour from tokens so both shelves work, and keep tap targets at least 44px.
- **Do** keep metadata lines to at most one middle dot.

### Don't:
- **Don't** use a legend hue (red, amber, green, blue) as decoration or as a doctor's colour.
- **Don't** pulse or glow a ring around anything at rest; a ring moves only while a call or recording is live.
- **Don't** put em or en dashes in visible text.
- **Don't** set body paragraphs or table data in Baloo Da 2 where Hind Siliguri is loaded.
- **Don't** draw icons with text glyphs or emoji; use Lucide.
