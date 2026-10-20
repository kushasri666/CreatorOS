# Self-correcting evidence memory

CreatorOS adapts the supplied architecture to performance learning. It verifies evidence consistency, not the factual truth of an LLM's interpretation. Lessons remain tentative experiments; a format correlation does not prove causation.

Before generation, `memory.retrieve` checks each lesson's linked metrics, source post, brand version/profile, platform, account, observation cohort and timestamp. SHA-256 fingerprints detect changed evidence, source content or lesson text. Missing evidence, disconnected accounts, mismatched scope and observations older than 14 days prevent reuse. Withheld lessons remain visible in **Learning loop → Self-correcting memory** with the reason.

Comparable API observations are re-evaluated deterministically from stored data. A changed result replaces the current hypothesis, increments its version and saves a previous-version receipt. Repeating an unchanged refresh does not create another version. A comparison that no longer has sufficient support invalidates its previous lesson. Manual/model-written interpretations are withheld after evidence changes; they are not silently rewritten or promoted to facts.

`GET /memory/{brand_id}/{platform}` inspects memory; `POST /memory/{brand_id}/{platform}/refresh` re-derives supported API comparisons locally. Neither endpoint calls a model or social provider. Account synchronization remains a separate operation. Generation receives only usable, account-compatible lessons; compact prompts retain stable memory version/status metadata without cache-breaking check timestamps.

New manual feedback is anchored after its evidence transaction. Older records are anchored on first inspection: that baseline cannot reconstruct or verify historical changes before migration. The system is not a general fact-checker and does not automatically fetch external sources. Fingerprints provide change detection, not authentication against a database administrator. YouTube revision receipts omit old prose; this feature alone does not establish full platform retention compliance.

## Offline validation

Run `python -m unittest discover -s tests -p test_memory.py -v` with project dependencies installed. Six tests cover fresh tentative memory/cache stability, metric mutation and retrieval exclusion, post/brand/claim mutation, missing evidence, scope/freshness failures, and winner reversal with version history, idempotence and loss of support. They use temporary databases and no paid calls. The winner-reversal fixture changes the observed best format from story to checklist; the stored rule changes and version advances from 1 to 2.

The numbers in the reference diagram are not CreatorOS evaluation results. These tests establish consistency and correction behavior, not measured engagement improvement or semantic correctness of all model-written lessons.
