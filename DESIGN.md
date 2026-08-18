---
name: TicketAI
description: Clean, precision-desk helpdesk backoffice — a RAG answer-validation workspace with an opaque neutral chrome and emerald-accent content glass.
colors:
  emerald-primary: "#10b981"
  emerald-deep: "#059669"
  emerald-glow: "#34d399"
  emerald-tint-bg: "#ecfdf5"
  green-active-bg: "#dcfce7"
  green-active-ink: "#15803d"
  ink-heading: "#1f2937"
  ink-strong: "#374151"
  ink-body: "#4b5563"
  ink-muted: "#6b7280"
  ink-faint: "#9ca3af"
  line: "#e5e7eb"
  surface-subtle: "#f9fafb"
  surface-base: "#ffffff"
  night: "#05070f"
  state-info: "#2563eb"
  state-info-bg: "#eff6ff"
  state-warn: "#ca8a04"
  state-warn-bg: "#fefce8"
  state-lock: "#f59e0b"
  state-lock-bg: "#fffbeb"
  state-danger: "#dc2626"
  state-danger-bg: "#fef2f2"
  chart-blue: "#3b82f6"
  chart-blue-dark: "#60a5fa"
  chart-amber: "#f59e0b"
  chart-amber-dark: "#fbbf24"
  chart-violet: "#8b5cf6"
  chart-violet-dark: "#a78bfa"
  chart-teal: "#0d9488"
  chart-teal-dark: "#2dd4bf"
  chart-rose: "#e11d48"
  chart-rose-dark: "#fb7185"
  chart-purple: "#9333ea"
  chart-purple-dark: "#c084fc"
typography:
  page-title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  section-title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "normal"
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "normal"
  eyebrow:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.05em"
  meta:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  sm: "4px"
  lg: "8px"
  xl: "12px"
  2xl: "16px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.emerald-primary}"
    textColor: "{colors.surface-base}"
    rounded: "{rounded.xl}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.emerald-deep}"
    textColor: "{colors.surface-base}"
  button-secondary:
    backgroundColor: "{colors.surface-base}"
    textColor: "{colors.ink-body}"
    rounded: "{rounded.lg}"
    padding: "6px 12px"
  glass-panel:
    backgroundColor: "{colors.surface-base}"
    rounded: "{rounded.2xl}"
    padding: "24px"
  input:
    backgroundColor: "{colors.surface-base}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
  status-pill:
    backgroundColor: "{colors.emerald-tint-bg}"
    textColor: "{colors.emerald-deep}"
    rounded: "{rounded.full}"
    padding: "2px 10px"
  nav-item-active:
    backgroundColor: "{colors.emerald-tint-bg}"
    textColor: "#15803d"
    rounded: "{rounded.lg}"
    padding: "7px 10px"
  chrome-sidebar:
    backgroundColor: "#ffffff"
    darkBackgroundColor: "#111113"
    borderColor: "#e5e7eb"
    darkBorderColor: "#1f1f1f"
    width: "224px"
    collapsedWidth: "56px"
  chrome-topbar:
    backgroundColor: "#ffffff"
    darkBackgroundColor: "#111113"
    borderColor: "#e5e7eb"
    darkBorderColor: "#1f1f1f"
    height: "56px"
  page-background:
    backgroundColor: "#f9fafb"
    darkBackgroundColor: "#0d0d0d"
---

# Design System: TicketAI

## 1. Overview

**Creative North Star: "The Precision Desk"**

TicketAI is a human-in-the-loop workspace where validators review AI-drafted helpdesk answers before they ship. The layout chrome — sidebar, topbar, page background — is opaque, neutral, and razor-clean (Vercel / Linear register): solid white in light mode, near-black `#111113` in dark mode, separated by a single `1px` border. Content panels (cards, modals, tables) use frosted glass (`glass-card`) over the `#f9fafb` / `#0d0d0d` page background, giving depth without distracting chrome.

Emerald is the one true accent — it marks primary actions, the active nav item, canonical answers, and success states. It never appears as decoration. Neutrals carry the text hierarchy; Geist Variable is the typeface throughout.

Density and calm coexist. Tables run wide and compact; forms and detail panels breathe. The tool should feel trustworthy enough that a validator signs off on an answer without second-guessing the interface.

