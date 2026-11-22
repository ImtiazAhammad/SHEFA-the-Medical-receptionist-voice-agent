---
name: SHEFA
description: The exposure record. A bilingual clinic voice receptionist drawn in one neutral zone ramp, one magenta, and hatching instead of colour.
colors:
  z0: "oklch(0.17 0.006 260)"
  z1: "oklch(0.235 0.007 260)"
  z2: "oklch(0.31 0.007 260)"
  z3: "oklch(0.39 0.007 260)"
  z4: "oklch(0.47 0.006 260)"
  z5: "oklch(0.56 0.006 260)"
  z6: "oklch(0.65 0.005 260)"
  z7: "oklch(0.745 0.005 260)"
  z8: "oklch(0.845 0.004 260)"
  z9: "oklch(0.925 0.003 260)"
  z10: "oklch(0.982 0.002 260)"
  white: "oklch(1 0 0)"
  dichroic: "oklch(0.54 0.215 352)"
  dichroic-ink: "oklch(0.5 0.2 352)"
  on-dichroic: "oklch(0.99 0.01 352)"
  dichroic-wash: "oklch(0.955 0.03 352)"
typography:
  display:
    fontFamily: "Anek, 'Noto Sans Bengali', Kalpurush, system-ui, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 600
    lineHeight: 1.02
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 78"
  headline:
    fontFamily: "Anek, 'Noto Sans Bengali', Kalpurush, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.02
    fontVariation: "'wdth' 78"
  title:
    fontFamily: "Anek, 'Noto Sans Bengali', Kalpurush, system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: "Anek, 'Noto Sans Bengali', Kalpurush, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Anek, 'Noto Sans Bengali', Kalpurush, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.3
  label-en:
    fontFamily: "Anek, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.14em"
    fontVariation: "'wdth' 90"
  num:
    fontFamily: "Martian, Anek, ui-monospace, monospace"
    fontSize: "1.4375rem"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontFeature: "'tnum' 1, 'zero' 1"
rounded:
  none: "0px"
spacing:
  space-1: "0.25rem"
  space-2: "0.5rem"
  space-3: "0.75rem"
  space-4: "1rem"
  space-5: "1.5rem"
  space-6: "2rem"
  space-7: "3rem"
  tap: "44px"
components:
  button:
    backgroundColor: "transparent"
    textColor: "{colors.z0}"
    rounded: "{rounded.none}"
    padding: "0.55rem 1rem"
    height: "{spacing.tap}"
  button-hover:
    backgroundColor: "{colors.z9}"
  button-active:
    backgroundColor: "{colors.z8}"
  button-primary:
    backgroundColor: "{colors.z0}"
    textColor: "{colors.z10}"
    rounded: "{rounded.none}"
    padding: "0.55rem 1rem"
    height: "{spacing.tap}"
  button-primary-hover:
    backgroundColor: "{colors.z2}"
  button-shefa:
    backgroundColor: "{colors.dichroic}"
    textColor: "{colors.on-dichroic}"
    rounded: "{rounded.none}"
    padding: "0.3rem 0.7rem"
    height: "36px"
  button-shefa-hover:
    backgroundColor: "{colors.dichroic-ink}"
  button-small:
    padding: "0.3rem 0.7rem"
    height: "36px"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.z0}"
    rounded: "{rounded.none}"
    padding: "0.45rem 0.7rem"
    height: "{spacing.tap}"
  mark:
    backgroundColor: "{colors.white}"
    textColor: "{colors.z0}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0.05rem 0.55rem"
    height: "1.6rem"
  mark-selected:
    backgroundColor: "{colors.z0}"
    textColor: "{colors.z10}"
  mark-shefa:
    textColor: "{colors.dichroic-ink}"
  seg-pressed:
    backgroundColor: "{colors.z0}"
    textColor: "{colors.z10}"
    height: "36px"
  nav-rail:
    backgroundColor: "{colors.z1}"
    textColor: "{colors.z9}"
    width: "15.5rem"
  nav-item-active:
    backgroundColor: "{colors.z10}"
    textColor: "{colors.z0}"
    height: "{spacing.tap}"
  table-head:
    backgroundColor: "{colors.z9}"
    textColor: "{colors.z3}"
    typography: "{typography.label}"
    padding: "0.65rem 0.75rem"
  sheet:
    backgroundColor: "{colors.white}"
    width: "min(46rem, 100vw)"
---

# Design System: SHEFA

## Overview

**Creative North Star: "The Exposure Record"**

