---
name: SHEFA
description: A Bangla voice receptionist for small clinics, on a light clinic desk with medicine-box labels.
colors:
  shelf: "oklch(0.975 0.004 250)"
  box: "oklch(0.995 0.002 250)"
  box-2: "oklch(0.965 0.006 250)"
  ink: "oklch(0.24 0.02 260)"
  ink-2: "oklch(0.43 0.02 260)"
  ink-3: "oklch(0.52 0.015 260)"
  rule: "oklch(0.91 0.008 255)"
  rule-strong: "oklch(0.8 0.012 255)"
  rail: "oklch(0.99 0.003 250)"
  rail-hover: "oklch(0.955 0.008 250)"
  rail-rule: "oklch(0.91 0.008 255)"
  rail-ink: "oklch(0.24 0.02 260)"
  rail-ink-2: "oklch(0.45 0.02 260)"
  rail-tint: "oklch(0.965 0.006 250)"
  rail-line: "oklch(0.8 0.012 255)"
  primary: "oklch(0.5 0.17 265)"
  primary-hover: "oklch(0.45 0.17 265)"
  primary-wash: "oklch(0.955 0.03 265)"
  on-primary: "oklch(0.99 0.005 265)"
  brand: "oklch(0.5 0.17 265)"
  urgent: "oklch(0.55 0.2 27)"
  urgent-ink: "oklch(0.49 0.19 27)"
  urgent-wash: "oklch(0.955 0.03 27)"
  on-urgent: "oklch(0.99 0.01 27)"
  waiting: "oklch(0.82 0.15 82)"
  waiting-ink: "oklch(0.5 0.11 70)"
  waiting-wash: "oklch(0.965 0.05 88)"
  done: "oklch(0.5 0.12 158)"
  done-ink: "oklch(0.45 0.11 158)"
  done-wash: "oklch(0.955 0.035 158)"
  on-done: "oklch(0.99 0.01 158)"
  shefa: "oklch(0.52 0.15 300)"
  shefa-ink: "oklch(0.47 0.15 300)"
  shefa-wash: "oklch(0.96 0.025 300)"
  on-shefa: "oklch(0.99 0.01 300)"
  focus: "oklch(0.5 0.17 265)"
  doc-0: "oklch(0.5 0.1 195)"
  doc-1: "oklch(0.5 0.12 345)"
  doc-2: "oklch(0.5 0.1 225)"
  doc-3: "oklch(0.5 0.1 50)"
  doc-4: "oklch(0.5 0.1 115)"
  doc-5: "oklch(0.44 0.025 250)"
typography:
  display:
    fontFamily: "'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  headline:
    fontFamily: "'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.4375rem"
    fontWeight: 600
    lineHeight: 1.25
  title:
    fontFamily: "'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 600
    lineHeight: 1.25
  figure:
    fontFamily: "'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.1
    fontFeature: "tnum"
  brand:
    fontFamily: "'Baloo Da 2', 'Hind Siliguri', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "1.45rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "0.03em"
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
  mark:
    fontFamily: "'Hind Siliguri', 'Baloo Da 2', 'Noto Sans Bengali', system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.2
rounded:
  sm: "8px"
  md: "12px"
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
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.sm}"
    padding: "0.5rem 1.05rem"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
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
    typography: "{typography.mark}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-waiting:
    backgroundColor: "{colors.waiting-wash}"
    textColor: "{colors.waiting-ink}"
    typography: "{typography.mark}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-urgent:
    backgroundColor: "{colors.urgent}"
    textColor: "{colors.on-urgent}"
    typography: "{typography.mark}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-shefa:
    backgroundColor: "{colors.shefa-wash}"
    textColor: "{colors.shefa-ink}"
    typography: "{typography.mark}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  mark-live:
    backgroundColor: "{colors.shefa}"
    textColor: "{colors.on-shefa}"
    typography: "{typography.mark}"
    rounded: "{rounded.pill}"
    padding: "0.05rem 0.65rem"
  box:
    backgroundColor: "{colors.box}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "1rem"
  doc-name:
    textColor: "{colors.ink}"
  stamp:
    backgroundColor: "{colors.box-2}"
    textColor: "{colors.ink-2}"
    padding: "0.05rem 0.45rem"
  ref-chip:
    backgroundColor: "{colors.primary-wash}"
    textColor: "{colors.ink}"
    padding: "0.1rem 0.7rem"
  rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-ink}"
    width: "16rem"
  rail-item-active:
    backgroundColor: "{colors.primary-wash}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "44px"
