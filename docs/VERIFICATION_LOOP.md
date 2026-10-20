# Source verification loop

Supported verdicts now also require a verbatim quotation for every cited source;
the application checks these quotations against saved excerpts. See
[grounded output](GROUNDED_OUTPUT.md) for report structure and integrity checks.

Every live draft passes a separate Mesh-backed Verifier before approval. The Verifier receives the draft, Instagram slides when applicable, writer claim-to-source mappings, and the exact source excerpts saved for that post. It checks factual and numerical claims against only the cited source IDs, and returns a per-claim `supported`, `thin`, or `unsupported` verdict with the source IDs inspected and a reason. Unknown IDs, claims absent from the draft, omitted writer citations, or a mismatch between the writer's cited sources and verifier-inspected sources fail closed.

When verification fails on thin, unsupported or disputed claims, CreatorOS performs one bounded retrieval retry targeted at those claims through the executable state graph. The retry can inspect another relevant excerpt from an uploaded brand document, up to three additional already-collected API observations from the same enabled account, and up to two more pages on the supplied official product site. It does not issue generic topic searches or bypass provider sync limits. New evidence receives new source IDs and is saved with the draft.

The Writer then gets one correction pass: remove or qualify unsupported claims; use additional evidence only when it directly supports a thin claim; remove it if evidence remains weak. A second independent Verifier call checks the changed draft. The Editor re-scores that corrected version. If verification fails, the correction is unchanged, retrieval finds nothing, or the Mesh call budget cannot complete the correction and re-check, CreatorOS keeps the unsupported/thin claim flags visible and sets the post to `needs_review`; it cannot be scheduled or published through the approved flow. The system never treats an invalid verifier response as a pass.

The verifier uses the configured `MESH_VERIFIER_MODEL` route (default `openai/gpt-4.1-mini`) through the Mesh gateway. To keep the existing ten-call per-run limit, live writer/editor refinement reserves enough calls for verification and one correction cycle; visual generation is skipped if those required calls consume the remaining budget. Every verification pass and targeted retrieval is recorded in the audit trail and shown with source links in Final post.

Offline fixture output explicitly says `not_run_offline_fixture`; it does not claim factual verification. No live verifier call was made for the recorded self-evaluation. The verifier is an LLM judgment about source entailment, not a guarantee of truth, and users should still review important claims.
