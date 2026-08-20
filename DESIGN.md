---
name: TicketAI
description: AI-powered internal helpdesk where validated answers compound into institutional knowledge — a calm expert workspace with emerald as the only accent.
colors:
  emerald-action: "#059669"
  emerald-signal: "#10b981"
  emerald-vivid: "#2FE272"
  emerald-deep: "#168B46"
  surface-base: "oklch(1 0 0)"
  surface-page: "#f9fafb"
  surface-muted: "oklch(0.97 0 0)"
  surface-void: "oklch(0.145 0 0)"
  surface-elevated-dark: "oklch(0.205 0 0)"
  ink: "oklch(0.145 0 0)"
  ink-mid: "oklch(0.556 0 0)"
  ink-dim: "oklch(0.708 0 0)"
  rule: "oklch(0.922 0 0)"
  rule-dark: "oklch(1 0 0 / 10%)"
  danger: "oklch(0.577 0.245 27.325)"
  status-blue: "#3b82f6"
  status-amber: "#f59e0b"
typography:
  display:
    fontFamily: "'Geist Variable', sans-serif"
    fontSize: "clamp(1.75rem, 3vw, 2rem)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "'Geist Variable', sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  title:
    fontFamily: "'Geist Variable', sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.005em"
  body:
    fontFamily: "'Geist Variable', sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "'Geist Variable', sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0.06em"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "14px"
  2xl: "18px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.emerald-action}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-primary-hover:
    backgroundColor: "#047857"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-mid}"
    rounded: "{rounded.md}"
    padding: "6px 6px"
  chip-emerald:
    backgroundColor: "#ecfdf5"
    textColor: "#065f46"
    rounded: "{rounded.full}"
    padding: "2px 10px"
  chip-blue:
    backgroundColor: "#eff6ff"
    textColor: "#1d4ed8"
    rounded: "{rounded.full}"
    padding: "2px 10px"
  chip-danger:
    backgroundColor: "#fef2f2"
    textColor: "#dc2626"
    rounded: "{rounded.full}"
    padding: "2px 10px"
  glass-card:
    backgroundColor: "rgba(255,255,255,0.76)"
    rounded: "{rounded.xl}"
    padding: "{spacing.md}"
---

# Design System: TicketAI

## Overview

**Creative North Star: "The Expert's Workshop"**

