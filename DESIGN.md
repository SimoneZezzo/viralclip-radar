---
version: 1
name: ViralClip Radar
description: "Dark, dense analyst workspace for ranking Twitch clips. Green-tinted near-black canvas (#101110), a four-step surface ladder with hairline borders, light ink (#eff1ea) and one chromatic accent: radar lime (#d1f95b), reserved for the brand mark, the score, the primary action and focus. Structure adapted from the Linear DESIGN.md in VoltAgent/awesome-design-md; palette, brand and product rules are ViralClip Radar's own."

colors:
  accent: "#d1f95b"
  accent-hover: "#e0ff84"
  on-accent: "#182309"
  accent-line: "#7d9839"
  ink: "#eff1ea"
  ink-muted: "#dbe0d3"
  ink-subtle: "#a4ab9e"
  canvas: "#101110"
  chrome: "#121411"
  surface-1: "#171916"
  surface-2: "#21251b"
  surface-3: "#242b1b"
  control: "#262b23"
  hairline: "#2d312b"
  hairline-strong: "#40483a"
  hairline-accent: "#505e31"
  danger: "#ffb999"

typography:
  display: { fontSize: "clamp(2.3rem, 6vw, 4rem)", fontWeight: 700, lineHeight: 1.0, letterSpacing: "-0.075em" }
  panel-title: { fontSize: 1.06rem, fontWeight: 600, letterSpacing: "-0.025em" }
  clip-title: { fontSize: 1.14rem, fontWeight: 600, letterSpacing: "-0.035em" }
  body: { fontSize: 0.98rem, fontWeight: 400, lineHeight: 1.45 }
  row: { fontSize: 0.9rem, fontWeight: 600 }
  meta: { fontSize: 0.76rem, fontWeight: 400, lineHeight: 1.4 }
  button: { fontSize: 0.8rem, fontWeight: 700 }
  mono: { fontFamily: "IBM Plex Mono, Consolas, monospace", fontSize: 0.74rem }

rounded: { xs: 4px, sm: 5px, md: 8px, lg: 12px, pill: 20px, full: 50% }
spacing: { base: 4px, xs: 8px, sm: 12px, md: 16px, lg: 24px, xl: 48px }
---

# ViralClip Radar design system

Read this file only for frontend or UI work. The current UI is the local
portfolio demo: a React + TypeScript app in `web/` (Vite, Tailwind CSS,
TanStack Query) built to `web/dist` and served by the FastAPI app in
`src/viralclip/demo.py`. Future UIs, such as the M4 dashboard, follow the
same rules.

## Implementation

- Tokens live once, in the `@theme` block of `web/src/index.css`, as Tailwind
  theme variables (`--color-accent`, `--color-surface-1`, ...). Use the
  generated utilities (`bg-surface-1`, `text-ink-subtle`, `border-hairline`)
  rather than raw hex values.
- Breakpoints are theme variables used with `max-*` variants: `max-md` below
  851px, `max-sm` below 666px, `max-xs` below 351px.
- Components: `TopBar`, `Overview`, `RankingPanel`, `ClipDetails` in
  `web/src/components/`. Shared button styles are the `button-primary` and
  `button-secondary` component classes.
- Checks: Vitest and Testing Library for behavior and truthful states;
  Playwright against the built demo for console errors (including CSP
  violations) and no horizontal scroll at 1264, 850, 665 and 320px.

## Product identity

ViralClip Radar is a research instrument, not a marketing site. A clipper or
editor opens it to answer one question: *which clips should I edit first?*
The UI must read as precise, honest and calm.

- **The ranking is the protagonist.** Linear's pages lead with product
  screenshots; ours leads with the ranked clip list and the selected clip.
  Chrome stays minimal so the data does the work.