**Key Characteristics:**
- Two-layer material system: opaque chrome (sidebar, topbar) + frosted-glass content panels.
- One accent (emerald): primary actions, active nav, canonical / success, focus rings.
- Geist Variable, fixed rem type scale, single family, tight hierarchy.
- Class-toggled dark mode; sidebar and topbar shift from white to `#111113`.
- Standardized semantic state colors mapped to business statuses.

## 2. Colors

A restrained emerald-on-neutral palette where the only saturated hue is the brand green; every other color is either a gray or a narrow semantic-state signal.

### Primary
- **Emerald Primary** (`#10b981`): The one true accent. Primary buttons, the "Add Ticket" CTA, focus rings (`ring-emerald-500`), and the lightest aurora color stop. Used on a small fraction of any screen.
- **Emerald Deep** (`#059669`): Hover state for every primary button and the darkest aurora stop.
- **Emerald Glow** (`#34d399`): Mid aurora color stop only — the light that rises through the glass.
- **Emerald Tint BG** (`#ecfdf5`): Soft fill behind success/canonical pills and confirmation icons.
- **Green Active BG** (`#dcfce7`) / **Green Active Ink** (`#15803d`): The active navigation item and the table header row. A cooler, flatter green than the accent — deliberately calmer than a button.

### Neutral
- **Ink Heading** (`#1f2937` / gray-800): Page titles (`h1`), strong headings.
- **Ink Strong** (`#374151` / gray-700): Form labels, emphasized values.
- **Ink Body** (`#4b5563` / gray-600): Default body and paragraph text.
- **Ink Muted** (`#6b7280` / gray-500): Secondary meta text, eyebrow labels.
- **Ink Faint** (`#9ca3af` / gray-400): Icons at rest, placeholders, breadcrumb, empty-state text.
- **Line** (`#e5e7eb` / gray-200): Borders and dividers; panels use `gray-200/70` (70% opacity) so the aurora shows through the edge.
- **Surface Subtle** (`#f9fafb` / gray-50): Inset fields, quiet fills inside panels.
- **Surface Base** (`#ffffff`): Panels render as `white/80`–`white/90` — never fully opaque.
- **Chrome BG dark** (`#111113`): Sidebar and topbar background in dark mode.
- **Page BG dark** (`#0d0d0d`): Content area background in dark mode. Dark chrome borders are `#1f1f1f`; dark dividers are `#1a1a1a`.

### State (semantic signals, mapped to business status)
- **Info** (`#2563eb` on `#eff6ff`): Validated (`VALIDÉ`) tickets and answers.
- **Warn** (`#ca8a04` on `#fefce8`): Suggestion (`RÉPONDU`) — reused validated answer, still needs review.
- **Lock** (`#f59e0b` on `#fffbeb`): Ticket locked/checked-out by another validator; read-only banners and the lock chip.
- **Danger** (`#dc2626` on `#fef2f2`): Rejected (`REJETÉ`/`REJETÉE`) answers, form errors.
- Success/Canonical reuses **Emerald** (`emerald-50`/`emerald-600`), tying canonical answers to the brand.

### Named Rules
**The One Emerald Rule.** Emerald is reserved for primary action, current selection, canonical/success state, and focus rings. It is never used as a decorative fill, gradient, or background band. If green appears and it is not one of those four things, it is wrong.

**The Two-Layer Rule.** Chrome surfaces (sidebar, topbar) are opaque and flat. Content surfaces (cards, modals, panels) are frosted glass (`glass-card`). Never apply glassmorphism to chrome; never make content panels opaque solid white.

## 3. Typography

