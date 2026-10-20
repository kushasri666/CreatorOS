# Grounding and completeness evaluation

Dataset: `creatoros-product-grounding-v1` · 16 cases · 24 questions.

**Authored synthetic stress fixtures. These are not live model-quality scores.**

Before/after applies the production evidence-receipt filter to the same fixture responses; it does not call the writer or verifier.

| Measure | Submitted fixtures | After receipt filtering |
|---|---:|---:|
| grounded claim fraction | 10/22 (45.5%) | 10/17 (58.8%) |
| citation integrity | 17/22 (77.3%) | 17/17 (100.0%) |
| annotation coverage | 22/22 (100.0%) | 17/17 (100.0%) |
| required fact completeness | 10/18 (55.6%) | 10/18 (55.6%) |
| question completeness | 11/24 (45.8%) | 11/24 (45.8%) |
| abstention accuracy | 2/8 (25.0%) | 2/8 (25.0%) |

Unsupported claims remaining after the receipt filter: **6**. A valid quotation alone cannot establish semantic support.

AI calls: **0**. Validation spend: **$0**.

## Limitations

- Default responses and source snapshots are authored synthetic stress fixtures, not live Mesh outputs or measured model quality.
- Before/after compares submitted fixtures with the actual deterministic evidence-receipt filter; it does not simulate semantic verification or a writer correction.
- Gold annotations are authored separately. The filter never receives them. Grounding needs both correct gold support and valid source quotations.
- Unknown wording is labeled unscored and reduces the grounding lower bound; annotate legitimate paraphrases before interpreting a model comparison.
- Empty output has no claim-rate denominator (null), and receives zero completeness on answerable questions. Missing cases are rejected.
- Abstentions are scored only if supplied in the response, never synthesized from gold answers.
- Completeness is relative to these specified product questions, not all possible facts. This small authored set is not independent human or production evaluation.
- No live semantic-verifier accuracy, brand-voice quality, visual quality or engagement uplift was measured.
