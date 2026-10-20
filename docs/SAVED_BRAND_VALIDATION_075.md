# Saved-brand live validation — 20 October 2026

Both saved brands were exercised through the production Mesh agents, using their
existing profiles learned from three samples each. Customer account credentials
were not copied into the isolated validation database. No public publishing or
live social engagement collection occurred.

## Combined spending

| Item | USD |
|---|---:|
| Earlier fictional-product validation | 0.16066170 |
| These two brands, including failed attempts and corrections | 0.17901520 |
| **Cumulative total** | **0.33967690** |
| Authorized combined limit | 0.75000000 |
| Unused allowance | 0.41032310 |

The sum of known request charges matches the cumulative account balance decrease.
The continuation inherited every previous request, unresolved reservation, price
and the original starting balance. Its private ledger links to the original
ledger by SHA-256; the original report remains unchanged. The $0.70 internal
dollar guard was retained. The explicitly authorized continuation permitted up
to 130 cumulative requests and three cumulative images, including the earlier
validation. Actual totals: **129 requests**, **three images**; 51 requests and
two images belong to this continuation. Existing profiles were reused without
paid voice relearning. There were no paid audio/video/embedding calls.

## Outcomes, including holds

| Case | Primary content | Source verification | Learning-driven second post |
|---|---|---|---|
| LearnAIwithSachit / LinkedIn | Approved after genuine revision | Passed | Approved; saved learning ID applied; output changed |
| Content Tracker AI / Instagram | Approved after genuine revision | Passed | Changed and applied saved learning, but held for review |

Both primary posts scored **100 → 100** on the unchanged editorial proxy.
Real revisions occurred, but saturated structural/lexical checks showed no score
increase. These scores do not establish semantic quality, factual accuracy,
brand fidelity, visual quality or engagement improvement.

Content Tracker AI's second post was accepted by its editor but its verifier
marked paraphrases thin and a promotional invitation unsupported. Some reasons
appear overly literal, conflating semantic support with identical wording, and
the invitation judgment conflicts with the intended nonfactual-CTA guidance.
The hold is preserved, not overridden to obtain a passing result. Verifier
calibration therefore remains a limitation; this is not a claim that those
passages are objectively false.

Both primary posts were stored, scheduled and moved through the queue handoff.
Simulated engagement was explicitly labeled and interpreted by live learning
agents. Learning changed subsequent output; no real audience uplift was measured.
Product capability evidence came from the owner's saved samples. Marketing
language in those samples is not independent evidence of product effectiveness.
Successful diagnostics used GPT-4.1 writer/editor/verifier overrides, not a
validation of the economical default models.

## Media and defects found

Both brands received real matching images through Mesh. Both local motion
slideshows decoded successfully at **720×1280 with AAC music**:

- LearnAIwithSachit: 6 seconds, 637,609 bytes; 71 recorded audit events.
- Content Tracker AI: 8 seconds, 726,432 bytes; 91 recorded audit events.

Poster inspection confirmed readable overlaid captions. Content Tracker AI's
generated illustration contains garbled small text and an illustrative chart;
it needs visual review before sharing. It is **not actual analytics or a verified
product screenshot**. Successful image generation does not mean the visual passed
a quality gate. No generated asset was publicly posted.

Initial failures are retained: unsupported embellishment exhausted the first
LearnAIwithSachit run's correction capacity; Content Tracker AI's verifier output
truncated at 1,000 tokens. A shorter content brief, compact verifier guidance and
a bounded 1,600-token verifier ceiling enabled successful primary runs. The
renderer also incorrectly stopped at the first font size for long brand/tool
names; it now tries smaller sharp fonts without truncating the caption.

## Records and offline verification

The [sanitized summary](validation-saved-brands-075-summary.json) contains costs,
quality checks and outcomes. Full outputs, source quotations, billing ledger,
HTML evidence reports, audit exports and media remain local in gitignored
`data/saved-brand-validation-075/` and `data/videos/`. Raw customer samples and
generated copy are not committed in this continuation.

After the changes **153 tests passed** with paid calls disabled. One earlier
full-suite attempt encountered a Windows temporary-file replacement permission
error; the targeted tests and subsequent complete suite passed. Both historical
recorded evaluations also reproduce independently without paid calls.

The opt-in runner is `scripts/validate_saved_brands.py`. A normal invocation on
the finalized ledger exits without inference; phase flags preserve completed
steps. Do not delete/reset the private ledger to repeat a paid experiment under
the same budget. Any later paid work must continue from this latest cumulative
ledger rather than the older fictional-product ledger.