---

# Design System: SHEFA

## Overview

**Creative North Star: "Clinic Light"**

SHEFA looks like a bright clinic desk that carries the labels of a Bangladeshi medicine shelf. Off-white boxes sit on a cool near-white field with slate ink, never cream. A light rail with a hairline edge runs down the staff app, and a light bar with a hairline beneath runs across the top of every public page. Boxes are edged by a 1px hairline rather than a drop shadow. Serials and references sit in quiet grey chips with tabular digits. Every doctor wears their own box colour across the whole product, carried as a small colour dot beside their name and as the fill of their session bars, so the desk finds a doctor's sessions, list and patients by colour, the way a pharmacist reaches for the right box.

Status is a printed legend: one colour, one meaning, everywhere, and always with words beside the colour. Red means a caller needs a person, or there is a clash or an error. Amber means waiting. Green means done. SHEFA violet means SHEFA itself: a live call, a booking it made, its side of a transcript. Gone is grey and struck through. One strong blue, outside the legend, is the colour of every action. The legend sits at the foot of the rail on desktop and repeats on the page on a phone.

The density is a working desk's, but friendly and local rather than austere. Bangla comes first. Type is one family, Hind Siliguri: semibold (600) for headings, names and the numbers that matter, regular for everything else. The round Baloo Da 2 survives only in the SHEFA wordmark. Corners are soft (8px and 12px), and boxes sit on the shelf inside a hairline with a barely-there lift. The world has a light theme and a navy-graphite dark theme that keeps the same blue and violet, lightened, chosen by the device or by the viewer.

**Key Characteristics:**
- Off-white boxes on a cool near-white field; a light rail or top bar with a hairline.
- One colour, one meaning: urgent red, waiting amber, done green, SHEFA violet, gone grey, always with words.
- One strong blue for every action, kept apart from the legend.
- Six doctor box colours, one per doctor, on every surface that names them.
- Hairline-edged boxes, a colour dot beside each doctor's name, and quiet grey chips for serials.
- Hind Siliguri throughout, semibold for headings and figures; Baloo Da 2 for the SHEFA wordmark only.
- Light and navy-graphite dark themes, with a three-way theme switch (follow device, light, dark).

## Colors

A cool near-white field and box board with slate ink, a light rail edged by a hairline, one strong blue for action, a five-meaning status legend, and six doctor box colours that each get a meaning of their own.

### Primary
- **Action Blue** (primary): the colour of every action. Primary buttons, the active nav item's icon, the patient's current step and chosen day and time, the demo's step numbers and resting orb, checkbox and radio accents, the skip link, links, text selection, the input caret and the focus halo (primary-wash). It is not a legend colour and never means done.
- **Action Blue, deep** (primary-hover): the hover state for primary actions.
- **Action Blue, wash** (primary-wash): the active nav row on the rail, and the chip behind the patient's booking reference on the receipt.
- **On Blue** (on-primary): text and icons on a solid blue fill.
- **Brand Blue** (brand): the logo tile and the sign-in field. The code aliases it to `--primary`, so it follows the theme.
- **Focus Blue** (focus): the 3px focus outline, in the action hue, lighter on the dark theme.

### Secondary
- **SHEFA Violet** (shefa, shefa-ink, shefa-wash, on-shefa): what SHEFA itself is doing or did. The live-call pill, the live demo orb, the "now" line on the day axis, the in-progress count and the SHEFA bar in the source report. Its wash is the background of SHEFA's transcript turns.

### Tertiary: the legend
- **Needs-a-Person Red** (urgent, urgent-ink, urgent-wash, on-urgent): a caller who needs a person, a clash in the week preview, an error, the emergency notice. A solid red fill is reserved for the loudest cases: the needs-a-person count, the desk alert, the "needs a person" pill. When callers wait, the needs-a-person box's title turns urgent ink; the box itself takes no red band, ring or row wash. Errors in a field use the wash with an urgent border.
- **Waiting Amber** (waiting, waiting-ink, waiting-wash): pending, unconfirmed, retrying. Mostly used as a wash for notes and sample banners, with amber ink on the pill.
- **Settled Green** (done, done-ink, done-wash, on-done): done, confirmed, seen. The done pill, the patient receipt's top band, and the top band of each patient in a doctor's day feed. Green is no longer the colour of going ahead.
- **Gone**: cancelled, off or disabled renders as ink-3 text, struck through, with no dot. The tokens.css file declares a `--gone` value, but the build never reads it.

