# Product research and cost design

Research date: 20 October 2026. These are product observations and hypotheses, not
a claim that CreatorOS is objectively better, cheapest, or already production-ready.

## Existing services and agents

- [Buffer Insights](https://support.buffer.com/en-us/articles/using-insights-in-buffer-x4gLauQU5a)
  already supports many networks including Threads, YouTube and LinkedIn profiles.
  Its documentation explains native/API discrepancies and channel-dependent history
  limits. Legacy Analyze and newer Insights have different capabilities; do not
  infer a current product limitation from an older help article.
- [Metricool](https://metricool.com/pricing/) offers scheduling and analytics;
  [its free-plan guide](https://help.metricool.com/main-differences-between-free-and-paid-plans-bl0v9)
  describes a 30-day history window. Paid access does not create historical data
  that a platform never exposed. [Backfill rules](https://help.metricool.com/historical-data-available-5zavf)
  vary by network.
- [Postiz](https://postiz.com/pricing) already provides agent-accessible MCP/CLI/API
  scheduling and analytics. Its published entry plan is $29/month, with bounded
  AI-video allowances. Existing agent surfaces are useful references; importing
  their provider-specific AI code would not satisfy this project's Mesh-only rule.
- [Predis.ai credits](https://help.predis.ai/knowledgebase/en/article/understanding-the-credit-system-on-predisai)
  vary by media/model/duration; voiceovers can cost separately and unused credits
  do not roll over. Its pre-generation credit estimates are a useful UX precedent.

## Pain points to test with real customers

Public [user reports](https://www.reddit.com/r/SocialMediaMarketing/comments/1i0lk9i/need_help_finding_a_social_media_analytics_tool/)
describe difficulty accessing older analytics. Another
[Metricool report](https://www.reddit.com/r/SocialMediaManagers/comments/1k05c2h)
describes historical-range frustration. These are anecdotes, not representative
surveys or verified service defects. Provider API limits affect every service.

CreatorOS responses implemented in this iteration:

| Pain | Product response | Remaining boundary |
|---|---|---|
| Unclear account eligibility | Visible account-type, permission and fee requirements | User/provider must authorize and approve access |
| Numbers do not match native dashboards | Source, exact formula, window, age and timestamp displayed | Different provider definitions and delays remain |
| Analytics charts do not suggest an action | Evidence-linked tentative next-brief experiment | Correlation is not causal uplift |
| Hidden AI/image expenses | Separate paid-media lock, one submission/day, dashboard-cap requirement | Exact model charges require actual provider pricing/usage |
| Blurry embedded playback | Sharp 720p frame preview, fullscreen or expanded-view fallback | Preview 3 fps; downloaded MP4 15 fps |
| Accidental repeat work | Idempotent brand saving, export fingerprints and 24-hour response cache | Deliberate new generations still incur costs |

## Caveman and token efficiency

[JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) and
[Shawnchee/caveman-skill](https://github.com/Shawnchee/caveman-skill) focus on terse
agent output. Their claimed savings are not a guarantee for our prompts, models,
or content quality. No third-party skill or proxy was installed.

`prompt_policy.py` removes redundant payload fields and whitespace, keeps all
retrieved rule IDs/reasons, full draft/revision text, and tone/vocabulary/structure/
CTA/avoidance rules. Voice inference still receives every historical sample.
Internal rationales are concise; customer-facing copy is not forced into broken
grammar. Untrusted-content instructions and bounded editor revision remain.

An offline synthetic-context benchmark in `prompt-efficiency.json` counts
**7,732 input tokens before vs 1,895 after** using `cl100k_base`. This is payload
accounting, not a live quality test or provider bill. It excludes system/output
tokens and overrepresents duplicated context. Do not market it as a guaranteed
75% reduction in total spend. Existing quality evaluation remains unchanged.

Identical structured requests can reuse a 24-hour local cache; changed brief,
brand rules, evidence or model creates a different key. Cache hits appear in the
audit but are excluded from paid-call totals. `MESH_CACHE_ENABLED=0` disables it.
The local cache stays within the single-user workspace; public multi-user tenancy
must add explicit isolation before deployment.

## Mesh media controls

Official [video](https://developers.meshapi.ai/docs/capabilities/video-generation)
and [speech](https://developers.meshapi.ai/docs/capabilities/text-to-speech)
APIs are implemented behind independent disabled-by-default gates. All inference
goes to `api.meshapi.ai`. No live media generation was performed in this iteration.
Model and voice selection are explicit; no expensive model is silently selected.

Configure a Mesh key spend cap before setting both media-enable flags. Submission
also needs explicit UI confirmation. One video/speech submission per UTC day is
permitted globally, including ambiguous failures, with no automatic re-POST.
Video jobs are at most five seconds, 720p; polling is throttled to 30 seconds.
Speech is limited to 500 characters and exports WAV; it is not automatically mixed
into an existing slideshow. Model-generated video audio is optional and can cost
more. Local synthesized music remains a zero-inference option.

The downloaded slideshow can still be created with zero new AI calls. No claim of
highest quality at the lowest price is justified until users, actual usage costs,
retention, quality and competitor comparisons are measured.
