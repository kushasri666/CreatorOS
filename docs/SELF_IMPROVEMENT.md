# Bounded outer self-improvement loop

The supplied diagram inspires control flow; this is a content-quality loop, not an
autonomous web-research agent. The existing performance-feedback loop still learns
separately from actual observations. All live AI remains behind the Mesh gateway.

Each writer/editor pass records the draft, slides, criterion scores, concrete
edits, issues, score change and preserved brief/voice/evidence references.
The coordinator then chooses:

- **REFINE:** apply editor feedback to the actual draft and slides. Even a strong
  first draft must undergo a changed revision.
- **ACCEPT:** a revised draft averages at least 8/10, has no criterion below 6/10,
  and meets the platform's deterministic character limit.
- **RESTART:** if the second draft stalls or regresses and has not passed, revisit
  the strategy once. The strategist receives the original brief, voice, evidence,
  last draft and critique. This consumes the remaining third draft slot; it never
  resets the budget or erases rejected work.
- **NEEDS_REVIEW:** stop after at most three drafts. Preserve the strongest revised
  candidate, withhold approval/scheduling, and skip visual/image generation.

An accept is not a claim of factual correctness. `confidence_score` is the editor
average divided by ten and is explicitly uncalibrated. It does not measure truth,
real audience response or probability of success. Content still needs human review.
There is no extra LLM confidence judge or automated broad research/citation fetching.

Normal success uses the existing seven calls including an image. A recovery path
uses at most ten logical generation calls: two strategist, three writer, three
editor, one visual director, one image. Mesh's existing global call cap still
applies, including optional format repair calls. No paid validation was performed.

The agent log exposes every `improvement` decision. Self-check scores shows the
decision trajectory, selected version, score and preserved state. Older posts have
no fabricated assessments; regenerate only when paid generation is authorized.

## Reproduction and measured boundaries

`python -m unittest discover -s tests -v` passes 37 local tests. New cases cover
successful refinement without extra calls, one strategy restart followed by
recovery, exhaustion with no image spend, preserving a stronger earlier revision,
and preventing a high average from hiding a very weak criterion or length failure.

`python scripts/evaluate_improvement.py` reproduces four labeled scripted cases in
`evaluation-improvement.json`. These are routing measurements, not new AI quality
results. Existing historical real-output evaluation numbers remain unchanged.

![Scripted browser demonstration](self-improvement-preview.png)
