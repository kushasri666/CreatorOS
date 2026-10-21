# Submission readiness against the supplied rules

Updated 21 October 2026. Source and earlier evaluation reports are committed to
the [public repository](https://github.com/kushasri666/CreatorOS). Submission
eligibility still depends on the organizer's checks and dashboard accepting the
final pushed commit. This document review made no Mesh or social-platform calls.
The current [gap validation report](GAP_VALIDATION.md) records the additional
repairs, measured outcomes and cumulative spending; historical results below
remain separate.

| Criterion | Evidence and limit |
| --- | --- |
| Python backend | FastAPI in `main.py`; dependencies in `requirements.txt` |
| Mandatory Mesh | Sole live client in `workflow.py`, fixed Mesh URL, environment key; no provider fallback |
| Real multi-agent work | Executable custom state graph with named research, strategy, writing, editing, verification, correction and visual nodes; separate brand/learning prompts and deterministic scheduler |
| Editor improvement loop | Actual previous text/slides and edits passed into revisions; a genuine content change is mandatory; bounded revision/replanning and source-retrieval loops; failed gates withhold approval |
| Domain core: performance loop | Validated post-linked metrics → normalized comparison → evidence-linked hypothesis → matching future strategy/writer context |
| Learned brand voice | Live analyst uses at least three distinct supplied posts; exact profile snapshot reaches agents |
| Visuals and scheduling | Mesh illustration generation with locally composed exact copy, retained prompt and explicit human visual review before Instagram preparation; persistent timestamped queue and once-only handoff |
| Real ingestion and persistence | Brand samples/documents/transcripts and metrics retained with provenance in SQLite; six official-platform analytics adapters exist, but real-account authorization/read-back is not live-validated |
| Evaluation exists | Preserved historical Mesh outputs, platform rubrics, grounding fixtures and adversarial software tests; additional live semantic evaluation is reported separately in the gap validation report |
| Auditable decisions | Post-linked strategy, draft versions, scorecards, edit requests, routing, visual prompt, slot basis, metric evidence and learning context |
| No fake production features | Normal mode selects Mesh and fails when spending is locked. Fixtures require explicit development mode and are labeled; there is no silent fallback |
| Secret handling | `.env` and `mesh.env` ignored; no secret values printed during checks; source kept separate from local credentials |
| Public repository | Source and earlier reports have been pushed; include the final intended changes/reports and verify that exact remote commit before submission |
| Official CI eligibility | Official workflow is present; verify both required secrets and the complete organizer result on the final pushed commit. A passing local test suite alone does not establish eligibility |
| Real publishing | Optional Instagram single-photo API implementation with explicit account/post confirmation, disabled-by-default flag and duplicate protection. Live account access is unverified; carousel/Reel and other-platform publishing are not implemented |
| Video/deployment | Local 720p slideshow export, original synthesized music and sharp fullscreen preview implemented; deployment not performed |

## Honest measured results

The original saved real generation dataset contains eight cases. Under the preserved v1
heuristic, initial-to-revised mean is **1.5/5 → 1.625/5**: one improved case, seven
unchanged, zero regressed; all revisions changed text. The memory condition's mean
score is **0.25 lower** than the paired no-memory condition. These numbers do not
prove that feedback improves quality or engagement. The rubric also has known bias
towards numbered lists and a strict 280-character ceiling across all platforms.

These are historical outputs, not live validation of subsequent changes. Reproduce
them without model calls using `python evaluate.py`. The platform-specific v2
benchmark, [budgeted live runs](LIVE_VALIDATION_075.md),
[saved-brand runs](SAVED_BRAND_VALIDATION_075.md),
[adversarial software evaluation](TOUGH_VALIDATION.md), and
[current gap validation](GAP_VALIDATION.md) measure different things. Passing
scripted tests or lexical editorial checks does not establish semantic accuracy,
brand fidelity, visual quality or engagement uplift. Unfavorable results and held
posts remain part of the evidence.

## Required before submitting

1. Review and push the final intended source/evidence files; leave local keys,
   customer samples, dependencies and databases ignored.
2. Confirm GitHub Actions secrets `MESH_API_KEY` and `SUBMISSION_TOKEN` exist, and
   verify the official workflow and organizer dashboard accept that exact commit.
3. Describe the live social-account blocker accurately. Instagram requires a
   reviewed developer app/permissions, human OAuth consent and a public HTTPS JPEG
   URL before publishing can be exercised. Other providers have their own access
   requirements. No working adapter or successful test double proves live access.
4. Preserve explicit labels for simulated performance, model opinions, independent
   proxy rubrics and human review. A changed draft does not demonstrate audience
   uplift; human visual acknowledgement is not automated visual verification.

Paid validation must continue the existing cumulative authorization ledger rather
than start a fresh allowance. The gap validation report records its final total.
