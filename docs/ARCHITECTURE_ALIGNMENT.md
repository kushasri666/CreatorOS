# Alignment with the supplied hackathon screenshots

The screenshots describe the target capabilities and demo interactions. Their
example engagement, score and token numbers are not evidence about this implementation.
Brew Lab Coffee is an optional fictional scenario; no production path depends on it.
Updated 21 October 2026 against the current source. Current repair/validation
outcomes are recorded in [gap validation](GAP_VALIDATION.md).

| Reference capability | Implementation |
| --- | --- |
| Brief: topic and platform | Custom brief and platform selection; persisted with brand ID |
| Learned voice from five posts | At least three samples for any brand; optional sample scenarios contain five; source evidence retained |
| Learnings store | SQLite hypotheses scoped by brand/platform with evidence IDs, source, confidence and normalized rate |
| Strategist: angle, hook, audience, why | Distinct strategist prompt with structured output and applied learning IDs |
| Writer: platform draft | Distinct writer prompt; Instagram slide strings plus separate caption |
| Editor: five criteria | Hook, clarity, voice, platform and CTA; complete scorecard and concrete edits |
| Rewrite and rescore | Prior draft/slides and critique passed back to writer; a genuine text or slide change is required; at least one revision and at most three drafts |
| Matching visual plus prompt | Distinct visual director; Mesh illustration with exact headline/brand composed using local fonts; explicit human image/caption review before Instagram preparation; labeled placeholder offline |
| Scheduler: best slot with analysis | Comparable API observations use actual provider publication times, account/format/window/age/formula scope, and at least two posts in each of two weekday/hour slots. Otherwise retain separately labeled manual/simulated 24-hour evidence or an explicit heuristic |
| Queue | Atomic SQLite jobs, UTC timestamps, once-only due handoff, recovery of overdue jobs on app restart |
| Published post | Optional, explicitly confirmed Instagram single-photo API flow; real provider receipt required to mark published. Other publishing remains a manual handoff |
| Performance table and chart | Persisted manual metrics plus six-platform API adapters and comparable rate cohorts; missing values remain absent. Imported Instagram formats distinguish carousel/photo/reel rather than pooling them as FEED |
| Learner | Distinct learning prompt for entered metrics; deterministic evidence-linked experiments for API observations. Rules feed matching strategist/writer context; optional interpretation failure preserves valid metrics |
| Without/with learning | Explicit generation toggle; stored matching-brief outputs displayed together with score and mode labels |
| Voice switch | Profile/sample comparison and brand selection; same brief can be run for a different brand |
| Self-check scores | Before/after score bars, actual draft text changes, editor requests and full version history |
| Agent log and usage | Timestamped persisted events; actual response usage counted in live mode; zero fake token counts offline |
| Interactive workflow diagram | Twelve selectable nodes, storage boundaries, rewrite/learning edges, Mesh gateway and saved-trace playback |
| Auto / step-by-step demo | Actual run progress polling plus replay of saved decisions; previous/next/play/reset/latest, 1×/2× and keyboard controls |

## Agent architecture

The coordinator executes the custom `CreatorOS StateGraph` in `agent_graph.py` and
`pipeline_graph.py`. Named handlers fetch/review sources, plan an angle, write,
score, verify, retrieve again, correct and generate the visual. It also coordinates
the deterministic scheduler and performance learner. A separate brand analyst prepares the voice.
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
  role-specific text ceilings of up to 1,600 output tokens, zero automatic transport retries, and
  zero implicit schema retries. These bound calls/tokens, not currency cost.

## Remaining limits

Real social account authorization, provider permissions and live publishing/read-back
remain unverified. The implemented Instagram publisher requires a separate opt-in,
OAuth publishing permission, reviewed image/caption, public HTTPS JPEG URL and final
per-post confirmation; it does not auto-publish scheduled jobs. Carousel, Reel and
other-platform publication are not implemented.

Historical scenarios and example analytics are fictional. Learning is observational;
changed output and applied evidence IDs do not establish causal engagement uplift.
Editor ratings are model opinions; lexical/structural scores are limited proxies.
Human image review records an acknowledgement, not automated visual correctness.
The current gap report separates live measurements from earlier results and test
doubles; this architecture comparison does not itself make new model/platform calls.

Provider timing recommendations need fresh snapshots with pinned account identity
and provider publication-time provenance. Legacy or manually linked timestamps do
not silently acquire that provenance. YouTube discovery retains the generic `video`
label when Shorts/long-form classification is not verified.

Generation background tasks run in the app process; interrupted generation is not
automatically retried on restart, to avoid silently spending more Mesh credits.
Durable scheduling is independent of generation tasks. This remains a local,
single-user application without hosted tenancy or application authentication.