**Display Font:** none — this is a product UI, not a brand surface.
**Body Font:** System sans stack (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`) — Tailwind v4's default `font-sans`.
**Label/Mono Font:** none distinct; keyboard hints (`<kbd>`) use the same sans at `text-xs`.

**Character:** One well-tuned system sans carries every role — headings, labels, body, table data, buttons. No pairing, no display face. Hierarchy comes from size and weight, never from a second family. This is the correct product move: familiar, fast, invisible.

### Hierarchy
- **Page Title** (600, `1.5rem` / text-2xl, line-height 1.2): One per screen — "Tickets", "Besoin d'un renseignement ?". Color `ink-heading`.
- **Section Title** (600, `1.125rem`–`1rem` / text-lg–text-base, 1.3): Panel and card headers — "Dernières questions", "Réponses".
- **Title / Emphasis** (600, `0.875rem` / text-sm): Inline strong values, list-item names.
- **Body** (400, `0.875rem` / text-sm, 1.5): Default text, table cells, paragraph copy. Cap prose panels at 65–75ch.
- **Label** (500, `0.875rem` / text-sm): Form field labels; color `ink-strong`.
- **Eyebrow** (600, `0.75rem` / text-xs, uppercase, `tracking-wide` 0.05em): Panel section markers — "Informations", "Demandeur". Color `ink-muted`.
- **Meta** (400, `0.75rem` / text-xs): Timestamps, pagination counts, hints. Color `ink-faint`.

### Named Rules
**The Fixed-Scale Rule.** Type sizes are fixed rem steps, never `clamp()`/fluid. A validator views at consistent DPI; headings that shrink in a collapsed sidebar look broken, not responsive.

**The Weight-Not-Color Rule.** Emphasis is created with weight (500/600) and the gray ramp, not with the accent. Text is almost never emerald.

## 4. Elevation

Depth comes from two sources: the border between opaque chrome and frosted-glass content panels, and the `glass-card` blur over the `#f9fafb` / `#0d0d0d` page background. There is no deep shadow vocabulary.

### Shadow Vocabulary
- **Panel lift** (`box-shadow: 0 1px 2px 0 rgba(17,24,39,0.05)`): The only structural shadow. Applied to `glass-card` panels. Barely visible by design.
- **Chrome border**: A `1px` `#e5e7eb` / `#1f1f1f` border separates sidebar from content and topbar from main — this is the elevation signal for chrome, not shadow.

### Named Rules
**The No-Chrome-Shadow Rule.** The sidebar and topbar carry no drop shadow — only a `1px` border. Depth inside content surfaces comes from `backdrop-blur` + translucency (`glass-card`), not from heavy shadows. Do not add `shadow-lg` to chrome elements.

## 5. Components

Consistency is absolute: the same button shape, the same panel material, the same pill, screen to screen.

### Buttons
- **Shape:** Rounded (`rounded-xl` 12px for CTAs and detail actions; `rounded-lg` 8px for compact/secondary). Icon buttons are `rounded-lg` squares.
- **Primary:** `bg-emerald-500` → `hover:bg-emerald-600`, white text, `text-sm font-medium`, padding `px-4 py-2`, `transition-colors`. The navbar CTA adds a `lucide` `Plus` icon and `shadow-emerald-200`.
- **Secondary / Ghost:** Transparent-to-`white/80` fill, `border border-gray-200` (dark `border-white/15`), `text-gray-600`, `hover:bg-gray-50` (dark `hover:bg-white/10`).
- **Icon button:** `p-1.5`/`p-2`, `text-gray-400`, `hover:bg-gray-100` (dark `hover:bg-white/10`), `rounded-lg`.
- **Disabled:** `disabled:opacity-40 disabled:cursor-not-allowed`. Loading swaps the leading icon for a spinning `lucide` `Loader2`.
- **Focus:** `focus:ring-2 focus:ring-emerald-500` on inputs and interactive controls.

### Status Pills
- **Style:** `inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border`, with a small `w-1.5 h-1.5 rounded-full bg-current` leading dot.
- **State mapping:** Canonique → emerald; Validée → blue; Suggestion → yellow; Rejetée → red; Nouvelle → blue. Every pill uses the `{bg}-50 / {ink}-600 / {border}-200` light triad and a `{color}-500/10` translucent dark variant.

### Cards / Containers (the Glass Panel)
- **Corner Style:** `rounded-2xl` (16px).
- **Material:** `bg-white/80` (dark `bg-white/5`) + `backdrop-blur-xl`. Never fully opaque.
- **Border:** `border border-gray-200/70` (dark `border-white/10`).
- **Shadow:** `shadow-sm shadow-gray-900/5` — see Elevation.
- **Internal Padding:** `p-5`–`p-6`; sectioned panels use `px-6 py-4` header/footer rows split by `border-gray-100` dividers.

### Inputs / Fields
- **Style:** `border border-gray-200` (or `-300` for prominent textareas), `rounded-lg`/`rounded-xl`, `bg-white` (dark `bg-white/5`), `px-3 py-2`, `text-sm`.
- **Focus:** `focus:outline-none focus:ring-2 focus:ring-emerald-500` — the emerald ring is the universal focus signal.
- **Placeholder:** `placeholder:text-gray-400`. Textareas are `resize-y`.
- **Select:** identical border/radius/focus treatment as text inputs for a single form-control vocabulary.

### Navigation
- **Sidebar:** Opaque aside (`bg-white dark:bg-[#111113]`), `border-r border-gray-200 dark:border-[#1f1f1f]`, collapsible `w-56` ↔ `w-14` with a `duration-300 cubic-bezier(0.4,0,0.2,1)` width transition; labels fade out on collapse. Logo mark stays fixed at `w-7 h-7`; wordmark fades.
- **Nav item (text-sm):** `rounded-md px-2.5 py-[7px] mx-2`. **Active:** `bg-emerald-50 text-emerald-700 font-medium` (dark `bg-emerald-500/[0.08] text-emerald-400`). **Inactive:** `text-gray-600 hover:bg-gray-100 hover:text-gray-900` (dark `text-gray-400 hover:bg-white/[0.05] hover:text-gray-200`). Collapsed icon-only: `w-9 h-9 rounded-md justify-center mx-auto`.
- **Section labels:** `text-xs font-semibold uppercase tracking-[0.06em] text-gray-400`; hidden on collapse.
- **Topbar:** `h-14` opaque bar, `bg-white dark:bg-[#111113]`, `border-b border-gray-200 dark:border-[#1f1f1f]`. Icon buttons use `p-1.5 rounded-md text-gray-500 hover:bg-gray-100`; primary CTA is `bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-3 py-1.5 rounded-md`.
- **SidebarToggle:** `w-5 h-5 rounded-full bg-white dark:bg-[#1c1c1e]`, `border border-gray-200 dark:border-[#2a2a2d]`, `shadow-sm`; positioned at `top-7` at `left-56` / `left-14`.

## 6. Do's and Don'ts

### Do:
- **Do** keep emerald to the sanctioned roles: primary action, active nav, canonical/success state, focus rings. See The One Emerald Rule.
- **Do** keep chrome (sidebar, topbar) fully opaque and flat — no blur, no glass, no translucency.
- **Do** render content panels as frosted glass: `glass-card` (`white/76` + `backdrop-blur-xl` + border) over `#f9fafb` / `#0d0d0d` background.
- **Do** use the emerald focus ring (`focus-visible:ring-2 focus-visible:ring-emerald-500`) on every interactive control.
- **Do** map status to the standardized semantic triad (emerald / blue / yellow / red) and always pair a light and a `/10` dark variant.
- **Do** use fixed rem type sizes (Tailwind's `text-xs` / `text-sm` / `text-base` / `text-lg` / `text-2xl`) and Geist Variable throughout.
- **Do** provide light and dark variants for every color — dark mode is a first-class class-toggled theme.
- **Do** keep transitions to `transition-colors duration-150`; reserve `duration-300` for the sidebar collapse only.

### Don't:
- **Don't** apply glassmorphism (`backdrop-blur`, translucent bg) to the sidebar or topbar — those are opaque chrome.
- **Don't** ship a solid opaque `#ffffff` card with a hard drop shadow in the content area — use `glass-card`.
- **Don't** reach for `shadow-lg`/deep shadows; chrome depth comes from a `1px` border, content depth from `glass-card` blur.
- **Don't** use emerald as a decorative fill, gradient text, or background band. No `background-clip: text` gradients anywhere.
- **Don't** use colored `border-left`/`border-right` side-stripes on panels, alerts, or list items.
- **Don't** introduce a second font family or a display face for UI labels, buttons, or data.
- **Don't** use `clamp()`/fluid type in the app UI; headings stay at fixed rem steps.
- **Don't** invent new status colors or one-off accent hues; extend the existing semantic vocabulary instead.
