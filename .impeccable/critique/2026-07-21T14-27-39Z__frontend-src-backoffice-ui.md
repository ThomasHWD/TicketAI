---
target: frontend/src backoffice UI
total_score: 22
p0_count: 0
p1_count: 3
timestamp: 2026-07-21T14-27-39Z
slug: frontend-src-backoffice-ui
---
Method: ⚠️ DEGRADED: single-context (harness guardrail — sub-agents not spawned without explicit user request)

Target: `frontend/src` backoffice + user surfaces (Sidebar, Navbar, TicketsList, TicketDetail, NewTicket, UserTicketHistory, UserTicketDetail, Aurora). Register: **Product**.

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Good loading/spinner/lock feedback; raw `statut_job` enum leaks to UI |
| 2 | Match System / Real World | 2 | Raw enum (`statut_job`) + raw `domaine` ("RH") in history table while detail maps to "Ressources humaines"; fabricated "Objet"/requester |
| 3 | User Control and Freedom | 2 | No confirm/undo on the irreversible **Valider**; Esc doesn't cancel edit |
| 4 | Consistency and Standards | 3 | Strong visual system; domaine mapped in one screen, raw in another; two back-button labels |
| 5 | Error Prevention | 2 | Validation promotes an answer with zero confirmation step |
| 6 | Recognition Rather Than Recall | 3 | Nav labeled; navbar Bell/Grid icon-only; `⌘/` hint implies a shortcut that doesn't exist |
| 7 | Flexibility and Efficiency | 1 | Search is a fake `<span>`; no real keyboard shortcuts; no bulk actions on the queue |
| 8 | Aesthetic and Minimalist Design | 3 | Clean, coherent; muted-gray text hurts scannability |
| 9 | Error Recovery | 2 | `role="alert"` + form preserved, but messages are raw `e.message` (backend text) |
| 10 | Help and Documentation | 1 | No contextual help at validate/correct decision points; "Documentations" route unbuilt |
| **Total** | | **22/40** | **Acceptable — real improvements needed before validators are happy** |

## Anti-Patterns Verdict

**Does this look AI-generated? Mixed — better than slop, but the shell is template-y.**

**LLM assessment:** The core is a *committed* design choice, not a reflex: one emerald accent, a genuine custom WebGL Aurora, real French domain specificity, and above-average accessibility attributes. That lifts it out of pure slop. But two tells remain: (1) **glassmorphism as the default surface** — every panel is `white/80 + backdrop-blur-xl`; the skill lists decorative glass among absolute bans, and here it's applied uniformly rather than earned per-surface; (2) the **navbar is a stock SaaS silhouette** — fake search box, notification bell with a red dot, `pravatar` avatar, `⌘/` kbd — the exact furniture that says "dashboard template." None of it is wired up.

**Deterministic scan:** `detect.mjs --json frontend/src` returned `[]` (no findings). Treat as **under-scoped, not a clean bill** — the detector reads HTML/CSS, and this project's styling lives entirely in inline Tailwind classes inside `.tsx`, which it doesn't parse. No HTML/CSS slop signatures to catch; the LLM review is the load-bearing signal here.

**Visual overlays:** Not available — no dev server running and no browser-automation tool exposed this session. No live contrast sampling was performed; contrast calls below are computed from the Tailwind hex values against their backgrounds.

## Overall Impression

This is a coherent, disciplined interface with a real point of view — the emerald-glass-over-aurora system is consistent screen to screen, and the accessibility scaffolding (keyboard-navigable rows, `aria-*`, focus rings, `role="alert"`) is genuinely above the AI baseline. The single biggest opportunity: **it looks more finished than it is.** A validator sits down to a topbar full of controls that do nothing and a ticket detail that shows a hardcoded requester ("Sophie Martin") and a hardcoded subject regardless of the real ticket. The visual polish writes a check the wiring doesn't cash. Close that gap — remove or wire the fake affordances, kill the mock data, fix muted-text contrast — and this jumps a full band.

## What's Working

1. **A real, enforced design system.** The `StatutBadge` (pill + `bg-current` dot + label), the glass panel, the emerald primary button, the emerald focus ring — reused verbatim across 6 screens. This is the hardest thing to get right in product UI and it's genuinely consistent.
2. **Accessibility is not an afterthought.** Rows are `role="link"` + `tabIndex=0` with Enter/Space handlers, decorative icons carry `aria-hidden`, errors use `role="alert"`, loading uses `aria-live="polite"`, badges pair color with a text label (not color alone). Rare in generated UI.
3. **Status is honestly modeled to the domain.** Canonique/Validée/Suggestion/Rejetée map to real business states, and the user-facing history intelligently relabels them ("Répondu" / "En cours de traitement") and hides unvalidated answers — thoughtful trust design.

## Priority Issues

