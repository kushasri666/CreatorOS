"""Bounded quality routing, not a calibrated probability or an engagement forecast."""
POLICY_VERSION = "trajectory-v2-editorial"


def assess(review, text, limit, version, previous=None, restarts=0, max_drafts=3,
           target_average=8, minimum_criterion=6):
    scores = review["scores"]
    average = sum(scores.values()) / len(scores)
    issues = []
    if len(text) > limit:
        issues.append("Platform character limit exceeded")
    if min(scores.values()) < minimum_criterion:
        issues.append(f"At least one editor criterion is below {minimum_criterion}/10")
    if average < target_average:
        issues.append(f"Editor average is below {target_average}/10")
    ready = not issues and version >= 2
    delta = None if previous is None else round(average-previous["average"], 3)
    if ready:
        action, reason = "accept", "Revised content meets the rubric and deterministic platform gate"
    elif version >= max_drafts:
        action, reason = "needs_review", "Draft budget exhausted; human review required"
    elif version >= 2 and delta is not None and delta <= 0 and restarts == 0:
        action, reason = "restart", "Revision stalled or regressed; reconsider the angle once using preserved evidence"
    else:
        action, reason = "refine", "Apply targeted editor feedback" if issues else "Mandatory first-draft critique and revision"
    return dict(policy=POLICY_VERSION, action=action, reason=reason, version=version,
                target_average=target_average, minimum_criterion=minimum_criterion,
                confidence_score=round(average/10, 3),
                confidence_basis="Uncalibrated editor rubric; not factual certainty or predicted engagement",
                ready=ready, issues=issues, score_delta=delta,
                remaining_drafts=max_drafts-version, restarts_used=restarts)
