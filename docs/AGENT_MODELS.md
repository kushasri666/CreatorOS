# Economical model selection — 20 October 2026

Update: the [subsequent live text comparison](MODEL_COMPARISON_075.md) used
$0.0123379 of one combined $0.75 allowance. The selection rationale below records
the initial pre-benchmark decision; read the comparison for current limitations,
including unsupported analytics attributions and DeepSeek reasoning truncation.

Operating decision after the comparison: retain the selected explicit routes.
Unrestricted `auto` selection is rejected rather than silently changing models.
No extra judge, router model or premium escalation is added. API-derived format
comparisons remain deterministic; LLM explanations are tentative experiments.
This is the current cost/quality compromise, not a universal optimum.

Source: authenticated **GET https://api.meshapi.ai/v1/models**, metadata only.
The compact catalogue snapshot is `mesh-model-catalog-selection.json`.
Listing proves advertised availability/capabilities, not successful inference,
content quality or access under every account/key policy. No paid benchmark ran.

| Agent | Selected Mesh ID | Input / output USD per million tokens | Reason for selection |
|---|---|---|---|
| Brand analyst | `openai/gpt-4.1-mini` | $0.40 / $1.60 | Preserve nuanced voice rules; profile reused rather than inferred per post |
| Strategist | `google/gemini-2.5-flash-lite` | $0.10 / $0.40 | Short structured angle/hook from supplied evidence; inexpensive initial choice |
| Writer and rewriter | `openai/gpt-4.1-mini` | $0.40 / $1.60 | Prioritize instruction following and publishable copy; editor gate remains |
| Editor | `openai/gpt-4.1-mini` | $0.40 / $1.60 | Preserve concrete prose critiques plus five rubric scores |
| Verifier | `openai/gpt-4.1-mini` | $0.40 / $1.60 | Check every factual claim against its cited evidence; fail closed on unknown or unchecked citations |
| Follow-up | `openai/gpt-4.1-mini` | $0.40 / $1.60 | Reuse saved research for optional questions; independent verifier and a two-call client ceiling |
| Visual director (prompt) | `google/gemini-2.5-flash-lite` | $0.10 / $0.40 | Compact image brief from selected content |
| Learning analyst (interpretation) | `google/gemini-2.5-flash-lite` | $0.10 / $0.40 | Explain supplied statistics as tentative hypotheses |
| Image generation | `openai/gpt-image-1-mini` | Variable by image tokens/quality | Mesh documents this endpoint explicitly; 1024-square, explicit medium quality |
| Coordinator, metric arithmetic, scheduling, connectors, local video/music | Python / official APIs | No AI tokens | Keep permissions, counting, queueing and spending bounds deterministic |

These are **provisional cost-conscious selections**, not measured best-in-class
winners. Same-family writer/editor may share biases; switching editor to a
different family is a benchmark question, not a proven improvement. Existing
historical quality results used older models and do not validate these routes.

## Other models considered

- `deepseek/deepseek-v4.1-flash` is listed with chat + structured output and
  $0.30 input / $1.20 output per million tokens. It remains a strategist/writer
  challenger. Thinking defaults, output-budget behavior and writing quality need
  a bounded compatibility/quality test before activation. No guessed DeepSeek alias
  or unverified reasoning parameter is enabled.
- `typesafe/jev-1.13` is listed at $0.042 per million input tokens and free output,
  but is an **evaluation** model served at `/v1/evaluate`, not chat completions.
  It cannot write prose, editorial edit instructions or image prompts. The current
  editor contract needs these, so Jev is not silently substituted for it.
- FLUX generation routes are listed and may cost less per image, but their image
  quality and provider-specific handling have not been validated in this app.
  No claim that GPT Image Mini is the cheapest image route is made.

## Controls and reproducibility

`model_policy.py` maps roles to model IDs and output-token ceilings. Explicit
role settings override `MESH_TEXT_MODEL`; if neither is set, role defaults apply.
All routes still use Mesh's fixed base URL and the existing paid-call lock.
Writer/rewriter share a route. No automatic premium escalation or extra calls.

Role ceilings: brand 1,400; strategy 700; writer 1,600; editor 900; visual prompt
400; learner 500; verifier 1,600. The verifier ceiling was increased after a live
structured response truncated at 1,000 tokens; duplicate-check guidance also
reduces unnecessary output. `MESH_MAX_OUTPUT_TOKENS` can lower any ceiling; other local
caps are preserved. Lower ceilings bound output but can truncate difficult outputs;
they are not proof of improved token efficiency. Invalid output fails visibly.

The response cache key now includes model selection and output cap, preventing
reuse across policy changes. Audits include requested/returned models, actual
input/output tokens when reported, and configured token ceiling.

Local `.env` was updated only for role/model selections; credentials, global token
cap, paid-generation enablement and paid-media locks were preserved. The running
server must reload to pick up the new environment. Prior saved posts are preserved.

41 local tests pass, including routing precedence, matching catalogue capabilities,
Jev misuse rejection and SDK model/token-limit propagation. SDKs are mocked.
No model calls were made. A future human-reviewed test set should measure brand
voice, factuality, revision quality, schema pass rate, latency and actual **cost per
accepted post**, including failed attempts, before promoting these as optimal.

References: [Mesh models](https://developers.meshapi.ai/docs/reference/models),
[Mesh image generation](https://developers.meshapi.ai/docs/capabilities/image-generation).

## Subsequent gap validation

The [21 October gap report](GAP_VALIDATION.md) records actual economical-verifier,
stronger-reference and saved-brand runs within the same combined $0.75 ledger.
Mini achieved 16/16 factual decisions on a small untouched holdout, but three
coverage manifests failed. The stronger reference also missed an assertion in
the diagnostic set. This does not justify automatic premium escalation or a
universal model ranking. The successful new brand run used a stronger writer
and editor; another run with a mini writer stayed held for incomplete source
coverage. Defaults remain unchanged. Exact source packet compaction and local
image typography save redundant work without bypassing verification or sending
AI calls outside Mesh.