TicketAI is a professional tool that earns its invisibility. The interface is a neutral membrane between domain experts and their work — structured, unhurried, consistently dense without feeling crowded. Every primary aesthetic decision (Geist's geometric precision, the layered glass hierarchy, the single emerald accent) serves one purpose: keeping the expert focused on the ticket, not the interface itself.

The palette is deliberately restrained. Zinc-gray neutrals carry 90% of the screen; emerald enters only where it signals actionability or resolution — primary buttons, active navigation items, and validated-answer badges. This rarity is the point: when you see green, something is done or requires your action. Every other hue is strictly semantic (blue = in-progress, red = rejected/alert, amber = count badges).

Glass-morphism is structural rather than decorative. There is no animated background — the Aurora WebGL component was removed for legibility. Cards float above a clean `#f9fafb` page background (`#0d0d0d` dark) via `backdrop-filter` blur, creating clear depth hierarchy without atmospheric distraction.

**Key Characteristics:**
- Single-accent palette — emerald only, deployed with surgical precision
- Glass as a structural depth signal, not an aesthetic statement
- Geist Variable — one geometric family for all hierarchy levels
- 56px chrome (sidebar + navbar) maximizes vertical space for content
- Semantic color system: emerald = validated/action · blue = processing · red = error · amber = count

## Colors

A near-achromatic base with one living accent: emerald. The system works by contrast of presence — most of the screen is gray, so a single green element commands full attention.

### Primary

- **Verdigris Action** (`#059669`): The primary action color. Filled buttons, active nav item text/background, focus rings (`ring-emerald-500`), validated/canonical status chip fills. The color that reads "this is done" or "do this now."
- **Signal Mid** (`#10b981`): Softer emerald for icon tints, trend chip fills (`bg-emerald-50`), positive chart accents. Supports Verdigris Action without competing.
- **Electric Lime** (`#2FE272`): Reserved exclusively for the login page CTA gradient endpoint and robot mascot animations. Does not appear in the authenticated app shell — its neon vibrancy would overwhelm the operational context.
- **Forest Anchor** (`#168B46`): Login brand panel fill and login CTA gradient origin. Does not cross into the app shell.

### Neutral

- **Cloud Base** (`oklch(1 0 0)` / `#ffffff`): Sidebar, navbar, and modal backgrounds in light mode. The structural chrome layer.
- **Ash Page** (`#f9fafb`): `gray-50`. Main content area background — one perceptible step below Cloud Base so glass-card surfaces read as elevated.
- **Frost Muted** (`oklch(0.97 0 0)`): Secondary surfaces, skeleton loader fills.
- **Void** (`oklch(0.145 0 0)` / `#111113`): Dark-mode chrome (sidebar, navbar).
- **Card Dark** (`oklch(0.205 0 0)` / `#141416`): Dark-mode modal backgrounds. One step above Void.
- **Ink Primary** (`oklch(0.145 0 0)`): Body text in light mode.
- **Ink Mid** (`oklch(0.556 0 0)`): Secondary text, icon fills, placeholder text.
- **Ink Dim** (`oklch(0.708 0 0)`): Tertiary text — timestamps, metadata (dark mode foreground).
- **Rule Default** (`oklch(0.922 0 0)` / `#e5e7eb`): Borders and dividers (light). Dark: `oklch(1 0 0 / 10%)`.

### Semantic Status

- **Processing Blue** (`#3b82f6`): In-progress job states, pending-review badges. Cool neutral — informative, not urgent.
- **Alert Amber** (`#f59e0b`): Count badge fills on nav items; SUGGESTION-branch answer chips. Never used for body text.
- **Danger Red** (`oklch(0.577 0.245 27.325)`): Rejected-answer chips, error notifications, alert dot indicators.
- **Sky** (`#0ea5e9`): "Nouvelle" ticket status chip; processing/EN_COURS states in ticket tracking. A step lighter than Processing Blue — signals "new and unread" rather than "actively in progress."
- **Purple** (`#a855f7`): "Hors domaine" ticket chips — tickets that landed outside any managed domain. Used only for this single, exceptional state.
- **Violet** (`#7c3aed`): "Assigné" ticket chips; RAG-sourced answer source labels. Distinct from purple — slightly warmer, indicates explicit assignment.

**The Rarity Rule.** Emerald appears on at most 10–15% of any given screen. Its signal value depends entirely on scarcity. Never use it for decorative borders, hover effects unrelated to validation, or any non-action context.

## Typography

**App Font:** Geist Variable (`@fontsource-variable/geist`), `system-ui, sans-serif` fallback.  
**Login Exception:** Space Grotesk (login form and brand panel); JetBrains Mono (uppercase spaced tagline). These do not enter the authenticated interface.

**Character:** Geist is geometric without austerity. Its variable weight axis lets one family carry the full hierarchy from 400-weight body copy to 700-weight display heads without optical friction. Slight negative tracking at larger sizes — down to `–0.02em` at display level — keeps headings tight and purposeful, matching the density philosophy.

### Hierarchy

- **Display** (700, `clamp(1.75rem, 3vw, 2rem)`, lh 1.2, ls –0.02em): Login page headline only. The authenticated shell rarely uses this level — it leads with section headings.
- **Headline** (600, 1.125rem / 18px, lh 1.3, ls –0.01em): Section headings, modal titles, tab-level headings.
- **Title** (600, 0.9375rem / 15px, lh 1.4, ls –0.005em): Sidebar wordmark, stat card values, ticket subject lines.
- **Body** (400, 0.875rem / 14px, lh 1.5): All running copy, table cells, form fields, dropdown items. The default text size for the operational context.
- **Label** (500, 0.6875rem / 11px, lh 1, ls 0.06em, UPPERCASE): Sidebar section group headers, stat card metric titles, status chip text.

**The Single Family Rule.** Geist Variable is the only typeface in the authenticated shell. Space Grotesk and JetBrains Mono are login-page exceptions and must not cross that boundary.

## Layout

The shell is a fixed-viewport composition. Sidebar and navbar form a permanent chrome layer; the main content region scrolls independently inside its own overflow container.

- **Sidebar:** Fixed left — 56px (3.5rem) collapsed / 224px (14rem) expanded. `transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]`. Labels dissolve via `opacity`/`width` on collapse.
- **Navbar:** Fixed top, 56px. Content scrolls below via `padding-top: 56px`.
- **Content region:** `position: absolute; inset: 0; padding-top: 56px; overflow-y: auto` — each page scrolls its own stack independently.
- **Page inset:** `p-6` (24px) is standard. Dense list views may use `p-4`.
- **Max-width containers:** Modals `max-w-xl` (512px); forms `max-w-3xl` (768px). Dashboards and lists fill available width.
- **Dashboard grid:** 4-column at `xl`, 2-column at `sm`. Gap: `gap-4` (16px).
- **Spacing rhythm:** 4px base grid. Component gaps: `gap-2`–`gap-4` (8–16px). Section separations: `gap-6` (24px) or border dividers.
- **Density stance:** Cards at `p-4` (16px) keep more data visible. Dashboards are information-dense by design.

## Elevation & Depth

Depth is conveyed through two discrete mechanisms: **glass translucency** for card-level surfaces and **solid opaque backgrounds** for chrome and dialogs. There is no animated layer — Aurora was removed. Glass floats over a clean `#f9fafb` (light) or `#0d0d0d` (dark) background.

### Shadow Vocabulary

- **Glass Card** (`glass-card` class): `backdrop-filter: blur(20px) saturate(1.5) brightness(1.02)`. Background: `rgba(255,255,255,0.76)` light / `rgba(255,255,255,0.11)` dark. Highlights: `inset 0 1px 0 rgba(255,255,255,0.9)` top + `0 8px 32px rgba(17,17,26,0.07)` ambient diffuse. The primary surface token — used on all dashboard cards, stat cards, notification panels, admin cards.
- **Modal Dialog**: Non-glass. `shadow-2xl` over solid white / `#141416` backgrounds. Scrim: `bg-gray-900/25` light / `bg-black/60` dark.
- **Focus Ring**: `ring-2 ring-emerald-500 ring-offset-1` — always Verdigris Action. An accessibility signal, not a shadow.
- **Interactive card lift**: `hover:shadow-md transition-shadow` on a small number of interactive cards (e.g., HorsDomaineCard). Rare.

**The Glass-Is-Structural Rule.** Apply `glass-card` only to card-level containers that group a discrete unit of information. Nav elements, form fields, tooltips, and table rows are not cards.

**The Flat-Chrome Rule.** Sidebar and navbar use solid backgrounds (`bg-white dark:bg-[#111113]`), not glass. Chrome always recedes behind content.

## Shapes

All corners are curved. Nothing is square; nothing pill-shaped except badges and dots.

- **Nav items / Buttons / Icon buttons:** `rounded-md` (8px) — compact and decisive.
- **Icon containers / Inline chips:** `rounded-lg` (10px) — marginally softer for non-interactive wrappers.
- **Compact cards (stat cards, row cards):** `rounded-xl` (14px) — the lightweight card signature.
- **Large dashboard cards (charts, heatmap, satisfaction, notification panel):** `rounded-2xl` (18px) — larger-footprint containers.
- **Modals / Dialogs:** `rounded-2xl` (18px) — overlays share the radius of large cards.
- **Status badges / Count chips / Avatars:** `rounded-full` — pills and circles signal semantic, non-interactive labels.

**The Radius Ladder Rule.** Use `rounded-md` for interactive actions, `rounded-xl` for compact cards, `rounded-2xl` for large cards and dialogs. A button should never be rounder than the card it lives inside.

## Components

### Buttons

Dense and immediate — the primary button states its intent without theatrical effects.

- **Shape:** `rounded-md` (8px)
- **Primary:** `bg-emerald-600 hover:bg-emerald-700 text-white`, `px-3 py-1.5 text-sm font-medium`. Internal icon: 14px, `strokeWidth 2.2`, `gap-1.5`.
- **Hover:** `bg-emerald-700` — one step darker. No transform, no shadow lift. `transition-colors duration-150`.
- **Focus:** `focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1`.
- **Ghost / Icon button:** `text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/[0.06] rounded-md p-1.5`. Used for theme toggle, logout, close, secondary icon actions.
- **Login CTA (exception):** `background: linear-gradient(100deg, #168B46, #2FE272); box-shadow: 0 8px 24px -8px rgba(47,226,114,.6)`. Gradient fills and glow shadows are confined to the login page only.

### Status Chips

The primary semantic layer — carry the truth about every ticket and response.

- **Anatomy:** `inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border` with a leading filled dot (`w-1.5 h-1.5 rounded-full bg-current`).
- **Emerald** (`bg-emerald-50 text-emerald-700 border-emerald-200` / dark `bg-emerald-500/10 text-emerald-300 border-emerald-500/20`): Validated, canonical, answered.
- **Blue** (`bg-blue-50 text-blue-600 border-blue-200` / dark `bg-blue-500/10 text-blue-300 border-blue-500/20`): In-progress, processing. Dot uses `animate-pulse`.
- **Sky** (`bg-sky-50 text-sky-700 border-sky-200` / dark `bg-sky-500/10 text-sky-300 border-sky-500/20`): New/unread ticket status ("Nouvelle"), processing in TicketTracking.
- **Amber** (`bg-amber-50 text-amber-700 border-amber-200` / dark `bg-yellow-500/10 text-yellow-300 border-yellow-500/20`): SUGGESTION-branch answers — reusing a validated answer that still needs review.
- **Purple** (`bg-purple-50 text-purple-700 border-purple-200` / dark `bg-purple-500/10 text-purple-300 border-purple-500/20`): Out-of-domain tickets ("Hors domaine").
- **Violet** (`bg-violet-50 text-violet-700 border-violet-200` / dark `bg-violet-500/10 text-violet-300 border-violet-500/20`): Assigned tickets ("Assigné"), RAG-sourced answer labels.
- **Red** (`bg-red-50 text-red-600 border-red-200`): Rejected.
- **Gray** (`bg-gray-100 text-gray-500 border-gray-200` / dark `bg-white/10 text-gray-400 border-white/10`): Closed, archived.

### Cards / Containers

All card surfaces use `glass-card`. Two size variants in practice:

- **Compact card** (`glass-card rounded-xl p-4`): StatCard, HorsDomaineCard, compact admin cards.
- **Large card** (`glass-card rounded-2xl p-5`): Charts, heatmap, satisfaction, recent-docs, notification panel.
- **Background:** `rgba(255,255,255,0.76)` light (effectively opaque on `#f9fafb`), `rgba(255,255,255,0.11)` dark.
- **Border:** `1px solid rgba(255,255,255,0.55)` light / `rgba(255,255,255,0.15)` dark.
- **Skeleton state:** `animate-pulse` with `bg-gray-200 dark:bg-white/10` fills inside the same `glass-card` shell.

### Inputs / Fields

- **Style:** 1px solid border, `rounded-lg` or `border-radius: 11px` (login). Solid white background.
- **Focus:** `ring-2 ring-emerald-500` in the app shell. Login: `border-color: #2FE272; box-shadow: 0 0 0 3px rgba(47,226,114,.18)`.
- **Placeholder:** `text-gray-400`.
- **Font:** Geist Variable 14px body throughout the app shell.

### Navigation

- **Shell:** `<aside>` fixed left, solid `bg-white dark:bg-[#111113]`, `border-r border-gray-200 dark:border-[#1f1f1f]`.
- **Section labels:** `text-xs font-semibold tracking-[0.06em] uppercase text-gray-400 dark:text-gray-600 px-2 pt-4 pb-1`.
- **Nav items:** `rounded-md text-sm`, icon `15px / strokeWidth 1.7`, `gap-2.5`. Default: `text-gray-600 dark:text-gray-400`. Hover: `bg-gray-100 dark:bg-white/[0.05] text-gray-900 dark:text-gray-200`. Active: `bg-emerald-50 dark:bg-emerald-500/[0.08] text-emerald-700 dark:text-emerald-400 font-medium`.
- **Badge indicators:** Boolean dot — `w-1.5 h-1.5 rounded-full bg-red-500` at `-top-0.5 -right-0.5`. Count chip — `bg-amber-500 text-white text-[9px] min-w-[1rem] rounded-full tabular-nums`.
- **Collapse:** `transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]`. Labels fade via `opacity`/`width`.

### Modal

Two-layer: scrim behind, dialog in front.

- **Scrim:** `fixed inset-0 bg-gray-900/25 dark:bg-black/60 cursor-default`, click-to-dismiss.
- **Dialog:** `rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-white/10 dark:bg-[#141416]`. Max height `86vh`.
- **Anatomy:** fixed `<header>` with `border-b`, scrollable `<div>` (`overflow-y-auto min-h-0 flex-1`), optional fixed `<footer>` with `border-t`.
- **Eyebrow:** `text-[11px] font-semibold uppercase tracking-wider text-gray-400` above title.
- **Dismiss:** Escape key + scrim click + explicit ✕ ghost icon button.

### User Avatar

Generated SVG — no asset required per user.

- **Shape:** Circle, 36px default.
- **Color:** HSL derived from name hash — stable and unique per user. `hsl(${hue} 55% 88%)` background, `hsl(${hue} 45% 32%)` text, `hsl(${hue} 40% 78%)` ring stroke.
- **Structure:** Colored circle + ghost silhouette shapes (low opacity) + uppercase initial + 1.5px outer ring.
- **Photo variant:** `rounded-full object-cover ring-2 ring-white/60 dark:ring-white/10`.

## Do's and Don'ts

### Do:
- **Do** use `glass-card rounded-xl p-4` for compact cards and `glass-card rounded-2xl p-5` for large dashboard cards. These two sizes are the full card vocabulary.
- **Do** deploy emerald exclusively on: primary action buttons, active nav items, validated/canonical status chips, and focus rings.
- **Do** use `text-xs font-semibold tracking-[0.06em] uppercase text-gray-400` for all sidebar section labels and stat card metric titles.
- **Do** use `transition-colors duration-150` on every interactive color change; `duration-300` only for sidebar width collapse.
- **Do** keep icons at 14–17px with `strokeWidth 1.7–2.2`. Small and precise — functional signals, not decorative glyphs.
- **Do** use `rounded-full` only for pills (status chips), count badges, and circles (avatars, dots).
- **Do** provide dark variants (`dark:`) for every color choice — dark mode is first-class.

### Don't:
- **Don't** use the login gradient (`linear-gradient(100deg, #168B46, #2FE272)`) or its emerald glow shadow inside the authenticated shell.
- **Don't** render the Aurora WebGL component — removed for legibility.
- **Don't** apply `glass-card` to nav elements, table rows, form fields, or tooltips. Glass signals a card-level container.
- **Don't** apply `rounded-2xl` to buttons or inline nav items. That radius is reserved for large cards and dialogs.
- **Don't** use blue as an action or brand color — blue appears only in the "in-progress / processing" semantic state.
- **Don't** place more than one filled `bg-emerald-600` button in a single view region. Ghost and icon variants absorb secondary actions.
- **Don't** add extra `shadow-*` to `glass-card` containers — the glass token already includes its shadow vocabulary.
