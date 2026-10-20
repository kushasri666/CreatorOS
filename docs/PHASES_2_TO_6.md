# CreatorOS: phases 2–6 and architecture alignment

> Historical planning/audit document written before the implementation pass.
> Its “current gaps” describe the original prototype. See README.md, source,
> tests, and evaluation artifacts for the implemented behavior and remaining limits.

## Source and scope

Official source: https://career.krishnaik.in/hackathons/agent-arena-2026
(reviewed 20 October 2026). The public brief specifies capabilities, not numbered
phases 2–6. The phases below are our implementation plan derived from that brief
and the supplied architecture screenshot; they are not organizer-authored phases.

All AI calls, including brand extraction, text, image prompts, images, learning,
and AI evaluation, must use Mesh API. Real platform publishing is an optional bonus.
User-entered or simulated engagement is allowed, with its origin clearly labeled.

## Phase 1 audit

- Public repository exists: https://github.com/kushasri666/CreatorOS
- Required dependencies and official workflow path exist locally.
- Latest public run inspected failed:
  https://github.com/kushasri666/CreatorOS/actions/runs/39290034943
- Secret presence and failure cause remain unverified; never infer them from a failed run.
- `main.py`, `workflow.py`, and `evaluate.py` were untracked at inspection time.
- Local `.env` was created from the existing `mesh.env` without displaying its contents.
  Both filenames are ignored. Key validity has not been checked.
- A README and measured evaluation results were absent; README now documents actual status.

## Phase 2: persistent foundation and learned brand voice

Build SQLite storage and validated request/response schemas before adding more agents.
Use brand IDs and post IDs throughout. Learn a versioned voice profile from multiple
user-provided historical posts: tone, vocabulary, structure, CTA habits, examples,
and constraints. Store which samples produced each profile. Inject it into strategy,
writing, editing, and visuals. Treat sample content as data, not executable instructions.

Proposed records: brands, brand_samples, voice_profiles, posts, draft_versions,
editor_reviews, assets, scheduled_jobs, performance_metrics, learnings, audit_events.
Each belongs to a brand; post-related records reference a post ID. Store timestamps
in UTC and retain the requested display timezone.

Acceptance: data survives restart; two distinct multi-sample brands produce visibly
different content; a run can show the exact profile version it used.

Current gap: `BRAND_VOICE_PROFILE` is a constant; no sample ingestion or database exists.

## Phase 3: orchestration and real editor refinement

Use the existing LangGraph skeleton: strategist → writer → editor. The strategist
returns structured angle, hook, audience, platform, and reasons informed by the brand
profile and relevant learnings. The writer receives the brief, platform constraints,
strategy, and—on revision—the actual prior draft and actionable editor feedback.

The editor returns validated scores for hook, clarity, voice, platform fit, and CTA,
plus concrete edits. Proposed policy: average score at least 8/10, maximum three
drafts. These thresholds come from the prototype/screenshot, not a mandated score.
At the limit, retain a below-threshold piece for review instead of silently marking
it approved. Malformed reviews should produce a controlled retry/error.

Persist every draft, score, feedback item, routing decision, and rationale. Avoid
generic audit strings such as “Drafted content.”

Acceptance: demonstrate a failing draft, the editor's requested changes, a changed
revision, and a bounded termination path. Verify platform rules and brand context
actually reach the editor.

Current gaps: writer never receives the previous draft; editor lacks brand/platform
context; capped low scores go on to visuals; audit data is only returned in memory.

## Phase 4: visuals, persistent scheduling, and content lifecycle

Generate a matching visual through a verified Mesh-supported image model; persist
prompt, model, asset reference, and generation status. Preserve the visual prompt
in the API response. Handle expired URLs or base64 image responses as applicable.

Select a concrete future timestamp with timezone and a reason based on available
platform/audience evidence. Without historical evidence, label the recommendation
as a heuristic. Persist the finished piece and queue it for execution. Use APScheduler
with persistent job state or a database-backed due-job worker; reconstruct pending
work on restart and prevent duplicate execution.