SHEFA is drawn as a darkroom printer's exposure card: a ruled record of zones, densities and marks, read by people who need to know at a glance what is filling up, what clashes, and where the machine acted. Tone comes from a single eleven-step neutral zone ramp, faintly cool and never cream. Load and conflict are drawn, not coloured: a session fills with hatching that gets denser as its serials are taken, and two things that collide cross-hatch at ninety degrees. Every state is drawn and also said in words; the drawing never carries meaning on its own.

One dichroic magenta belongs to SHEFA's own voice and actions: a live call, a booking SHEFA made, a call SHEFA handed to a person, SHEFA's turns in a transcript. Everything else is zone. The world rejects the category default, which is white cards, a slate sidebar, one teal accent and KPI tiles. Data sits on the field in ruled ledgers and tables. Measures are ruled tables, and detail opens as a sheet of tracing paper over the list, so the list stays in place underneath.

Bangla is the primary language and is set first. English is the second view, and only English goes to tracked caps. The density is a working desk: hairline rows of 52px, 44px targets, and no ornament the record doesn't need.

**Key Characteristics:**
- Eleven neutral zones (z0 to z10) are the only tonal tokens. The dark theme reads the same ramp the other way round.
- One magenta, reserved for SHEFA's voice and actions.
- State vocabulary: selected is the deepest zone, waiting is hatched, conflict is cross-hatched, held back is a dotted outline, cancelled or disabled is struck through, and settled is a plain frame.
- Square everywhere, with 1px hairlines and a 2px ink rule heading each page and table.
- Anek for words (condensed for display), Martian Mono for Latin quantities, Anek for Bangla quantities.
- The only elevation is the sliding sheet.

## Colors

A cool neutral zone ramp carries all tone; one dichroic magenta carries SHEFA.

### Primary
- **Dichroic Magenta** (`dichroic`): SHEFA's own voice and nothing else. It appears as the live-call dot, the "needs a person" alert band and its action button, the square swatch on a booking SHEFA made, the 1px rule beside SHEFA's transcript turns, the caret in fields, and the third bar of the logo. In dark mode it lifts to oklch(0.72 0.19 352).
- **Dichroic Ink** (`dichroic-ink`): magenta used as text, such as SHEFA-mark labels, the callback heading when people are waiting, and the speaker name on SHEFA's turns. It is also the hover state of the magenta button. In dark mode it is oklch(0.78 0.16 352).
- **On Dichroic** (`on-dichroic`): text on a magenta fill.
- **Dichroic Wash** (`dichroic-wash`): the faint row ground behind a callback SHEFA raised for a person. It is the only tinted surface in the world. In dark mode it is oklch(0.3 0.07 352).

### Neutral
The zone ramp runs from z0 (near-black) to z10 (near-white), hue 260, with chroma at or below 0.007. Components use the semantic roles below, never raw zones, except where a zone itself is the meaning (the selected state, the zone wedge).

| Role | Light | Dark | Use |
|---|---|---|---|
| ground | z10 | z1 | The work field |
| sheet | white | z2 | A sheet laid over the field: fields, marks, notes, the sliding sheet |
| field-2 | z9 | z2 | Table heads, wells, row and button hover |
| ink | z0 | z10 | Text and heavy rules |
| ink-2 | z3 | z8 | Secondary text (8:1 on ground) |
| ink-3 | z4 | z7 | Faintest allowed text (5.9:1); dotted and held-back outlines |
| rule | z8 | z3 | Hairline between rows |
| rule-strong | z0 | z8 | Frame of a control, table or sheet |
| hatch-ink | z3 | z7 | Load hatching |
| rail / rail-ink | z1 / z9 | z0 / z9 | The staff app's left rail |
| select / on-select | z0 / z10 | z10 / z0 | Selected state, primary action |
| focus | z0 | z10 | Focus outline |

Fields use a z6 border at rest and a z3 border on hover. Disabled frames use z7.

### Named Rules
**The One Voice Rule.** Magenta marks only what SHEFA did or needs: a live call, a booking SHEFA made, a hand-off to a person, SHEFA speaking. Never use it for navigation, selection, errors, danger or decoration. If a person did it, or nobody did, it is zone.

**The Zone-Only Rule.** No other hue enters the world. There is no red for errors, no green for success and no amber for warnings. Severity is drawn with hatching, cross-hatching, dotted or struck rules, and weight, and it is always said in words.

**The Reversed Ramp Rule.** Dark mode does not invent colours. It maps the same roles onto the ramp the other way round, chosen by the viewer's system or by `data-theme`.

