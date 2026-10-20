# Product-content self-evaluation

CreatorOS now has a reference-based grounding/completeness benchmark alongside
its historical copy heuristics and controller contract tests. The benchmark
includes **16 scenarios, 24 questions and 18 required facts** across Instagram,
YouTube, LinkedIn, Telegram, Threads and X. Source snapshots are deliberately
synthetic product documents and account observations; none are labeled real
customer analytics or live web retrievals.

## What is measured

| Measure | Definition |
|---|---|
| Grounded claim fraction | Claims matching a reference fact, with valid verbatim evidence covering every required premise, divided by all submitted factual claims |
| Citation integrity | Claims whose cited IDs exist and whose quotes occur verbatim in those source excerpts, divided by all submitted claims |
| Required-fact completeness | Distinct required reference facts grounded in the output, divided by all required facts; duplicates give no extra credit |
| Question completeness | Answerable questions with all required facts grounded, plus unanswerable questions explicitly abstained from without an invented answer, divided by all questions |
| Abstention accuracy | Evidence-gap questions correctly abstained from, divided by all evidence-gap questions |
| Annotation coverage | Submitted claims with an accepted reference wording or explicit unsupported-claim annotation, divided by all claims |

Numerators and denominators accompany every percentage, per case, per platform
and in the aggregate. Aggregates use summed counts, not an average of per-case
percentages that could hide short/empty cases. Claims outside accepted wordings
are `unscored_needs_annotation`, not automatically described as hallucinations;
they lower the grounding bound and need annotation before a model comparison is
interpreted. Default fixture annotation coverage is 100%.

An empty report gets a null claim fraction, **not 100%**. It still gets zero fact
and question completeness for answerable questions. Missing cases, duplicate
claims, wrong dataset IDs and malformed reference support are rejected. Saying
"I don't know" and also inventing an answer does not earn abstention credit.

## Data and separation

- `evals/grounding/questions.json`: briefs, source packets, questions, reference
  facts/accepted wording, exact supporting passages and unsupported assertions.
- `evals/grounding/fixtures.json`: independently stored authored candidate
  reports, with deliberately incomplete answers, bad citations and some
  incorrect supported-verdict judgments. They are **not generated model outputs**.
- `self_evaluation.py`: scoring and comparison. `filter_prediction` receives
  only the submitted report and sources, never reference answers; it exercises
  the actual `grounding.build_report` production filter. Reference annotations
  are consulted only afterward to score the resulting output.

The annotations were authored during development; they have not been reviewed
by an independent human panel. This is a small controlled stress set, not a
representative production distribution. Source-injection, stale specs,
multi-premise citation gaps, incorrect metric denominators, missing reach,
incomparable reporting windows, media-note provenance and empty output are
explicit cases. Valid quotes backing unrelated assertions remain an important
semantic-verification failure mode.

## Recorded results — 20 October 2026

| Measure | Submitted fixtures | After production receipt filtering |
|---|---:|---:|
| Grounded claims | 10/22 (45.5%) | 10/16 (62.5%) |
| Citation integrity | 17/22 (77.3%) | 16/16 (100%) |
| Required-fact completeness | 10/18 (55.6%) | 10/18 (55.6%) |
| Question completeness | 11/24 (45.8%) | 11/24 (45.8%) |
| Correct abstention | 2/8 (25.0%) | 2/8 (25.0%) |

The filters remove six claims with broken citation receipts while preserving
the ten fully grounded facts. It does not fill missing facts or rewrite content.
Five annotated unsupported assertions and one incompletely cited multi-source
assertion remain. Therefore **100% citation integrity is not 100% factuality**.
The semantic Mesh verifier is responsible for detecting such unsupported
assertions in real runs; its live accuracy has not been measured by this test.
These results do not validate the full editor/retrieval/writer loop's quality,
brand voice, media quality or engagement improvement.

`docs/evaluation-grounding.json` records every assessed claim, missing fact,
question result, platform subgroup and source/code fingerprint.
`docs/evaluation-grounding.md` is generated from the same result. In the app,
**Self-evaluation** displays these results and flags stale code/data fingerprints.
`GET /evaluation/grounding` exposes the saved result without an AI call.

## Reproduce and prevent silent regressions

```powershell
python scripts/evaluate_grounding.py
python scripts/evaluate_grounding.py --check-recorded
python -m unittest tests.test_self_evaluation -v
```

All these commands use local files only and require no API key. The evaluator
and its tests use Python's standard library plus the production grounding
module. Validation spend is **$0**, with **0 AI calls**. The dedicated
`.github/workflows/grounding-evaluation.yml` runs the scoring tests and
`--check-recorded` on pushes and pull requests. That check fails if committed
metrics, per-case decisions or fingerprints differ from recomputation. It is a
reproducibility/regression check, not a claim that quality targets are achieved.
Text fingerprints normalize CRLF/LF so Windows and Linux reproduce the result.

Earlier local validation on 20 October 2026, before the state-graph/source-review expansion: **92/92 repository tests passed**,
including ten evaluator arithmetic/anti-gaming tests and the API's labeled-result
integration test. The recorded benchmark reproduced exactly. Python compilation,
JavaScript syntax and whitespace checks passed. The API test fixture was explicitly
marked offline and the account-isolation fixture was updated for the existing
required product-name field; neither test claims live verification. No Mesh or
social-provider calls were made during this validation.

## Evaluate captured Mesh responses later

```powershell
python scripts/evaluate_grounding.py --export-prompts data/eval-prompts.json
python scripts/evaluate_grounding.py --predictions data/captured-responses.json --output data/captured-evaluation.json
```

The prompt export removes reference facts, supported/unsupported labels,
answerability flags and required-fact IDs. It includes briefs, questions and
source packets only. The command does not send them anywhere. Any later paid
generation must be separately authorized, capped and routed through Mesh.
No new live benchmark was run while paid validation is deferred.

Captured predictions use this shape for every case ID (see the authored fixture
file for the full schema):

```json
{
  "dataset_id": "creatoros-product-grounding-v1",
  "origin": {"kind": "captured_mesh_outputs", "capture_note": "Record models, time and spend here"},
  "cases": [{
    "id": "specs-and-health",
    "text": "Brew Mini has 12 grind settings.",
    "claims": [{
      "text": "Brew Mini has 12 grind settings.",
      "source_ids": ["S1"],
      "evidence": [{"source_id": "S1", "quote": "Brew Mini features 12 grind settings and steel burrs."}],
      "question_ids": ["Q1"]
    }],
    "abstentions": []
  }]
}
```

The abbreviated example is illustrative; all 16 case IDs are required to score
a complete run. Origin metadata is supplied by the caller, not independently
verified by the scorer. Review unseen paraphrases and extend accepted aliases
before reporting a real model-quality result. Keep captured customer/private
content under gitignored `data/`, rather than publishing it in the benchmark.

## Source-conflict guard update

The current production filter also withholds unqualified numeric claims disputed across sources. On the same cases, this removes one additional stale-spec assertion. The preceding receipt-only results are preserved in [the evaluation history](evaluation-history/receipt-filter-v1.json); the reference questions and candidate responses are unchanged. See [structured research](STRUCTURED_RESEARCH.md) for implementation and limits.

After the structured graph, source-conflict guard, HTML export and saved-research follow-ups were added, the complete suite passed **109/109 tests** and the current benchmark reproduced exactly. No live AI or provider calls were made.
