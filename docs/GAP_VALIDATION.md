# Gap repairs and combined-budget validation

Evaluated 21 October 2026. All live model/image requests used Mesh's OpenAI-compatible gateway. Failed attempts remain in the same cumulative ledger; it was not reset to obtain another allowance. Raw customer samples, generated copy, account metadata, invoices and the validation SQLite database remain under gitignored `data/`.

## Cost and boundaries

| Item | USD |
| --- | ---: |
| Earlier validation charges inherited | 0.33967690 |
| This gap-repair validation | 0.14978430 |
| **Combined actual charge** | **0.48946120** |
| Authorized combined maximum | 0.75000000 |
| Unspent | 0.26053880 |

[Recorded accounting](validation-gaps-075-cost.json) is finalized. The available request charges sum to the account balance decrease, independently reconciled through metadata-only Mesh calls. Nine individual receipts remain unavailable/unpriced in the inherited ledger; conservative reservations remain for those requests. The equal account delta is not a claim that every per-request receipt was retrieved.

This phase added **75 inference requests, including one image**. Combined history contains 204 requests and four images. Transport retries and schema retries were disabled. A guarded SDK HTTP transport reserves a conservative cost bound before each request, uses a shared process lease, checks metadata pricing, rejects unsupported options and stops before a request would exceed its admission limit. Some larger diagnostic requests were rejected before inference; they incurred no charge. The internal admission limit was raised from $0.70 to $0.745 under the user's explicit permission to use the full $0.75 allowance. The original balance and prior charges were retained.

The validation guard is specific to this authorized run. Normal production call/token limits are not a dollar budget. Client controls also do not replace provider-side limits. We stopped after the useful planned tests; unused authorization was not spent merely to exhaust the budget.

## Gaps repaired

| Gap found | Implementation and evidence |
| --- | --- |
| Exact quotations were mistaken for semantic proof; valid paraphrases and attributed disagreements were sometimes held | `semantic_policy.py` separates literal claim/receipt matching from meaning: entity, scope, numbers, conditions, time and negation must agree. `source_policy.py` recognizes explicit packaging/label attribution and document disagreement without allowing a trailing CTA to disguise an unqualified disputed fact. |
| A verifier could inspect cited caption claims while missing independent slide assertions | `verification_contract.py` adds deterministic sentence/clause units and a full classification manifest. Every factual/mixed unit must link checked exact candidates. Missing units or missing checks hold the post. Claim annotations now match exact wording and case. This is an accounting contract; semantic classification still depends on the model. |
| Re-running an entire post was expensive when only source review was incomplete | `verification_service.py` shares a focused source packet. `reverification.py` and `POST /posts/{id}/reverify` support an explicit one-call recheck without rewriting or generating an image. Prior failed judgments stay in history. |
| A source-only recheck could reuse a different draft's editorial approval | Rechecks bind the selected draft, slide version and passing editor assessment to the exact saved copy. Missing lineage stays held. Changes to editorial state, sources, conflicts, platform or content during a call make its result stale. Stable request IDs replay the exact operation without another call. |
| Generated images could contain unreliable lettering or imply an actual product interface | The image prompt requests an illustration without text, UI or charts. `visual_composer.py` lays out exact selected copy locally at 1080×1080, fits fonts without truncating and retains the raw illustration. Video rendering uses the illustration rather than nesting cover typography. |
| Text approval could be confused with visual correctness | `visual_review.py` binds an explicit human review to the exact image and caption. Changing either invalidates it. Instagram preparation/staging/publishing requires this acknowledgement for generated images. It does not claim automated image understanding or verify that a separately hosted JPEG has identical bytes. |
| Imported Instagram formats and scheduling did not fully use API evidence | Import maps carousel albums, individual photos and Reels to distinct formats. Scheduling can use recent API observations with verified publication timestamps, matching account/format/window/age/formula, at least two posts per slot and two slots. It records cohort/evidence IDs and falls back explicitly when evidence is insufficient. No cross-account/platform mixing or inferred Shorts classification. |
| Redundant prompts and unclear UI copy wasted context or confused review | Exact duplicate owner facts are removed only when the same complete text is already in the research packet. Verifiers omit irrelevant voice/history context while retaining exact sources. UI punctuation was repaired and a misleading fixed quality threshold was replaced with wording that applies across saved policies. |

## Actual Mesh results

The fixed diagnostic dataset contains 12 synthetic product-copy cases and **18 annotated factual assertions**. Gold labels were not sent to the model. The baseline, improved and stronger-reference replies are retained publicly in [recorded synthetic predictions](../evals/semantic/predictions.json).

| Diagnostic condition | Correct factual decisions | Missed assertions | False claim approvals |
| --- | ---: | ---: | ---: |
| GPT-4.1 mini, baseline | 12/18 | 6 | 0 |
| GPT-4.1 mini, first improved pass | 16/18 | 0 | 0 |
| Same improved replies replayed after generic attribution repair | 18/18 | 0 | 0 |
| GPT-4.1 stronger reference | 17/18 | 1 | 0 |

