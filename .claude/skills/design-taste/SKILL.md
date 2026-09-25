---
name: design-taste
description: Anti-slop checklist for Sanocea frontend work (Command Centre, WhatsApp demo, website). Load after the visual proposal is approved under the design-approval gate in CLAUDE.md, and again as a pre-flight check before showing the final screenshot. Not a substitute for frontend-design-preview / frontend-visual-qa — this is the taste layer that sits inside implementation.
---

# Sanocea Design Taste

**Provenance:** this skill was written by reading `skills/taste-skill/SKILL.md` from
[Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) (MIT licensed) per the OSS-first rule
in `CLAUDE.md`. Decision made: **C — learn semantics/pattern only**. No code was copied; the rules
below are rewritten for Sanocea's actual stack (React 19 + Vite + `framer-motion` + plain CSS — no
Next.js, no Tailwind, no GSAP, no shadcn/Radix/Carbon/Fluent) and filtered down to what's stack-agnostic
and relevant to Sanocea's own Design Constitution. The upstream skill's design-system matrix, Block
Library schema, and framework-specific code skeletons (RSC, Tailwind utilities, GSAP ScrollTrigger,
shadcn install commands) were dropped — they don't apply here and would only rot.

This does not reopen the OSS-first exclusion list; `taste-skill` was never a dependency Sanocea needed
to keep, only a pattern worth learning once.

