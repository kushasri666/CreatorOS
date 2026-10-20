# Adversarial system evaluation — 21 October 2026

**202 tests passed, including 49 new adversarial tests. Zero failures, errors or
skips. Zero AI calls and $0 additional spending.** The historical combined live
validation spend remains $0.33967690 of its $0.75 allowance.

This evaluation runs the actual coordinator, receipt validation, SQLite queue,
learning memory, FastAPI handlers, SDK response parser, media renderer and social
adapters. Model responses and provider HTTP responses are explicitly scripted.
Normal httpx network transports are blocked, paid flags are disabled and the
runner substitutes a nonusable Mesh key. Budget concurrency includes a separate
real subprocess. Videos render locally and their media streams are decoded.

These are software contracts under difficult inputs, not live model accuracy,
actual social account access, or a security certification for a hosted product.

## What the hard cases found and fixed

| Area | Reproduced failure | Result after correction |
|---|---|---|
| Empty verification | An empty check list could approve uncited factual content | Holds the draft and withholds the image |
| Missing numeric claim | A supported feature could hide an unchecked “90% electricity reduction” assertion | Unchecked numeric assertions enter targeted retrieval/correction; no approval until checked |
| Contradictory evidence | “Save this report” could satisfy an overly broad attribution keyword test | Attribution must introduce the assertion and identify a source; explicit manufacturer attribution still works |
| Gateway response | Truncated-but-parseable JSON, duplicate keys, wrong field types and nonfinite numbers could be accepted/cached | Replies are structurally validated before reuse; truncated or ambiguous responses fail |
| Damaged cache | An incomplete cached record bypassed reply validation | Invalid cache entries are ignored and replaced only by a validated response |
| Scheduling | A queued job could restore a revoked approval | Cancel the stale handoff, preserve the revoked state and record why |
| Publishing identity | Changing an Instagram connection after staging could still publish the earlier account's container | Pin the staged account and block the changed connection before publishing |
| Metric ownership | X metrics did not verify the post's author | Compare author ID; resolve selected handles against authenticated identity when needed |
| Shared spending | Independent processes could reserve against stale copies of one allowance | Durable authorization-family lease and history cursor block overlap and stale parent ledgers |
| Request pricing | Multiple completions or multimodal options were not fully covered by a text-only reservation | Reject unreviewed options before inference |
| Evaluation labels | A failed media return could be labeled passed | Inspect returned media/queue status and nonempty output, not just absence of exceptions |

The 49 new tests comprise 12 graph/evidence cases, 14 connector/delivery cases,
6 gateway/cache cases, 12 budget cases and 5 reporting/format cases. Several
cases exercise multiple hostile inputs through subtests.

Positive controls verify that the safeguards still allow a genuine rewrite,
fully supported numeric claims, explicit source attribution with disagreements
visible, an approved image, handle-based X ownership, and successful local media.
Additional cases cover fabricated quotations, forged conflict evidence, duplicate
retrieval IDs, exhausted call budgets, image opt-out, ambiguous publication
timeouts, malformed success responses, partial collector failure, invalid metric
counters, changed token encryption keys and repeated-publication prevention.

## Limits the numbers must not hide

The existing authored grounding benchmark still scores **62.5% grounded claims**
after receipt filtering, **55.56% required-fact completeness** and **45.83%
question completeness**. Five intentionally unsupported fixture claims survive
because their scripted verifier judgments and real-but-irrelevant quotations
cannot be corrected by quote matching alone. These unfavorable results remain
recorded; they are not relabeled as 202 passing tests or current live accuracy.

The earlier saved-brand Instagram 100/100 measured six generic editorial proxy
checks and omitted optional carousel structure. New strict-format regressions
explicitly require slide count, distinct short slides, or a YouTube short-script
format. They demonstrate that missing/duplicate slides and prose masquerading as
a script lose points; they do not retroactively rewrite historical scores or
establish a new quality benchmark.

Other remaining limitations:

- A verifier can miss an uncited nonnumeric assertion or misjudge semantic
  support. Numeric coverage is a conservative partial guard, not exhaustive
  claim discovery. Literal receipt validation does not establish truth.
- The saved Content Tracker AI learning-driven post remains held by the verifier.
  Its generated illustration also needs review for garbled text. No new live
  calls were spent trying to obtain favorable outcomes.
- Simulated or mocked metrics establish learning plumbing; changed output is not
  causal engagement uplift. Sparse owner samples are not independent proof.
- OAuth, publishing and engagement read-back were mocked here. No live account
  permissions or real public posting were tested.
- This remains a single-user local app without application authentication. These
  tests do not establish tenant isolation for a hosted SaaS product, load capacity
  or all browser interactions.
- The spending guard assumes reviewed catalog pricing and its conservative retry
  allowance. It does not replace a provider-side hard spending limit. Unknown
  outcomes retain a blocking lease until billing is reconciled; never remove
  that lease merely because time has passed.

## Reproduce without spending

```powershell
python scripts/evaluate_resilience.py
python scripts/evaluate_resilience.py --check-recorded
python scripts/evaluate_grounding.py --check-recorded
python scripts/evaluate_content.py --check-recorded
```

[Full machine-readable results](evaluation-resilience.json) include every test ID,
result, the unfavorable grounding metrics and normalized implementation/test
fingerprints. The check-only command validates the record against saved sources;
it does not rerun tests or infer a fresh live result. The full runner executes
the suite with temporary synthetic databases, preserving customer brands, media,
credentials and the live billing ledger.
