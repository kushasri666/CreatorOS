"""Deterministic evidence receipts and cited reports. No model or network calls."""
import hashlib
from source_policy import review_sources,blocking_conflicts


def evidence_receipts(check, sources):
    """Require a verbatim excerpt for every cited source, never a model-written quote."""
    ids = check.get("source_ids", [])
    evidence = check.get("evidence", [])
    if not isinstance(ids, list) or not ids or not isinstance(evidence, list):
        return [], "Every supported claim needs source IDs and verbatim evidence."
    receipts = []
    for item in evidence:
        if not isinstance(item, dict):
            return [], "Malformed evidence receipt."
        sid, quote = item.get("source_id"), item.get("quote")
        if not isinstance(sid, str) or sid not in ids or sid not in sources:
            return [], "Evidence referenced an unknown or uncited source."
        source = sources[sid]
        excerpt = source.get("excerpt", "")
        digest = hashlib.sha256(excerpt.encode()).hexdigest()
        if item.get("excerpt_sha256") and item["excerpt_sha256"] != digest:
            return [], "Saved source excerpt changed after verification; re-verification is required."
        if not isinstance(quote, str) or not quote.strip() or quote not in excerpt:
            return [], "Evidence quotation was not found verbatim in the saved source excerpt."
        receipts.append(dict(source_id=sid, quote=quote, quote_start=excerpt.index(quote),
            excerpt_sha256=digest))
    if {r["source_id"] for r in receipts} != set(ids):
        return [], "At least one cited source has no verbatim evidence receipt."
    return receipts, None


def build_report(post):
    """A report of supported factual claims, separated from flagged draft claims."""
    rows = post.get("sources") or []
    sources = {s["source_id"]: s for s in rows}
    verification = post.get("verification") or {}
    saved_conflicts=(post.get("evidence_review") or {}).get("conflicts",[])
    evidence_review=review_sources(rows,saved_conflicts)
    claims, withheld = [], []
    content = [post.get("text", ""), *(post.get("slides") or [])]
    for check in verification.get("checks", []):
        receipts, error = evidence_receipts(check, sources)
        disputed=blocking_conflicts(check.get("claim",""),check.get("source_ids",[]),evidence_review["conflicts"])
        if disputed:error="Unqualified claim relies on unresolved source disagreement: "+", ".join(disputed)
        present = any(check.get("claim", "") and check["claim"] in part for part in content)
        if check.get("verdict") != "supported" or error or not present:
            withheld.append(dict(claim=check.get("claim", ""),
                reason=error or ("Claim is absent from final content." if not present else check.get("reason", "Unverified"))))
            continue
        claims.append(dict(claim_id=f"C{len(claims)+1}", claim=check["claim"],
            source_ids=list(dict.fromkeys(check["source_ids"])), evidence=receipts,
            verification_reason=check.get("reason", "")))
    used = {sid for c in claims for sid in c["source_ids"]}
    snapshots = []
    for sid in sorted(used):
        source = sources[sid]
        # Copy only public provenance fields, never connector tokens or configuration.
        snapshot = {k: source.get(k) for k in ("id", "source_id", "source_type", "title", "url",
            "document_id", "sha256", "excerpt_start", "metric_id", "connection_id", "account_id",
            "window", "collected_at", "retrieved_at", "excerpt", "media_type", "transcript_origin",
            "transcript_sha256", "attachment_url") if k in source}
        snapshot["quality"]=next(q for q in evidence_review["sources"] if q["source_id"]==sid)
        snapshot["excerpt_sha256"] = hashlib.sha256(source.get("excerpt", "").encode()).hexdigest()
        snapshots.append(snapshot)
    content_hash = hashlib.sha256("\0".join(content).encode()).hexdigest()
    prior_hash = (post.get("grounded_report") or {}).get("content_sha256")
    changed = prior_hash is not None and prior_hash != content_hash
    passed = verification.get("passed") is True and not withheld and len(sources) == len(rows) and not changed
    return dict(schema_version="grounded-report-v1", status="verified" if passed else "unverified",
        passed=passed, claims=claims, withheld_claims=withheld, sources=snapshots,
        evidence_review=evidence_review,
        content_sha256=content_hash, content_changed_since_verification=changed,
        limitations=["Source support is assessed by the Mesh verifier; a real quotation does not itself prove a claim true.",
            "Brand-owner facts and uploaded documents retain their origin; they are not independent verification.",
            "Creative wording, opinions and calls to action are not reported as factual evidence.",
            "Claim detection may miss factual assertions; no guarantee of zero hallucinations is made."])
