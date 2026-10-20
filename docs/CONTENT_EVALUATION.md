# Platform-specific editorial evaluation

Version: `platform-editorial-v2`. All rescoring is local: **zero AI calls, $0**.
The old v1 outputs/results remain unchanged for auditability. This rubric was
designed after viewing historical outputs, so this is a retrospective diagnostic,
not an independently held-out benchmark or proof that the new pipeline improves.

## Dataset and provenance

The evaluator uses every one of the eight draft/revision pairs already saved in
`docs/evaluation-live.json` (two brands, X and LinkedIn, with/without learning).
It also includes both exact-schema Instagram carousel pairs in
`docs/model-comparison-075.json` (GPT-4.1 mini and Gemini Flash-Lite). These are
historical real Mesh outputs. Invalid pilot outputs are retained in their original
ledger but excluded from the paired editorial comparison because they lack a
matching revision; they are not counted as successful generations here.

The ten pairs broaden format coverage, but still cover only two topics: AI safety
and coffee. They are not representative of a customer population. Twelve separately
authored pairs in `evals/content/cases.json` exercise all six supported rubric
platforms, including regression cases. These are fixed scorer tests, never model
outputs. There are no real YouTube, Telegram or Threads generation measurements
in this evaluation. No automatic paid generation is triggered by either script.

## Measure

Each applicable check gets one point; the score is passed checks / applicable
checks × 100. A score is an editorial proxy, not publish approval or predicted
engagement. Every result includes the raw numerator, denominator and reason for
each check. Empty text gets zero, including on normally easy length checks.

| Check | Policy |
|---|---|
| Length | Editorial character budgets: X 280, Threads 500, Instagram 2200, LinkedIn 3000, Telegram 4096, YouTube 5000 |
| Readability | Paragraph and sentence word budgets vary by platform; X has the tightest budgets |
| Hook | Opening text or first slide has 4–30 words; questions are allowed |
| Brief coverage | Every configured concept group has at least one lexical alternative present |
| CTA | A configured action cue appears in closing text/slide; no mandatory question |
| Voice cues (when supplied) | At least one configured brand vocabulary cue appears |
| Carousel structure (when requested) | Exact requested count, distinct nonempty slides, <=35 words each |
| Short-script structure (when requested) | 40–160 words and an explicit visual/scene/shot cue |

Budgets are evaluation policies, not claims about current provider API limits or
account entitlements. Counts use Python characters, not X weighted URL/emoji
counting. Script word counts include visual cues and do not measure runtime.
Keyword coverage can be gamed and cannot establish meaning, full tip completeness,
factuality or voice fidelity. Distinct slide strings can still repeat the same idea.
Source grounding is measured separately by `scripts/evaluate_grounding.py`.

## Recorded results

| Historical Mesh cohort | Pairs | Before /100 | After /100 | Improved / tied / regressed |
|---|---:|---:|---:|---|
| X | 4 | 66.666 | 62.500 | 1 / 1 / 2 |
| LinkedIn | 4 | 75.000 | 75.000 | 0 / 4 / 0 |
| Instagram carousel | 2 | 100.000 | 100.000 | 0 / 2 / 0 |
| All historical pairs | 10 | 76.667 | 75.000 | 1 / 7 / 2 |

All ten revisions changed. The mean decline is **1.667 points**; this provides no
evidence that these revisions consistently improved quality. A carousel scoring
100 only passed these shallow checks; it may still contain unsafe advice or weak
writing. Differences in applicable checks and the small cohort sizes make pooled
scores unsuitable for ranking platforms or models. No confidence interval or
statistical significance is claimed.

Four explicit matched memory comparisons are also recorded, with each learned
final score minus its same-brand/platform unlearned final score. These compare
supplied simulated-memory conditions, not real performance-driven learning or
causal engagement uplift. They must not be marketed as such.

The authored cohort deliberately contains six improvements and six regressions.
Its mean is a property of the authored examples, not evidence of studio quality.
The scorer is read-only: it neither filters poor cases from the denominator nor
changes the app's production approval rules to obtain higher benchmark scores.

## Reproduce

```powershell
python scripts/evaluate_content.py
python scripts/evaluate_content.py --check-recorded
python -m unittest tests.test_content_quality -v
```

`docs/evaluation-content-v2.json` contains per-case checks, separate cohort and
platform summaries, memory comparisons and normalized SHA-256 fingerprints of
the scorer, evaluator, authored dataset and historical sources. CI reproduces it
exactly. No timestamps or network calls introduce variation.

Before making stronger quality claims, use newly captured Mesh outputs for diverse
real briefs with fixed budgets, independently reviewed voice/factuality ratings,
and predefined evaluation expectations. Paid validation remains deferred; adding
authored fixtures does not substitute for this missing live evidence.