### Doctor box colours
- **Teal, Rose, Steel, Copper, Olive, Graphite** (doc-0 to doc-5, in that order): each doctor's identity, all at one lightness and strength so no doctor shouts louder than another; Graphite replaced a sky blue that read too close to the blue SHEFA once wore. Steel (doc-2) took the place of a violet that shared SHEFA's hue (see the Box Colour Rule). Each colour appears as a small round dot before the doctor's name (in ink), the fill of their session bars on the day axis, and a round chip dot in dense lists; no type is reversed out of a doctor colour. In code, a `.doc-cN` class sets a local `--doc` that every doctor-coloured element reads.

### Neutral
- **Cool Field** (shelf): the page field behind every box.
- **Box Board** (box): every container, button and input face.
- **Box Board, shaded** (box-2): table heads, hover rows, the segmented-control well, editor panels, summary cards, user transcript turns.
- **Slate Ink** (ink, ink-2, ink-3): body text, secondary text, and hints, placeholders and disabled text.
- **Fold Lines** (rule, rule-strong): row dividers, and the stroke on controls and dashed empty states.
- **Light Rail** (rail, rail-hover, rail-rule, rail-ink, rail-ink-2): the staff rail with its hairline edge, the phone tab bar, and the patient, demo and collector top bars with a hairline beneath. On the dark theme the rail is the deepest navy, darker than the field.
- **Rail Tint and Rail Line** (rail-tint, rail-line): the fills and strokes of things on the rail: the segmented and theme-switch wells, the rail's buttons and the public language toggle. In light they alias box-2 and rule-strong; in dark they are translucent white.

### Named Rules
**The One Colour, One Meaning Rule.** Each legend hue means one thing on every surface: red needs a person, amber waits, green is done, violet is SHEFA, grey struck through is gone. Blue stands outside the legend: it is the one colour of action, and it never means done. Never use a legend hue for decoration, and never let colour speak without a word beside it.

**The Box Colour Rule.** Doctors wear only the six doc colours, meant to sit clear of the legend hues. Steel (doc-2) sits where a violet once was, so no doctor shares SHEFA's hue. A doctor's colour appears wherever that doctor does (name dot, session bar fill, chip dot). A clash overrides the doctor's colour with urgent red.

**The Two Shelves Rule.** Every colour has a dark-theme value (see the sidecar). The theme is chosen by `prefers-color-scheme`, unless `:root[data-theme]` forces light or dark. Surfaces read tokens and never hard-code a light value. On the dark theme, text on a solid blue, green, violet or red fill turns dark (the on-primary, on-done, on-shefa and on-urgent values), so the fills keep their hue and stay legible.

## Typography

**Display Font:** Hind Siliguri at 600, falling back to Noto Sans Bengali and system-ui
**Body Font:** Hind Siliguri (400, 500, 600, 700), falling back to Baloo Da 2, Noto Sans Bengali and system-ui
**Brand Font:** Baloo Da 2 (800 for SHEFA, 600 for শেফা), the wordmark only

**Character:** One quiet, highly legible Bangla family carries the whole product; hierarchy comes from size and a single semibold step, not from a second display face. Baloo Da 2, round and bold, is kept for the SHEFA wordmark alone. Both are self-hosted under SIL OFL. Public pages for patients and volunteers on slow phones load the light set (Hind Siliguri 400 and 600 only, about 190 KB), so their wordmark falls back to Hind.

### Hierarchy
- **Display** (600, 1.75rem, 1.25): page titles. On a phone, page titles step down to 1.5rem. The sign-in statement uses the display class (600, line-height 1.15) at clamp(2.4rem, 5.5vw, 4.75rem), 2.5rem on a phone.
- **Headline** (600, 1.4375rem, 1.25): section heads such as "today's chambers" and "recent calls".
- **Title** (600, 1.1875rem, 1.25): box titles, the doctor band, transcript text size.
- **Figure** (600, 1.875rem, 1.1, tabular): measures in the overview and report tables, counts, and the big serial on a doctor's phone.
- **Brand** (Baloo Da 2, 800, 1.45rem, 1, 0.03em): the SHEFA wordmark in the rail and the public top bars, with শেফা beside it at 600.
- **Body** (400, 1rem, 1.65; English 1.5): running text and data. Transcript lines hold to 62ch.
- **Label** (600, 0.875rem, 1.3): field labels, table heads and hints. Status marks are 500. Axis hours and legend entries drop to 0.75rem.