Lifecycle: draft → needs_review/approved → scheduled → ready_to_publish or published.
Only use “published” after a real platform response or an explicitly labeled simulated
publication. Scheduling a piece does not itself publish it.

Acceptance: generated image matches the piece; future job survives restart; due work
executes once; failures are recorded. A live publishing integration is optional.

Current gaps: scheduler produces a day/time string only; no queue, post storage,
background job, durable asset storage, or publishing implementation exists.

## Phase 5: performance feedback and the learning loop

Capture metrics against a specific post ID with source (real, user-entered, simulated),
observation window, platform, and timestamps. Validate nonnegative counts and make
metric ingestion idempotent. Include reach/impressions where available so raw audience
size does not masquerade as content quality.

Compare posts within relevant brand/platform contexts. Have the learner produce
evidence-linked, versioned hypotheses about hooks, structure, CTA, topics, and time
slots. Record evidence and confidence; limited observations should remain tentative.
Retrieve relevant learnings for the next strategist and record which were applied.

Acceptance: show post A → metrics → stored learning → changed strategy/output for B.
Prove brand isolation and prevent duplicate metrics from generating duplicate evidence.
Clearly label simulated data; do not claim real engagement uplift from simulation.

Current gaps: `/learner` accepts arbitrary post text rather than an existing post ID;
its raw engagement threshold is not normalized; one shared JSON file mixes brands;
there is no metric history or persistent causal trail.

## Phase 6: evaluation, interactive demo, and submission

Create a versioned test set spanning multiple brands and platforms, strong/weak
drafts, and positive/negative feedback cases. Use paired briefs and consistent model
settings to compare initial versus revised drafts and with versus without learnings.
Report per-criterion quality, revision rate, threshold pass rate, platform compliance,
brand consistency, and failure rate. Preserve raw outputs, model/settings, date,
sample count, and cost where available. Independent review helps limit self-scoring bias.
Record measured numbers, including regressions; never substitute illustrative numbers.

Add meaningful tests for routing, malformed reviews, max-iteration behavior, restart
recovery, duplicate execution, feedback linkage, and brand isolation. Mock AI calls
for deterministic tests; keep separately labeled live Mesh integration runs.

Demo surfaces matching the screenshot: brief/brand form, pipeline trace, versioned
editor feedback, final text/image, schedule queue, metrics entry, learning history,
and post-linked audit history. Brew Lab Coffee is a demo scenario, not a hardcoded
special case. Use the example “five ways to make cafe-style coffee at home” to show
one complete flow, then demonstrate a contrasting brand and a second learning-aware run.

Submission acceptance: public source, reproducible README, test set and measured
results, passing critical GitHub checks, and no committed secrets. Deployment and
video are optional; they do not replace the working core loops.

Current gap: `evaluate.py` compares two generations without a test set, controlled
comparison, persisted results, or evidence of measured improvement. No UI exists.

## Screenshot mapping

| Screenshot box | Required implementation |
| --- | --- |
| Your brief | Validated topic/platform input linked to brand and post |
| Brand voice profile | Versioned profile learned from multiple samples |
| Learnings store | Brand/platform-scoped, evidence-linked memory |
| Strategist | Angle/hook/audience and reason; consumes profile and learnings |
| Writer | Platform-aware drafts and revisions using prior draft |
| Editor | Five criteria, actionable feedback, bounded rewrite routing |
| Visual | Mesh-generated matching image and retained prompt |
| Scheduler | Persistent timestamped queue and execution status |
| Published post | Real publication or explicit simulation; not inferred from queue |
| Performance metrics | Post-linked observations with source and time window |
| Learner | Evidence-based hypotheses injected into future generation |
| Audit log | Durable per-post decisions, reasons, versions, and outcomes |

## Implementation order

1. Diagnose the failed Actions run, verify repository secrets, and push source safely.
2. Add schemas, SQLite persistence, sample ingestion, and brand profile extraction.
3. Harden structured agent outputs and demonstrate the real rewrite loop.
4. Persist visuals and schedule executable, restart-safe jobs.
5. Link metrics to posts and prove learning changes future output.
6. Build evaluation evidence and the demo views, update README, and rerun checks.