- **[P1] Muted-gray text fails contrast across every screen.** `text-gray-400` (#9ca3af ≈ 2.8:1 on white) is the default for table secondary cells, timestamps, `dt` labels, the "similarité 87 %" meta, placeholders, and empty-state text. It fails the 4.5:1 floor for body/meta, and it's worse where it sits over the translucent glass + aurora. This is the #1 reason the UI will feel hard to read.
  - **Why it matters:** Validators scan queues fast; low-contrast meta (dates, similarity scores, domains) is exactly the data they triage on. Sam (low vision) can't read it; everyone reads it slower.
  - **Fix:** Bump secondary text to `text-gray-500`→`gray-600` (#4b5563 ≈ 7:1), placeholders to `gray-500`. Reserve `gray-400` for genuinely decorative glyphs only.
  - **Suggested command:** `/impeccable colorize` (or `/impeccable audit` for a full contrast pass).

- **[P1] The topbar is a wall of dead affordances.** The search field is a `<span>Search...</span>` (not an input), the `⌘/` kbd advertises a shortcut that doesn't exist, the Bell shows an unread dot with no notifications behind it, the LayoutGrid button and the user chevron do nothing, and even **"Add Ticket" has no `onClick`.**
  - **Why it matters:** Every non-functional control is a small lie that erodes trust and wastes clicks. Alex reaches for the search first and hits a dead span; Jordan clicks the bell and nothing happens.
  - **Fix:** Either wire them or remove them for now. At minimum: make search a real `<input>` (even if it only filters the current list), drop the `⌘/` hint until the shortcut exists, and give "Add Ticket" a route to `/nouveau-ticket`.
  - **Suggested command:** `/impeccable harden` (edge cases + honest affordances) then `/impeccable clarify`.

- **[P1] TicketDetail ships fabricated data to a decision-maker.** `MOCK_OBJET` ("Demande de clarification sur la politique de télétravail") is rendered as the `h1` for *every* ticket, and the entire "Demandeur" panel is a hardcoded `MOCK_AUTHOR` ("Sophie Martin", phone, email).
  - **Why it matters:** A validator approving an answer sees a requester and subject that have nothing to do with the actual ticket. That's not a placeholder gap — it's misinformation at the exact high-stakes moment the tool exists for. Riley spots it in one click; in production it's a correctness bug.
  - **Fix:** Render `ticket.question`/real subject in the header and either populate the requester from real data or hide the panel until it exists (empty state, not fake state).
  - **Suggested command:** `/impeccable harden`.

- **[P2] No confirmation or undo on the irreversible "Valider."** One click promotes an answer toward canonical (`nb_validations++`) with no "are you sure," no undo, and no post-action toast. Correction has a guard; validation doesn't.
  - **Why it matters:** Error Prevention on the single most consequential action is missing. A misclick on the wrong response in a multi-answer thread is unrecoverable from the UI.
  - **Fix:** Add a lightweight inline confirm (not a modal) on Valider, and a success toast with an undo affordance for a few seconds.
  - **Suggested command:** `/impeccable harden`.

- **[P2] No mobile/responsive structure for the shell or detail view.** The detail pages are `flex gap-5` with a fixed `w-72` sidebar and no breakpoint to stack; below ~700px the main column is crushed. The Sidebar/Navbar never collapse to a drawer on small screens. The register calls for structural responsive behavior — it's largely absent (tables do have `overflow-x-auto`, which is the one bright spot).
  - **Why it matters:** Casey on a phone can't use the detail or the nav. Even on a laptop, the two-column detail gets tight.
  - **Fix:** Stack the detail columns under `lg:` (`flex-col lg:flex-row`), and give the sidebar an off-canvas drawer + hamburger below `md:`.
  - **Suggested command:** `/impeccable adapt`.

## Persona Red Flags

**Alex (Power User):** Reaches for the search box → it's a non-interactive span. Sees `⌘/` → presses it → nothing. No keyboard shortcuts for validate/correct/next-ticket. No bulk actions on the queue (one ticket at a time only). The efficiency furniture is painted on.

**Sam (Accessibility / low vision):** `text-gray-400` meta text and placeholders fail 4.5:1. Keyboard focus on table rows relies on a `focus-within` *background tint* rather than a visible focus outline — easy to lose your place. The continuously-animating Aurora background has no `prefers-reduced-motion` off-switch (vestibular risk), and neither does the sidebar width transition.

**Riley (Stress tester):** Opens any ticket → the subject and requester are identical hardcoded mock values regardless of the record. Validates an answer → no confirmation, no feedback, action is silent and irreversible. History table shows raw `RH` while the detail says "Ressources humaines" for the same record — an inconsistency that reads as a bug.

## Minor Observations

- **Hierarchy inversion in UserTicketDetail:** the `h1` is the *domain* ("Ressources humaines") while the actual question is demoted into a panel below. The question is the subject — it should lead.
- **Raw enum leak:** "Statut traitement" prints `EN_ATTENTE`/`TERMINÉ` verbatim; map to human labels.
- **Loading is centered text ("Chargement…"), not skeleton rows** — the product register prefers skeletons for content areas.
- **Two back-button labels** ("Retour" vs "Retour aux tickets" vs "Retour à l'historique") — fine, but the error-state one says just "Retour" while the happy path says "Retour aux tickets."
- **Arbitrary values:** `min-h-[420px]` on the correction textarea is a magic number; consider a rows-based or `clamp` height.
- **Empty states are decent** ("Vous n'avez encore posé aucune question") but don't teach the next action (no "Poser une question" CTA in the empty history).

## Questions to Consider

- What would this feel like if the topbar contained only controls that *work* — maybe just breadcrumb + theme + user? Confidence often means fewer, real affordances rather than a full-looking bar.
- The Aurora is your signature. Is it earning its cost on a dense triage queue, or does it belong to the calmer surfaces (login, empty states, the user-facing question form) while the working queue stays flat and fast?
- Validation is the one moment that matters most. What would a version that made the validator feel *certain* — full context, requester, source doc, a beat to confirm — look like?