The type steps are 0.75, 0.875, 1, 1.1875, 1.4375, 1.875 and 2.5rem.

### Named Rules
**The Wordmark Rule.** Baloo Da 2 sets the SHEFA wordmark and nothing else. Headings, names, buttons, chips and figures are Hind Siliguri at 600; weight, not a second face, carries emphasis.

**The Tabular Digits Rule.** Times, serials, phone numbers, counts and tables always use tabular numerals.

## Layout

The staff app is a two-column grid: a sticky 16rem light rail with a hairline edge, and a main work field with padding of clamp(1rem, 3.2vw, 3rem) and a maximum width of 86rem. Page heads put the title and tools on one line and wrap. Sections stack with 2rem gaps. Spacing runs 0.25, 0.5, 0.75, 1, 1.5, 2 and 3rem, and every tap target is at least 44px. Live leads with the needs-a-person box, then today's chambers (a 12rem name column beside a time axis), then two working boxes laid out in an auto-fit grid of columns at least 24rem wide.

At 52rem and below, the rail becomes a top bar and the nav moves to a fixed bottom tab bar with icons over labels. The legend repeats on the page, and day-axis rows stack the doctor's name above the bar. At 40rem and below, tables become stacked records with each cell labelled, and a doctor's day becomes a feed: one patient fills most of the screen in its own box, with a green top band, and the page snaps from one patient to the next. Patient, demo and volunteer pages are single columns of 40rem (patient) or 560px (volunteer), with a sticky light top bar and a hairline beneath.

Detail opens in a sheet: a box pulled off the shelf that slides in from the right, up to 46rem wide, with a 16px leading radius. It slides in over 0.24s on the drawer curve `cubic-bezier(0.32, 0.72, 0, 1)` (no overshoot) and back out over 0.16s when closed with the pointer; Esc closes it at once. The backdrop fades with it.

### Motion

Motion explains a change; it never decorates. Durations are a scale like the spacing one, after transitions.dev and capped at 300ms because staff see them all day: `--dur-1` 80ms (a shake step), `--dur-2` 150ms (press, colour), `--dur-3` 200ms (content arriving, a row leaving), `--dur-4` 250ms (the switch pill), `--dur-5` 300ms (a count rolling over). One curve for nearly everything: `--ease-out`, `cubic-bezier(0.22, 1, 0.36, 1)`; the sheet keeps its drawer curve.