- **Honesty beats polish.** Synthetic data, baselines, missing scores and
  unavailable actions are always visible and never styled to look like
  something else (see [Truthful states](#truthful-states)).
- **Brand.** Wordmark "ViralClip Radar" with "Radar" in accent, beside the
  concentric-ring radar mark with a lime blip. Keep both as they are.

## Principles adapted from Linear

| Linear principle | ViralClip Radar adaptation |
| --- | --- |
| Near-black canvas with faint tint | `canvas` #101110 with a faint green tint, never `#000` |
| One scarce chromatic accent | Radar lime, never lavender; no second accent |
| Surface ladder plus hairlines instead of shadows | `canvas` → `chrome` → `surface-1` → `surface-2` → `surface-3`; 1px borders; no drop shadows |
| Negative tracking on display, neutral body | Display −0.075em, titles −0.025 to −0.035em, body and meta 0 |
| Mono only in code contexts | Mono only for record values: IDs, versions, UTC timestamps |
| 8px controls, 12px cards | 7–8px buttons and inputs, 12px panels, pills only for status tags |
| No atmospheric gradients or spotlight cards | Same; the only gradient is the legibility scrim on video previews |
| Dense, technical, quiet | Dense rows, tabular numbers, short labels, no hero imagery |

Deliberate differences: Linear's marketing type scale (80px heroes, 96px
section gaps) is too large for a single-screen tool, so ours tops out at 4rem
and uses 12–48px gaps. Linear's lavender is not used anywhere.

## Color

- **Accent (`accent`).** Use only for: brand mark and "Radar", the score
  column, the primary button, the focus ring and the live dot in the demo tag.
  Never as a panel fill, section background or decoration. `accent-hover` is
  the hover state of the primary button. Text on accent uses `on-accent`.
- **Accent-tinted neutrals.** `accent-line`, `hairline-accent` and
  `surface-3` are desaturated accent mixes for the brand ring and the selected
  row. They signal selection, not emphasis.
- **Surfaces.** `canvas` page, `chrome` top bar, `surface-1` panels and the
  overview strip, `surface-2` row hover, `surface-3` selected row and job
  panel, `control` secondary buttons and chips. Lift one step at a time.
- **Text.** `ink` for titles and values, `ink-muted` for secondary emphasis,
  `ink-subtle` for labels, captions and notes. Keep `ink-subtle` at or above
  WCAG AA (4.5:1) on every surface it sits on.
- **Danger.** `danger` for error text only. There is no success green: a
  completed job is stated in words, not color.
- Define colors once as CSS custom properties on `:root`. New hard-coded hex
  values in rules are a smell; add or reuse a token instead.

## Typography

Family: `Geist, "DM Sans", system-ui, sans-serif`, no web-font download (the
demo works offline). Mono: `"IBM Plex Mono", Consolas, monospace`.

| Token | Use |
| --- | --- |
| `display` | Page title only ("Twitch Shortlist") |
| `panel-title` | Panel headings (`h2`) and brand wordmark |
| `clip-title` | Selected clip title (`h3`), wraps with `overflow-wrap: anywhere` |
| `body` | Intro and explanatory text |
| `row` | Clip titles in ranking rows, single line with ellipsis |
| `meta` | Labels, channel names, notes, availability messages |
| `button` | Button labels |
| `mono` | `dd` values in the clip record |

- Every number that can be compared (rank, score, pool size, dates) uses
  `font-variant-numeric: tabular-nums`.
- Weights: 400 body, 600 titles, 700 display, numbers and buttons. The
  current CSS also uses 640 and 740; converge on the scale when editing those
  rules, not in a dedicated restyle.
- Labels are sentence case. No all-caps eyebrows.

## Layout and spacing

- 4px base. Common gaps: 8, 12, 16, 18, 24, 48px. Panel heading 13×17px,
  panel body 7–13px, row 8px.
- Container `.shell`: max 1264px, side gutter `clamp(16px, 4vw, 48px)`.
- Page order: top bar → intro with game picker → overview strip (cutoff,
  method, pool size, pool date) → workspace grid (ranking 1.36fr, selected
  clip 1fr).
- Breakpoints: 850px tightens the row grid; 665px stacks the workspace,
  turns the overview into 2×2 and puts the picker below the title; 350px
  shrinks brand and tag. Minimum supported width 280px, no horizontal scroll.

## Components

- **Top bar.** `chrome` background, bottom hairline, height ≥64px, brand left,
  demo tag right.
- **Demo tag.** Pill with hairline-strong border, accent dot and the text
  "Local demo · Synthetic data". Required whenever data is synthetic.
- **Overview strip.** One `surface-1` card split by vertical hairlines; label
  in `meta`, value in tabular `ink`.
- **Panel.** `surface-1`, 1px `hairline`, 12px radius, heading row with title
  left and a `meta` hint right ("Score / 100"), optional `panel-note` footer.
- **Ranking row.** Full-width button, grid of rank, thumbnail, title and
  channel, score. Hover `surface-2`; selected uses `aria-pressed="true"`,
  `surface-3` and `hairline-accent`. Score in accent; a missing score shows
  "—" in `ink-subtle` via `.is-missing`.
- **Preview.** 16:9 poster, 8px radius, dark scrim at the bottom for the
  tag. The site plays no video.
- **Clip record.** `dl` with `meta` labels left and mono values right inside a
  hairline box: version, score, clip cutoff, clip link.
- **Clip actions.** Primary "Copy clip link"; secondary "Open on Twitch"
  link, disabled with `aria-disabled="true"` and a stated reason when the
  clip has no Twitch page (rendered as a disabled button, since a link
  without `href` is not announced). An "Edit in your own editor" block lists
  external editors as plain links, with no integration.
- **Buttons.** `primary`: accent fill, `on-accent` text, grows to fill the
  row; one per view. `secondary`: `control` fill with `hairline-strong`
  border. Height ≥40px. Disabled at 0.49 opacity with no hover change, and
  always paired with a visible reason.
- **Inputs.** `surface-1` select with a strong border, 8px radius, ≥44px tall.
- **Status line.** `meta` text with `role="status"` and `aria-live="polite"`
  for copy results and link availability.

## Truthful states

These rules come from the product's research invariants and the
[demo review](docs/DEMO_REVIEW.md) and override aesthetics:

- Synthetic data is labeled on the page (demo tag, "Synthetic preview").
  Anything built on synthetic fixtures for M4 carries
  `SYNTHETIC / NOT REAL TWITCH DATA`.
- The method shown in the overview names the ranker: a baseline such as
  `latest_views` is never presented as a model score.
- Missing, unavailable or late data is shown as "—" or a sentence, never as
  zero.
- Scores are relative 1–100 within a pool; the UI shows no view counts and
  does not call scores probabilities before calibration.
- The site handles no media: it shows the clip link and external editors
  only. A disabled link says why, and the card reminds the user to ask the
  creator before publishing.
- Timestamps are UTC and appear in mono in the record.

## Accessibility and interaction

- Visible `:focus-visible` ring: 2px accent, 3px offset, on every control.
- Semantic landmarks and headings; every section is labelled
  (`aria-labelledby` or `aria-label`). Decorative marks get
  `aria-hidden="true"`.
- Touch targets ≥40px for buttons and ≥44px for the select.
- Motion is minimal: state changes are instant color changes. If transitions
  are added, keep them under 150ms and respect `prefers-reduced-motion`.
- Dark only (`color-scheme: dark`). A light theme is out of scope until
  someone asks for it.

## Do and don't

Do:

- Reuse the tokens and classes in `styles.css` before adding new ones.
- Keep one primary action per view and keep the ranking visible on desktop.
- Check the page at 1264px, 850px, 665px and 320px after layout changes.

Don't:

- Add a second accent color, gradients, glows, drop shadows or glassmorphism.
- Fill large areas with lime or use it for non-interactive decoration.
- Load fonts, icons or scripts from a CDN; the demo must run offline.
- Show Twitch media or links beyond the approved metadata workflow, or hide
  a missing permission behind an enabled-looking button.
- Change behavior, API contracts or copy meaning while restyling.

## Provenance

Structure and principles adapted on 2026-11-24 from
`design-md/linear.app/DESIGN.md` in
[VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md).
Token values were extracted from the first demo stylesheet, not
copied from the reference.