## Typography

**Display Font:** Anek (self-hosted Anek Bangla, variable weight 100–800 and width 75–125%), falling back to Noto Sans Bengali, Kalpurush, system-ui
**Body Font:** Anek
**Label/Mono Font:** Martian Mono (family name `Martian`) for Latin quantities

**Character:** Tall, condensed display type sits over a calm, open Bangla text face. Quantities sit in a ruled monospace, like the figures on a print log.

### Hierarchy
- **Display** (600, 2.75rem, line-height 1.02, width 78%): page titles in the page head, over a 2px ink rule. English display goes to uppercase with no tracking. Bangla has no case and keeps its shaping. On a phone it drops to 2rem. The sign-in statement scales up to clamp(2.5rem, 6vw, 5.5rem).
- **Headline** (600, 2rem, width 78%): sheet titles and the patient page h1 (2.1rem, 650).
- **Title** (650, 1.1875rem): section heads, which sit over a 1px ink rule, and doctor names.
- **Body** (400, 1rem, line-height 1.6 in Bangla and 1.5 in English): running text. Transcript turns run at 1.1875rem with a 62ch measure. Patient and collector pages set the body at 17–18px for phones.
- **Label** (600, 0.8125rem, ink-2): the legend over a field or column, table heads, and the sheet-bar identity. In English it becomes 0.6875rem uppercase, tracked 0.12–0.14em, at 90% width.
- **Num** (Martian, 500, tabular with a slashed zero): serials, counts, times, references and measure values. Measures run at 1.4375rem and right-align. The patient booking reference is 2.6rem.

The step scale runs 0.6875, 0.8125, 1, 1.1875, 1.4375, 2, 2.75 and 4rem.

### Named Rules
**The Bangla Quantity Rule.** Martian draws Latin digits only. Under `:lang(bn)`, `--font-num` swaps to Anek, so a Bangla serial or time never mixes two faces. Tables still right-align it with tabular figures.

**The Part-of-Day Rule.** Bangla times read by part of the day, never AM or PM: "সকাল ৯:০০", দুপুর, বিকাল, সন্ধ্যা, রাত. This is one clock everywhere: axes, rows, call summaries and the patient page.

**The English-Only Caps Rule.** Tracked uppercase applies only to English labels, buttons, marks and Latin display. Bangla is never tracked or forced into a case.

**The Light Fonts Rule.** Public pages (patient, demo, volunteer) load `fonts-lite.css`, which has no width axis. Their display type falls back to normal width, which the source calls the honest trade for about 290 KB less on a slow phone. The staff and admin pages load the full file.

## Layout

The staff app is a two-column shell: a 15.5rem z1 rail and a work field capped at 84rem, padded `space-6` above and clamp(1rem, 3.2vw, 3rem) at the sides. Pages open with a page head (display title and tools, a 2px ink rule, `space-5` below). Sections are separated by `space-6` and headed by a 1px ink rule.

Data is set in ledgers and tables, not cards. Ledger rows are at least 52px high with 1px rule separators and a field-2 hover. Table wraps carry a 2px ink top and a 1px ink bottom, and tables have z9 heads. Measures are a single-column ruled table, at most 52rem wide, with the label on the left and a right-aligned Martian figure. Two working lists sit side by side in auto-fit columns of at least 24rem.

Time is drawn to scale. In the Live chamber strip and the Setup week preview, a block's length is its real duration on an hourly axis with z9 tick lines, and a 2px ink "now" line with a square head marks the present.

The spacing rhythm follows space-1 to space-7 (0.25, 0.5, 0.75, 1, 1.5, 2 and 3rem). Targets are at least 44px (`tap`). Small buttons and segmented choices are 36px.

**Phone (52rem and below):** the rail collapses to a top bar, and navigation moves to a fixed bottom bar of equal cells with icons over labels. The chamber strip drops its axis and stacks the name over the track. The sheet goes full-screen and opaque. At 40rem and below, a stack table turns each row into a stacked record with a per-cell label, so nothing is clipped. Public pages are single-column, mobile-first at 360px, and capped at 40rem (patient) or 560px (volunteer).

**Print:** the day list prints one doctor per page as a black-ruled table, with the chrome hidden.

## Elevation & Depth

The world is flat. Depth comes from tone (field, sheet and rail zones) and rules. The only lift is the sheet: a panel slides in from the right over a z0 backdrop at 18% opacity and casts one long, soft shadow to its left, paired with a 1px edge.