- **Loading:** skeleton rows breathe (opacity 1 to 0.5 over 1s, alternating), never a sweeping gradient, which repaints every frame on a desk PC. The real content (ledgers, tables, stats, doctor grid, today's chambers, the My Day feed) fades in over 200ms where the skeleton stood, through `@starting-style` on the container, so rows a poll adds do not each animate.
- **A live count changes** (callers waiting, calls in progress): the new figure rolls in from the direction of change, up when it grows, with a 0.04em blur, over 300ms (`LiveCount`). Never on first render, never when a poll returns the same figure.
- **A caller is resolved:** the row fades and drifts 0.5rem toward the end over 200ms, then the list refreshes; it leaves rather than vanishing.
- **Sign-in refused:** the card shakes once, 6px, -6px, 2px over 280ms, alongside the red message.
- **Reduced motion:** loops stop, nothing slides or scales, colour and opacity still fade; every animation ends on its visible state.

## Elevation & Depth

Boxes are nearly flat: a 1px hairline ring in the rule colour with a barely-there contact lift, so they read as edged rather than raised. Only what is pulled forward (the sheet, the desk alert, the sign-in card, the receipt, the demo orb) carries a real drop shadow. On the dark theme the resting box is the hairline alone, and the lifted shadow becomes plain black at higher opacity. Empty states lift nothing: they are a dashed outline on the bare shelf.

### Shadow Vocabulary
- **Hairline box** (`box-shadow: 0 0 0 1px var(--rule), 0 1px 2px oklch(0.3 0.02 260 / 0.04)`; dark: `0 0 0 1px var(--rule)`): every resting container and the chosen segment.
- **Pulled forward** (`box-shadow: 0 2px 4px oklch(0.3 0.02 260 / 0.08), 0 18px 40px -12px oklch(0.3 0.02 260 / 0.24)`): sheet, desk alert, sign-in card, receipt, demo orb. A hovered patient card only firms its hairline to rule-strong; nothing lifts on hover.

### Named Rules
**The Live Ring Rule.** A ring only pulses while a call or a recording is live (the violet live orb, the dot in a live pill). Static strokes that mark a state are fine, such as the focus outline or the thin dashed outline of a session on leave. Decorative halos and glow rings at rest are not, and urgency is told by red words and a red count, not by a ring around the box.

## Shapes

Soft, modern corners: 8px for controls and week-preview bars; 12px for boxes, notes and panels; full pills for marks, chips, patient choice chips and the slim session bars on the day axis. Status dots, doctor dots and doctor chips are circles. Serial and reference chips are small rounded rectangles with no border. Transcript turns are 14px bubbles with one 4px corner on the speaker's side. Dashed borders mean something not yet there or set apart: an empty state, a session on leave, the danger zone divider, the patient's callback divider. Leave on the day axis is a thin dashed outline with no fill, and its label is struck through.

## Components

### Buttons
Plainly labelled, set in Hind Siliguri at 600.
- **Shape:** gently rounded (8px), at least 44px tall, padding 0.5rem 1.05rem; Lucide icons at 16px inline, with a 0.45rem gap.
- **Default:** box face, strong rule stroke, ink text. On hover (pointer devices only), hover is a surface step, never a shadow: the face shades to box-2 and the stroke firms to ink-3. When pressed, it drops to box-2 and scales to 0.98, easing back over 0.16s. Every pressable control uses the same 0.98.
- **Primary:** action-blue fill with on-primary text; on hover, deep blue. Used for going ahead (book, save, confirm).
- **SHEFA:** violet fill, for actions that hand work to SHEFA.
- **Urgent:** red fill, for the needs-a-person action. **Danger** is a default button with urgent ink that turns to an urgent wash on hover.
- **Quiet:** no stroke and no fill; hover shades to box-2. **Small:** 36px tall at 0.875rem.
- **Disabled:** box-2 face, rule stroke, ink-3 text, not-allowed cursor.
- **Focus:** 3px focus-blue outline offset 2px.

### Marks (status pills)
The legend in pill form: colour plus words.
- **Style:** pill, at least 1.65rem tall, 0.875rem at 500, with a 0.4rem dot in the current colour before the words.
- **Variants:** done (green wash, green ink), waiting (amber wash, amber ink), needs a person (solid red, white), SHEFA (violet wash, violet ink), live (solid violet, with the dot pulsing every 1.6s), quiet (outlined, hollow dot), gone (no fill, ink-3, struck through, no dot), selected (ink fill with a green dot).

### Doctor name, band and chip
A doctor is a colour dot and their name; the colour marks, the ink speaks.
- **Name:** a round dot (about 0.55 to 0.6rem) in the doctor's colour, then the name in ink, Hind Siliguri at 600. It heads each row of the day axis, appears inline wherever a doctor is named, and heads the patient's doctor cards and chosen-doctor line.
- **Band:** on the Doctors page, each doctor's box opens with the dotted name in ink at title size over a 1px rule.
- **Chip:** a 0.55rem round colour dot before a doctor's name in dense lists, at 600.

### Serial and reference chips
A quiet grey chip: box-2 background, ink-2 text, no border, small rounded corners, holding tabular digits at 600 and a smaller unit at 0.7em. It carries serials and references. Above a session bar the count drops the chip and reads as plain ink text. The patient receipt prints its booking reference large (2.3rem, 600) on a primary-wash chip in ink.

### Boxes / Containers
- **Corner Style:** 12px.
- **Background:** box on the shelf.
- **Shadow Strategy:** the hairline box at rest; pulled-forward only for what comes off the shelf (see Elevation).
- **Border:** none; the edge is the hairline ring in the box shadow. Rows inside a box are divided by 1px rule lines, and table heads shade to box-2.
- **Internal Padding:** 1rem to 1.5rem; ledger rows at least 54px tall.

### Inputs / Fields
- **Style:** box face, 1px strong rule stroke, 8px corners, at least 44px tall (50px on patient pages). Labels sit above in 0.875rem at 600, in ink-2. A unit field prints its unit in a box-2 cell beside the input.
- **Focus:** the border turns focus blue, with a 3px primary-wash halo.
- **Error:** urgent border on an urgent wash; the message sits below in urgent ink at 600.
- **Select:** a drawn chevron, no native arrow. Checkboxes and radios are accent blue.

### Segmented control
A box-2 well with a 3px inset. The chosen segment is a box-face pill with the hairline box shadow that slides under the chosen button (`.seg-pill`, placed by `useSegPill` in lib/motion.tsx) over 250ms on the ease-out; buttons keep `aria-pressed` and the pill is decoration. On the rail, the well takes rail-tint with a rail-line stroke. Also used for the summary page's period (today, 7 days, 30 days). It is used for language (বাংলা / English) and the three-way theme switch (follow device, light, dark; Lucide Monitor, Sun and Moon at 16px). The theme choice is remembered per device under `shefa.theme` and applied before first paint.

### Navigation
- **Rail (desktop):** a 16rem light column with a hairline edge. At the top is the capsule logo (a white and lavender (#c9b8f4) capsule tilted on a brand-blue tile; the favicons match) with the SHEFA wordmark in Baloo Da 2 at 800 and শেফা beside it at 600. Nav items are 44px rows, each with a bare Lucide icon in rail-ink-2 (no tile). On hover the row turns rail-hover. The active item takes the primary wash, ink text at 700, and a primary-coloured icon. The legend sits at the rail's foot, then preferences, then the signed-in user.
- **Phone:** the rail collapses to a top bar holding the logo and preferences, and the nav becomes a fixed bottom tab bar on the light rail, with a hairline above and icons over 0.72rem labels.
- **Public pages:** a sticky light top bar with a hairline beneath, the logo on its brand-blue tile, a pill language toggle and the theme switch.

### Today's chambers (signature)
One row per doctor: the dotted name, then a time axis with hourly ticks and a violet "now" line. Each session is a slim pill bar (0.5rem tall) on a 16% tint of the doctor's colour, filling in solid doctor colour as serials are booked. Booked over capacity sits above the bar as plain text, the figures in ink and the rest in ink-2. A full session adds the word "full" in ink-2 and gains no ring. Leave is a thin dashed outline with no fill, its label struck through.

### Needs-a-person box (signature)
The first box on Live. When callers are waiting, its title turns urgent ink and the count beside it is a solid red pill; the box keeps the ordinary hairline, with no red header bar, outline or glow, and its rows carry no red wash. When nobody waits, it shrinks to a quiet one-line box with an ink-2 heading.

### Week preview
In setup, each session is an 8px-rounded bar in the doctor's colour, as long as the session really is. Overlapping sessions turn urgent red, and a clash pill sits on top.

## Do's and Don'ts

### Do:
- **Do** put words beside every status colour; a mark is always a dot plus a label.
- **Do** give each doctor one of the six box colours and use it on every surface that names them.
- **Do** use action blue for every primary action, settled green only for done, and SHEFA violet for what SHEFA is doing or did.
- **Do** set serials and references in a quiet grey chip (box-2, ink-2, no border) with tabular digits.
- **Do** keep corners on the scale: 8px controls, 12px boxes, pill for marks, chips and session bars.
- **Do** mark a doctor with a small colour dot beside their name in ink, and edge boxes with the hairline, not a drop shadow.
- **Do** use Lucide icons (lucide-react in the app; Lucide paths copied into static sprites) at 16 to 20px with a 2px stroke.
- **Do** read every colour from tokens so both themes work, including rail-tint and rail-line for anything on the rail, and keep tap targets at least 44px.
- **Do** keep metadata lines to at most one middle dot.

### Don't:
- **Don't** use a legend hue (red, amber, green, violet) or action blue as decoration, or give a new doctor a legend hue.
- **Don't** pulse or glow a ring around anything at rest; a ring moves only while a call or recording is live.
- **Don't** put em or en dashes in visible text.
- **Don't** use Baloo Da 2 for anything but the SHEFA wordmark.
- **Don't** reverse type out of a solid doctor colour, or wrap a box in a coloured outline or header bar to make it urgent.
- **Don't** draw icons with text glyphs or emoji; use Lucide.