**Second provenance note:** the `PRODUCT.md` / `DESIGN.md` convention referenced below was learned the
same way from [pbakaus/impeccable](https://github.com/pbakaus/impeccable) (Apache-2.0). Impeccable
itself was **not** installed — its skill downloads and runs an opaque compiled binary via auto-triggered
edit hooks, which conflicts with the Linux-portability and deterministic-first invariants in CLAUDE.md.
Its markdown reference docs (`init.md`, `document.md`) were readable and MIT/Apache-compatible to learn
from; only the file-shape pattern was kept.

## PRODUCT.md and DESIGN.md

Sanocea now has both, at the repo root: `PRODUCT.md` (durable product truth — users, purpose,
positioning, constraints, evidence; doesn't change per-task) and `DESIGN.md` (the visual design system
— colors, typography, layout, elevation, shapes, components, do's/don'ts; follows the open
[design.md spec](https://github.com/google-labs-code/design.md)). Read both before starting non-trivial
frontend work, alongside this checklist. `DESIGN.md`'s Layout and Components sections are a first-pass
scan and should be tightened against the real JSX (`website/src/*.jsx`) rather than trusted blindly —
see the note at the top of that file. Update `DESIGN.md` when a design-approval-gate preview changes an
established token or pattern; update `PRODUCT.md` only when product truth itself changes, never for a
single task's visual decisions.

## Backend counterpart

For backend/Python quality (this repo's actual backend stack — see `PRODUCT.md`), Sanocea installed a
curated subset of [trailofbits/skills](https://github.com/trailofbits/skills) (CC-BY-SA-4.0) directly
rather than re-deriving them — Decision **A, reuse directly**, since they're markdown-only skills with
no opaque binaries or auto-hooks, from a specialist security firm, actively maintained: `static-analysis`,
`modern-python`, `differential-review`, `supply-chain-risk-auditor`, `insecure-defaults`,
`post-patch-validation`, `sharp-edges`, `property-based-testing`. The marketplace has ~40 more plugins
(mostly blockchain/C/C++/Rust-specific) that were deliberately skipped as not matching this repo's stack.

## Why this exists

CLAUDE.md's Design Constitution already says Sanocea must not look like "a generic SaaS platform" or
"a generic inventory dashboard." Most of what makes AI-generated UI look generic has names — this
skill is that vocabulary, kept short enough to actually run as a checklist before shipping.

## Relationship to the design-approval gate

This skill does not replace any step in CLAUDE.md's `REQUEST → PREVIEW → APPROVE → IMPLEMENT → QA` gate.
Use it at two points:
- While building the approved preview, to avoid reintroducing generic patterns the preview didn't have.
- As a mechanical pre-flight pass (Section 3 below) right before the "RENDER IN BROWSER, SCREENSHOT"
  step, alongside `frontend-visual-qa`.

## 1. AI tells to avoid by default

Override any of these only when the *approved* design preview explicitly calls for it — this list
exists to stop silent drift back to generic defaults during implementation, not to override an
approved decision.

**Copy**
- No em dash (`—` or `–` as a separator). Use a period, comma, or hyphen. This is the single
  most-recognizable LLM tell — treat it as zero-tolerance, not "sparingly."
- No filler verbs: "elevate," "seamless," "unleash," "next-gen," "revolutionize."
- No generic placeholder names ("John Doe," "Acme," "SmartFlow") in demo/seed content — Sanocea's own
  honesty rule already requires real or clearly-labeled representative data, so this is enforcement of
  something CLAUDE.md already asks for.
- No fake-precise numbers (`99.99%`, exact round figures) unless they trace to real seeded/live data
  per the Evidence-beats-claims principle already in CLAUDE.md.
- Re-read every visible string before calling it done: grammatically broken fragments, unclear
  referents, and "trying to sound clever" copy all get rewritten to something plain.

**Layout**
- No three-equal-column feature cards as a default. If a row of cards is the right call, vary sizes or
  break the symmetry — don't reach for the generic grid.
- No section-numbering eyebrows (`00 / INDEX`, `001 · Capabilities`). Name the topic in plain language.
- Max one eyebrow-style micro-label per three sections. If the previous section had one, the next
  shouldn't.
- No more than two consecutive sections using the same layout family (e.g. two image+text splits in a
  row is the ceiling — the third is a fail).
- No decorative dots, scroll cues ("Scroll ↓"), version-stamp footers (`v1.4.2`), or locale/weather
  strips unless the content is genuinely about that (a real build number on an internal tool, a real
  timezone-distributed feature).
- No `border-t`/`border-b` on every row of a long list — that's the lazy default for spec/data lists.
  Group into 2-3 visual chunks or use cards instead.

**Color & type**
- Max one accent color per surface, used identically everywhere it appears on that surface — don't let
  a different CTA color sneak in three sections down.
- Don't default to a random serif "because it feels premium." Sanocea already has a brand
  wordmark/palette per the Design Constitution — stay inside it rather than reaching for a trend font.
- No AI-purple gradient glows as a default accent treatment.

**Motion (`framer-motion`, this repo's actual library)**
- Every animation must be justifiable in one sentence: hierarchy, sequence/storytelling, feedback, or
  state change. "It looked cool" is not a reason — this echoes CLAUDE.md's own "motion should reinforce
  hierarchy or a real state change, not exist for its own sake" line almost exactly.
- Prefer `whileInView` / `useScroll` from `framer-motion` over hand-rolled `window.addEventListener('scroll', ...)` or scroll position kept in `useState` — both are jank-prone and unnecessary here.
- Anything above a subtle level of motion should degrade cleanly for `prefers-reduced-motion`.
- Don't add a second continuous/looping animation to a page that already has one — most sections should
  be still.

## 2. Where Sanocea already overrides the generic default

Don't "fix" these — they're deliberate per CLAUDE.md, not slop:
- Brand palette and wordmark are locked (Design Constitution) — the upstream skill's "rotate palettes
  to avoid repetition" advice does not apply to Sanocea's core brand color.
- The product surfaces are exactly two: Command Centre and WhatsApp/chat. Don't introduce a third
  generic "dashboard" pattern to solve a UI problem — solve it inside one of the two.
- Motion is intentionally restrained per the Design Constitution ("one strong, real interaction beats
  many marketing cards or an animated sequence").

## 3. Pre-flight checklist

Run this before the final screenshot in the design-approval gate's QA step. Anything unchecked gets
fixed or gets flagged to the user as an explicit deviation — never shipped silently.

- [ ] Zero em dashes anywhere in visible copy (headings, labels, body, alt text).
- [ ] Every visible string re-read for grammar/clarity; nothing that sounds like an AI trying to be
      clever.
- [ ] All numbers/claims shown trace to real seeded or live data, or are explicitly labeled as
      sample/representative.
- [ ] One accent color, used consistently across the whole surface being shipped.
- [ ] No two adjacent-in-scroll sections share a layout family three times in a row.
- [ ] No section-numbering eyebrows, scroll cues, decorative dots, or version-stamp footers unless they
      carry real information.
- [ ] Every animation can be justified in one sentence (hierarchy / sequence / feedback / state change).
- [ ] `prefers-reduced-motion` degrades cleanly for anything beyond a subtle transition.
- [ ] Rendered in-browser and screenshotted (per CLAUDE.md's gate) — not just reviewed as code.
- [ ] Checked against the *approved* preview — any deviation is either fixed or explicitly re-approved
      by the user, never silently reinterpreted as the new baseline.
