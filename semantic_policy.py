"""Trusted semantic guidance; source text never supplies these instructions."""
GUIDANCE=(
    'Exactness applies to candidate text and source receipts, NOT to wording between a claim and its evidence. '
    'Accept supported paraphrases when all asserted meaning follows from cited excerpts. Compare entity, action, object, scope, quantity/unit, conditions, time/version and negation. '
    'Do not add mechanisms, speed, benefits, superiority, certainty or causal guarantees. A matching topic/product name or an irrelevant real quote is not support. '
    'Pure invitations such as review/save/comment and explicitly imagined aspirations are nonfactual; do not reject them for not appearing in a product manual. '
    'An invitation containing a product capability or measurable benefit still needs verification. Check the factual portion of mixed fact/CTA prose. '
    'Cover every independent assertion, including uncited nonnumeric capabilities. Never assume writer citations exhaust the factual content. '
    'For EVERY coverage unit return exactly one coverage item with unit_id, kind factual|mixed|nonfactual, candidate_ids and reason. '
    'Factual/mixed units must link ALL factual assertion candidates to actual checks, even if unsupported. Pure nonfactual units use candidate_ids:[] and a brief explanation. '
    'Prefer exact sentence candidates over overlapping full-post checks. Do not classify a guarantee, comparison, product capability or claimed outcome as mere creative wording. '
    'Always return all three top-level keys checks, conflicts and coverage. Use conflicts:[] when no disagreement exists; never omit the field.'
    ' Copy EVERY supplied U identifier into coverage, including factual wording repeated in slides. Nonfactual rows MUST have candidate_ids:[]; factual rows MUST select checked candidates. '
    'Do not substitute clause C identifiers for unit U identifiers. A check may be reused by multiple units only when its exact passage occurs in those units.'
)
