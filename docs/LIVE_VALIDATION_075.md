# Budgeted live validation — 20 October 2026

The completed validation cost **$0.16066170**, below the authorized **$0.75**
ceiling, leaving **$0.58933830** unused. This is the cumulative cost of the
resumed validation, including unsuccessful attempts and diagnostic repairs.
No further paid calls were made after finalization.

The [summary](validation-live-075-summary.json) records the final measurements.
The [complete sanitized record](validation-live-075.json) retains earlier failed
and held passes, actual model outputs, source receipts, decisions and revisions.

## What ran live

One fictional product, Brew Mini, supplied the facts for this exercise. Its voice
was learned from three fictional historical samples; a real text attachment was
ingested alongside brand facts. These are explicitly test inputs, not customer
content or independent evidence about an actual product.

- The production coordinator ran strategist → writer → editor → writer revision
  and source verification, followed by a matching image generated through Mesh.
- Both caption and slides genuinely changed. Two complete Instagram content
  runs were approved with supporting receipts from two saved sources each.
- The isolated SQLite database stored the post and scheduled queue. Ticking the
  queue reached `ready_to_publish`; no public account was posted to.
- A real 720×1280 video was rendered locally using the generated image and
  original synthesized music. The final file is 844,145 bytes. Generative video
  and audio models were not called.
- Explicitly simulated engagement was ingested. A live learning agent produced
  a stored lesson, and the second approved run recorded that lesson's ID in its
  strategy. Strategy and output changed; this does not prove engagement uplift.
- A grounded follow-up about the number of grind settings completed. The final
  regression check reused cached real Mesh responses and made zero new AI calls.
- X, LinkedIn, YouTube, Telegram and Threads ran actual writer/editor pairs.
  These were format checks, not complete graph runs or live publishing tests.

## Measured quality, including weaknesses

The unchanged `platform-editorial-v2` scorer checks length, readability, hook,
brief concept coverage, closing action, vocabulary cues and applicable format
structure. These are structural/lexical proxies. They do not measure semantic
truth, full brand fidelity, visual appeal or independently judged writing quality.

| Live case | Before editor | Final score /100 | Scope |
|---|---:|---:|---|
| Instagram | 100.000 | 100.000 | Complete graph; verified and approved |
| Instagram using saved learning | 100.000 | 100.000 | Complete graph; verified and approved |
| X | — | 83.333 | Writer/editor revision pair |
| LinkedIn | — | 100.000 | Writer/editor pair |
| YouTube | — | 100.000 | Writer/editor pair |
| Telegram | — | 100.000 | Writer/editor pair |
| Threads | — | 66.667 | Writer/editor revision pair |

The mean of these seven selected final outputs is **92.857/100**. X still fails
the opening-length check. Threads still fails opening length and readability.
The two Instagram scores did not improve on this scorer despite actual edits;
its checks were already saturated. Earlier failures remain in the full record.
This is a retrospective diagnostic on one product and voice, with prompt/model
repairs during validation, not a held-out benchmark or population estimate.
The separate historical ten-pair benchmark remains **76.667 → 75.000/100**.

The economical default models were held for review in earlier attempts. The
successful diagnostic profile used GPT-4.1 for writing, editing and verification,
and GPT-4.1 mini for the successful learning step. Overrides applied only to the
validation process; permanent customer model settings were not changed. This
run therefore does not establish that the cheaper defaults meet the strict target.

## Fixes established by this validation

Source verification now uses stable claim/receipt IDs that resolve to exact saved
text. Unknown IDs fail closed. Only terminal punctuation can be normalized to an
existing literal claim; words and numbers cannot be repaired into evidence.
Multiple checks of the same claim merge validated source receipts and retain
the worst verdict, preventing either lost citations or hidden rejections.

The editor gives a concrete first-round revision request without seeing the
numeric approval target. Slide-only substantive edits count as real revisions;
changing citations alone does not. A malformed optional learning response no
longer discards valid engagement: the explicit, audited fallback uses deterministic
metric evidence and keeps the failure visible. Trusted Mesh image CDN assets are
validated and materialized so local video rendering includes the generated image.

## Spending controls and accounting

All AI requests used the production OpenAI-compatible client through
`https://api.meshapi.ai/v1`. The single private ledger persisted before requests,
survived every resumed phase and was never reset. SDK retries were disabled.
There were **78 inference requests**, including gateway-cache responses, and
exactly **one image request**. No paid embeddings, transcription or extra image
comparisons were run.

The internal admission cap was **$0.70**. The maximum recorded combined billed
and reserved liability was **$0.60858100**. Reservations use conservative priced
token/output bounds and unknown outcomes retain their allowance. Sequential
reservations reuse settled headroom: their gross sum is not money spent.

Known request-level billed charges sum to **$0.16066170**, matching the account
balance decrease over this validation. Six successful receipt events returned
null costs, consistent with documented gateway caching. Historical missing cache
headers were not assumed free by the guard; conservative usage-price bounds
remained in admission accounting. Reports exclude absolute balances and secrets.

## Reproducibility and remaining boundaries

The sanitized JSON includes raw text and detailed checks; the private isolated
database, original billing ledger and generated media remain in gitignored
`data/`. Credentials and customer data are not needed to inspect the results.
The finalizer exits without new inference once its ledger is finalized. Do not
reset that ledger to repeat a paid experiment under the same budget.

Offline verification with paid calls disabled:

**151/151 tests passed** after the fixes. Both recorded content and grounding
evaluations reproduced exactly with zero AI calls. Source compilation and Git
whitespace checks also passed.

```powershell
$env:MESH_ENABLE_PAID='0'
python -m unittest discover -s tests
python scripts/evaluate_content.py --check-recorded
python scripts/evaluate_grounding.py --check-recorded
```

Social OAuth, platform posting and engagement collection were covered by mocked
regressions only; live account credentials/permissions were unavailable. No live
social API integration success, customer engagement improvement, held-out
entailment accuracy, or universal end-to-end platform readiness is claimed.
