# Working toward scores above 90

The independent `platform-editorial-v2` rubric and its historical results remain
unchanged: **76.667 → 75.000/100**, ten recorded Mesh pairs. Nothing in this update
establishes a new achieved benchmark score or engagement lift. No paid calls made.

The diagnostics show concrete weaknesses in the saved final posts:

| Area | Change in generation |
|---|---|
| Weak or overlong openings | Writer and editor receive an explicit 4–30 word hook target and measured feedback |
| Lost brief/audience | Contract requires preservation of the actual topic, product and requested audience; brand metaphors cannot replace them |
| Weak closing action | Editor checks the relevance of one closing action/question and brand CTA habits |
| X overlength | Local count, 240-character drafting preference, 280-character gate; content is never blindly truncated |
| Readability | Per-platform paragraph/sentence diagnostics feed the next existing writer call |
| Carousel structure | Distinct slides, 3–10 count, <=35 words each; promised tip completeness remains a semantic editor responsibility |
| Regressing revisions | Newly lost passing local checks block approval, even when the editor gives a high opinion score |
| Weak dimensions hidden by averages | Live editor average target 9.1, individual floor 8; low-scoring work stays for review |

`editorial_guidance.py` creates the compact contract and zero-cost observations.
`pipeline_graph.py` supplies these to the existing agents, persists them in the
post and audit, and routes targeted repairs. No extra judge agent, provider, or
model escalation is introduced. A third draft may use available capacity, keeping
the existing ten-call maximum and reserving independent source verification.
The original shorter success path remains when a revised draft passes. Verification
failures retain their real research retry and fail-closed behavior.

The higher live editor threshold is an opinion-based approval policy, **not** a
new independent rubric measurement. The historical data is never rewritten, the
scorer is not relaxed, and passing scripted scores in control-flow tests do not
count toward the benchmark. Stricter targets can increase review holds; they do
not guarantee good output or justify unsupported claims.

The evaluator's 90+ target should be validated later on a fixed set of newly saved
outputs, reporting all cases including failed/held runs, before/after scores,
source verification and independently reviewed brand voice. Paid validation remains
deferred. Existing historical paired results are useful diagnostics, not validation
of these new prompts or the changed selection/routing policy.
