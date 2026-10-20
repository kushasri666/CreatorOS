# Alignment with the supplied hackathon screenshots

The screenshots describe the target capabilities and demo interactions. Their
example engagement, score and token numbers are not evidence about this implementation.
Brew Lab Coffee is an optional fictional scenario; no production path depends on it.

| Reference capability | Implementation |
| --- | --- |
| Brief: topic and platform | Custom brief and platform selection; persisted with brand ID |
| Learned voice from five posts | At least three samples for any brand; optional sample scenarios contain five; source evidence retained |
| Learnings store | SQLite hypotheses scoped by brand/platform with evidence IDs, source, confidence and normalized rate |
| Strategist: angle, hook, audience, why | Distinct strategist prompt with structured output and applied learning IDs |
| Writer: platform draft | Distinct writer prompt; Instagram slide strings plus separate caption |
| Editor: five criteria | Hook, clarity, voice, platform and CTA; complete scorecard and concrete edits |
| Rewrite and rescore | Prior draft and critique passed back to writer; changed text required; at least one revision and at most three drafts |
| Matching visual plus prompt | Distinct visual director; image through Mesh in live mode; labeled SVG placeholder offline |
| Scheduler: best slot with analysis | Deterministic analysis of comparable 24-hour observations; one latest observation per post; real/user-entered sources kept apart from simulation; explicit heuristic if no evidence |
| Queue | Atomic SQLite jobs, UTC timestamps, once-only due handoff, recovery of overdue jobs on app restart |
| Published post | Manual publishing handoff only; app never claims a platform publication it did not perform |
| Performance table and chart | Live persisted metrics table and normalized weighted-rate bars by format/source/window |
| Learner | Distinct learning prompt receives source strategy, metrics and baseline; rules feed the next matching strategist and writer |
| Without/with learning | Explicit generation toggle; stored matching-brief outputs displayed together with score and mode labels |
| Voice switch | Profile/sample comparison and brand selection; same brief can be run for a different brand |
| Self-check scores | Before/after score bars, actual draft text changes, editor requests and full version history |
| Agent log and usage | Timestamped persisted events; actual response usage counted in live mode; zero fake token counts offline |
| Interactive workflow diagram | Twelve selectable nodes, storage boundaries, rewrite/learning edges, Mesh gateway and saved-trace playback |
| Auto / step-by-step demo | Actual run progress polling plus replay of saved decisions; previous/next/play/reset/latest, 1×/2× and keyboard controls |

## Agent architecture

The coordinator drives six specialist responsibilities: strategist, writer, editor,
visual director, scheduler and learner. A separate brand analyst prepares the voice.
The writer performs rewriting; it is not a duplicate agent name hiding the same prompt.
The scheduler uses code and recorded evidence rather than spending an LLM call on date arithmetic.
All actual AI calls, including profiles, images and learning, use the same Mesh gateway.

There are two explicit execution modes:

The normal default is `live`, with spending locked until explicitly enabled.
Fixture mode must be selected deliberately and is not submission quality evidence.

- `offline`: deterministic fixtures for interface development and regression tests.
  No AI or network generation calls. Scores, historical data and visuals are labeled.
- `live`: actual specialist model calls through Mesh, gated by `MESH_ENABLE_PAID=1`.
  Default limits are ten calls per gateway operation, one image call per run,
  1,200 output tokens per text response, zero automatic transport retries, and
  zero implicit schema retries. These bound calls/tokens, not currency cost.

## Remaining limits

No platform publishing integration is connected. Historical scenarios are fictional,
learning remains observational, and stored editor scores are model opinions or
explicit offline fixtures. The existing live evaluation predates this alignment
pass and must not be presented as a new validation of these changes. Generation
background tasks run in the app process; interrupted generation is not automatically
retried on restart, to avoid silently spending more Mesh credits. Durable scheduling
is independent of generation tasks.