Four baseline responses failed the required schema. They remain failures in the denominator. The original [16/18 report](evaluation-semantic-live-initial.json) remains unchanged. The later 18/18 is **retrospective regression evidence**, not a fresh independent test or proof that the cheaper model is universally better. See [reproducible diagnostic results](evaluation-semantic-reproduced.json).

A separate frozen **eight-case holdout** was then run **once**, without tuning on its results. It covers conditional benefits, negated automation, platform scope, bundled items, price conditions, analytics periods, mixed CTA/capability wording and unsupported causality.

- **16/16 annotated factual decisions** were correct: 12 supported and four correctly withheld unsupported assertions.
- No factual assertion was missed; no case was falsely approved or falsely held.
- **Three coverage manifests were invalid.** Those responses remain blocked. They occurred on cases that already required a hold, so correct case decisions must not hide their contract failures.
- This is a small synthetic set, not a general factuality estimate, real engagement score or calibrated confidence measure.

[Holdout predictions](../evals/semantic/holdout-predictions.json) and [holdout results](evaluation-semantic-holdout.json) preserve the failures. Exact candidate scoring deliberately does not grant credit for an overlapping larger assertion unless it matches an annotated passage.

## Real saved-brand pipeline attempts

| Brand/run | Observed outcome |
| --- | --- |
| LearnAIwithSachit, compact learning-enabled run | Approved after two actual drafts. Editor opinion 9.8 → 10.0; source receipt and coverage gates passed. A saved evidence-linked learning ID reached the run. Image generation was deliberately disabled for this repeated text validation. |
| Content Tracker AI, economy writer + stronger editor | Three actual drafts; editor opinion 8.8 → 10.0. **Held** because the verifier did not fully check/classify the separate slide assertions. Two focused rechecks, including a stronger verifier, also stayed held. High editorial scores did not override missing verification. |
| Earlier larger attempts in this phase | Some stopped at the conservative spending guard before another expensive request. All charges from work already performed remain included; failed runs are not counted as accepted posts. |

These editor numbers are model opinions, not independent quality scores or predicted engagement. The successful run used GPT-4.1 for writing/editing, GPT-4.1 mini for verification and Flash-Lite for planning/visual prompting. The economy Content Tracker run used a mini writer. Permanent model defaults were not silently promoted based on these few observations.

One replacement illustration was generated through Mesh's `alibaba/z-image-turbo` route for **$0.0032**, then composed with local typography and visually inspected. It contains a warm abstract notebook illustration, legible copy and no fabricated dashboard. It remains subject to the product's human review acknowledgement before Instagram preparation. No public post or real account authorization was performed.

## Remaining work, in priority order

1. **Verifier contract reliability:** the real Content Tracker run and three holdout manifests show incomplete accounting despite useful semantic judgments. Keep those posts held. Future work should reduce duplicate output structure and evaluate a bounded targeted recovery on a new frozen set; do not weaken the gate or repeatedly rerun this holdout until it passes.
2. **Live social authorization and read-back:** six analytics adapters exist, but this phase had no configured human OAuth consent or real platform metrics. Account permissions, provider app review and HTTPS media hosting remain external blockers. Instagram single-photo publishing is implemented and mock-tested; carousel/Reel publishing and publication adapters for the other platforms remain missing.
3. **Actual business validation:** simulations show data flowing into future strategy. Neither these tests nor the historical paired benchmark establish causal engagement uplift, audience satisfaction, retention, profitable pricing or cost per accepted post across representative customers.
4. **Media understanding and quality:** audio/video attachments use supplied transcripts/notes; automatic transcription or watching is absent. Local slideshow export is not generative motion video. The new visual workflow is inspected on one illustration, not a broad product-image benchmark. Public hosted asset bytes need a trusted hosting flow or independent inspection.
5. **Hosted product hardening:** the app remains a local studio. Authentication, tenant isolation, public deployment, production load testing and live OAuth recovery are not established. Do not expose this local app as a multi-customer service as-is.
6. **Evaluation coverage:** preserve the older unfavorable content benchmark (76.667 → 75/100) and the adversarial grounding fixture's five remaining unsupported claims. Synthetic semantic gains do not erase those distinct results. Add independently reviewed brand/platform outputs and a new untouched dataset before making a broad >90 quality claim.

## Reproduce without spending

Install `requirements.txt`, then:

```powershell
$env:MESH_ENABLE_PAID='0'
python scripts/evaluate_semantic.py --check-recorded
python scripts/evaluate_grounding.py --check-recorded
python scripts/evaluate_resilience.py
python scripts/evaluate_resilience.py --check-recorded
python scripts/evaluate_content.py --check-recorded
```

The resilience runner disables normal HTTP transports and uses isolated synthetic databases, mocked platform responses and scripted agents. **271 tests passed, including 49 adversarial tests**, with zero failures, errors or skips and no model calls. All 95 Python source/test/script files compiled; seven JavaScript files passed syntax checks. It is a software/contract test, not a model quality score. Full results are recorded in [evaluation-resilience.json](evaluation-resilience.json). Recorded semantic scoring makes zero inference requests. The live execution script requires `--execute`, retains its private inherited ledger and refuses further inference after finalization.
