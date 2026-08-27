# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Employees (all company staff)** — ask questions in their domain (RH, IT, Juridique) when they need a procedural or policy answer. They work at a desk, often under time pressure, and expect a quick, reliable reply without having to chase a specialist. They interact only through the employee-facing space (new ticket, history, my space).

**Subject-matter experts (domain leads: RH, IT, Legal)** — validate, correct, or reject AI-generated answers in the backoffice. They see tickets filtered to their domain, manage the knowledge base, and monitor response quality. They are comfortable with nuanced decisions about answer accuracy. Their main risk is spending time re-validating the same questions over and over.

**Admins** — configure the system (groups, site settings, thresholds), monitor platform health, and manage user access. Typically one or two IT administrators.

## Product Purpose

TicketAI is an AI-powered internal helpdesk that auto-answers employee questions (HR, IT, Legal) by searching a validated knowledge base and internal documents, then routes unanswered questions to the right domain expert for human validation. Validated answers accumulate confidence and eventually become canonical — served instantly without any human review. Success means employees get accurate answers faster, and domain experts spend time only on genuinely new questions, not repetition.

## Positioning

The key mechanism is the **human-in-the-loop validation loop that compounds over time**: every validated answer raises its confidence score, and high-confidence answers become canonical and bypass expert review entirely. Competing tools either force a human on every ticket or go fully automated without quality control. TicketAI offers a middle path that gets smarter with use.

## Operating Context

- Single organisation, internal deployment — no multi-tenancy
- French-language product (UI, prompts, documents, and answers are all in French)
- Domain structure: RH, IT, Juridique (extendable by admin)
- Employees submit questions from any browser; validators process a queue in the backoffice; admins configure thresholds and groups
- The AI pipeline runs asynchronously (Celery workers); users and validators see real-time status updates via SSE
- Documents (PDF, DOCX, TXT, MD) are the knowledge source; versioned and updateable without losing history

## Capabilities and Constraints

- Three response branches: **CANONIQUE** (instant, no review), **SUGGESTION** (reuses a validated answer, requires review), **RAG** (LLM-generated from document chunks, requires review)
- Validation gate: a validator cannot validate their own ticket
- Canonical promotion threshold: 3 validations (configurable, `seuil_canonique`)
- Cosine similarity threshold for canonical/suggestion lookup: calibrated per dataset, default 0.90 (`seuil_cosinus`)
- Document update pipeline detects semantic changes and flags affected answers for re-review (`a_relire`)
- Dark mode supported; reduced-motion preference respected
- `ADMIN` role, `BACKOFFICE` role (domain experts), and regular users — each sees a different interface

## Brand Commitments

- Product name: **TicketAI**
- Font: **Geist Variable** (committed, loaded from `@fontsource-variable/geist`)
- No primary colour locked yet — current neutral/emerald palette is working but not binding
- Glass-morphism aesthetic (glass-panel + glass-card with backdrop blur) and Aurora WebGL background are established UI motifs, not provisional

## Evidence on Hand

- Full working codebase with both employee and backoffice spaces implemented
- No external press, testimonials, or case studies
- No brand guide or logo spec beyond the SVG assets in `frontend/src/assets/`

## Product Principles

1. **Compound expertise.** Every validation makes the next answer cheaper — design to surface this flywheel to both employees and validators.
2. **Trust, then verify.** High-confidence answers serve instantly; lower-confidence answers always get a human gate. The threshold is the product's central control knob.
3. **Domain ownership.** Each domain's experts own their queue. The system enforces this boundary; it should feel like it respects professional authority, not bypasses it.
4. **Transparent uncertainty.** When the AI cannot answer with confidence, it says so and routes cleanly — never silently guesses.
5. **Progressive disclosure.** Employees need simplicity; validators need depth; admins need control. Three distinct interfaces, not one.

## Accessibility & Inclusion

- `prefers-reduced-motion` is respected globally (Aurora WebGL renders statically; transitions suppressed)
- WCAG AA contrast is maintained in both light and dark modes (glass-card opacity tuned for ≥ 4.5:1 on gray-500+)
- No specific assistive technology requirement recorded beyond standard browser accessibility
