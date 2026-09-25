<!--
Visual design system for the Sanocea website/demo frontend (website/src/*). Follows the DESIGN.md
format spec (github.com/google-labs-code/design.md) — frontmatter carries machine-readable tokens,
the markdown body carries context. Learned from pbakaus/impeccable's `document.md` skill reference
(Apache-2.0; pattern learned, not copied — OSS-first Decision C in CLAUDE.md). This is a first-pass
scan-mode extraction from website/src/styles.css's `:root` block — colors and fonts are confirmed
from source; the Components section is a lighter first pass and should be refined against the
actual JSX components (website/src/*.jsx) before treating it as exhaustive.

Do not overwrite without checking this file first — re-run a scan (grep the CSS custom properties)
before regenerating, per the "don't silently overwrite" rule this convention itself specifies.
-->
---
name: Sanocea Commerce OS
description: AI commerce operations layer — Command Centre and WhatsApp chat surfaces
colors:
  ink: "#08233d"
  ink-deep-blue: "#16466f"
  deep-navy: "#061421"
  deep-navy-2: "#09233a"
  paper: "#f7fbff"
  paper-tint: "#eaf5fb"
  white: "#ffffff"
  cyan: "#11c6dc"
  cyan-soft: "rgba(17, 198, 220, 0.16)"
  line: "rgba(8, 35, 61, 0.13)"
  line-strong: "rgba(8, 35, 61, 0.24)"
  line-dark: "rgba(255, 255, 255, 0.16)"
  muted: "#5a7184"
  muted-dark: "#a7bdce"
typography:
  body:
    fontFamily: "'Archivo', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
  mono:
    fontFamily: "'IBM Plex Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace"
rounded:
  pill: "999px"
  card-sm: "14px"
  card-md: "18px"
  card-lg: "24px"
  circle: "50%"
---

# Design System: Sanocea Commerce OS

## Overview

**Creative North Star: "Control room, not dashboard."**

The palette is deep navy ink on cool white paper, with a single electric-cyan accent used the way a
status light is used — sparingly, to mark what's live or actionable. The mood is evidence-first and
operational: monospace type for data/labels (order numbers, timestamps, status strings), sans-serif
for narrative copy. This is a deliberate rejection of the generic "AI SaaS" look CLAUDE.md's Design
Constitution warns against — no purple gradients, no default Inter, no centered-hero-over-mesh
pattern. **Confirmed visual rejection (per CLAUDE.md):** does not look like a catalogue tool, a
marketplace dashboard, a generic inventory dashboard, a chatbot, or a template SaaS site.

**Key Characteristics:**
- Deep navy ink (`#08233d`) on cool white paper (`#f7fbff`), not pure black on pure white.
- One accent color, electric cyan (`#11c6dc`), used for live/actionable/status signals only.
- Monospace (`IBM Plex Mono`) reserved for data-like content — labels, timestamps, status pills.
- Soft, navy-tinted shadows (never pure black) for elevation; cyan-tinted glow only on hover/active
  states that represent a live or successful signal.

## Colors

Single-accent system on a cool, dark-ink-on-light-paper base, with a full dark navy variant for
contrast sections.

### Primary
- **Cyan** (`#11c6dc`): the only accent. Live status, active/hover glow, primary CTA emphasis. Used
  sparingly — this is a signal color, not a fill color.

### Neutral
- **Ink** (`#08233d`): primary text and default foreground color on paper background.
- **Ink Deep Blue** (`#16466f`): secondary ink, used for lighter-weight text on paper.
- **Deep Navy** (`#061421`) / **Deep Navy 2** (`#09233a`): dark-section background pair (the
  contrast/inverted sections of the page).
- **Paper** (`#f7fbff`) / **Paper Tint** (`#eaf5fb`): light background pair — default page background
  and a slightly tinted variant for nested surfaces.
- **White** (`#ffffff`): true white, used sparingly (cards on paper, not the page background itself).
- **Muted** (`#5a7184`) / **Muted Dark** (`#a7bdce`): secondary/caption text on light and dark
  backgrounds respectively.
- **Line** (`rgba(8, 35, 61, 0.13)`) / **Line Strong** (`rgba(8, 35, 61, 0.24)`): hairline borders on
  light backgrounds, two weights. **Line Dark** (`rgba(255, 255, 255, 0.16)`): hairline borders on
  dark/navy sections.

### Named Rules
**The One Accent Rule.** Cyan is the only saturated color in the system. Everything else is navy ink,
paper, or navy-tinted neutrals. If a new UI element needs a second accent color, that's a signal the
composition needs rethinking, not a second color.

## Typography

**Body Font:** Archivo (with `ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif`)
**Mono Font:** IBM Plex Mono (with `ui-monospace, 'SFMono-Regular', Menlo, monospace`)

**Character:** Archivo carries narrative/marketing copy; IBM Plex Mono is reserved for anything that
reads as data or system output (labels, timestamps, order/status strings) — this is what gives the
"control room" character rather than a generic marketing-site feel.

### Named Rules
**The Mono-Means-Data Rule.** If a string on the page is a label, a timestamp, an identifier, or a
status word, it's mono. If it's a sentence a human wrote, it's Archivo. Don't use mono for decorative
effect on prose.

## Layout

Not yet fully catalogued from source — this section needs a follow-up scan against the actual JSX
components (`website/src/*.jsx`) for grid/breakpoint/spacing rhythm before it can be treated as
normative. Known from CSS: the page uses both light-paper and dark-navy full-bleed sections
(a deliberate contrast device, consistent with the Design Constitution's demand for one strong real
interaction over generic template rhythm) — see the Page Theme note under Do's and Don'ts.

## Elevation & Depth

Shadows are used, always tinted to ink or cyan — never pure black. Two families observed:

### Shadow Vocabulary
- **Resting card shadow** (`0 28px 90px rgba(8, 35, 61, 0.14)`, the `--shadow` token): soft, wide,
  ink-tinted. Used for elevated cards/panels at rest.
- **Hover/active glow** (e.g. `0 34px 110px rgba(17, 198, 220, 0.22)`): cyan-tinted, appears on
  hover or to mark a live/successful state — not applied at rest.

### Named Rules
**The Tinted-Shadow Rule.** No pure-black drop shadows. Ink-tinted at rest, cyan-tinted only when
marking a live or interactive state.

## Shapes

No single fixed corner-radius scale — radii range roughly 14-24px on cards/panels, full pill
(`999px`) on buttons and status badges, and perfect circles (`50%`) on avatars, dots, and status
indicators. This is a soft, rounded system throughout (no sharp/brutalist corners observed). A
follow-up pass should confirm whether card radius should be tightened to a strict 2-3 step scale
(the `design-taste` skill's Shape Consistency Lock calls for one locked scale — this file should be
updated once that's confirmed rather than left to drift).

## Components

Lighter first pass — confirm against actual components before treating as exhaustive.

### Buttons
- **Shape:** full pill (`999px`).
- **Hover/Active:** `transform` + `box-shadow` transition (`180ms ease`), shadow deepens and can
  shift toward the cyan-tinted glow.

### Cards / Panels
- **Corner style:** 14-24px depending on panel size (larger panels get larger radius).
- **Background:** white or paper-tint on light sections; deep-navy-2 on dark sections.
- **Shadow strategy:** see Elevation & Depth — ink-tinted at rest, cyan glow on hover/live state.

### Status / Live Indicators
- **Style:** small circular dots or pill badges, cyan, often with a `box-shadow` glow
  (`0 0 18-24px rgba(17, 198, 220, ...)`) to read as "live."

## Do's and Don'ts

### Do:
- **Do** keep cyan as the only saturated accent color across the whole surface being shipped.
- **Do** use mono type for anything that reads as data (labels, timestamps, status strings).
- **Do** tint every shadow to ink (resting) or cyan (hover/live) — never pure black.
- **Do** preserve the wordmark and this palette through any redesign (CLAUDE.md Design Constitution).

### Don't:
- **Don't** introduce a second accent color without a documented reason.
- **Don't** use pure `#000000` or pure white as a page background.
- **Don't** make the site look like a generic SaaS dashboard, catalogue tool, or chatbot UI — see
  `PRODUCT.md`'s Positioning section and CLAUDE.md's Design Constitution.
- **Don't** treat this file as exhaustive for Layout/Components — re-scan against the real JSX before
  relying on those two sections for a pixel-accurate rebuild.