### Shadow Vocabulary
- **Sheet shadow** (`box-shadow: -24px 0 48px -12px oklch(0.17 0.006 260 / 0.22), -1px 0 0 var(--z0)`; in dark mode `-24px 0 48px -12px oklch(0 0 0 / 0.6), -1px 0 0 var(--z6)`): the sliding sheet only.
- **Inset rule** (`box-shadow: inset 0 0 0 1px` or `inset 3px 0 0 -2px`): not elevation. It thickens a focused field's frame and draws the 1px magenta rule beside SHEFA's transcript turns.

### Named Rules
**The Tracing Paper Rule.** The sheet is blurred tracing paper: the sheet tone at 82% with a 10px backdrop blur, so the tone of the list shows through and its words do not. A second sheet sits beneath it at 70%, askew by -0.8deg, behind a z7 hairline. On a phone the sheet is fully opaque, with no blur.

**The Settle Rule.** The sheet slides in over 0.42s on `cubic-bezier(0.22, 1, 0.36, 1)`. It arrives with mass and settles with no overshoot or bounce.

## Shapes

Every corner is square (0px): buttons, fields, marks, notes, blocks, tables and the sheet. Circles are kept for things in motion: the live dot (a 0.5rem magenta circle that pulses on a live call) and the volunteer page's small loading spinner. SHEFA's own mark is a 0.5rem magenta square. Rules are 1px hairlines in `rule` between rows, 1px `rule-strong` frames around controls, and a 2px ink rule under page heads, across table tops and around the patient emergency notice. Dotted rules mean held back or set aside (held marks, leave blocks, empty states, the danger zone). Struck text means cancelled or disabled.

Hatching is the recurring texture. It runs at 135deg with a 1px line, in four densities of load at gaps of 9, 6, 4 and 2.75px. Conflict crosses 45deg over 135deg. SHEFA's hatch is magenta at 1.25px.

**The Hatch Never Behind Words Rule.** Hatching never runs under text. On marks and chips it sits in a swatch cell (1.1rem wide, with a 1px divider) at the start. On messages it is a 7px band across the top of the box (6px on the desk alert and receipt). In a load bar, the count sits on an opaque sheet chip over the fill.

## Components

### Buttons
Square, framed and quiet. The frame does the work.
- **Shape:** square (0px), 1px `rule-strong` frame, 44px high, weight 600. English labels are uppercase at 0.8125rem, tracked 0.06em, at 90% width.
- **Default:** transparent with ink text. Hover fills field-2 and press fills z8, over 0.15s on `cubic-bezier(0.16, 1, 0.3, 1)`.
- **Primary:** a select (z0) fill with on-select text. Hover goes to z2 and press to z3.
- **SHEFA:** a magenta fill, only for acting on what SHEFA raised (the "needs a person" alert). It ships at the small size.
- **Quiet:** no frame until hover, which shows a rule-coloured frame.
- **Disabled:** ink-3 text, a z7 frame and a struck label, never faded opacity.
- **Segment:** a button may carry a unit or count in a trailing segment behind a 1px divider, set in the num face.
- **Small:** 36px high. **Block:** full width.

### Marks (state chips)
State is drawn and said. A mark is a small framed label (1.6rem high, label type, white sheet ground).
- **Settled / info:** a plain 1px frame.
- **Waiting:** a hatched swatch cell at the start.
- **Conflict / failed:** a cross-hatched swatch cell.
- **Held back:** a dotted ink-3 frame with ink-2 text.
- **Cancelled:** a z7 frame with ink-3 struck text.
- **Selected:** a select fill.
- **SHEFA:** a magenta frame, dichroic-ink text and a leading magenta square.
- **Live:** a SHEFA mark with a pulsing round magenta dot (1.6s).

### Cards / Containers
There are no cards in the dashboard sense. Containers are framed sheets.
- **Corner Style:** square (0px).
- **Background:** sheet on the ground.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** a 1px ink frame for notes, editors and form panels. Ledger items and doctor cells use 1px rule dividers only.
- **Internal Padding:** `space-4` (editor `space-4`/`space-5`).
- **Notes:** a warning note carries a 7px hatched top band and an error note a 7px cross-hatched band, with the message in words below.
- **Empty:** a dotted ink-3 frame, a title and a hint.

### Inputs / Fields
- **Style:** square, with a 1px z6 frame on a sheet ground and 44px high (50px on public pages). The caret is magenta.
- **Hover / Focus:** hover darkens the frame to z3. Focus shows a rule-strong frame doubled by an inset 1px, with no glow.
- **Error:** an ink frame with a 3px double rule along the bottom, plus a worded field error below.
- **Unit field:** an input with its unit in a trailing cell ("045.0 | SEC"). On focus the unit cell fills with select.
- **Select:** a drawn chevron, square.
- **Labels:** a label-type legend above the field. In English it is tracked caps.

