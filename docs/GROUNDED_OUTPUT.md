# Grounded, cited output

Every newly generated live post stores a `grounded_report` alongside its final
caption and slides. Final post displays a structured report of supported factual
claims with clickable `[S1]` references, exact evidence quotations and source
snapshots. `GET /posts/{id}/evidence-report` rebuilds the report from stored records
without an AI call, provider request or credit spend. Historical posts and offline
fixtures do not silently inherit verification.

## Evidence contract

- The writer supplies claim-to-source mappings. The Mesh Verifier inspects factual
  assertions in the caption and slides, including uncited claims. It must assess
  the writer's exact cited sources and provide verbatim supporting quotations.
- Application code requires each quote to occur literally in that source's saved
  excerpt. Unknown IDs, a quote borrowed from another source, paraphrased or
  invented quotes, missing evidence and omitted writer-cited claims fail closed.
- The report includes only supported claims with valid receipts. Thin or
  unsupported draft claims appear separately as withheld claims. Unresolved
  verification prevents new live content from being approved. The existing bounded
  retrieval/rewrite/re-check loop handles correction.
- Each receipt records its quote position and excerpt SHA-256. Source snapshots
  retain the actual retrieved URL and retrieval time, uploaded document ID and
  document hash/excerpt position, or provider metric ID/account/window. These
  details come from saved retrieval records, not model-generated URLs.
- An excerpt changed after verification invalidates its receipt. Appending or
  changing final copy invalidates the previously saved report's content hash.
  Duplicate source IDs also prevent the report from passing.

The social caption stays suitable for its platform. The adjacent cited report
contains the evidence references; creative phrasing, opinions and calls to action
are not presented as factual research. Brand-owner facts and uploaded documents
are labeled by origin, not described as independent confirmation.

## Validation

On 20 October 2026, the following local command passed **15/15 tests**: eight
grounding integrity cases, three verification-loop cases and four controller
cases. The fixtures are explicitly synthetic. **0 Mesh calls; $0 validation
spend.** Python compilation, JavaScript syntax and whitespace checks also pass.

```powershell
python -m unittest tests.test_grounding tests.test_verification_loop tests.test_improvement -v
```

These are contract and integrity results, not a measurement of live factuality.
Quote matching proves that cited text exists in a retrieved snapshot. The
Mesh Verifier still judges whether it actually supports the claim; it may miss
claims or make entailment errors, and a retrieved source can itself be wrong.
CreatorOS therefore does not promise that an LLM can never invent a claim. Live
evaluation of detection/entailment accuracy remains outstanding and was not run
because paid validation is currently deferred.
