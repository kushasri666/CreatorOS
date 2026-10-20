# Auditable decision trail

Each generated post's ID is its run ID. SQLite stores timestamped audit events
linked to this ID. The **Run audit** tab shows evidence questions, actual
retrieval attempts, all claim verdicts and the complete chronological timeline.
`GET /posts/{id}/audit-trail` exports the same persisted records as JSON, with
source snapshots and the current grounded report. Reading or exporting makes no
model, provider or other external network call.

## What is recorded

1. `run_started` identifies the brief, brand and platform. `research_plan` records
   explicit product-fact, uploaded-document and connected-account questions.
   This bounded initial plan is deterministic; it adds no planning-model call.
2. `research_attempt` records the actual excerpt-selection query and document
   ID/hash/position, or the exact brand/platform/account/source/limit filters
   used to look up already-collected provider observations. Local lookups are
   labeled local; they do not claim a new social API fetch occurred.
3. Official product-page requests get a paired `started` and result event with
   a shared attempt ID, validated URL, excerpt-selection query, timestamp,
   HTTP status when available, and success/failure/no-new-evidence status.
   Missing inputs and unavailable account evidence are logged as skips or no
   evidence. These are product-page requests, not general web search queries.
4. Every `verification` event retains claim text, source IDs, supporting
   quotations when valid, verdict and reason. It identifies both the draft
   version and verification pass. Rejections remain in the history after a
   later correction passes; exported `passed_claims` and `rejected_claims`
   summarize **all passes**, rather than pretending all refer to the final copy.
5. Thin claims create named retry questions and targeted retrieval attempts.
   Writer revisions, editor scores, strategy choices, routing decisions and
   Mesh usage already have their own saved events. `run_completed` records
   final status/selected version; `run_failed` preserves the interrupted run.
   Source records are exported even when retrieval succeeded but generation
   later failed before the final post was saved.

Events use SQLite insertion order, so equal timestamps retain their original
order. Queries and IDs come from executing code; the UI/export does not ask an
LLM to reconstruct a plausible history. Connector credentials are not included
in lookup audit fields. Decisions record concise reasons, not private model
reasoning. This local log is not tamper-proof or externally signed.

Older runs may lack question/attempt/draft-version fields. These gaps are shown
explicitly; historical searches are never invented. Fictional demo traces stay
labeled offline and do not claim live retrieval or verification.

## Local verification

On 20 October 2026, **22/22 tests passed** across run-audit, grounding,
verification-loop and improvement-controller tests. Seven audit tests exercise
actual SQLite persistence, mocked HTTP success/503 failure, document queries,
bounded retry requests, earlier rejection retention, failed-run evidence,
account-credential exclusion and the export function's run isolation. HTTP and
DNS are mocked; no Mesh or provider calls are made. Validation spend: **$0**.

```powershell
python -m unittest tests.test_run_audit tests.test_grounding tests.test_verification_loop tests.test_improvement -v
```

The retrieval tests also cover an excerpt-selection bug fixed in this change:
source text and character offsets must be returned in the expected order, so
page/document evidence is stored as text rather than an integer offset.