### Segmented choice
A 1px rule-strong frame split by 1px dividers, 36px high. The pressed segment fills with select. It is used for language and view switches, including in the rail, where the pressed segment fills z10.

### Navigation
- **Rail (desktop):** z1, holding the wordmark (SHEFA in 75% width with tracked caps, plus শেফা in rail-ink-2), then full-width 44px items divided by z3 rules, with an icon, a Bangla label and weight 500. Hover fills z2. The active item reverses to a z10 fill with z0 text at weight 650.
- **Foot:** the voice console link, the sound toggle, the language segment and the user with sign-out.
- **Phone:** a fixed bottom bar of equal cells, with the icon over a 0.72rem label.

### Tables and measures
Tables have 1px rule rows, z9 heads in label type over an ink rule, start-aligned text and end-aligned numbers. Hovered rows fill field-2. Measures (overview, report) are a ruled two-column table of label and Martian figure, never number tiles.

### The Sheet (signature)
A modal panel on the right (up to 46rem) for any call, booking or record. It is tracing paper over the list (see Elevation & Depth). Its sticky bar holds a small identity label and a quiet close button over a 1px ink rule, and its title uses the headline style. Esc, the close button or a click on the backdrop dismisses it, and focus returns to the row that opened it. Destructive actions sit far below in a danger zone set off by a dotted rule.

### Day Load strip (signature)
Each doctor has one row: a name column of 11rem and a time track. Each session is a framed block whose length is its real duration. The block fills from the start in proportion to serials booked, with hatching at one of four densities (up to a third, two thirds, below full, full). The count ("১৯/২৪") sits on an opaque chip over the fill, with a worded version for screen readers. A full session adds a bold "full" word. Leave is a dotted block with a struck count. The Setup week preview uses the same grammar. Overlapping sessions cross-hatch and carry a conflict mark beside the block.

### Transcript turns
Each turn is a two-column row: speaker and time on the left, words on the right at 1.1875rem. SHEFA's turns take a dichroic-ink speaker name and a 1px magenta rule at the left edge. Caller turns are plain.

### Patient steps and receipt
The booking steps form a zone wedge. Each completed step fills z8, and the current step fills select. The receipt is a framed ticket with the reference set huge in the num face and a 6px magenta hatch band along its foot, because SHEFA made the booking.

## Do's and Don'ts

### Do:
- **Do** draw every state and also say it in words: hatch density for load, cross-hatch for conflict, dotted for held back, struck for cancelled or disabled, and the deepest zone for selected.
- **Do** take tone from the zone roles (ground, sheet, field-2, ink, ink-2, ink-3, rule, rule-strong) so dark mode reverses for free.
- **Do** keep magenta to SHEFA's own actions and voice: a live dot, a swatch, a 1px rule, the needs-a-person alert.
- **Do** put hatching in a swatch cell, a 7px top band or behind an opaque count chip, never under words.
- **Do** set quantities in the num face with tabular figures, right-aligned in tables, and let `:lang(bn)` swap it to Anek.
- **Do** write Bangla times by part of the day ("সকাল ৯:০০").
- **Do** show measures as a ruled table with the label on the left and a right-aligned figure.
- **Do** draw time to scale: a block's length is its real duration.
- **Do** open detail as the sheet over the list, opaque on a phone.
- **Do** keep targets at 44px by default and on every phone or public surface (50px on public forms). 36px is allowed only for small buttons and segments in dense desktop rows, and stacked tables restore 44px on a phone.

### Don't:
- **Don't** use white rounded cards, a slate sidebar with one teal accent, or KPI number tiles.
- **Don't** use magenta for navigation, selection, tabs, errors, danger, offline states or decoration.
- **Don't** introduce any hue beyond the zone ramp and the one magenta. There is no red, green or amber state colour.
- **Don't** round corners. Circles are only for motion indicators (the live dot, a loading spinner).
- **Don't** add elevation shadows to anything but the sheet.
- **Don't** run hatching behind text.
- **Don't** fade a disabled control with opacity. Strike it and drop it to ink-3 and z7.
- **Don't** track or uppercase Bangla.
- **Don't** let the sheet bounce or overshoot.
- **Don't** mix Martian and Anek inside one Bangla quantity.
