# Agent loop, native adaptation, publishing and feedback

## Implementation and evidence

| Requested capability | Implementation | Validation boundary |
|---|---|---|
| Structured agent framework | Custom `StateGraph` with 12 named handlers, validated edges, a 48-step ceiling, writer/editor refinement, one strategy restart and a bounded research retry | Executed in tests and stored as a per-run trace; not LangGraph |
| One idea, native platform adaptations | Six explicit `format_contract` policies; saved-post adaptation keeps the brief, brand, product inputs and selected documents, while running a new platform-specific pipeline | Context/route tests and historical outputs on three platforms; no newly generated live examples on all six |
| Platform API publishing with read-back | Instagram single-image container creation, readiness check, explicit publish, returned media ID registration, periodic official-API metric collection | Mock HTTP integration exercises publication followed by the real collector; no successful live account publication is claimed |
| Performance-driven next output | Comparable account-scoped observations yield a tentative format experiment, with winning/alternative formats, means, sample sizes and evidence IDs. Versioned memory reaches the next strategist/writer/editor context | Tests reverse observations and verify the derived lesson, next strategy and draft change; agents/HTTP are scripted/mocked in this test, so it proves wiring rather than LLM efficacy or engagement uplift |

## Adapt an idea

Open a saved post's **Final post** tools, select another platform and choose
**View format plan · free** or **Create adapted post**. Generation uses one normal
Mesh pipeline, not six automatic runs. The paid lock and ten-call cap remain in
force. The new post records `adaptation_of` and its own source/agent audit.

API:

- `GET /posts/{id}/adaptation-plan`: six native format contracts; zero AI calls.
- `POST /posts/{id}/adapt` with `{"platform":"youtube","use_learnings":true}`:
  creates one linked background run. This can spend credits when live Mesh is
  enabled; it never publishes. Same-platform requests are rejected.

Adaptation is deliberately from the original **brief**, not a blind copy of the
old caption. The previous generated text is not promoted to factual evidence.
Brand voice uses the current learned profile and sources are retrieved/verified
again for the target run. Cross-platform account selection is validated normally.

## Publishing coverage

Only Instagram single-image publishing is implemented. Instagram carousels,
Reels and publishing to LinkedIn, YouTube, Telegram, Threads and X are **not**
implemented. Their available read connectors do not imply publishing support.
The scheduler is a persistent queue/manual handoff, not unattended publication.

Instagram needs an authorized compatible account/application and publishing
permission, `INSTAGRAM_ENABLE_PUBLISHING=1`, a publicly accessible JPEG, and
confirmation of the account/caption/asset. See `INSTAGRAM_PUBLISHING.md` for setup.
Once publication succeeds, its provider media ID is automatically linked to the
post so the enabled collector can poll engagement. No real post was published
while implementing or validating these changes. Account/API readiness remains
an external authorization requirement, not a test-fixture success.

## What learning changes

`social.dashboard` groups observations by brand, platform, account, source,
reporting window, age bucket and available-metric formula. It requires at least
two posts in each of two formats and a strict mean-rate difference before forming
a tentative experiment. Ties and insufficient evidence produce no experiment.
`learn_from_observations` persists API-derived lessons only; sample data never
becomes API evidence. `memory.retrieve` checks versions/freshness/scope and supplies
the structured experiment to agents. Experiment fields participate in the memory
integrity hash, so changing the selected format without a new grounded version
is detected. Stale or disconnected-account evidence is withheld.

Agents receive both the experiment and native format requirements. A winning
historical format is an experiment suggestion, not permission to ignore an
explicit user request or label a carousel as a generated video. Learned format
differences do not justify unsupported causal claims about wording, CTA or tone.

## Repeatable validation

```powershell
python -m unittest tests.test_feedback_cycle tests.test_instagram_publish tests.test_research_features -v
python scripts/evaluate_content.py --check-recorded
python scripts/evaluate_grounding.py --check-recorded
```

All test provider responses and adaptive-agent outputs are explicitly synthetic
and isolated in temporary databases. The tests execute production aggregation,
memory, graph, publication and collection code around those boundaries. They do
not spend Mesh credits, contact social accounts or publish live content. Real
model sensitivity to memory was observed in earlier small historical comparisons,
but no sustained live-account engagement improvement has been demonstrated.
