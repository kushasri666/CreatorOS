# Submission readiness against the supplied rules

Status: **local implementation; not submission-ready until source is pushed and the
official critical checks pass.** No Mesh requests were made for this audit.

| Criterion | Evidence and limit |
| --- | --- |
| Python backend | FastAPI in `main.py`; dependencies in `requirements.txt` |
| Mandatory Mesh | Sole live client in `workflow.py`, fixed Mesh URL, environment key; no provider fallback |
| Real multi-agent work | Distinct strategy, writing, editing, visual and learning prompts; deterministic evidence-based scheduler |
| Editor improvement loop | Actual previous text and edits passed into revisions; changed text mandatory; bounded routing; below-threshold work withheld from queue |
| Domain core: performance loop | Validated post-linked metrics → normalized comparison → evidence-linked hypothesis → matching future strategy/writer context |
| Learned brand voice | Live analyst uses at least three distinct supplied posts; exact profile snapshot reaches agents |
| Visuals and scheduling | Live Mesh image generation, retained prompt, persistent timestamped queue and once-only handoff |
| Real ingestion and persistence | User-supplied historical samples and metrics, stored with IDs, source labels, profile versions and audit events in SQLite |
| Evaluation exists | Eight preserved actual Mesh outputs; default evaluator reproduces their scores, records source hash, raw before/after and regressions, and makes zero AI calls |
| Auditable decisions | Post-linked strategy, draft versions, scorecards, edit requests, routing, visual prompt, slot basis, metric evidence and learning context |
| No fake production features | Normal mode selects Mesh and fails when spending is locked. Fixtures require explicit development mode and are labeled; there is no silent fallback |
| Secret handling | `.env` and `mesh.env` ignored; no secret values printed during checks; source kept separate from local credentials |
| Public repository | An origin remote is configured, but implementation files are currently untracked/uncommitted locally. They must be pushed for evaluation |
| Official CI eligibility | Workflow file retained. GitHub secret configuration and a passing current official run are not verified |
| Real publishing | Not implemented; optional bonus. UI accurately calls the result a manual publishing handoff |
| Video/deployment | Local 720p slideshow export, original synthesized music and sharp fullscreen preview implemented; deployment not performed |

## Honest measured results

The saved real generation dataset contains eight cases. Under the preserved v1
heuristic, initial-to-revised mean is **1.5/5 → 1.625/5**: one improved case, seven
unchanged, zero regressed; all revisions changed text. The memory condition's mean
score is **0.25 lower** than the paired no-memory condition. These numbers do not
prove that feedback improves quality or engagement. The rubric also has known bias
towards numbered lists and a strict 280-character ceiling across all platforms.

These are historical outputs, not live validation of subsequent changes. Scripted
fixture scores are test-only evidence and are excluded from the main quality result.
No model calls are needed to reproduce this report's scores with `python evaluate.py`.

## Required before submitting

1. Review and commit all intended source and evidence files; leave local keys,
   dependencies and databases ignored. Push the implementation to the public repo.
2. Configure GitHub Actions secrets `MESH_API_KEY` and `SUBMISSION_TOKEN`, and verify
   the official workflow passes all critical checks on that exact pushed commit.
3. State the evaluation limitations and manual-publishing boundary accurately.
   Do not present fictional scenario metrics or scripted scores as real performance.

Further paid validation remains subject to the owner's explicit authorization and
should use a small, specified budget rather than a broad generation sweep.
